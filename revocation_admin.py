"""
revocation_admin.py
--------------------
Admin-side helpers (used only by keygen.py — the Offset Key Generator)
for maintaining the hosted "revoked keys" list.

This uses a GitHub Gist rather than a file inside your main repo,
specifically so it works even when your source code repo is PRIVATE:
raw.githubusercontent.com refuses to serve files from private repos to
unauthenticated requests (the running app has no token), which would
make revocation silently never work. A Gist is a separate, small,
standalone snippet — you can make just this one thing public while your
actual source stays private.

You need a GitHub Personal Access Token (classic, with the "gist"
scope) to create/update the gist. Create one at:
https://github.com/settings/tokens

The token is stored ONLY in a local config file on this machine
(keygen_config.json, next to your other Offset app data) and is never
bundled into, or required by, the distributed app.py / .exe. Keep this
config file and the Key Generator tool private.
"""

import base64
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

API_ROOT = "https://api.github.com"


def _config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".config"
    folder = base / "OffsetAutoRenamer"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _config_path() -> Path:
    return _config_dir() / "keygen_config.json"


DEFAULT_CONFIG = {
    "gist_id": "",
    "filename": "revoked_keys.json",
    "token": "",
}


def load_config() -> dict:
    path = _config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cfg = dict(DEFAULT_CONFIG)
            cfg.update(data)
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    path = _config_path()
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    path.write_text(json.dumps(merged, indent=2), encoding="utf-8")


class GitHubError(Exception):
    pass


def _api_request(method: str, url: str, token: str, body: dict = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "OffsetKeyGenerator")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise GitHubError(f"GitHub API error {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise GitHubError(f"Network error contacting GitHub: {e}") from e


def create_gist(token: str, filename: str = "revoked_keys.json") -> dict:
    """
    Creates a brand-new PUBLIC gist containing an empty revoked-keys list.
    Returns the raw gist API response (includes 'id' and 'files').
    """
    if not token:
        raise GitHubError("A GitHub access token (with 'gist' scope) is required.")
    body = {
        "description": "Offset Auto Renamer — revoked license keys",
        "public": True,
        "files": {
            filename: {"content": "[]\n"}
        },
    }
    return _api_request("POST", f"{API_ROOT}/gists", token, body)


def raw_url_for(cfg: dict) -> str:
    """
    The public, no-auth-required URL app.py should be pointed at
    (REVOCATION_URL). Without a pinned revision hash, this always
    serves the gist's latest content.
    """
    gist_id = cfg.get("gist_id", "").strip()
    filename = cfg.get("filename", "revoked_keys.json").strip()
    if not gist_id:
        return ""
    return f"https://gist.githubusercontent.com/raw/{gist_id}/{filename}"


def get_remote_list(cfg: dict):
    """
    Returns the current set of revoked keys stored in the gist.
    Raises GitHubError if the gist can't be read (bad id/token/etc).
    """
    gist_id = cfg.get("gist_id", "").strip()
    filename = cfg.get("filename", "revoked_keys.json").strip()
    if not gist_id:
        return set()

    result = _api_request("GET", f"{API_ROOT}/gists/{gist_id}", cfg.get("token", ""))
    files = result.get("files", {})
    file_info = files.get(filename)
    if not file_info:
        return set()

    content = file_info.get("content")
    if content is None and file_info.get("truncated") and file_info.get("raw_url"):
        # Very large files come back truncated; fall back to fetching raw_url.
        req = urllib.request.Request(file_info["raw_url"], headers={"User-Agent": "OffsetKeyGenerator"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8")

    try:
        keys = json.loads(content or "[]")
        if not isinstance(keys, list):
            keys = []
    except Exception:
        keys = []
    return {str(k).strip().upper() for k in keys}


def put_remote_list(cfg: dict, keys, message: str = None):
    """Writes `keys` (an iterable of key strings) back to the gist."""
    gist_id = cfg.get("gist_id", "").strip()
    filename = cfg.get("filename", "revoked_keys.json").strip()
    if not gist_id:
        raise GitHubError("No gist configured yet — create one in Settings first.")

    body_text = json.dumps(sorted(set(k.strip().upper() for k in keys)), indent=2) + "\n"
    payload = {
        "files": {
            filename: {"content": body_text}
        }
    }
    return _api_request("PATCH", f"{API_ROOT}/gists/{gist_id}", cfg.get("token", ""), payload)


def revoke_key(cfg: dict, key: str) -> int:
    """Adds `key` to the remote revoked list. Returns the new list size."""
    key = key.strip().upper()
    keys = get_remote_list(cfg)
    keys.add(key)
    put_remote_list(cfg, keys, f"Revoke key {key}")
    return len(keys)


def unrevoke_key(cfg: dict, key: str) -> int:
    """Removes `key` from the remote revoked list, if present. Returns the new list size."""
    key = key.strip().upper()
    keys = get_remote_list(cfg)
    keys.discard(key)
    put_remote_list(cfg, keys, f"Un-revoke key {key}")
    return len(keys)
