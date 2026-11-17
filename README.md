<div align="center">

# 📦 Nexus Collection Downloader

**Download whole Nexus Mods collections with a free account — no Premium needed.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Playwright](https://img.shields.io/badge/Playwright-1.48%2B-2EAD33?logo=playwright&logoColor=white)](https://playwright.dev/python/)
[![GUI](https://img.shields.io/badge/GUI-Tkinter%20%2B%20Sun%20Valley-FFB000)](https://github.com/rdbende/Sun-Valley-ttk-theme)
[![Nexus Mods](https://img.shields.io/badge/Nexus%20Mods-Collections-DA8E35)](https://www.nexusmods.com/)
[![Last commit](https://img.shields.io/github/last-commit/Sappyhad/mod_collection_downloader)](https://github.com/Sappyhad/mod_collection_downloader/commits)
[![Repo size](https://img.shields.io/github/repo-size/Sappyhad/mod_collection_downloader)](https://github.com/Sappyhad/mod_collection_downloader)

</div>

Paste a Nexus Mods collection link → the app shows the list of mods → tick the ones you want → the app downloads them one by one using **slow download**.

Downloaded mods are remembered, so if you stop and start again, only the missing ones get downloaded.

---

## ✨ Features

- 🔗 **Paste any collection link** (or bare slug, optionally with a specific revision).
- ☑️ **Pick what you want** – tick / untick mods, optional mods shown in grey.
- 🐢 **Free-account friendly** – uses the same "slow download" endpoint as the website button.
- ⏯️ **Stop & resume** – already downloaded files are skipped.
- 📂 **Tidy folders** – every collection gets its own `Downloads\[collection name]_mods_downloaded` folder.
- 🔐 **Log in once** – the browser session is kept in a local profile and reused next time.
- 🌙 **Dark UI** – clean Sun Valley theme.

---

## 🧰 What you need

1. **Windows** (10 or 11).
2. **Google Chrome or Microsoft Edge** – if Chrome is your default browser the app uses Chrome, otherwise Edge (built into Windows).
3. **Python 3.10 or newer** – https://www.python.org/downloads/
   - Click the big yellow "Download Python" button.
   - Run the installer.
   - **IMPORTANT:** on the first installer screen, tick the **"Add python.exe to PATH"** checkbox at the bottom. Nothing will work without it.
   - Click "Install Now" and wait.
4. **A Nexus Mods account** – a free one is enough: https://www.nexusmods.com/

---

## 🚀 How to start

1. Download the app (green **Code** button → **Download ZIP**, then unzip) or clone it:
   ```
   git clone https://github.com/Sappyhad/mod_collection_downloader.git
   ```
2. Open the app folder.
3. Double-click **`start.bat`**.
4. The **first** time, a black window pops up and installs stuff for a minute or two. Don't close it. Next time the app starts almost instantly.
5. The app window opens.

> Prefer the terminal? `start.bat` does exactly this:
> ```
> python -m venv .venv
> .venv\Scripts\pip install -r requirements.txt
> .venv\Scripts\python app.py
> ```

---

## 📖 How to use

### First time only: log in

1. Click **"🔑 Log in to Nexus"** (top right corner).
2. A separate browser window opens with the Nexus Mods login page.
3. Log in to your Nexus account there.
4. **Don't close** that browser window – the app downloads files through it. You can minimize it.

The login is remembered, so next time you'll already be logged in.

### Downloading a collection

1. Go to the collection page on Nexus Mods and copy the link from the address bar, e.g.
   `https://www.nexusmods.com/games/cyberpunk2077/collections/iszwwe`
2. Paste it into the **"1. Collection"** field and click **"Load mods"**.
3. The mod list appears. All mods are ticked (☑) by default.
   - Click a row to tick / untick a mod.
   - **"Select all"** / **"Deselect all"** – do what they say.
   - Grey rows are optional mods.
4. Under **"2. Download"** you'll see the folder where files are saved. The app sets it automatically to **`Downloads\[collection name]_mods_downloaded`**, e.g. `Downloads\Welcome to Night City 2.31a_mods_downloaded`. Every collection gets its own folder, so your Downloads folder stays clean. You can change it with **"📁 Browse..."** (if you pick the bare Downloads folder, it goes back to the automatic collection folder).
5. Click **"▶ Download selected"**.
6. Wait. The **Status** column shows what's going on:
   - `⏳ downloading` – downloading right now,
   - `✓ downloaded` – done,
   - `✗ failed` – didn't work (a list of failed mods with links appears in the log at the end).

Slow download is slow (around 1–3 MB/s) and a big collection can be over 10 GB, so this can take hours. Leave the computer alone and go make some tea. ☕

### Stopping and resuming

- **"■ Stop"** – stops after the file that is currently downloading.
- To resume, click **"▶ Download selected"** again. Already downloaded mods are skipped (the app keeps a list in a hidden `.downloaded.json` file inside the mods folder).
- If you delete a file from the folder, the app downloads it again.

---

## 🛠️ Something's not working?

| Problem | What to do |
|---|---|
| `start.bat` says "Python not found" | Reinstall Python and **tick "Add python.exe to PATH"**. Then restart your computer. |
| "Failed to open browser" | Install Microsoft Edge (or Google Chrome, if it is your default browser). |
| "are you logged in?" / "Not logged in to Nexus Mods" | Click "Log in to Nexus" and log in in the browser window that opens. |
| "Cloudflare captcha" | Click "Log in to Nexus", pass the check in the tab that opens, then click "Download selected" again. |
| "Nexus temporarily suspended your account" | Too many downloads too fast. Wait ~10 minutes and resume. |
| "Collection not found" | Check the link. The collection may be private or deleted. |
| Installation failed | Delete the `.venv` folder and run `start.bat` again. |
| One mod failed but the rest downloaded | Click its link in the log and download it manually from the website. |

---

## 🗂️ What's where (for the curious)

| Path | Purpose |
|---|---|
| `app.py` | The app window (Tkinter GUI). |
| `nexus_api.py` | Fetches the mod list of a collection from the public Nexus Mods GraphQL API. |
| `browser_downloader.py` | Drives the browser (Playwright over CDP) and downloads the files. |
| `start.bat` | One-click launcher – creates the virtual environment and starts the app. |
| `.browser_profile/` | Saved browser profiles (one per browser) with your Nexus login. |

> [!WARNING]
> **Never send the `.browser_profile/` folder to anyone** – it contains your Nexus Mods session. It is excluded from git by `.gitignore`.

---

<div align="center">
<sub>Not affiliated with or endorsed by Nexus Mods. Please respect the Nexus Mods terms of service and support mod authors.</sub>
</div>
