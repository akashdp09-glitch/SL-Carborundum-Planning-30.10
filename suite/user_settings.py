"""Append-only, traceable user settings (holidays, out-of-service machine cells ...).

Every change is a new row with user, Asia/Bangkok time and reason; nothing is overwritten, so the full history can be shown and any earlier value restored.
Stored in <SL_SHARED_ROOT>/DATA/user_settings.sqlite (SQLite, WAL).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from .common import bkk_now

KEY_HOLIDAYS = "calendar.holidays"                 # [{"date": "YYYY-MM-DD", "label": "..."}]
KEY_OUT_OF_SERVICE = "capacity.out_of_service_cells"   # ["D7", ...] cells of the 'M/C.' column on sheet CAP ขึ้นรูป


class SettingsStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._c() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS settings_log(id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, value_json TEXT NOT NULL,
                         changed_by TEXT NOT NULL, reason TEXT NOT NULL, changed_at TEXT NOT NULL)""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_settings_key ON settings_log(key, id)")

    def _c(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def get(self, key: str, default: Any = None) -> Any:
        with self._c() as c:
            r = c.execute("SELECT value_json FROM settings_log WHERE key=? ORDER BY id DESC LIMIT 1", (key,)).fetchone()
        return default if r is None else json.loads(r["value_json"])

    def set(self, key: str, value: Any, user: str, reason: str) -> int:
        if not (user or "").strip():
            raise ValueError("A user name is required so the change is traceable")
        if not (reason or "").strip():
            raise ValueError("A reason is required so the change is traceable")
        with self._c() as c:
            cur = c.execute("INSERT INTO settings_log(key,value_json,changed_by,reason,changed_at) VALUES(?,?,?,?,?)",
                            (key, json.dumps(value, ensure_ascii=False, sort_keys=True), user.strip(), reason.strip(), bkk_now().isoformat(timespec="seconds")))
            return cur.lastrowid

    def history(self, key: str | None = None) -> pd.DataFrame:
        q, a = "SELECT id,key,value_json,changed_by,reason,changed_at FROM settings_log", ()
        if key:
            q, a = q + " WHERE key=?", (key,)
        with self._c() as c:
            return pd.DataFrame([dict(r) for r in c.execute(q + " ORDER BY id DESC", a)])


def owner_decisions() -> dict:
    from .common import REPO_ROOT
    return json.loads((REPO_ROOT / "knowledge" / "owner_decisions.json").read_text(encoding="utf-8"))


def default_out_of_service() -> list:
    return list(next(d for d in owner_decisions()["decisions"] if d["id"] == "OD-4")["out_of_service_cells"])


def effective_out_of_service(store: "SettingsStore | None") -> list:
    """Latest saved list, else the owner's list of 2026-10-04."""
    saved = store.get(KEY_OUT_OF_SERVICE) if store else None
    return list(saved) if saved is not None else default_out_of_service()


def effective_holidays(store: "SettingsStore | None") -> list:
    return list(store.get(KEY_HOLIDAYS, []) if store else [])
