"""Slow-downloading mod files through a real browser window driven by Playwright.

Google Chrome is used when it is the user's default browser, otherwise
Microsoft Edge (ships with Windows). The app starts the browser as a plain
process with a remote debugging port and Playwright only attaches over CDP when
downloading - Cloudflare's login captcha rejects browsers launched by Playwright.
The browser uses a persistent profile, so the user logs in to Nexus Mods once
and the session is reused on later runs. Every download goes through the same
"slow download" endpoint that the website button uses.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from nexus_api import ModFile

PROFILE_DIR = Path(__file__).parent / ".browser_profile"
DEFAULT_BROWSER_KEY = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
APP_PATHS_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
CHANNEL_EXECUTABLES = {"chrome": "chrome.exe", "msedge": "msedge.exe"}
NEXUS_HOME = "https://www.nexusmods.com/"
NEXUS_LOGIN = "https://users.nexusmods.com/auth/sign_in"
DOWNLOAD_START_TIMEOUT_MS = 60_000
BROWSER_START_TIMEOUT_S = 20

# Runs inside the Nexus page so the request carries the user's session cookies.
GENERATE_URL_JS = """
async ({fileId, gameId}) => {
  const response = await fetch(
    "https://www.nexusmods.com/Core/Libs/Common/Managers/Downloads?GenerateDownloadUrl",
    {
      method: "POST",
      credentials: "include",
      headers: {
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: `fid=${fileId}&game_id=${gameId}`,
    },
  );
  if (!response.ok) return "";
  const json = await response.json().catch(() => ({}));
  return json.url || json.URI || json.src || json.download_url || "";
}
"""


class DownloadError(Exception):
    pass


class FatalDownloadError(DownloadError):
    """Further downloads make no sense (not logged in, rate limited...)."""


def browser_channel() -> str:
    """Playwright channel: Chrome if it is the default browser, otherwise Edge."""
    if sys.platform != "win32":
        return "chrome"
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DEFAULT_BROWSER_KEY) as key:
            prog_id = winreg.QueryValueEx(key, "ProgId")[0]
    except OSError:
        return "msedge"
    return "chrome" if prog_id == "ChromeHTML" else "msedge"


def browser_executable(channel: str) -> str:
    """Path of the installed Chrome/Edge executable, from the Windows "App Paths" registry."""
    import winreg

    name = CHANNEL_EXECUTABLES[channel]
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, rf"{APP_PATHS_KEY}\{name}") as key:
                return winreg.QueryValueEx(key, "")[0]
        except OSError:
            continue
    raise FileNotFoundError(f"{name} is not installed")


class BrowserDownloader:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None
        self.browser_name = browser_channel()
        # Separate profile per browser - profiles of different browsers are not compatible.
        self._profile = PROFILE_DIR / self.browser_name

    def open_for_login(self):
        """Show the Nexus login page with Playwright detached, so the captcha sees a normal browser."""
        self.close()
        if self._debug_port():
            # The browser is already running - this only opens a new tab in it.
            subprocess.Popen([browser_executable(self.browser_name), f"--user-data-dir={self._profile}", NEXUS_LOGIN])
        else:
            self._start_browser(NEXUS_LOGIN)

    def open(self):
        if self._browser:
            self._page.bring_to_front()
            return
        if not self._debug_port():
            self._start_browser(NEXUS_HOME)
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self._debug_port()}")
        except PlaywrightError:
            self._playwright.stop()
            self._playwright = None
            raise
        self._page = self._browser.contexts[0].new_page()

    def close(self):
        """Detach Playwright; the browser window itself stays open."""
        if self._browser:
            self._page.close()
            self._browser.close()
            self._playwright.stop()
        self._browser = self._playwright = self._page = None

    def _start_browser(self, url: str):
        self._port_file().unlink(missing_ok=True)
        subprocess.Popen([
            browser_executable(self.browser_name),
            f"--user-data-dir={self._profile}",
            "--remote-debugging-port=0",
            "--no-first-run",
            url,
        ])
        deadline = time.monotonic() + BROWSER_START_TIMEOUT_S
        while not self._debug_port():
            if time.monotonic() > deadline:
                raise DownloadError(f"{self.browser_name} did not start in {BROWSER_START_TIMEOUT_S} s")
            time.sleep(0.3)

    def _port_file(self) -> Path:
        # Chromium writes its debugging port here and deletes the file on a clean exit.
        return self._profile / "DevToolsActivePort"

    def _debug_port(self) -> str:
        """Debugging port of the running browser, or "" if it is not running."""
        try:
            port = self._port_file().read_text().split()[0]
            # The file is left behind when the browser crashes - check something listens there.
            socket.create_connection(("127.0.0.1", int(port)), timeout=1).close()
        except (OSError, IndexError, ValueError):
            return ""
        return port

    def download(self, mod: ModFile, target_dir: Path) -> Path:
        """Download one mod file and wait until it is fully saved."""
        self.open()
        page = self._page
        page.goto(mod.page_url, wait_until="domcontentloaded")
        _raise_if_blocked(page.content())

        url = page.evaluate(GENERATE_URL_JS, {"fileId": mod.file_id, "gameId": mod.game_id})
        if not url:
            raise DownloadError("Nexus returned no download link (are you logged in?)")

        with page.expect_download(timeout=DOWNLOAD_START_TIMEOUT_MS) as download_info:
            page.evaluate("url => { window.location.href = url; }", url)
        download = download_info.value

        target = target_dir / download.suggested_filename
        try:
            download.save_as(target)
        except PlaywrightError as error:
            raise DownloadError(f"Download interrupted: {download.failure() or error}") from error
        finally:
            # Playwright keeps its own temp copy until the browser closes - drop it now.
            download.delete()
        return target


def _raise_if_blocked(html: str):
    if 'class="replaced-login-link"' in html:
        raise FatalDownloadError("Not logged in to Nexus Mods - log in in the browser window.")
    if "Just a moment..." in html:
        raise FatalDownloadError(
            "Cloudflare captcha - click 'Log in to Nexus', pass the check in the new tab and resume."
        )
    if "temporarily suspended" in html:
        raise FatalDownloadError("Nexus temporarily suspended your account for too many requests. Try again in ~10 min.")
