"""Small shared helpers (no Streamlit). Factory date/time is Asia/Bangkok."""
from __future__ import annotations
import datetime as dt
import hashlib
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    BKK = ZoneInfo("Asia/Bangkok")
except Exception:  # pragma: no cover - tzdata missing
    BKK = None

REPO_ROOT = Path(__file__).resolve().parents[1]


def bkk_now() -> dt.datetime:
    """Current factory wall-clock time (naive datetime in Asia/Bangkok)."""
    return dt.datetime.now(BKK).replace(tzinfo=None) if BKK else dt.datetime.now()


def bkk_today() -> dt.date:
    return bkk_now().date()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cell_ref(sheet: str, coord: str) -> str:
    return f"{sheet}!{coord}"
