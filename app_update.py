"""Updates for the packaged .exe, from the GitHub repository's releases.

A release is a GitHub release tagged ``v<version>`` (e.g. ``v0.2.0``) with ``DesignDataManager.exe``
attached. The app asks GitHub for the latest release when it starts; if it's newer than
``APP_VERSION``, it offers to download it, swaps it in for the running .exe (Windows lets a running
.exe be renamed, not overwritten) and restarts. The old .exe is deleted on the next start.
"""

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from config.app_paths import APP_VERSION, LATEST_RELEASE_API_URL

EXE_ASSET_NAME = "DesignDataManager.exe"
OLD_SUFFIX = ".old"
NEW_SUFFIX = ".download"


class UpdateError(Exception):
    """Checking for or installing an update failed; the message says why, in plain words."""


def parse_version(text):
    """``"v0.2.0"`` or ``"0.1.0 Beta"`` -> ``(0, 2, 0)``; ``None`` if there's no version in it."""
    match = re.search(r"(\d+(?:\.\d+)*)", text or "")
    if not match:
        return None
    parts = [int(part) for part in match.group(1).split(".")]
    return tuple(parts + [0] * (3 - len(parts)))


def is_newer(latest, current=APP_VERSION):
    latest_version, current_version = parse_version(latest), parse_version(current)
    return latest_version is not None and current_version is not None and latest_version > current_version


def _get_json(url, timeout):
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "DesignDataManager-Updater",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def latest_release(url=LATEST_RELEASE_API_URL, timeout=10, get_json=_get_json):
    """The latest release: ``{"version", "notes", "exe_url", "page"}``, or ``None`` when it has no
    .exe attached. Raises ``UpdateError`` when GitHub can't be reached."""
    try:
        release = get_json(url, timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:  # no release published yet
            return None
        raise UpdateError(f"Couldn't check GitHub for updates ({exc}).") from exc
    except (OSError, ValueError) as exc:
        raise UpdateError(f"Couldn't reach GitHub to check for updates ({exc}).") from exc
    exe = next((asset for asset in release.get("assets", []) if asset.get("name") == EXE_ASSET_NAME), None)
    if exe is None:
        return None
    return {
        "version": release.get("tag_name", "").lstrip("vV"),
        "notes": (release.get("body") or "").strip(),
        "exe_url": exe.get("browser_download_url"),
        "page": release.get("html_url", ""),
    }


def available_update(current=APP_VERSION, **kwargs):
    """The latest release if it's newer than ``current``, else ``None``."""
    release = latest_release(**kwargs)
    return release if release and is_newer(release["version"], current) else None


def _download(url, target, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": "DesignDataManager-Updater"})
    with urllib.request.urlopen(request, timeout=timeout) as response, open(target, "wb") as out:
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)


def install_update(release, exe_path, timeout=300, download=_download):
    """Download ``release``'s .exe and put it in place of ``exe_path`` (the running .exe, renamed to
    ``.old``). Returns ``exe_path``. Raises ``UpdateError``; the running .exe is left as it was."""
    exe_path = Path(exe_path)
    new_path = exe_path.with_name(exe_path.name + NEW_SUFFIX)
    old_path = exe_path.with_name(exe_path.name + OLD_SUFFIX)
    try:
        download(release["exe_url"], new_path, timeout)
        with open(new_path, "rb") as file:
            if file.read(2) != b"MZ" or new_path.stat().st_size < 1_000_000:
                raise UpdateError("The downloaded file isn't the Design Data Manager program. Try again later.")
    except (OSError, ValueError) as exc:
        new_path.unlink(missing_ok=True)
        raise UpdateError(f"The update couldn't be downloaded ({exc}).") from exc
    except UpdateError:
        new_path.unlink(missing_ok=True)
        raise
    try:
        old_path.unlink(missing_ok=True)
        exe_path.rename(old_path)
    except OSError as exc:
        new_path.unlink(missing_ok=True)
        raise UpdateError(f"The program couldn't be replaced ({exc}). Is its folder read-only?") from exc
    try:
        new_path.rename(exe_path)
    except OSError as exc:
        old_path.rename(exe_path)  # put the running version back
        raise UpdateError(f"The program couldn't be replaced ({exc}).") from exc
    return exe_path


def restart(exe_path):
    """Start the (updated) .exe as a fresh program; the caller then closes this one."""
    env = dict(os.environ)
    # A PyInstaller .exe started from another one would otherwise reuse its unpacked files.
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen([str(exe_path)], env=env, close_fds=True)


def remove_old_version(exe_path):
    """Delete the ``.old`` .exe an update left behind (it was running then, so it couldn't be)."""
    try:
        Path(exe_path).with_name(Path(exe_path).name + OLD_SUFFIX).unlink(missing_ok=True)
    except OSError:
        pass
