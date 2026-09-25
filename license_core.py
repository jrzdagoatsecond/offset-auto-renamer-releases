"""
license_core.py
----------------
Shared key-generation / key-validation logic for Offset Auto Renamer.

This is a simple, self-contained licensing scheme:
  * Keys are generated locally by keygen.py (the "Offset Key Generator").
  * Keys are validated locally by app.py using an HMAC-SHA256 signature
    derived from a shared secret, so only keys produced by keygen.py
    (or someone who has this source / secret) will validate.
  * A valid key is cached locally so the user only has to enter it once
    per machine.
  * Keys can be DEACTIVATED after the fact: keygen.py can push a key
    onto a small "revoked keys" list hosted online (a JSON file in your
    GitHub repo). app.py checks that list on every launch, so a revoked
    key stops working the next time the person opens the app.
  * Keys come in two TYPES: "lifetime" (never expires) and "month"
    (expires 30 days after it was generated). The type and issue date
    are encoded directly into the key itself (in the first group after
    OFST-), so expiry checking works fully offline, just like the
    checksum. Keys generated before this feature existed have no
    parseable type in that group and are treated as lifetime keys, so
    nothing already issued breaks.

NOTE: This is intended as a lightweight "enter a generated key to unlock
the tool" gate for your own software distribution, not as unbreakable
DRM -- anyone with the source (which includes the secret below) can
generate their own keys. If you want per-customer control, change
SECRET to something private and only distribute compiled builds, or
move validation to a server you control.
"""

import base64
import hashlib
import hmac
import json
import os
import platform
import random
import string
import sys
import time
import urllib.request
import urllib.error
import uuid
from datetime import date, timedelta
from pathlib import Path

# Change this to your own private value before distributing compiled builds.
SECRET = b"OFFSET-SHOP-AUTORENAMER-SECRET-2026"

GROUP_LEN = 4
NUM_GROUPS = 4          # e.g. XXXX-XXXX-XXXX-XXXX
CHECK_LEN = 4           # last group is derived from the others
ALPHABET = string.ascii_uppercase + string.digits
# Characters that look alike are excluded to avoid user typos.
AMBIGUOUS = "0O1I"
ALPHABET = "".join(c for c in ALPHABET if c not in AMBIGUOUS)

# --------------------------------------------------------------------------
# Key types + expiry.
#
# The first group after "OFST-" doubles as a metadata group: its first
# character is a type marker, and the remaining three characters are a
# base-N (N = len(ALPHABET)) encoding of how many days after DAY_EPOCH the
# key was issued. That's enough range for well over 80 years, and it means
# expiry can be checked with no network call, the same way the checksum is.
#
# "lifetime" keys never expire. "month" keys expire MONTH_KEY_DURATION_DAYS
# days after they were generated.
# --------------------------------------------------------------------------
KEY_TYPE_LIFETIME = "lifetime"
KEY_TYPE_MONTH = "month"
KEY_TYPES = {"L": KEY_TYPE_LIFETIME, "M": KEY_TYPE_MONTH}
TYPE_CHARS = {KEY_TYPE_LIFETIME: "L", KEY_TYPE_MONTH: "M"}

MONTH_KEY_DURATION_DAYS = 30
DAY_EPOCH = date(2025, 1, 1)
DAY_CODE_LEN = GROUP_LEN - 1  # 3 chars of the 4-char metadata group


def _encode_base_n(n: int, width: int) -> str:
    """Encode a non-negative int as `width` characters drawn from ALPHABET."""
    base = len(ALPHABET)
    chars = []
    for _ in range(width):
        n, r = divmod(n, base)
        chars.append(ALPHABET[r])
    return "".join(reversed(chars))


def _decode_base_n(s: str) -> int:
    base = len(ALPHABET)
    n = 0
    for ch in s:
        n = n * base + ALPHABET.index(ch)
    return n

# --------------------------------------------------------------------------
# Revocation list configuration.
#
# This should point at the RAW url of a small JSON file (a plain array of
# revoked key strings, e.g. ["OFST-AAAA-BBBB-CCCC-DDDD"]).
#
# This MUST be a URL that's readable with no authentication, since the
# distributed app has no GitHub token. A file inside a private repo does
# NOT work for this (raw.githubusercontent.com 404s on private-repo files
# for unauthenticated requests) — use a public GitHub Gist instead, which
# keygen.py's "Deactivation Settings" panel can create for you. It's fine
# for this URL to be public knowledge — it only ever contains key strings,
# never the SECRET, so it can't be used to mint new keys.
#
# Example, once you've created a gist via keygen.py:
#   "https://gist.githubusercontent.com/raw/<gist_id>/revoked_keys.json"
#
# Leave this blank to disable online revocation checks entirely (keys will
# only be checked for format/checksum, exactly like before).
# --------------------------------------------------------------------------
REVOCATION_URL = "https://gist.githubusercontent.com/raw/8bf0b3fbdba7807fe8aaf60fb6c7c939/revoked_keys.json"

# Network timeout for each revocation check (seconds).
REVOCATION_FETCH_TIMEOUT = 5

# How often the running app re-checks (in the background, ignoring the
# cache TTL above) whether its *current* key has been deactivated while
# the tool is already open. Keep this short enough to feel "immediate"
# but not so short it hammers GitHub.
LIVE_REVOCATION_CHECK_INTERVAL = 60  # seconds


def _checksum(payload: str) -> str:
    """Derive a short, deterministic checksum group from the payload using HMAC-SHA256."""
    digest = hmac.new(SECRET, payload.encode("utf-8"), hashlib.sha256).digest()
    b32 = base64.b32encode(digest).decode("utf-8")
    b32 = "".join(c for c in b32 if c not in AMBIGUOUS and c.isalnum())
    return b32[:CHECK_LEN].upper()


def generate_key(key_type: str = KEY_TYPE_LIFETIME) -> str:
    """
    Generate a brand-new, valid license key.

    `key_type` is either KEY_TYPE_LIFETIME ("lifetime", the default) or
    KEY_TYPE_MONTH ("month"), which expires MONTH_KEY_DURATION_DAYS days
    from today. The type and issue date are baked into the key's first
    group so no server lookup is needed to enforce the expiry later.
    """
    if key_type not in TYPE_CHARS:
        raise ValueError(f"Unknown key_type: {key_type!r}")

    type_char = TYPE_CHARS[key_type]
    issued_days = (date.today() - DAY_EPOCH).days
    meta_group = type_char + _encode_base_n(issued_days, DAY_CODE_LEN)

    groups = [meta_group]
    for _ in range(NUM_GROUPS - 2):
        groups.append("".join(random.choice(ALPHABET) for _ in range(GROUP_LEN)))
    payload = "-".join(groups)
    check = _checksum(payload)
    return f"OFST-{payload}-{check}"


def is_valid_key(key: str) -> bool:
    """Validate a key's format + checksum only (does not check revocation)."""
    if not key:
        return False
    key = key.strip().upper()
    parts = key.split("-")
    # Expected shape: OFST-XXXX-XXXX-XXXX-CHECK
    if len(parts) != NUM_GROUPS + 1:
        return False
    if parts[0] != "OFST":
        return False
    payload = "-".join(parts[1:-1])
    provided_check = parts[-1]
    expected_check = _checksum(payload)
    return hmac.compare_digest(provided_check, expected_check)


def parse_key_meta(key: str):
    """
    Returns (key_type, issued_date) for a valid key, or None if the key is
    invalid, or if it's valid but predates this feature (in which case it
    has no parseable type/date in its metadata group -- callers should
    treat that as a legacy lifetime key, which get_key_type()/is_key_expired()
    already do).
    """
    if not is_valid_key(key):
        return None
    parts = key.strip().upper().split("-")
    meta_group = parts[1]
    key_type = KEY_TYPES.get(meta_group[0])
    if key_type is None:
        return None
    try:
        issued_days = _decode_base_n(meta_group[1:1 + DAY_CODE_LEN])
        issued_date = DAY_EPOCH + timedelta(days=issued_days)
    except Exception:
        return None
    return key_type, issued_date


def get_key_type(key: str) -> str:
    """
    Returns KEY_TYPE_LIFETIME or KEY_TYPE_MONTH. Keys that don't carry
    parseable metadata (invalid keys, or keys generated before this
    feature existed) are treated as lifetime keys -- old keys already in
    the wild keep working exactly as before.
    """
    meta = parse_key_meta(key)
    if meta is None:
        return KEY_TYPE_LIFETIME
    return meta[0]


def get_key_expiry_date(key: str):
    """Returns the date a 'month' key expires on, or None for lifetime keys."""
    meta = parse_key_meta(key)
    if meta is None:
        return None
    key_type, issued_date = meta
    if key_type != KEY_TYPE_MONTH:
        return None
    return issued_date + timedelta(days=MONTH_KEY_DURATION_DAYS)


def is_key_expired(key: str) -> bool:
    """True only for 'month' keys whose expiry date has passed."""
    expiry = get_key_expiry_date(key)
    if expiry is None:
        return False
    return date.today() > expiry


def describe_key(key: str) -> str:
    """Short human-readable label for display in the UI, e.g. in keygen.py."""
    expiry = get_key_expiry_date(key)
    if expiry is None:
        return "Lifetime"
    if date.today() > expiry:
        return f"1 Month — expired {expiry.isoformat()}"
    return f"1 Month — expires {expiry.isoformat()}"


# ---------------------------------------------------------------------
# Hardware ID (HWID)
#
# A stable, per-machine identifier the customer can hand to you (and you
# can record against their key in Offset Key Generator's Key Log) so you
# know which machine a key is tied to. It's a one-way hash of local
# machine info (MAC address + hostname + OS) -- not reversible, and not
# transmitted anywhere automatically. The activation screen just displays
# it with a "Copy System ID" button; getting it to you is a manual step
# (support chat, email, etc.), the same way the key itself gets to them.
# ---------------------------------------------------------------------
def get_hwid() -> str:
    """Deterministic, human-shareable hardware ID for this machine."""
    raw = f"{uuid.getnode()}|{platform.node()}|{platform.system()}|{platform.machine()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    chunk = digest[:12]
    return "-".join(chunk[i:i + 4] for i in range(0, 12, 4))


def _license_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".config"
    folder = base / "OffsetAutoRenamer"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _license_file_path() -> Path:
    return _license_dir() / "license.dat"


def _revocation_cache_path() -> Path:
    return _license_dir() / "revoked_cache.json"


def load_saved_key() -> str:
    path = _license_file_path()
    if path.exists():
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""
    return ""


def save_key(key: str) -> None:
    path = _license_file_path()
    try:
        path.write_text(key.strip(), encoding="utf-8")
    except Exception:
        pass


def clear_saved_key() -> None:
    path = _license_file_path()
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------------
# Revocation checking (app-side / consumer of the revoked list)
# ---------------------------------------------------------------------
def fetch_revoked_keys(url: str = None, timeout: int = REVOCATION_FETCH_TIMEOUT):
    """
    Fetch the revoked-keys JSON list from `url` (defaults to REVOCATION_URL).
    Returns a set of upper-cased key strings on success, or None if the
    fetch failed (no internet, bad URL, etc.) so the caller can decide how
    to handle "unknown" vs "confirmed not revoked".
    """
    target = url or REVOCATION_URL
    if not target:
        return None
    try:
        req = urllib.request.Request(target, headers={"User-Agent": "OffsetAutoRenamer"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, list):
            return {str(k).strip().upper() for k in data}
        return set()
    except Exception:
        return None


def _load_revocation_cache():
    path = _revocation_cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("fetched_at", 0), set(data.get("keys", []))
    except Exception:
        return None


def _save_revocation_cache(keys):
    path = _revocation_cache_path()
    try:
        path.write_text(
            json.dumps({"fetched_at": time.time(), "keys": sorted(keys)}),
            encoding="utf-8",
        )
    except Exception:
        pass


def is_key_revoked(key: str, force: bool = True) -> bool:
    """
    Checks whether `key` is on the revoked list.

    Always tries a live online fetch first (this used to be gated behind
    a 30-minute "trust the cache" window, which meant a key deactivated
    shortly after being activated could keep working for up to 30 more
    minutes even across app restarts — that was a bug, not a feature, so
    it's gone now). The local cache exists purely as an OFFLINE fallback,
    not as a way to skip checking.

    Behavior:
      - If REVOCATION_URL is blank, revocation checking is disabled and
        this always returns False.
      - Always attempts an online fetch first.
      - If the online fetch fails (no internet) and there IS a
        previously cached list, falls back to that cached list so
        revocations still apply based on the last known-good data.
      - If there's no cache AND the fetch fails (e.g. first run, no
        internet), fails OPEN (treats the key as not revoked) rather
        than locking out a legitimate user with no connectivity. Once
        a connection succeeds even once, revocations start applying
        immediately and reliably.

    The `force` parameter is kept for backward compatibility with
    existing call sites but no longer changes behavior — every call now
    behaves as force=True.
    """
    if not REVOCATION_URL:
        return False

    key = (key or "").strip().upper()
    if not key:
        return False

    fresh = fetch_revoked_keys()
    if fresh is not None:
        _save_revocation_cache(fresh)
        return key in fresh

    # Fetch failed — genuinely offline. Fall back to the last known list.
    cached = _load_revocation_cache()
    if cached:
        _, cached_keys = cached
        return key in cached_keys

    # No cache and no connectivity at all: fail open.
    return False


def has_valid_saved_license() -> bool:
    key = load_saved_key()
    if not is_valid_key(key):
        return False
    if is_key_expired(key):
        clear_saved_key()
        return False
    if is_key_revoked(key):
        clear_saved_key()
        return False
    return True

