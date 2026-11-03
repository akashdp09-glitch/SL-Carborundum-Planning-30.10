"""One shared Plan-2026 (and the other Home uploads) for Hub, Daily, Firing and the phone.

Home writes ``CENTRAL_DATA/COMPANY_DATA/Plan-2026-LATEST.xlsx``. Daily, Firing and
``sync_mobile_plan.py`` used to look at different folders, so QR labels could be
printed from the uploaded plan while the phone database stayed empty and Daily
raised “Upload latest Plan 2026 first.”

This module only *finds* an existing file. It never invents a workbook.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .common import REPO_ROOT

POINTER_NAME = "runtime_paths.json"

# Filename every module already reads from COMPANY_DATA (or from the pointer).
PLAN_FILE = "Plan-2026-LATEST.xlsx"
FIRING_FILE = "Firing-Plan-LATEST.xlsx"
JOB_REGISTER_FILE = "Job-Register-LATEST.xlsx"
PROCESS_CLOSE_FILE = "Process-Close-LATEST.xlsx"

LEGACY_FILES = (
    PLAN_FILE,
    FIRING_FILE,
    "Sales-Forecast-LATEST.xlsx",
    "Stock-on-Hand-LATEST.xlsx",
    "Packaging-Standard-LATEST.xlsx",
    "P280526-LATEST.xlsx",
    "New-Request-Reference-LATEST.xlsx",
    JOB_REGISTER_FILE,
    PROCESS_CLOSE_FILE,
    "CAPACITY_DATABASE.xlsx",
)

SLOT_FOR_FILE = {
    PLAN_FILE: "PLAN_2026",
    FIRING_FILE: "FIRING_PLAN",
    "Sales-Forecast-LATEST.xlsx": "SALES_FORECAST",
    "Stock-on-Hand-LATEST.xlsx": "STOCK_ON_HAND",
    "Packaging-Standard-LATEST.xlsx": "PACKAGING_STANDARD",
    "P280526-LATEST.xlsx": "SD_RECIPE_MASTER",
    "New-Request-Reference-LATEST.xlsx": "NEW_REQUEST_REFERENCE",
    JOB_REGISTER_FILE: "SEPT_OPEN_CLOSED",
    PROCESS_CLOSE_FILE: "PROCESS_CLOSE",
    "CAPACITY_DATABASE.xlsx": "CAPACITY_DATABASE",
}


def program_root(start: Optional[Path] = None) -> Path:
    return Path(start or REPO_ROOT).resolve()


def shared_root(env: Optional[dict] = None, start: Optional[Path] = None) -> Path:
    env = env if env is not None else os.environ
    raw = env.get("SL_SHARED_ROOT")
    if raw:
        return Path(raw).resolve()
    return (program_root(start) / "CENTRAL_DATA").resolve()


def company_data(env: Optional[dict] = None, start: Optional[Path] = None) -> Path:
    env = env if env is not None else os.environ
    raw = env.get("SL_COMPANY_DATA")
    if raw:
        return Path(raw).resolve()
    return (shared_root(env, start) / "COMPANY_DATA").resolve()


def db_path(env: Optional[dict] = None, start: Optional[Path] = None) -> Path:
    env = env if env is not None else os.environ
    raw = env.get("SL_DB_PATH")
    if raw:
        return Path(raw).resolve()
    return (shared_root(env, start) / "DATABASE" / "sl_planning.db").resolve()


def pointer_path(env: Optional[dict] = None, start: Optional[Path] = None) -> Path:
    return shared_root(env, start) / POINTER_NAME


def read_pointer(env: Optional[dict] = None, start: Optional[Path] = None) -> dict:
    path = pointer_path(env, start)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _existing(path) -> Optional[Path]:
    if not path:
        return None
    p = Path(path)
    try:
        p = p.resolve()
    except Exception:
        p = Path(path)
    return p if p.is_file() and p.stat().st_size > 0 else None


def _source_manager_path(filename: str, env: Optional[dict] = None, start: Optional[Path] = None) -> Optional[Path]:
    slot = SLOT_FOR_FILE.get(filename)
    if not slot:
        return None
    root = shared_root(env, start)
    db = root / "source_manager.sqlite"
    if not db.exists():
        return None
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT stored_path FROM revisions WHERE slot_id=? AND active=1 LIMIT 1", (slot,)
            ).fetchone()
        finally:
            con.close()
        return _existing(row[0]) if row else None
    except Exception:
        return None


def resolve_file(filename: str, env: Optional[dict] = None, start: Optional[Path] = None) -> Optional[Path]:
    """Return the existing workbook this install should read, or None."""
    env = env if env is not None else os.environ
    name = Path(filename).name
    pointer = read_pointer(env, start)
    files = pointer.get("files") if isinstance(pointer.get("files"), dict) else {}
    candidates = [
        files.get(name),
        company_data(env, start) / name,
        shared_root(env, start) / "COMPANY_DATA" / name,
        program_root(start) / "CENTRAL_DATA" / "COMPANY_DATA" / name,
        program_root(start) / "company_data" / name,  # pre-V12 folder only
    ]
    for raw in candidates:
        found = _existing(raw)
        if found:
            return found
    return _source_manager_path(name, env, start)


def resolve_plan(env: Optional[dict] = None, start: Optional[Path] = None) -> Optional[Path]:
    return resolve_file(PLAN_FILE, env, start)


def original_name_for(filename: str, env: Optional[dict] = None, start: Optional[Path] = None) -> Optional[str]:
    """Original upload name (e.g. October-2026.xls) for a COMPANY_DATA file, if recorded."""
    name = Path(filename).name
    slot = SLOT_FOR_FILE.get(name)
    root = shared_root(env, start)
    if slot:
        db = root / "source_manager.sqlite"
        if db.exists():
            try:
                import sqlite3
                con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
                try:
                    row = con.execute(
                        "SELECT original_name FROM revisions WHERE slot_id=? AND active=1 LIMIT 1", (slot,)
                    ).fetchone()
                finally:
                    con.close()
                if row and row[0]:
                    return str(row[0])
            except Exception:
                pass
    for reg in (root / "source_registry.json", company_data(env, start).parent / "source_registry.json"):
        try:
            data = json.loads(reg.read_text(encoding="utf-8"))
            entry = data.get(name) if isinstance(data, dict) else None
            orig = (entry or {}).get("original_name")
            if orig:
                return str(orig)
        except Exception:
            continue
    return None


def write_pointer(root: Optional[Path] = None, env: Optional[dict] = None) -> Path:
    """Record this program folder and the files that exist so child processes share them."""
    env = env if env is not None else os.environ
    root = program_root(root)
    shared = shared_root(env, root)
    data = company_data(env, root)
    shared.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in LEGACY_FILES:
        found = resolve_file(name, env, root)
        if found:
            files[name] = str(found)
    payload = {
        "program_root": str(root),
        "shared_root": str(shared),
        "company_data": str(data),
        "db_path": str(db_path(env, root)),
        "files": files,
    }
    dest = shared / POINTER_NAME
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def file_status(env: Optional[dict] = None, start: Optional[Path] = None) -> list[dict]:
    rows = []
    for name in LEGACY_FILES:
        found = resolve_file(name, env, start)
        rows.append({"name": name, "loaded": bool(found), "path": str(found) if found else ""})
    return rows


def missing_plan_message(thai: bool = False) -> str:
    if thai:
        return (
            "ยังไม่มี Plan-2026 ส่วนกลางที่ Daily / แผนเตา / มือถือจะอ่านได้ "
            "อัปโหลดครั้งเดียวที่หน้าหลัก → อัปโหลดไฟล์ "
            "(ไฟล์จะถูกเก็บที่ CENTRAL_DATA\\COMPANY_DATA\\Plan-2026-LATEST.xlsx) "
            "แล้วปิดหน้าต่าง Daily / แผนเตา / มือถือจากโฟลเดอร์ ZIP เก่าที่ยังเปิดพอร์ต 8511"
        )
    return (
        "The shared Plan-2026 is not on disk for Daily, Firing or the phone. "
        "Upload it once on Home → Upload / replace source files "
        "(stored as CENTRAL_DATA\\COMPANY_DATA\\Plan-2026-LATEST.xlsx). "
        "Then close Daily / Firing / phone windows from an older ZIP folder — "
        "those keep their own empty folder and cause “Upload latest Plan 2026 first” "
        "or “work order does not exist” on the phone."
    )


def child_environ(root: Optional[Path] = None, env: Optional[dict] = None) -> dict:
    """Environment so a child process reads the same folders as this hub."""
    env = dict(env if env is not None else os.environ)
    root = program_root(root)
    shared = shared_root(env, root)
    env["SL_SHARED_ROOT"] = str(shared)
    env["SL_COMPANY_DATA"] = str(company_data(env, root))
    env["SL_DB_PATH"] = str(db_path(env, root))
    env.setdefault("SL_PHOTO_ROOT", str(shared / "PHOTOS"))
    env.setdefault("SL_SOURCE_COPY_ROOT", str(shared / "SOURCE_COPIES"))
    env.setdefault("SL_REPORT_ROOT", str(shared / "REPORTS"))
    return env
