"""
updater.py
----------
Fully silent auto-update for the DISTRIBUTED .exe only (never triggers when
running from source with `python app.py` -- there's no running .exe to swap).

How it works, end to end:
  1. On launch, AutoRenamerWindow kicks off a background check (see the
     _UpdateCheckWorker QThread in app.py) against RELEASE_API_URL below.
     That URL is a PUBLIC repo containing nothing but built .exe releases --
     no source code, no SECRET, nothing sensitive. It needs no login.
  2. If the release's version is newer than APP_VERSION, the new .exe is
     downloaded in the background to a temp file next to the current one.
     Nothing about the running app is touched -- you can keep working.
  3. When the app closes normally, AutoRenamerWindow.closeEvent() calls
     prepare_and_launch_swap(), which writes a tiny one-shot .bat helper
     that waits for this process to fully exit, deletes the old .exe,
     moves the new one into its place, relaunches it, then deletes itself.
     A running .exe can't overwrite its own file on Windows, which is why
     this two-step (helper script + relaunch) dance is necessary.
  4. Next launch is already the new version. No dialogs, no clicks.

To ship a new version:
  - Bump APP_VERSION below.
  - Push a git tag like v1.1.0 to your PRIVATE source repo -- the "release"
    job in build.yml builds the .exe and publishes it as a GitHub Release
    on the public releases-only repo, named exactly OffsetAutoRenamer.exe.
"""

import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------
# Bump this with every release you tag and publish.
# ---------------------------------------------------------------------
APP_VERSION = "1.0.0"

# Public, source-free repo that only ever holds built .exe releases.
RELEASE_OWNER_REPO = "jrzdagoatsecond/offset-auto-renamer-releases"
RELEASE_API_URL = f"https://api.github.com/repos/{RELEASE_OWNER_REPO}/releases/latest"
RELEASE_ASSET_NAME = "OffsetAutoRenamer.exe"

_REQUEST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "OffsetAutoRenamer-UpdateCheck",
}


def _version_tuple(version: str):
    """'1.2.10' -> (1, 2, 10). Tolerant of a leading 'v' and odd suffixes."""
    version = version.strip().lstrip("vV")
    parts = []
    for chunk in version.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def is_newer(remote_version: str, local_version: str = APP_VERSION) -> bool:
    try:
        return _version_tuple(remote_version) > _version_tuple(local_version)
    except Exception:
        return False


def get_latest_release_info(timeout: int = 6):
    """
    Returns {"version": "1.1.0", "download_url": "..."} for the latest
    published release, or None if unreachable / no matching asset found.
    Never raises -- any failure here should just mean "no update found".
    """
    try:
        req = urllib.request.Request(RELEASE_API_URL, headers=_REQUEST_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None

    tag = data.get("tag_name", "")
    download_url = None
    for asset in data.get("assets", []):
        if asset.get("name", "").strip().lower() == RELEASE_ASSET_NAME.lower():
            download_url = asset.get("browser_download_url")
            break
    if not tag or not download_url:
        return None
    return {"version": tag.lstrip("vV"), "download_url": download_url}


def download_to_temp(url: str, timeout: int = 60) -> Path:
    """Downloads `url` to a temp file and returns its path. Raises on failure."""
    req = urllib.request.Request(url, headers=_REQUEST_HEADERS)
    fd, tmp_path = tempfile.mkstemp(prefix="OffsetAutoRenamer_update_", suffix=".exe")
    tmp_path = Path(tmp_path)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        with open(fd, "wb") as out_file:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out_file.write(chunk)
    return tmp_path


def check_and_download_update():
    """
    Runs entirely in a background thread (see _UpdateCheckWorker in app.py).
    Returns the path to a downloaded new .exe if an update was found and
    fetched, otherwise None. Silently no-ops (returns None) unless running
    as a real frozen .exe on Windows -- there's nothing to swap otherwise.
    """
    if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
        return None

    info = get_latest_release_info()
    if not info or not is_newer(info["version"]):
        return None

    try:
        return download_to_temp(info["download_url"])
    except Exception:
        return None


def prepare_and_launch_swap(new_exe_path: Path):
    """
    Called from AutoRenamerWindow.closeEvent() when a downloaded update is
    waiting. Writes a tiny helper .bat that waits for this process to fully
    exit, replaces the running .exe with the downloaded one, relaunches it,
    then deletes itself. No-ops safely if not running as a frozen .exe.
    """
    if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
        return

    current_exe = Path(sys.executable)
    new_exe_path = Path(new_exe_path)
    if not new_exe_path.exists():
        return

    bat_fd, bat_path = tempfile.mkstemp(prefix="OffsetAutoRenamer_apply_update_", suffix=".bat")
    bat_path = Path(bat_path)
    script = f"""@echo off
:wait_exit
tasklist /fi "PID eq {_current_pid()}" | find "{_current_pid()}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_exit
)

:retry_delete
del /f /q "{current_exe}"
if exist "{current_exe}" (
    timeout /t 1 /nobreak >nul
    goto retry_delete
)

move /y "{new_exe_path}" "{current_exe}"
start "" "{current_exe}"
del /f /q "%~f0"
"""
    with open(bat_fd, "w", encoding="utf-8") as f:
        f.write(script)

    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        ["cmd", "/c", str(bat_path)],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )


def _current_pid() -> int:
    import os
    return os.getpid()
