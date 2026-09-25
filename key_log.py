"""
key_log.py
----------
Local, persistent record of every key issued from Offset Key Generator
-- used only by keygen.py (the admin-side tool). Not imported by app.py
and never bundled into the distributed OffsetAutoRenamer.exe.

This is separate from the online "revoked keys" Gist (revocation_admin.py
/ REVOCATION_URL): that Gist is the source of truth for whether a key
currently WORKS. This file is your own local notebook of every key
you've minted, plus anything you've noted about it (who has it, what
HWID it's tied to). Deleting an entry here only removes it from your
notes -- it does NOT deactivate the key. Deactivating still goes through
the existing Gist-backed revoke/unrevoke flow.

Stored at the same per-user app-data folder as license.dat, in
key_log.json, as a list of records:
    {
        "key": "OFST-XXXX-XXXX-XXXX-XXXX",
        "type": "lifetime" | "month",
        "length": 24,
        "issued": "2026-09-24",          # ISO date encoded in the key
        "generated_at": "2026-09-24T10:11:12",  # when you minted it
        "hwid": "",                      # machine ID you've recorded, if any
        "note": ""                       # free-text note (customer name, etc.)
    }
"""

import json
from datetime import datetime, date
from pathlib import Path

import license_core


def _log_path() -> Path:
    return license_core._license_dir() / "key_log.json"


def load_log() -> list:
    path = _log_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def save_log(records: list) -> None:
    path = _log_path()
    try:
        path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    except Exception:
        pass


def find(records: list, key: str):
    key = (key or "").strip().upper()
    for rec in records:
        if rec.get("key", "").strip().upper() == key:
            return rec
    return None


def add_key(key: str, key_type: str = None, note: str = "") -> dict:
    """
    Appends a new record for `key` (skips if already logged) and returns
    the record. Type/issue date are read straight from the key itself
    when not given, since license_core encodes them there.
    """
    records = load_log()
    existing = find(records, key)
    if existing:
        return existing

    if key_type is None:
        key_type = license_core.get_key_type(key)
    meta = license_core.parse_key_meta(key)
    issued = meta[1].isoformat() if meta else date.today().isoformat()

    record = {
        "key": key.strip().upper(),
        "type": key_type,
        "length": len(key.strip()),
        "issued": issued,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "hwid": "",
        "note": note,
    }
    records.append(record)
    save_log(records)
    return record


def remove_key(key: str) -> bool:
    """Removes `key` from the local log only (does not deactivate it)."""
    records = load_log()
    key = (key or "").strip().upper()
    new_records = [r for r in records if r.get("key", "").strip().upper() != key]
    if len(new_records) == len(records):
        return False
    save_log(new_records)
    return True


def set_hwid(key: str, hwid: str) -> bool:
    records = load_log()
    rec = find(records, key)
    if not rec:
        return False
    rec["hwid"] = hwid.strip()
    save_log(records)
    return True


def set_note(key: str, note: str) -> bool:
    records = load_log()
    rec = find(records, key)
    if not rec:
        return False
    rec["note"] = note.strip()
    save_log(records)
    return True
