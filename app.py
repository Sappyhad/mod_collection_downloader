"""Nexus Mods collection downloader - GUI."""

import json
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import sv_ttk

from browser_downloader import BrowserDownloader, FatalDownloadError
from nexus_api import Collection, fetch_collection, parse_collection_url

PAUSE_BETWEEN_DOWNLOADS_S = 5
HISTORY_FILE_NAME = ".downloaded.json"
DOWNLOADS_DIR = Path.home() / "Downloads"
COLLECTION_FOLDER_SUFFIX = "_mods_downloaded"
INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
CHECKED, UNCHECKED = "☑", "☐"

STATUS_DONE = "✓ downloaded"
STATUS_ACTIVE = "⏳ downloading"
STATUS_FAILED = "✗ failed"

COLOR_OK = "#6ccb5f"
COLOR_ERROR = "#ff6b6b"
COLOR_ACTIVE = "#57c8ff"
COLOR_MUTED = "#9a9a9a"
LOG_BACKGROUND = "#202020"
LOG_FOREGROUND = "#e6e6e6"


class BrowserWorker:
    """Single thread that owns Playwright - its sync API is not thread-safe."""

    def __init__(self):
        self._jobs = queue.Queue()
        self.downloader = BrowserDownloader()
        threading.Thread(target=self._run, daemon=True).start()

    def submit(self, job):
        self._jobs.put(job)

    def _run(self):
        while True:
            job = self._jobs.get()
            if job is None:
                self.downloader.close()
                return
            job()

    def shutdown(self):
        self._jobs.put(None)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.collection: Collection | None = None
        self.checked: set[str] = set()
        self.custom_folder = False
        self.ui_events = queue.Queue()
        self.stop_requested = threading.Event()
        self.worker = BrowserWorker()

        root.title("Nexus Collection Downloader")
        root.geometry("1100x780")
        root.minsize(850, 600)
        sv_ttk.set_theme("dark")
        self._build_styles()
        self._build_ui()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(100, self._drain_ui_events)

    # ---------- UI ----------

    def _build_styles(self):
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 20))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground=COLOR_MUTED)
        style.configure("Collection.TLabel", font=("Segoe UI Semibold", 12))
        style.configure("Muted.TLabel", foreground=COLOR_MUTED)
        style.configure("Treeview", rowheight=28)

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=(20, 16))
        main.pack(fill="both", expand=True)

        header = ttk.Frame(main)
        header.pack(fill="x")
        titles = ttk.Frame(header)
        titles.pack(side="left")
        ttk.Label(titles, text="Nexus Collection Downloader", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            titles, text="Download Nexus Mods collections via browser slow download",
            style="Subtitle.TLabel",
        ).pack(anchor="w")
        ttk.Button(header, text="\U0001f511  Log in to Nexus", command=self.open_browser).pack(side="right")

        source = ttk.LabelFrame(main, text=" 1. Collection ", padding=12)
        source.pack(fill="x", pady=(16, 10))
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(source, textvariable=self.url_var, font=("Segoe UI", 10))
        url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        url_entry.bind("<Return>", lambda _: self.load_collection())
        self.load_button = ttk.Button(source, text="Load mods", style="Accent.TButton", command=self.load_collection)
        self.load_button.pack(side="left")

        self.title_var = tk.StringVar(
            value="Paste a collection link, e.g. https://www.nexusmods.com/games/cyberpunk2077/collections/iszwwe")
        ttk.Label(main, textvariable=self.title_var, style="Collection.TLabel").pack(anchor="w", pady=(0, 6))

        self._build_table(main)

        toolbar = ttk.Frame(main)
        toolbar.pack(fill="x", pady=(8, 10))
        ttk.Button(toolbar, text="Select all", command=lambda: self._set_all(True)).pack(side="left")
        ttk.Button(toolbar, text="Deselect all", command=lambda: self._set_all(False)).pack(side="left", padx=8)
        self.count_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.count_var, style="Muted.TLabel").pack(side="left", padx=8)

        self._build_download_panel(main)

    def _build_table(self, parent):
        table = ttk.Frame(parent)
        table.pack(fill="both", expand=True)
        columns = ("check", "mod", "file", "version", "size", "type", "status")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="none")
        for column, title, width, stretch in [
            ("check", "", 40, False),
            ("mod", "Mod", 300, True),
            ("file", "File", 240, True),
            ("version", "Version", 80, False),
            ("size", "Size", 90, False),
            ("type", "Type", 100, False),
            ("status", "Status", 120, False),
        ]:
            self.tree.heading(column, text=title, anchor="center" if column == "check" else "w")
            self.tree.column(column, width=width, stretch=stretch, anchor="center" if column == "check" else "w")
        self.tree.tag_configure("optional", foreground=COLOR_MUTED)
        self.tree.tag_configure("done", foreground=COLOR_OK)
        self.tree.tag_configure("active", foreground=COLOR_ACTIVE)
        self.tree.tag_configure("failed", foreground=COLOR_ERROR)
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<space>", lambda _: self._toggle(self.tree.focus()))

    def _build_download_panel(self, parent):
        panel = ttk.LabelFrame(parent, text=" 2. Download ", padding=12)
        panel.pack(fill="x")

        folder = ttk.Frame(panel)
        folder.pack(fill="x")
        ttk.Label(folder, text="Folder:").pack(side="left")
        self.folder_var = tk.StringVar(value=str(DOWNLOADS_DIR / f"[collection_name]{COLLECTION_FOLDER_SUFFIX}"))
        ttk.Entry(folder, textvariable=self.folder_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(folder, text="\U0001f4c1  Browse...", command=self._choose_folder).pack(side="left")

        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=(12, 0))
        self.download_button = ttk.Button(
            actions, text="▶  Download selected", style="Accent.TButton", command=self.start_download)
        self.download_button.pack(side="left")
        self.stop_button = ttk.Button(
            actions, text="■  Stop", command=self._request_stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.progress_var = tk.StringVar()
        ttk.Label(actions, textvariable=self.progress_var, style="Muted.TLabel").pack(side="right")
        self.progress = ttk.Progressbar(actions, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(8, 12))

        self.log = tk.Text(
            panel, height=7, state="disabled", wrap="word", relief="flat", borderwidth=0,
            background=LOG_BACKGROUND, foreground=LOG_FOREGROUND, font=("Consolas", 9), padx=8, pady=6,
        )
        self.log.pack(fill="x", pady=(12, 0))
        self.log.tag_configure("ok", foreground=COLOR_OK)
        self.log.tag_configure("error", foreground=COLOR_ERROR)
        self.log.tag_configure("muted", foreground=COLOR_MUTED)

    def _on_tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell":
            self._toggle(self.tree.identify_row(event.y))

    def _toggle(self, item_id: str):
        if not item_id:
            return
        if item_id in self.checked:
            self.checked.discard(item_id)
            self.tree.set(item_id, "check", UNCHECKED)
        else:
            self.checked.add(item_id)
            self.tree.set(item_id, "check", CHECKED)
        self._update_count()

    def _set_all(self, value: bool):
        items = self.tree.get_children()
        self.checked = set(items) if value else set()
        for item_id in items:
            self.tree.set(item_id, "check", CHECKED if value else UNCHECKED)
        self._update_count()

    def _update_count(self):
        total = len(self.tree.get_children())
        size_kb = sum(self.collection.mods[int(item_id)].size_kb for item_id in self.checked) if self.collection else 0
        self.count_var.set(f"Selected {len(self.checked)} / {total}  •  {_format_size(size_kb)}")

    def _set_status(self, item_id: str, status: str, tag: str):
        mod = self.collection.mods[int(item_id)]
        self.tree.set(item_id, "status", status)
        self.tree.item(item_id, tags=(tag,) if tag else ("optional",) if mod.optional else ())

    def _refresh_downloaded_status(self):
        if not self.collection:
            return
        history = _load_history(Path(self.folder_var.get()))
        for item_id in self.tree.get_children():
            mod = self.collection.mods[int(item_id)]
            if _is_downloaded(mod, history, Path(self.folder_var.get())):
                self._set_status(item_id, STATUS_DONE, "done")
            else:
                self._set_status(item_id, "", "")

    def _choose_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.folder_var.get())
        if not chosen:
            return
        # Picking the bare Downloads folder means "use the automatic per-collection folder".
        self.custom_folder = Path(chosen) != DOWNLOADS_DIR
        if self.custom_folder:
            self.folder_var.set(chosen)
        elif self.collection:
            self.folder_var.set(str(_collection_folder(self.collection.name)))
        self._refresh_downloaded_status()

    def _log(self, message: str, tag: str = ""):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _post(self, callback, *args):
        """Schedule a UI update from a background thread."""
        self.ui_events.put((callback, args))

    def _drain_ui_events(self):
        while not self.ui_events.empty():
            callback, args = self.ui_events.get_nowait()
            callback(*args)
        self.root.after(100, self._drain_ui_events)

    # ---------- Collection ----------

    def load_collection(self):
        try:
            slug, revision = parse_collection_url(self.url_var.get())
        except ValueError as error:
            messagebox.showerror("Error", str(error))
            return
        self.load_button.configure(state="disabled")
        self.title_var.set("Loading mod list...")
        threading.Thread(target=self._fetch_collection, args=(slug, revision), daemon=True).start()

    def _fetch_collection(self, slug: str, revision: int | None):
        try:
            collection = fetch_collection(slug, revision)
        except Exception as error:
            self._post(self._on_collection_error, error)
            return
        self._post(self._show_collection, collection)

    def _on_collection_error(self, error: Exception):
        self.load_button.configure(state="normal")
        self.title_var.set("Failed to load the mod list.")
        messagebox.showerror("Error", str(error))

    def _show_collection(self, collection: Collection):
        self.load_button.configure(state="normal")
        self.collection = collection
        self.tree.delete(*self.tree.get_children())
        for index, mod in enumerate(collection.mods):
            self.tree.insert("", "end", iid=str(index), values=(
                CHECKED, mod.mod_name, mod.file_name, mod.version,
                _format_size(mod.size_kb), "optional" if mod.optional else "required", "",
            ))
        self.checked = set(self.tree.get_children())
        if not self.custom_folder:
            self.folder_var.set(str(_collection_folder(collection.name)))
        self.title_var.set(f"{collection.name}  •  revision {collection.revision}  •  {len(collection.mods)} mods")
        self._refresh_downloaded_status()
        self._update_count()

    # ---------- Downloading ----------

    def open_browser(self):
        self._log("Opening browser - log in to Nexus Mods there (only needed once).", "muted")
        self.worker.submit(self._open_browser_job)

    def _open_browser_job(self):
        try:
            self.worker.downloader.open_for_login()
            self._post(self._log, f"Browser opened: {self.worker.downloader.browser_name}", "muted")
        except Exception as error:
            self._post(self._log, f"Failed to open browser: {error}", "error")

    def start_download(self):
        if not self.collection or not self.checked:
            messagebox.showinfo("Info", "Load a collection and select some mods first.")
            return
        item_ids = [item_id for item_id in self.tree.get_children() if item_id in self.checked]
        target_dir = Path(self.folder_var.get())
        target_dir.mkdir(parents=True, exist_ok=True)

        self.stop_requested.clear()
        self.download_button.configure(state="disabled")
        self.load_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress.configure(maximum=len(item_ids), value=0)
        self._set_progress(0, len(item_ids))
        self.worker.submit(lambda: self._download_job(item_ids, target_dir))

    def _request_stop(self):
        self.stop_requested.set()
        self._log("Stopping after the current file...", "muted")

    def _set_progress(self, done: int, total: int):
        self.progress.configure(value=done)
        self.progress_var.set(f"{done} / {total}")

    def _download_job(self, item_ids: list[str], target_dir: Path):
        history = _load_history(target_dir)
        failed = []
        total = len(item_ids)
        for number, item_id in enumerate(item_ids, start=1):
            if self.stop_requested.is_set():
                self._post(self._log, "Stopped.", "muted")
                break
            mod = self.collection.mods[int(item_id)]
            prefix = f"[{number}/{total}]"
            if _is_downloaded(mod, history, target_dir):
                self._post(self._log, f"{prefix} Already downloaded: {mod.mod_name}", "muted")
                self._post(self._set_status, item_id, STATUS_DONE, "done")
                self._post(self._set_progress, number, total)
                continue
            self._post(self._log, f"{prefix} Downloading {mod.mod_name} ({mod.file_name})...")
            self._post(self._set_status, item_id, STATUS_ACTIVE, "active")
            self._post(self.tree.see, item_id)
            try:
                saved = self.worker.downloader.download(mod, target_dir)
                history[str(mod.file_id)] = saved.name
                _save_history(target_dir, history)
                self._post(self._log, f"{prefix} OK -> {saved.name}", "ok")
                self._post(self._set_status, item_id, STATUS_DONE, "done")
            except FatalDownloadError as error:
                self._post(self._log, f"{prefix} {error}", "error")
                self._post(self._set_status, item_id, STATUS_FAILED, "failed")
                failed.append(mod)
                break
            except Exception as error:
                self._post(self._log, f"{prefix} ERROR: {error}", "error")
                self._post(self._set_status, item_id, STATUS_FAILED, "failed")
                failed.append(mod)
            self._post(self._set_progress, number, total)
            if number < total:
                time.sleep(PAUSE_BETWEEN_DOWNLOADS_S)
        self._post(self._on_download_finished, failed)

    def _on_download_finished(self, failed):
        self.download_button.configure(state="normal")
        self.load_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        if failed:
            self._log(f"Failed ({len(failed)}):", "error")
            for mod in failed:
                self._log(f"  {mod.mod_name}: {mod.page_url}", "error")
        else:
            self._log("Done.", "ok")

    def _on_close(self):
        self.stop_requested.set()
        self.worker.shutdown()
        self.root.destroy()


def _collection_folder(collection_name: str) -> Path:
    safe_name = INVALID_PATH_CHARS.sub("_", collection_name).strip().rstrip(".") or "collection"
    return DOWNLOADS_DIR / f"{safe_name}{COLLECTION_FOLDER_SUFFIX}"


def _is_downloaded(mod, history: dict[str, str], target_dir: Path) -> bool:
    saved_name = history.get(str(mod.file_id))
    return bool(saved_name) and (target_dir / saved_name).exists()


def _load_history(target_dir: Path) -> dict[str, str]:
    """Map of file_id -> saved file name for mods already downloaded into target_dir."""
    path = target_dir / HISTORY_FILE_NAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_history(target_dir: Path, history: dict[str, str]):
    path = target_dir / HISTORY_FILE_NAME
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(history, indent=1), encoding="utf-8")
    temp_path.replace(path)


def _format_size(size_kb: int) -> str:
    if size_kb < 1024:
        return f"{size_kb} KB"
    size_mb = size_kb / 1024
    return f"{size_mb / 1024:.2f} GB" if size_mb >= 1024 else f"{size_mb:.2f} MB"


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
