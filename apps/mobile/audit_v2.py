"""Shared audit record model + operator capture workflow (Stage A/B of PROJECT_REQUIREMENTS.md).

Installed from app.py with ``audit_v2.install(sys.modules[__name__])`` after ``init_db()``.
Everything here is additive: new tables, new nullable columns, new routes. Existing tables,
rows, routes and the production ``events`` ledger are untouched.

Rules implemented here (see AGENTS.md):
- physical observations live in mobile_audits / unidentified_parts and never write ``events``;
- unknown quantity is NULL + qty_unknown=1, never 0;
- a submission is acknowledged only after the DB commit and the photo files are on disk;
- every write carries a client_submission_id, so a retry returns the original record;
- timestamps use Asia/Bangkok; client_time (when the operator submitted) and
  server_received_at (when the server committed it) are stored separately.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from suite.qr_png import make as _make_qr_png
from typing import Optional
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

core = None  # the app module, injected by install()

MIGRATION_ID = "v2_001_audit_register"
AUDIT_STATUSES = ["OK", "SHORT", "EXCESS", "NOT_FOUND", "WRONG_LOCATION", "DAMAGE", "HOLD", "OTHER"]
UNIDENT_STATUSES = AUDIT_STATUSES + ["UNKNOWN"]
GPS_STATES = {"CAPTURED", "DENIED", "UNAVAILABLE", "NOT_REQUESTED"}
UNITS = [u.strip() for u in os.environ.get("SL_AUDIT_UNITS", "pcs,box,pallet,kg").split(",") if u.strip()]
MAX_PHOTOS = 6
IMAGE_EXT = {"jpeg": ".jpg", "png": ".png", "webp": ".webp", "heic": ".heic"}
THUMB_PX = 320

AUDIT_COLUMNS = [
    ("tracking_id", "TEXT"), ("client_submission_id", "TEXT"), ("client_time", "TEXT"), ("server_received_at", "TEXT"),
    ("qty_unit", "TEXT"), ("qty_unknown", "INTEGER NOT NULL DEFAULT 0"), ("batch_ref", "TEXT"),
    ("location_id", "INTEGER"), ("loc_building", "TEXT"), ("loc_section", "TEXT"), ("loc_position", "TEXT"),
    ("location_source", "TEXT"), ("gps_status", "TEXT"), ("gps_lat", "REAL"), ("gps_lon", "REAL"), ("gps_accuracy_m", "REAL"),
]
AUDIT_PHOTO_COLUMNS = [("sha256", "TEXT"), ("thumb_filename", "TEXT"), ("tracking_id", "TEXT"), ("byte_size", "INTEGER")]
UNID_COLUMNS = [
    ("description", "TEXT"), ("markings", "TEXT"), ("qty_unit", "TEXT"), ("qty_unknown", "INTEGER NOT NULL DEFAULT 0"),
    ("status_text", "TEXT"), ("client_submission_id", "TEXT"), ("client_time", "TEXT"), ("server_received_at", "TEXT"),
    ("location_id", "INTEGER"), ("loc_building", "TEXT"), ("loc_section", "TEXT"), ("loc_position", "TEXT"),
    ("location_source", "TEXT"), ("gps_status", "TEXT"), ("gps_lat", "REAL"), ("gps_lon", "REAL"), ("gps_accuracy_m", "REAL"),
    ("identification_state", "TEXT NOT NULL DEFAULT 'UNIDENTIFIED'"), ("resolved_at", "TEXT"), ("resolved_by", "TEXT"),
    ("counts_toward_wo", "INTEGER NOT NULL DEFAULT 1"),
]
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations(id TEXT PRIMARY KEY, applied_at TEXT NOT NULL, description TEXT);
CREATE TABLE IF NOT EXISTS factory_locations(
    id INTEGER PRIMARY KEY AUTOINCREMENT, building TEXT NOT NULL DEFAULT '', section TEXT NOT NULL DEFAULT '',
    position TEXT NOT NULL DEFAULT '', notes TEXT, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
    created_by TEXT, UNIQUE(building, section, position));
CREATE TABLE IF NOT EXISTS unidentified_photos(
    id INTEGER PRIMARY KEY AUTOINCREMENT, temp_id TEXT NOT NULL, filename TEXT NOT NULL, thumb_filename TEXT,
    original_name TEXT, content_type TEXT, sha256 TEXT, byte_size INTEGER, created_at TEXT NOT NULL,
    FOREIGN KEY(temp_id) REFERENCES unidentified_parts(temp_id));
CREATE TABLE IF NOT EXISTS reconciliation_history(
    id INTEGER PRIMARY KEY AUTOINCREMENT, temp_id TEXT NOT NULL, action TEXT NOT NULL, from_state TEXT, to_state TEXT,
    wo_id TEXT, counts_toward_wo INTEGER, user_name TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY(temp_id) REFERENCES unidentified_parts(temp_id));
CREATE INDEX IF NOT EXISTS idx_audits_wo_id ON mobile_audits(wo_id, id);
CREATE INDEX IF NOT EXISTS idx_audits_created ON mobile_audits(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_photos_audit ON mobile_audit_photos(audit_id);
CREATE INDEX IF NOT EXISTS idx_unid_state ON unidentified_parts(identification_state, created_at);
CREATE INDEX IF NOT EXISTS idx_unid_photos_temp ON unidentified_photos(temp_id);
CREATE INDEX IF NOT EXISTS idx_recon_temp ON reconciliation_history(temp_id, id);
CREATE TABLE IF NOT EXISTS record_edit_history(
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, record_id TEXT NOT NULL, field TEXT NOT NULL,
    old_value TEXT, new_value TEXT, user_name TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_edits_record ON record_edit_history(kind, record_id, id);
"""


# ----------------------------------------------------------------------------- helpers
def _now() -> str:
    return core.now_iso()


def _clip(value, n=200) -> str:
    return core.safe_text(value)[:n]


def _json(payload: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status)


def _err(msg: str, status: int = 400, code: str = "INVALID") -> JSONResponse:
    return _json({"ok": False, "error": msg, "code": code}, status)


def _user(request: Request):
    return core.require_login(request)


def _customer_allowed(user) -> bool:
    try:
        role=str(user["role"]).lower()
    except Exception:
        role="operator"
    return role in {"admin", "planning", "management"}


def _auth(request: Request, perm: str):
    """Return (user, error_response). Server-side authorization for every write."""
    user = _user(request)
    if not user:
        return None, _err("Session expired - please log in again", 401, "LOGIN_REQUIRED")
    if not core.can(user, perm):
        return user, _err("Your role is not allowed to do this", 403, "FORBIDDEN")
    return user, None


def _columns(con, table) -> set:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def _add_columns(con, table, specs):
    have = _columns(con, table)
    for name, ddl in specs:
        if name not in have:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


# ----------------------------------------------------------------------------- migration
def migrate() -> dict:
    """Idempotent additive migration. Backs the database up first if it already holds data."""
    con = core.db()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS schema_migrations(id TEXT PRIMARY KEY, applied_at TEXT NOT NULL, description TEXT)")
        if con.execute("SELECT 1 FROM schema_migrations WHERE id=?", (MIGRATION_ID,)).fetchone():
            return {"applied": False, "backup": None}
        backup = None
        has_data = any(con.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone() for t in ("work_orders", "mobile_audits", "events", "unidentified_parts"))
        if has_data:
            bdir = core.SHARED_ROOT / "BACKUPS"
            bdir.mkdir(parents=True, exist_ok=True)
            backup = bdir / f"sl_planning_pre_{MIGRATION_ID}_{core.bkk_now():%Y%m%d_%H%M%S}.db"
            dest = sqlite3.connect(backup)
            try:
                con.backup(dest)
            finally:
                dest.close()
        _add_columns(con, "mobile_audits", AUDIT_COLUMNS)
        _add_columns(con, "mobile_audit_photos", AUDIT_PHOTO_COLUMNS)
        _add_columns(con, "unidentified_parts", UNID_COLUMNS)
        con.executescript(SCHEMA_SQL)
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_audits_csid ON mobile_audits(client_submission_id) WHERE client_submission_id IS NOT NULL")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_unid_csid ON unidentified_parts(client_submission_id) WHERE client_submission_id IS NOT NULL")
        if not con.execute("SELECT 1 FROM factory_locations LIMIT 1").fetchone():
            # Sections only, taken from the application's own standard terminals. Buildings, racks and bins are
            # factory facts that must be configured by an administrator (Admin > Locations); none are invented here.
            for (section,) in con.execute("SELECT DISTINCT process_name FROM terminals WHERE process_name IS NOT NULL AND active=1 ORDER BY id"):
                con.execute("INSERT OR IGNORE INTO factory_locations(building,section,position,notes,created_at,created_by) VALUES('',?,'', 'Seeded from the standard PPC sections; add buildings/racks in Admin > Locations',?,'SYSTEM')", (section, _now()))
        con.execute("INSERT INTO schema_migrations(id,applied_at,description) VALUES(?,?,?)",
                    (MIGRATION_ID, _now(), "Shared audit record model: audit/unidentified columns, photos, locations, reconciliation history"))
        con.commit()
        return {"applied": True, "backup": str(backup) if backup else None}
    finally:
        con.close()


# ----------------------------------------------------------------------------- locations
def location_label(building, section, position) -> str:
    return " > ".join(p for p in (building, section, position) if p)


def list_locations() -> list[dict]:
    con = core.db()
    try:
        return [dict(r) | {"label": location_label(r["building"], r["section"], r["position"])}
                for r in con.execute("SELECT * FROM factory_locations WHERE active=1 ORDER BY building,section,position")]
    finally:
        con.close()


def _resolve_location(con, form):
    """Return (fields dict, error). Configured ids are looked up server-side; manual text is flagged as such."""
    lid = core.safe_text(form.get("location_id"))
    extra = _clip(form.get("location_notes"), 200)
    if lid:
        row = con.execute("SELECT * FROM factory_locations WHERE id=? AND active=1", (lid,)).fetchone() if lid.isdigit() else None
        if not row:
            return None, "Chosen location is not in the configured list"
        label = location_label(row["building"], row["section"], row["position"])
        return {"location_id": row["id"], "loc_building": row["building"], "loc_section": row["section"], "loc_position": row["position"],
                "location_source": "CONFIGURED", "physical_location": label + (f" ({extra})" if extra else "")}, None
    text = _clip(form.get("location_text"), 200)
    if text:
        return {"location_id": None, "loc_building": None, "loc_section": None, "loc_position": None,
                "location_source": "MANUAL", "physical_location": text}, None
    if core.safe_text(form.get("location_unknown")) == "1":
        return {"location_id": None, "loc_building": None, "loc_section": None, "loc_position": None,
                "location_source": "UNKNOWN", "physical_location": "UNKNOWN"}, None
    return None, "Choose the physical location, type it, or mark it unknown"


def _gps(form):
    status = core.safe_text(form.get("gps_status")).upper() or "NOT_REQUESTED"
    if status not in GPS_STATES:
        status = "UNAVAILABLE"
    lat = core.safe_float(form.get("gps_lat")); lon = core.safe_float(form.get("gps_lon")); acc = core.safe_float(form.get("gps_accuracy_m"))
    if status == "CAPTURED" and (lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180)):
        status, lat, lon, acc = "UNAVAILABLE", None, None, None
    if status != "CAPTURED":
        lat = lon = acc = None
    return {"gps_status": status, "gps_lat": lat, "gps_lon": lon, "gps_accuracy_m": acc}


def _client_time(form) -> str:
    raw = _clip(form.get("client_time"), 40)
    if raw:
        try:
            datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return raw
        except ValueError:
            pass
    return ""


# ----------------------------------------------------------------------------- photos
def _sniff(raw: bytes) -> Optional[str]:
    if raw[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    if raw[4:8] == b"ftyp" and raw[8:12] in (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"):
        return "heic"
    return None


def _write_durably(path: Path, raw: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "wb") as fh:
        fh.write(raw)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _make_thumb(raw: bytes, kind: str) -> Optional[bytes]:
    if kind == "heic":
        try:
            import qr_decode
            if not qr_decode.HEIF_AVAILABLE:
                return None
        except Exception:
            return None
    try:
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
        im.thumbnail((THUMB_PX, THUMB_PX))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=70, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


def _photo_dir(kind: str) -> Path:
    return core.MOBILE_AUDIT_DIR if kind == "audit" else core.PHOTO_ROOT / "UNIDENTIFIED_PARTS"


async def _read_photos(form):
    """Validate uploads. Returns (list of dict, error)."""
    files = [f for f in form.getlist("photos") if hasattr(f, "filename") and f.filename]
    if len(files) > MAX_PHOTOS:
        return None, f"At most {MAX_PHOTOS} photos per submission"
    out = []
    for f in files:
        raw = await f.read()
        if not raw:
            return None, f"Photo '{f.filename}' is empty"
        if len(raw) > core.MOBILE_AUDIT_MAX_PHOTO_BYTES:
            return None, f"Photo '{f.filename}' is larger than {core.MOBILE_AUDIT_MAX_PHOTO_BYTES // (1024 * 1024)} MB"
        kind = _sniff(raw)
        if not kind:
            return None, f"'{f.filename}' is not a JPG, PNG, WEBP or HEIC image"
        out.append({"raw": raw, "kind": kind, "original": Path(f.filename).name, "sha256": hashlib.sha256(raw).hexdigest()})
    return out, None


def _slug(text, n=40) -> str:
    s = re.sub(r"[^\w\-]+", "-", str(text or "").strip(), flags=re.UNICODE)
    s = re.sub(r"-{2,}", "-", s).strip("-._")
    return (s or "nloc")[:n]


def _photo_stem(tracking_id: str, location: str, when) -> str:
    """File name carries work order (or temp ID), location and date-time (owner decision OD-10)."""
    stamp = when.strftime("%Y%m%d-%H%M%S") if hasattr(when, "strftime") else re.sub(r"[^\d\-]", "", str(when))[:15]
    return f"{_slug(tracking_id, 40)}_{_slug(location, 36)}_{stamp}"


def _unique_name(base: Path, stem: str, ext: str) -> str:
    name = f"{stem}{ext}"
    n = 2
    while (base / name).exists():
        name = f"{stem}_{n}{ext}"
        n += 1
    return name


def _store_photos(photos, kind: str, stem: str):
    """Write files (and thumbnails) to disk; returns rows to insert. Raises on I/O failure."""
    base = _photo_dir(kind)
    written, rows = [], []
    try:
        for i, p in enumerate(photos, 1):
            piece = stem if len(photos) == 1 else f"{stem}_{i:02d}"
            name = _unique_name(base, piece, IMAGE_EXT[p["kind"]])
            _write_durably(base / name, p["raw"]); written.append(base / name)
            thumb_name = None
            tb = _make_thumb(p["raw"], p["kind"])
            if tb:
                thumb_name = _unique_name(base / "thumbs", Path(name).stem + "_t", ".jpg")
                _write_durably(base / "thumbs" / thumb_name, tb); written.append(base / "thumbs" / thumb_name)
            rows.append({"filename": name, "thumb": thumb_name, "original": p["original"], "type": p["kind"], "sha256": p["sha256"], "size": len(p["raw"])})
    except Exception:
        _unlink_all(written)
        raise
    return rows, written


def _unlink_all(paths):
    for p in paths:
        try:
            Path(p).unlink()
        except OSError:
            pass


# ----------------------------------------------------------------------------- submission
def _existing_submission(con, csid):
    row = con.execute("SELECT id, wo_id, tracking_id, server_received_at, created_at FROM mobile_audits WHERE client_submission_id=?", (csid,)).fetchone()
    if row:
        return {"kind": "WO_AUDIT", "audit_id": row["id"], "tracking_id": row["tracking_id"] or row["wo_id"], "wo_id": row["wo_id"],
                "server_received_at": row["server_received_at"] or row["created_at"]}
    row = con.execute("SELECT temp_id, server_received_at, created_at FROM unidentified_parts WHERE client_submission_id=?", (csid,)).fetchone()
    if row:
        return {"kind": "UNIDENTIFIED", "tracking_id": row["temp_id"], "temp_id": row["temp_id"], "server_received_at": row["server_received_at"] or row["created_at"]}
    return None


def _new_temp_id(con) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(20):
        tid = f"UNID-{core.bkk_now():%Y%m%d}-" + "".join(secrets.choice(alphabet) for _ in range(5))
        if not con.execute("SELECT 1 FROM unidentified_parts WHERE temp_id=?", (tid,)).fetchone():
            return tid
    raise RuntimeError("could not allocate a temporary tracking id")


def _validate_quantity(form):
    """Owner decision OD-9: no upper quantity limit. Non-numeric, infinite and negative values are still refused."""
    unknown = core.safe_text(form.get("qty_unknown")) == "1"
    qty = core.safe_float(form.get("verified_qty"))
    unit = _clip(form.get("qty_unit"), 16)
    if unknown:
        if qty is not None:
            return None, "Quantity and 'quantity unknown' were both given"
        return {"verified_qty": None, "qty_unknown": 1, "qty_unit": unit or None}, None
    if qty is None:
        return None, "Enter the counted quantity, or choose 'quantity unknown'"
    if qty != qty or qty in (float("inf"), float("-inf")):
        return None, "Quantity must be a finite number"
    if qty < 0:
        return None, "Quantity cannot be negative"
    if not unit:
        return None, "Choose the unit"
    return {"verified_qty": qty, "qty_unknown": 0, "qty_unit": unit}, None


async def api_audit(request: Request):
    user, bad = _auth(request, "mobile_capture")
    if bad:
        return bad
    form = await request.form()
    csid = _clip(form.get("client_submission_id"), 80)
    if not re.fullmatch(r"[A-Za-z0-9._-]{8,80}", csid):
        return _err("client_submission_id is required (8-80 safe characters)")
    mode = core.safe_text(form.get("mode")).upper() or "WO"
    if mode not in {"WO", "UNIDENTIFIED"}:
        return _err("Invalid mode")

    con = core.db()
    try:
        prior = _existing_submission(con, csid)
        if prior:
            return _json({"ok": True, "duplicate": True, **prior})

        qty, e = _validate_quantity(form)
        if e:
            return _err(e)
        loc, e = _resolve_location(con, form)
        if e and not (mode == "WO" and core.safe_text(form.get("status")).upper() == "NOT_FOUND"):
            return _err(e)
        loc = loc or {"location_id": None, "loc_building": None, "loc_section": None, "loc_position": None, "location_source": "NONE", "physical_location": ""}
        gps = _gps(form)
        status = core.safe_text(form.get("status")).upper() or ("UNKNOWN" if mode == "UNIDENTIFIED" else "OK")
        if status not in (UNIDENT_STATUSES if mode == "UNIDENTIFIED" else AUDIT_STATUSES):
            return _err("Invalid status")
        process = _clip(form.get("process"), 80) or ("UNKNOWN" if mode == "UNIDENTIFIED" else "")
        notes = _clip(form.get("notes"), 1000)
        client_time = _client_time(form)
        photos, e = await _read_photos(form)
        if e:
            return _err(e)

        if mode == "WO":
            wo_id = _clip(form.get("wo_id"), 80)
            wo = con.execute("SELECT wo_id FROM work_orders WHERE wo_id=?", (wo_id,)).fetchone()
            if not wo:
                return _err("Work Order not found - search again or use 'Unidentified / No work order'", 404, "WO_NOT_FOUND")
            kind = "audit"
        else:
            description = _clip(form.get("description"), 500)
            if not photos:
                return _err("A photograph of the part is required for an unidentified part")
            if not (description or _clip(form.get("markings"), 500)):
                return _err("Add a description or visible markings, or write 'none visible'")
            kind = "unid"

        written = []
        try:
            con.execute("BEGIN IMMEDIATE")
            prior = _existing_submission(con, csid)  # a concurrent retry may have won the race
            if prior:
                con.rollback()
                return _json({"ok": True, "duplicate": True, **prior})
            received = _now()
            if mode == "WO":
                cur = con.execute(
                    """INSERT INTO mobile_audits(wo_id,user_name,verified_qty,physical_status,physical_location,observed_process,notes,created_at,
                       tracking_id,client_submission_id,client_time,server_received_at,qty_unit,qty_unknown,batch_ref,location_id,loc_building,
                       loc_section,loc_position,location_source,gps_status,gps_lat,gps_lon,gps_accuracy_m)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (wo_id, user["username"], qty["verified_qty"], status, loc["physical_location"], process, notes, received,
                     wo_id, csid, client_time, received, qty["qty_unit"], qty["qty_unknown"], _clip(form.get("batch_ref"), 80),
                     loc["location_id"], loc["loc_building"], loc["loc_section"], loc["loc_position"], loc["location_source"],
                     gps["gps_status"], gps["gps_lat"], gps["gps_lon"], gps["gps_accuracy_m"]))
                audit_id = cur.lastrowid
                stored, written = _store_photos(photos, kind, _photo_stem(wo_id, loc["physical_location"], core.bkk_now()))
                for s in stored:
                    con.execute("INSERT INTO mobile_audit_photos(audit_id,filename,original_name,content_type,created_at,sha256,thumb_filename,tracking_id,byte_size) VALUES(?,?,?,?,?,?,?,?,?)",
                                (audit_id, s["filename"], s["original"], "image/" + s["type"], received, s["sha256"], s["thumb"], wo_id, s["size"]))
                result = {"kind": "WO_AUDIT", "audit_id": audit_id, "tracking_id": wo_id, "wo_id": wo_id}
            else:
                temp_id = _new_temp_id(con)
                con.execute(
                    """INSERT INTO unidentified_parts(temp_id,qty,process_name,location,issue_type,notes,reporter,created_at,description,markings,
                       qty_unit,qty_unknown,status_text,client_submission_id,client_time,server_received_at,location_id,loc_building,loc_section,
                       loc_position,location_source,gps_status,gps_lat,gps_lon,gps_accuracy_m,identification_state)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'UNIDENTIFIED')""",
                    (temp_id, qty["verified_qty"], process, loc["physical_location"], status, notes, user["username"], received,
                     description, _clip(form.get("markings"), 500), qty["qty_unit"], qty["qty_unknown"], status, csid, client_time, received,
                     loc["location_id"], loc["loc_building"], loc["loc_section"], loc["loc_position"], loc["location_source"],
                     gps["gps_status"], gps["gps_lat"], gps["gps_lon"], gps["gps_accuracy_m"]))
                stored, written = _store_photos(photos, kind, _photo_stem(temp_id, loc["physical_location"], core.bkk_now()))
                for s in stored:
                    con.execute("INSERT INTO unidentified_photos(temp_id,filename,thumb_filename,original_name,content_type,sha256,byte_size,created_at) VALUES(?,?,?,?,?,?,?,?)",
                                (temp_id, s["filename"], s["thumb"], s["original"], "image/" + s["type"], s["sha256"], s["size"], received))
                con.execute("INSERT INTO reconciliation_history(temp_id,action,from_state,to_state,user_name,reason,created_at) VALUES(?,?,?,?,?,?,?)",
                            (temp_id, "CREATED", None, "UNIDENTIFIED", user["username"], "Captured on mobile without work order/QR", received))
                result = {"kind": "UNIDENTIFIED", "tracking_id": temp_id, "temp_id": temp_id}
            con.commit()
        except sqlite3.IntegrityError:
            con.rollback(); _unlink_all(written)
            prior = _existing_submission(con, csid)
            if prior:
                return _json({"ok": True, "duplicate": True, **prior})
            raise
        except Exception:
            con.rollback(); _unlink_all(written)
            raise
        core.log_audit(user["username"], "PHYSICAL_AUDIT_V2" if mode == "WO" else "UNIDENTIFIED_PART", "TRACKING", result["tracking_id"],
                       f"status={status};qty={qty['verified_qty']};unknown={qty['qty_unknown']};location={loc['physical_location']};photos={len(photos)}")
        return _json({"ok": True, "duplicate": False, "server_received_at": received, "photos": len(photos), **result})
    finally:
        con.close()


EDITABLE_AUDIT = {"verified_qty": "verified_qty", "qty_unit": "qty_unit", "physical_status": "physical_status",
                  "physical_location": "physical_location", "observed_process": "observed_process", "notes": "notes"}
EDITABLE_UNID = {"qty": "qty", "qty_unit": "qty_unit", "status_text": "status_text", "location": "location",
                 "process_name": "process_name", "description": "description", "markings": "markings", "notes": "notes"}


def _ensure_edit_history(con):
    con.execute("""CREATE TABLE IF NOT EXISTS record_edit_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, record_id TEXT NOT NULL, field TEXT NOT NULL,
        old_value TEXT, new_value TEXT, user_name TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL)""")


def record_edit_history(con, kind: str, record_id: str, field: str, old, new, user: str, reason: str):
    _ensure_edit_history(con)
    con.execute("INSERT INTO record_edit_history(kind,record_id,field,old_value,new_value,user_name,reason,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (kind, str(record_id), field, None if old is None else str(old), None if new is None else str(new), user, reason, _now()))


async def api_edit(request: Request):
    """Submitted observations are immutable; add a new observation to correct one."""
    user, bad = _auth(request, "mobile_capture")
    if bad:
        return bad
    return _err("Submitted audit records are locked. Submit a new observation and explain the correction in Notes.", 409, "IMMUTABLE")
    body = await request.json()
    kind = core.safe_text(body.get("kind")).upper()
    reason = _clip(body.get("reason"), 500)
    if not reason:
        return _err("A reason is required so the change is traceable")
    fields = body.get("fields") or {}
    if not isinstance(fields, dict) or not fields:
        return _err("No fields to change")
    con = core.db()
    try:
        _ensure_edit_history(con)
        con.execute("BEGIN IMMEDIATE")
        changed = []
        if kind == "WO_AUDIT":
            rid = body.get("audit_id")
            row = con.execute("SELECT * FROM mobile_audits WHERE id=?", (rid,)).fetchone() if rid else None
            allowed = EDITABLE_AUDIT
        elif kind == "UNIDENTIFIED":
            rid = _clip(body.get("temp_id"), 80)
            row = con.execute("SELECT * FROM unidentified_parts WHERE temp_id=?", (rid,)).fetchone() if rid else None
            allowed = EDITABLE_UNID
        else:
            con.rollback()
            return _err("kind must be WO_AUDIT or UNIDENTIFIED")
        if not row:
            con.rollback()
            return _err("Record not found", 404, "NOT_FOUND")
        for key, col in allowed.items():
            if key not in fields:
                continue
            new = fields[key]
            old = row[col]
            if str(old) == str(new):
                continue
            if key in {"verified_qty", "qty"}:
                if new in (None, ""):
                    new = None
                else:
                    try:
                        new = float(new)
                    except (TypeError, ValueError):
                        con.rollback()
                        return _err("Quantity must be a finite number")
                    if new != new or new in (float("inf"), float("-inf")) or new < 0:
                        con.rollback()
                        return _err("Quantity must be a finite non-negative number")
            else:
                new = _clip(new, 1000) if new is not None else None
            if kind == "WO_AUDIT":
                con.execute(f"UPDATE mobile_audits SET {col}=? WHERE id=?", (new, rid))
            else:
                con.execute(f"UPDATE unidentified_parts SET {col}=? WHERE temp_id=?", (new, rid))
            record_edit_history(con, kind, rid, col, old, new, user["username"], reason)
            changed.append(col)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    core.log_audit(user["username"], "EDIT_AUDIT", kind, str(rid), f"fields={','.join(changed)};reason={reason}")
    return _json({"ok": True, "changed": changed, "kind": kind, "record_id": str(rid)})


# ----------------------------------------------------------------------------- lookup
def _parse_scan(value: str):
    raw = core.safe_text(value)[:2048]
    up = raw.upper()
    if up.startswith("SLTMP:"):
        return "TEMP", raw.split(":", 1)[1].strip()
    if up.startswith("SLWO:"):
        return "WO", raw.split(":", 1)[1].strip()
    try:
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2 and parts[-2] == "tmp":
                return "TEMP", parts[-1]
            if parts:
                return "ANY", parts[-1]
    except Exception:
        pass
    return "ANY", raw


def _wo_row(r) -> dict:
    return {"kind": "WO", "tracking_id": r["wo_id"], "wo_id": r["wo_id"], "title": r["production_code"] or r["wo_id"],
            "part": r["product_code"], "customer": r["customer_name"], "qty": r["qty"], "description": r["specification"]}


def find_candidates(value: str, limit: int = 10) -> list[dict]:
    """All records a scanned/typed code could mean. More than one means the caller must ask the operator."""
    kind, code = _parse_scan(value)
    if not code:
        return []
    key = core.norm_wo(code)
    m = re.match(r"^\s*([A-Za-z]{1,4}?)\s*(\d{3})\s*[-_ ]?\s*(\d{6})\s*$", code)
    if not m and key:
        m = re.match(r"^([A-Z]{1,4}?)(\d{3})(\d{6})$", key)
    canon = f"{m.group(1).upper()}{int(m.group(2)):03d}-{m.group(3)}" if m else ""
    con = core.db()
    try:
        out = []
        if kind in ("WO", "ANY"):
            rows = con.execute("SELECT wo_id,production_code,product_code,customer_name,qty,specification FROM work_orders WHERE wo_id=? OR production_code=? LIMIT ?", (code, code, limit)).fetchall()
            if not rows and canon:
                rows = con.execute("SELECT wo_id,production_code,product_code,customer_name,qty,specification FROM work_orders WHERE wo_id=? OR production_code=? LIMIT ?", (canon, canon, limit)).fetchall()
            if not rows and key:
                nwo = core.NORMALIZED_WO_SQL.format("wo_id"); npc = core.NORMALIZED_WO_SQL.format("production_code")
                rows = con.execute(f"SELECT wo_id,production_code,product_code,customer_name,qty,specification FROM work_orders WHERE {nwo}=? OR {npc}=? LIMIT ?", (key, key, limit)).fetchall()
            out += [_wo_row(r) for r in rows]
        if kind in ("TEMP", "ANY"):
            rows = con.execute("SELECT temp_id,description,markings,identification_state,resolved_wo_id FROM unidentified_parts WHERE temp_id=? OR UPPER(temp_id)=? LIMIT ?", (code, code.upper(), limit)).fetchall()
            out += [{"kind": "TEMP", "tracking_id": r["temp_id"], "wo_id": r["resolved_wo_id"], "title": r["temp_id"], "part": None,
                     "customer": None, "qty": None, "description": r["description"] or r["markings"], "state": r["identification_state"]} for r in rows]
        if not out and kind in ("WO", "ANY"):
            try:
                sys_root = Path(__file__).resolve().parents[2]
                if str(sys_root) not in __import__("sys").path:
                    __import__("sys").path.insert(0, str(sys_root))
                from suite.wo_lookup import candidate_rows
                fallback=candidate_rows(code, db_file=getattr(core, "DB_PATH", None), limit=limit)
                # A scan resolves an identity, never the first partial text suggestion.
                out += [r for r in fallback if core.norm_wo(r.get("wo_id"))==key or core.norm_wo(r.get("title"))==key]
            except Exception:
                pass
        return out
    finally:
        con.close()


def api_resolve(request: Request, value: str = "", method: str = "MANUAL"):
    user, bad = _auth(request, "dashboard")
    if bad:
        return bad
    try:
        core.kick_shared_plan_sync(wait_s=1.5)
    except Exception:
        pass
    value = core.safe_text(value)[:2048]
    if not value:
        return _err("Empty code")
    cands = find_candidates(value)
    result = "AMBIGUOUS" if len(cands) > 1 else "FOUND" if cands else "UNKNOWN_WO"
    method = method.upper() if method.upper() in {"LIVE_CAMERA", "MANUAL", "PHOTO"} else "MANUAL"
    con = core.db()
    try:
        recent = con.execute("SELECT 1 FROM qr_scan_log WHERE scanned_by=? AND payload=? AND result=? AND created_at>=?",
                             (user["username"], value, result, (core.bkk_now() - timedelta(seconds=3)).replace(microsecond=0).isoformat(sep=" "))).fetchone()
    finally:
        con.close()
    if not recent:
        core.record_qr_scan(user["username"], value, cands[0]["wo_id"] if len(cands) == 1 and cands[0]["wo_id"] else None, result, method)
    _role=str(user["role"] if "role" in user.keys() else "operator").lower()
    if _role not in {"admin", "planning", "management"}:
        for candidate in cands:
            candidate.pop("customer", None)
    return _json({"ok": bool(cands), "ambiguous": len(cands) > 1, "candidates": cands,
                  "error": None if cands else "Code read, but no matching work order or tracking ID. Search by hand or record an unidentified part."})


def api_search(request: Request, q: str = ""):
    user, bad = _auth(request, "dashboard")
    if bad:
        return bad
    try:
        core.kick_shared_plan_sync(wait_s=1.5)
    except Exception:
        pass
    q = core.safe_text(q)[:100]
    if len(q) < 1:
        return _json({"ok": True, "rows": []})
    exact = find_candidates(q)
    if exact:
        if not _customer_allowed(user):
            for row in exact: row.pop("customer", None)
        return _json({"ok": True, "rows": exact})
    key = core.norm_wo(q)
    like = "%" + q.replace("%", r"\%").replace("_", r"\_") + "%"
    con = core.db()
    try:
        nwo = core.NORMALIZED_WO_SQL.format("wo_id")
        npc = core.NORMALIZED_WO_SQL.format("production_code")
        seen, rows = set(), []
        if key:
            prefix_rows = con.execute(
                f"""SELECT wo_id,production_code,product_code,customer_name,qty,specification FROM work_orders
                    WHERE {nwo} LIKE ? OR {npc} LIKE ?
                    ORDER BY CASE WHEN {nwo}=? THEN 0 WHEN {nwo} LIKE ? THEN 1 ELSE 2 END, wo_id LIMIT 20""",
                (key + "%", key + "%", key, key + "%"),
            ).fetchall()
            for r in prefix_rows:
                if r["wo_id"] not in seen:
                    seen.add(r["wo_id"]); rows.append(_wo_row(r))
        if len(rows) < 20:
            if _customer_allowed(user):
                extra = con.execute("""SELECT wo_id,production_code,product_code,customer_name,qty,specification FROM work_orders
                    WHERE wo_id LIKE ? ESCAPE '\\' OR production_code LIKE ? ESCAPE '\\' OR product_code LIKE ? ESCAPE '\\' OR customer_name LIKE ? ESCAPE '\\'
                       OR order_no LIKE ? ESCAPE '\\' OR specification LIKE ? ESCAPE '\\' ORDER BY due_date IS NULL, due_date LIMIT 20""", (like,) * 6)
            else:
                extra = con.execute("""SELECT wo_id,production_code,product_code,customer_name,qty,specification FROM work_orders
                    WHERE wo_id LIKE ? ESCAPE '\\' OR production_code LIKE ? ESCAPE '\\' OR product_code LIKE ? ESCAPE '\\'
                       OR order_no LIKE ? ESCAPE '\\' OR specification LIKE ? ESCAPE '\\' ORDER BY due_date IS NULL, due_date LIMIT 20""", (like,) * 5)
            for r in extra:
                if r["wo_id"] not in seen:
                    seen.add(r["wo_id"]); rows.append(_wo_row(r))
        rows += [{"kind": "TEMP", "tracking_id": r["temp_id"], "wo_id": r["resolved_wo_id"], "title": r["temp_id"], "part": None, "customer": None, "qty": r["qty"],
                  "description": r["description"] or r["markings"], "state": r["identification_state"]}
                 for r in con.execute("SELECT temp_id,qty,description,markings,identification_state,resolved_wo_id FROM unidentified_parts WHERE temp_id LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR markings LIKE ? ESCAPE '\\' LIMIT 10", (like,) * 3)]
        if not _customer_allowed(user):
            for row in rows: row.pop("customer", None)
        return _json({"ok": True, "rows": rows})
    finally:
        con.close()


# ----------------------------------------------------------------------------- register
REGISTER_SQL = """
SELECT * FROM (
  SELECT COALESCE(a.tracking_id, a.wo_id) AS tracking_id, 'WO_AUDIT' AS kind, a.id AS obs_id, a.wo_id AS wo_id,
         COALESCE(w.product_code,'') AS part_code, COALESCE(w.specification,'') AS description, COALESCE(w.customer_name,'') AS customer,
         COALESCE(a.observed_process,'') AS section, a.physical_status AS status, a.verified_qty AS qty, CASE WHEN a.verified_qty IS NULL THEN 1 ELSE a.qty_unknown END AS qty_unknown,
         COALESCE(a.qty_unit,'') AS unit, COALESCE(a.physical_location,'') AS location,
         (SELECT COALESCE(p.thumb_filename, p.filename) FROM mobile_audit_photos p WHERE p.audit_id=a.id ORDER BY p.id LIMIT 1) AS photo,
         (SELECT p.thumb_filename IS NOT NULL FROM mobile_audit_photos p WHERE p.audit_id=a.id ORDER BY p.id LIMIT 1) AS photo_is_thumb,
         COALESCE(a.client_time, a.created_at) AS observed_at, a.created_at AS last_observed, a.user_name AS submitted_by,
         CASE WHEN a.verified_qty IS NULL THEN 'WO_ASSIGNED_QTY_UNKNOWN' ELSE 'WO_ASSIGNED' END AS ident_state,
         (SELECT COUNT(DISTINCT c.verified_qty) FROM mobile_audits c WHERE c.wo_id=a.wo_id AND COALESCE(c.physical_location,'')=COALESCE(a.physical_location,'')
             AND COALESCE(c.batch_ref,'')=COALESCE(a.batch_ref,'') AND c.verified_qty IS NOT NULL AND c.created_at >= datetime(a.created_at,'-24 hours')
             AND c.created_at <= a.created_at) > 1 AS conflict,
         1 AS counts
  FROM mobile_audits a JOIN work_orders w ON w.wo_id=a.wo_id
  WHERE a.id = (SELECT MAX(b.id) FROM mobile_audits b WHERE b.wo_id=a.wo_id AND COALESCE(b.physical_location,'')=COALESCE(a.physical_location,'')
                AND COALESCE(b.batch_ref,'')=COALESCE(a.batch_ref,''))
  UNION ALL
  SELECT u.temp_id, 'UNIDENTIFIED', u.id, u.resolved_wo_id, '', COALESCE(u.description,u.markings,''), COALESCE(w.customer_name,''),
         COALESCE(u.process_name,''), COALESCE(u.status_text,u.issue_type,'UNKNOWN'), u.qty, CASE WHEN u.qty IS NULL THEN 1 ELSE u.qty_unknown END,
         COALESCE(u.qty_unit,''), COALESCE(u.location,''),
         (SELECT COALESCE(p.thumb_filename, p.filename) FROM unidentified_photos p WHERE p.temp_id=u.temp_id ORDER BY p.id LIMIT 1),
         (SELECT p.thumb_filename IS NOT NULL FROM unidentified_photos p WHERE p.temp_id=u.temp_id ORDER BY p.id LIMIT 1),
         COALESCE(u.client_time, u.created_at), u.created_at, u.reporter,
         COALESCE(u.identification_state,'UNIDENTIFIED'), 0, CASE WHEN COALESCE(u.identification_state,'UNIDENTIFIED')='LINKED' THEN u.counts_toward_wo ELSE 0 END
  FROM unidentified_parts u LEFT JOIN work_orders w ON w.wo_id=u.resolved_wo_id
)
"""
FILTERS = {  # query-string name -> (SQL fragment, binder)
    "wo": ("wo_id LIKE ?", lambda v: v + "%"),
    "part": ("(part_code LIKE ? OR description LIKE ?)", lambda v: "%" + v + "%"),
    "customer": ("customer LIKE ?", lambda v: "%" + v + "%"),
    "section": ("section LIKE ?", lambda v: "%" + v + "%"),
    "status": ("status = ?", lambda v: v.upper()),
    "location": ("location LIKE ?", lambda v: "%" + v + "%"),
    "state": ("ident_state = ?", lambda v: v.upper()),
    "date_from": ("last_observed >= ?", lambda v: v),
    "date_to": ("last_observed < ?", lambda v: (datetime.fromisoformat(v) + timedelta(days=1)).strftime("%Y-%m-%d")),
}


def _like_escape(v: str) -> str:
    return v.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def register_query(params: dict, limit: int = 50, offset: int = 0, *, hide_customer: bool = False):
    where, args = [], []
    for name, (frag, bind) in FILTERS.items():
        if hide_customer and name == "customer":
            continue
        v = core.safe_text(params.get(name))
        if not v:
            continue
        if name.startswith("date_"):
            try:
                datetime.fromisoformat(v)
            except ValueError:
                continue
        elif "LIKE" in frag:
            v = _like_escape(v)
            frag = frag.replace("LIKE ?", "LIKE ? ESCAPE '\\'")
        n = frag.count("?")
        args += [bind(v)] * n
        where.append(frag)
    if core.safe_text(params.get("unidentified")) in {"1", "true", "on"}:
        where.append("kind='UNIDENTIFIED'")
    if core.safe_text(params.get("conflicts")) in {"1", "true", "on"}:
        where.append("conflict=1")
    q = core.safe_text(params.get("q"))
    if q:
        like = "%" + _like_escape(q) + "%"
        if hide_customer:
            where.append("(tracking_id LIKE ? ESCAPE '\\' OR wo_id LIKE ? ESCAPE '\\' OR part_code LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR location LIKE ? ESCAPE '\\')")
            args += [like] * 5
        else:
            where.append("(tracking_id LIKE ? ESCAPE '\\' OR wo_id LIKE ? ESCAPE '\\' OR part_code LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR customer LIKE ? ESCAPE '\\' OR location LIKE ? ESCAPE '\\')")
            args += [like] * 6
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    con = core.db()
    try:
        total = con.execute(f"SELECT COUNT(*) FROM ({REGISTER_SQL}){clause}", args).fetchone()[0]
        rows = [dict(r) for r in con.execute(f"{REGISTER_SQL}{clause} ORDER BY last_observed DESC, obs_id DESC LIMIT ? OFFSET ?", args + [limit, offset])]
    finally:
        con.close()
    for r in rows:
        r["photo_url"] = _photo_url(r["kind"], r["photo"], bool(r["photo_is_thumb"])) if r["photo"] else None
        if hide_customer:r.pop("customer",None)
    return rows, total


def _photo_url(kind: str, filename: str, thumb: bool) -> str:
    base = "audit" if kind == "WO_AUDIT" else "unid"
    return f"/media/part-photos/{base}/{'thumb/' if thumb else ''}{filename}"


def api_register(request: Request):
    user, bad = _auth(request, "dashboard")
    if bad:
        return bad
    qp = dict(request.query_params)
    limit = max(1, min(int(qp.get("limit", 50) or 50), 200)); offset = max(0, int(qp.get("offset", 0) or 0))
    rows, total = register_query(qp, limit, offset, hide_customer=not _customer_allowed(user))
    return _json({"ok": True, "total": total, "limit": limit, "offset": offset, "rows": rows})


EXPORT_COLS = ["tracking_id", "kind", "wo_id", "part_code", "description", "customer", "section", "status", "qty", "qty_unknown", "unit", "location",
               "observed_at", "last_observed", "submitted_by", "ident_state", "conflict", "photo_url"]


def register_export(request: Request, fmt: str):
    user, bad = _auth(request, "export")
    if bad:
        return bad
    hidden=not _customer_allowed(user)
    rows, total = register_query(dict(request.query_params), 50000, 0, hide_customer=hidden)
    export_cols=[c for c in EXPORT_COLS if not(hidden and c=="customer")]
    stamp = f"{core.bkk_now():%Y%m%d_%H%M%S}"
    if fmt == "csv":
        buf = io.StringIO(); w = csv.writer(buf); w.writerow(export_cols)
        for r in rows:
            w.writerow([("" if r.get(c) is None else r.get(c)) for c in export_cols])
        data = ("\ufeff" + buf.getvalue()).encode("utf-8")
        return StreamingResponse(io.BytesIO(data), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="SL_part_register_{stamp}.csv"'})
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "Part register"; ws.append(export_cols)
    for r in rows:
        ws.append([("" if r.get(c) is None else r.get(c)) for c in export_cols])
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    out = io.BytesIO(); wb.save(out)
    return StreamingResponse(io.BytesIO(out.getvalue()), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="SL_part_register_{stamp}.xlsx"'})


def part_detail(tracking_id: str) -> Optional[dict]:
    """Everything known about one tracking id: observations, photos, movements, reconciliation, conflicts, source evidence."""
    con = core.db()
    try:
        tid = core.safe_text(tracking_id)
        unid = con.execute("SELECT * FROM unidentified_parts WHERE temp_id=?", (tid,)).fetchone()
        wo = con.execute("SELECT * FROM work_orders WHERE wo_id=?", (tid,)).fetchone()
        if not unid and not wo:
            return None
        d: dict = {"tracking_id": tid, "kind": "UNIDENTIFIED" if unid else "WO", "wo": dict(wo) if wo else None, "unidentified": dict(unid) if unid else None}
        if unid:
            d["photos"] = [dict(p) | {"url": f"/media/part-photos/unid/{p['filename']}", "thumb_url": f"/media/part-photos/unid/thumb/{p['thumb_filename']}" if p["thumb_filename"] else f"/media/part-photos/unid/{p['filename']}"}
                           for p in con.execute("SELECT * FROM unidentified_photos WHERE temp_id=? ORDER BY id", (tid,))]
            d["reconciliation"] = [dict(r) for r in con.execute("SELECT * FROM reconciliation_history WHERE temp_id=? ORDER BY id", (tid,))]
            d["observations"] = []
            linked = unid["resolved_wo_id"]
            d["linked_wo"] = linked
            if linked:
                w = con.execute("SELECT * FROM work_orders WHERE wo_id=?", (linked,)).fetchone()
                d["wo"] = dict(w) if w else None
        else:
            obs = [dict(r) for r in con.execute("SELECT * FROM mobile_audits WHERE wo_id=? ORDER BY id DESC LIMIT 200", (tid,))]
            for o in obs:
                o["photos"] = [dict(p) | {"url": f"/media/part-photos/audit/{p['filename']}", "thumb_url": f"/media/part-photos/audit/thumb/{p['thumb_filename']}" if p["thumb_filename"] else f"/media/part-photos/audit/{p['filename']}"}
                               for p in con.execute("SELECT * FROM mobile_audit_photos WHERE audit_id=? ORDER BY id", (o["id"],))]
            d["observations"] = obs
            d["photos"] = [p for o in obs for p in o["photos"]]
            d["movements"] = [dict(r) for r in con.execute("SELECT * FROM events WHERE wo_id=? ORDER BY id DESC LIMIT 100", (tid,))]
            d["linked_unidentified"] = [dict(r) for r in con.execute("SELECT temp_id,description,qty,qty_unit,qty_unknown,location,counts_toward_wo,resolved_at,resolved_by FROM unidentified_parts WHERE resolved_wo_id=? AND identification_state='LINKED'", (tid,))]
            d["conflicts"] = _conflicts(obs)
            d["observed_total"], d["observed_total_note"] = _observed_total(con, tid)
            d["source"] = {"source_file": wo["source_file"], "plan_source_row": wo["plan_source_row"], "imported_at": wo["imported_at"],
                           "upload": dict(u) if (u := con.execute("SELECT filename,sha256,uploaded_by,uploaded_at FROM uploads WHERE filename=? ORDER BY id DESC LIMIT 1", (wo["source_file"],)).fetchone()) else None}
            d["reconciliation"] = [dict(r) for r in con.execute("SELECT * FROM reconciliation_history WHERE wo_id=? ORDER BY id", (tid,))]
        _ensure_edit_history(con)
        d["edits"] = [dict(r) for r in con.execute("SELECT * FROM record_edit_history WHERE record_id IN (?,?) ORDER BY id", (tid, str((d.get("unidentified") or {}).get("id") or "")))]
        if d.get("observations"):
            ids = [str(o["id"]) for o in d["observations"]]
            extra = [dict(r) for r in con.execute(f"SELECT * FROM record_edit_history WHERE kind='WO_AUDIT' AND record_id IN ({','.join('?'*len(ids))}) ORDER BY id", ids)] if ids else []
            d["edits"] = extra + d["edits"]
        return d
    finally:
        con.close()


def _conflicts(obs: list[dict]) -> list[dict]:
    """Same WO + location + batch, observed within 24 h of each other, with different non-null quantities."""
    groups: dict = {}
    for o in obs:
        groups.setdefault((o["physical_location"] or "", o.get("batch_ref") or ""), []).append(o)
    out = []
    for (loc, batch), items in groups.items():
        items = sorted(items, key=lambda x: x["created_at"])
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if a["verified_qty"] is None or b["verified_qty"] is None or a["verified_qty"] == b["verified_qty"]:
                    continue
                try:
                    gap = datetime.fromisoformat(b["created_at"]) - datetime.fromisoformat(a["created_at"])
                except ValueError:
                    continue
                if gap <= timedelta(hours=24):
                    out.append({"location": loc, "batch": batch, "first": a["id"], "second": b["id"], "first_qty": a["verified_qty"], "second_qty": b["verified_qty"],
                                "first_by": a["user_name"], "second_by": b["user_name"], "first_at": a["created_at"], "second_at": b["created_at"]})
    return out


def _observed_total(con, wo_id):
    """Latest observation per location/batch, plus linked unidentified lines flagged to count. Never added to stock or production."""
    rows = con.execute("""SELECT a.physical_location, a.verified_qty, a.qty_unknown FROM mobile_audits a WHERE a.wo_id=? AND a.id=(SELECT MAX(b.id) FROM mobile_audits b
        WHERE b.wo_id=a.wo_id AND COALESCE(b.physical_location,'')=COALESCE(a.physical_location,'') AND COALESCE(b.batch_ref,'')=COALESCE(a.batch_ref,''))""", (wo_id,)).fetchall()
    total = sum(r["verified_qty"] for r in rows if r["verified_qty"] is not None)
    unknown = sum(1 for r in rows if r["qty_unknown"])
    linked = con.execute("SELECT qty, qty_unknown FROM unidentified_parts WHERE resolved_wo_id=? AND identification_state='LINKED' AND counts_toward_wo=1", (wo_id,)).fetchall()
    total += sum(r["qty"] for r in linked if r["qty"] is not None)
    unknown += sum(1 for r in linked if r["qty"] is None)
    note = f"{len(rows)} location line(s) + {len(linked)} linked unidentified part(s); {unknown} line(s) with unknown quantity are not counted. Physical observation only - not stock, not production."
    return total, note


def api_part(request: Request, tracking_id: str):
    user, bad = _auth(request, "dashboard")
    if bad:
        return bad
    d = part_detail(tracking_id)
    return _json({"ok": True, **d}) if d else _err("Not found", 404, "NOT_FOUND")


# ----------------------------------------------------------------------------- reconciliation
async def api_link(request: Request, temp_id: str):
    user, bad = _auth(request, "link_part")
    if bad:
        return bad
    body = await request.json()
    wo_id = _clip(body.get("wo_id"), 80); reason = _clip(body.get("reason"), 500)
    counts = 1 if body.get("counts_toward_wo", True) else 0
    if not wo_id or not reason:
        return _err("Work order and a reason are required")
    con = core.db()
    try:
        con.execute("BEGIN IMMEDIATE")
        u = con.execute("SELECT * FROM unidentified_parts WHERE temp_id=?", (temp_id,)).fetchone()
        if not u:
            con.rollback(); return _err("Unknown temporary ID", 404, "NOT_FOUND")
        if not con.execute("SELECT 1 FROM work_orders WHERE wo_id=?", (wo_id,)).fetchone():
            con.rollback(); return _err("Work Order not found", 404, "WO_NOT_FOUND")
        if (u["identification_state"] or "UNIDENTIFIED") == "LINKED":
            con.rollback()
            same = u["resolved_wo_id"] == wo_id
            return _json({"ok": same, "duplicate": same, "error": None if same else f"Already linked to {u['resolved_wo_id']}; unlink first", "code": "ALREADY_LINKED"}, 200 if same else 409)
        now = _now()
        con.execute("UPDATE unidentified_parts SET resolved_wo_id=?, identification_state='LINKED', resolved_at=?, resolved_by=?, counts_toward_wo=? WHERE temp_id=?", (wo_id, now, user["username"], counts, temp_id))
        con.execute("INSERT INTO reconciliation_history(temp_id,action,from_state,to_state,wo_id,counts_toward_wo,user_name,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (temp_id, "LINKED", "UNIDENTIFIED", "LINKED", wo_id, counts, user["username"], reason, now))
        con.commit()
    except Exception:
        con.rollback(); raise
    finally:
        con.close()
    core.log_audit(user["username"], "LINK_UNIDENTIFIED", "TRACKING", temp_id, f"wo={wo_id};counts={counts}")
    return _json({"ok": True, "duplicate": False, "temp_id": temp_id, "wo_id": wo_id, "counts_toward_wo": counts})


async def api_unlink(request: Request, temp_id: str):
    user, bad = _auth(request, "link_part")
    if bad:
        return bad
    body = await request.json(); reason = _clip(body.get("reason"), 500)
    if not reason:
        return _err("A reason is required")
    con = core.db()
    try:
        con.execute("BEGIN IMMEDIATE")
        u = con.execute("SELECT * FROM unidentified_parts WHERE temp_id=?", (temp_id,)).fetchone()
        if not u:
            con.rollback(); return _err("Unknown temporary ID", 404, "NOT_FOUND")
        if (u["identification_state"] or "UNIDENTIFIED") != "LINKED":
            con.rollback(); return _err("Not linked", 409, "NOT_LINKED")
        now = _now()
        con.execute("UPDATE unidentified_parts SET resolved_wo_id=NULL, identification_state='UNIDENTIFIED', resolved_at=NULL, resolved_by=NULL, counts_toward_wo=1 WHERE temp_id=?", (temp_id,))
        con.execute("INSERT INTO reconciliation_history(temp_id,action,from_state,to_state,wo_id,user_name,reason,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (temp_id, "UNLINKED", "LINKED", "UNIDENTIFIED", u["resolved_wo_id"], user["username"], reason, now))
        con.commit()
    except Exception:
        con.rollback(); raise
    finally:
        con.close()
    core.log_audit(user["username"], "UNLINK_UNIDENTIFIED", "TRACKING", temp_id, reason)
    return _json({"ok": True, "temp_id": temp_id})


# ----------------------------------------------------------------------------- pages
def _need_login(request: Request, next_url: str):
    return None if _user(request) else RedirectResponse(f"/login?next={next_url}", 303)


def _html(request, template, **ctx):
    return HTMLResponse(core.render(request, template, **ctx))


def recent_submissions(username: str, limit: int = 30) -> list[dict]:
    con = core.db()
    try:
        rows = [dict(r) for r in con.execute("""SELECT 'WO_AUDIT' kind, COALESCE(tracking_id,wo_id) tracking_id, physical_status status, verified_qty qty, qty_unknown, qty_unit unit,
              physical_location location, COALESCE(server_received_at,created_at) received FROM mobile_audits WHERE user_name=? ORDER BY id DESC LIMIT ?""", (username, limit))]
        rows += [dict(r) for r in con.execute("""SELECT 'UNIDENTIFIED' kind, temp_id tracking_id, COALESCE(status_text,issue_type) status, qty, qty_unknown, qty_unit unit,
              location, COALESCE(server_received_at,created_at) received FROM unidentified_parts WHERE reporter=? ORDER BY id DESC LIMIT ?""", (username, limit))]
    finally:
        con.close()
    return sorted(rows, key=lambda r: r["received"] or "", reverse=True)[:limit]


def _wo_card(wo_id: str):
    snap = core.get_current_snapshot(wo_id)
    if not snap:
        return None
    con = core.db()
    try:
        last = con.execute("SELECT physical_location, observed_process, verified_qty, qty_unit, created_at, user_name, location_id FROM mobile_audits WHERE wo_id=? ORDER BY id DESC LIMIT 3", (wo_id,)).fetchall()
    finally:
        con.close()
    return {"snap": snap, "recent": [dict(r) for r in last]}


# Owner decision OD-8 (2026-10-04): every signed-in role may record, correct and link; every write stores user, time and reason.
# The anonymous default on the hub stays read-only because those edits could not be traced.
PERMISSION_DERIVATION = {
    "mobile_capture": {"all", "audit", "scan", "dashboard", "export"},
    "link_part": {"all", "planning", "supervisor", "dashboard", "export", "scan"},
}


def install(core_module):
    global core
    core = core_module
    info = migrate()
    app = core.app

    for role, meta in core.ROLES.items():
        for perm, derived_from in PERMISSION_DERIVATION.items():
            if meta["permissions"] & derived_from:
                meta["permissions"].add(perm)
    con = core.db()
    try:
        _ensure_edit_history(con)
        con.commit()
    finally:
        con.close()

    app.add_api_route("/api/v2/audit", api_audit, methods=["POST"])
    app.add_api_route("/api/v2/edit", api_edit, methods=["POST"])
    app.add_api_route("/api/v2/resolve", api_resolve, methods=["GET"])
    app.add_api_route("/api/v2/search", api_search, methods=["GET"])
    app.add_api_route("/api/register", api_register, methods=["GET"])
    app.add_api_route("/api/register/{tracking_id}", api_part, methods=["GET"])
    app.add_api_route("/api/v2/unidentified/{temp_id}/link", api_link, methods=["POST"])
    app.add_api_route("/api/v2/unidentified/{temp_id}/unlink", api_unlink, methods=["POST"])

    @app.get("/api/v2/locations")
    def locations_api(request: Request):
        user, bad = _auth(request, "dashboard")
        return bad or _json({"ok": True, "units": UNITS, "locations": list_locations()})

    @app.get("/api/v2/submissions")
    def submissions_api(request: Request):
        user, bad = _auth(request, "dashboard")
        return bad or _json({"ok": True, "rows": recent_submissions(user["username"])})

    @app.get("/media/part-photos/{kind}/{filename}")
    def photo_media(request: Request, kind: str, filename: str):
        if not _user(request):
            return _err("Login required", 401, "LOGIN_REQUIRED")
        if kind not in {"audit", "unid"}:
            return _err("Not found", 404)
        path = _photo_dir("audit" if kind == "audit" else "unid") / Path(filename).name
        return FileResponse(path) if path.is_file() else _err("Photo not found", 404)

    @app.get("/media/part-photos/{kind}/thumb/{filename}")
    def thumb_media(request: Request, kind: str, filename: str):
        if not _user(request):
            return _err("Login required", 401, "LOGIN_REQUIRED")
        if kind not in {"audit", "unid"}:
            return _err("Not found", 404)
        path = _photo_dir("audit" if kind == "audit" else "unid") / "thumbs" / Path(filename).name
        return FileResponse(path) if path.is_file() else _err("Photo not found", 404)

    # ---- mobile pages (operator workflows only)
    @app.get("/mobile/find", response_class=HTMLResponse)
    def mobile_find(request: Request, q: str = ""):
        if (r := _need_login(request, "/mobile/find")):
            return r
        rows = json.loads(api_search(request, q).body)["rows"] if len(q.strip()) >= 2 else []
        return _html(request, "mobile_find.html", q=q, rows=rows)

    @app.get("/mobile/confirm/{tracking_id}", response_class=HTMLResponse)
    def mobile_confirm(request: Request, tracking_id: str):
        if (r := _need_login(request, f"/mobile/confirm/{tracking_id}")):
            return r
        d = part_detail(tracking_id)
        if not d:
            return HTMLResponse("Not found", status_code=404)
        card = _wo_card(tracking_id) if d["kind"] == "WO" else None
        return _html(request, "mobile_confirm.html", d=d, card=card, can_capture=core.can(_user(request), "mobile_capture"))

    @app.get("/mobile/audit/{wo_id}", response_class=HTMLResponse)
    def mobile_audit(request: Request, wo_id: str):
        if (r := _need_login(request, f"/mobile/audit/{wo_id}")):
            return r
        card = _wo_card(wo_id)
        if not card:
            return HTMLResponse("Work Order not found", status_code=404)
        return _html(request, "mobile_audit_form.html", mode="WO", card=card, wo_id=wo_id, units=UNITS, statuses=AUDIT_STATUSES, locations=list_locations(),
                     can_capture=core.can(_user(request), "mobile_capture"))

    @app.get("/mobile/unidentified", response_class=HTMLResponse)
    def mobile_unidentified(request: Request):
        if (r := _need_login(request, "/mobile/unidentified")):
            return r
        return _html(request, "mobile_audit_form.html", mode="UNIDENTIFIED", card=None, wo_id="", units=UNITS, statuses=UNIDENT_STATUSES, locations=list_locations(),
                     can_capture=core.can(_user(request), "mobile_capture"))

    @app.get("/mobile/submissions", response_class=HTMLResponse)
    def mobile_submissions(request: Request):
        if (r := _need_login(request, "/mobile/submissions")):
            return r
        return _html(request, "mobile_submissions.html", rows=recent_submissions(_user(request)["username"]))

    @app.get("/mobile/report", response_class=HTMLResponse)
    def mobile_report(request: Request):
        if (r := _need_login(request, "/mobile/report")):
            return r
        import pandas as pd
        try:
            core.kick_shared_plan_sync()
        except Exception:
            pass
        sys_root = Path(__file__).resolve().parents[2]
        if str(sys_root) not in __import__("sys").path:
            __import__("sys").path.insert(0, str(sys_root))
        daily_root = sys_root / "apps" / "daily"
        from suite.audit_report import analyze, load_latest_audits, load_open_wip_by_process, load_production_wip_snapshot
        dbp = Path(os.environ.get("SL_DB_PATH", getattr(core, "DB", "")))
        audits = load_latest_audits(dbp)
        report = analyze(audits)
        production_wip, production_wip_errors = load_production_wip_snapshot(daily_root)
        def _rows(df):
            return [] if df is None or df.empty else df.to_dict("records")
        payload = {k: _rows(v) for k, v in report.items()}
        # Section audit counts use latest audit per WO. Quantities are summarized
        # by their recorded unit so pcs, kg, etc. are never added together.
        audit_sections = []
        if audits is not None and not audits.empty:
            _a = audits.copy()
            _a["_section"] = _a.get("observed_process", pd.Series("", index=_a.index)).fillna("").astype(str).str.strip().replace({"": "Not recorded"})
            _a["_qty"] = pd.to_numeric(_a.get("verified_qty"), errors="coerce")
            _a["_unit"] = _a.get("qty_unit", pd.Series("pcs", index=_a.index)).fillna("pcs").astype(str).str.strip().replace({"": "pcs"})
            _a["_unknown"] = pd.to_numeric(_a.get("qty_unknown", pd.Series(0, index=_a.index)), errors="coerce").fillna(0).astype(bool) | _a["_qty"].isna()
            for sec, g in _a.groupby("_section", dropna=False):
                unit_totals = g.loc[g["_qty"].notna()].groupby("_unit")["_qty"].sum()
                qty_text = "; ".join(f"{q:,.0f} {unit}" for unit, q in unit_totals.items()) or "—"
                audit_sections.append({"Section": str(sec), "Audited WOs": int(g["wo_id"].nunique()), "Quantity by unit": qty_text,
                                       "Unknown quantity": int(g["_unknown"].sum())})
            audit_sections.sort(key=lambda r: (-r["Audited WOs"], r["Section"]))
        payload["audit_section_summary"] = audit_sections
        payload["open_wip_by_process"] = _rows(load_open_wip_by_process(dbp))
        payload["basis"] = "Plan quantity less largest reported production completion, grouped at last scanned process. This is an order-balance indicator, not a physical WIP count."
        if not production_wip.empty:
            production_wip["Open WIP WO (Total − Closed)"]=pd.to_numeric(production_wip["Total WO"],errors="coerce")-pd.to_numeric(production_wip["Closed WO"],errors="coerce")
            production_wip["WIP WOs (source open)"]=pd.to_numeric(production_wip.get("WIP WOs (source open)",production_wip["Open WO"]),errors="coerce")
            production_wip["Summary check issue"]=production_wip.get("Summary variance / check",pd.Series("",index=production_wip.index)).ne("Summary matches detail") | production_wip.get("Section title mismatch",pd.Series(False,index=production_wip.index)).fillna(False)
            section = production_wip.groupby("Section", as_index=False).agg(**{"Open WIP t": ("Open t", "sum"), "Open WO records": ("WIP WOs (source open)", "sum"), "Data-check rows": ("Summary check issue", "sum")})
            category = production_wip.groupby("Category", as_index=False).agg(**{"Open WIP t": ("Open t", "sum"), "Open WO records": ("WIP WOs (source open)", "sum")})
            payload["production_wip_section"] = _rows(section.sort_values("Open WIP t", ascending=False))
            payload["production_wip_category"] = _rows(category.sort_values("Open WIP t", ascending=False))
            payload["production_wip_sources"] = _rows(production_wip[[c for c in ["Section", "Category", "Original filename", "Uploaded at"] if c in production_wip]].drop_duplicates())
            _total_t = pd.to_numeric(production_wip["Open t"], errors="coerce").sum(min_count=1)
            _total_wo = pd.to_numeric(production_wip["WIP WOs (source open)"], errors="coerce").sum(min_count=1)
            payload["production_wip_total_t"] = float(_total_t) if pd.notna(_total_t) else 0.0
            payload["production_wip_open_wo_records"] = float(_total_wo) if pd.notna(_total_wo) else 0.0
            payload["production_wip_data_checks"] = int((production_wip["Summary check issue"] | pd.to_numeric(production_wip["WO Balance Error"], errors="coerce").fillna(0).ne(0)).sum())
            _wip_max = pd.to_numeric(production_wip["Open t"], errors="coerce").max()
            payload["production_wip_t_max"] = float(_wip_max) if pd.notna(_wip_max) else 0.0
        else:
            payload["production_wip_section"] = []
            payload["production_wip_category"] = []
            payload["production_wip_sources"] = []
            payload["production_wip_t_max"] = 0
            payload["production_wip_total_t"] = 0
            payload["production_wip_open_wo_records"] = 0
            payload["production_wip_data_checks"] = 0
        payload["production_wip_errors"] = production_wip_errors or []
        payload["summary"] = payload.get("summary") or [{"Audited WOs": 0, "Locations": 0, "Statuses": 0, "Categories": 0}]
        latest_rows = _rows(audits.head(80) if not audits.empty else audits)
        for row in latest_rows:
            _photo_name = Path(str(row.get("photo_filename") or "")).name
            row["photo_url"] = f"/media/mobile-audits/{_photo_name}" if _photo_name else ""
        return _html(request, "mobile_report.html", report=payload, audits=latest_rows)

    @app.get("/mobile/part/{tracking_id}", response_class=HTMLResponse)
    def mobile_part(request: Request, tracking_id: str):
        if (r := _need_login(request, f"/mobile/part/{tracking_id}")):
            return r
        d = part_detail(tracking_id)
        return _html(request, "part_detail.html", d=d, compact=True, can_link=False) if d else HTMLResponse("Not found", status_code=404)

    # ---- desktop pages
    @app.get("/register", response_class=HTMLResponse)
    def register_page(request: Request):
        if (r := _need_login(request, "/register")):
            return r
        qp = dict(request.query_params)
        limit = 50; page = max(1, int(qp.get("page", 1) or 1))
        show_customer=_customer_allowed(_user(request))
        rows, total = register_query(qp, limit, (page - 1) * limit, hide_customer=not show_customer)
        keep = {k: v for k, v in qp.items() if k != "page" and v}
        from urllib.parse import urlencode
        return _html(request, "part_register.html", rows=rows, total=total, page=page, pages=max(1, -(-total // limit)), qp=qp, qs=urlencode(keep), show_customer=show_customer)

    @app.get("/register/export.csv")
    def register_csv(request: Request):
        return register_export(request, "csv")

    @app.get("/register/export.xlsx")
    def register_xlsx(request: Request):
        return register_export(request, "xlsx")

    @app.get("/register/{tracking_id}", response_class=HTMLResponse)
    def register_part(request: Request, tracking_id: str):
        if (r := _need_login(request, f"/register/{tracking_id}")):
            return r
        d = part_detail(tracking_id)
        return _html(request, "part_detail.html", d=d, compact=False, can_link=core.can(_user(request), "link_part")) if d else HTMLResponse("Not found", status_code=404)

    @app.get("/admin/locations", response_class=HTMLResponse)
    def admin_locations(request: Request):
        user = _user(request)
        if not user or not core.can(user, "all"):
            return RedirectResponse("/login?next=/admin/locations", 303)
        return _html(request, "location_admin.html", locations=list_locations())

    @app.post("/admin/locations")
    async def admin_locations_post(request: Request):
        user, bad = _auth(request, "all")
        if bad:
            return bad
        form = await request.form()
        building = _clip(form.get("building"), 80); section = _clip(form.get("section"), 80); position = _clip(form.get("position"), 80)
        if not (building or section or position):
            return _err("Enter at least a building, section or position")
        con = core.db()
        try:
            con.execute("INSERT OR IGNORE INTO factory_locations(building,section,position,notes,created_at,created_by) VALUES(?,?,?,?,?,?)",
                        (building, section, position, _clip(form.get("notes"), 200), _now(), user["username"]))
            con.commit()
        finally:
            con.close()
        return RedirectResponse("/admin/locations", 303)

    # ---- labels for temporary tracking IDs and selected WOs
    @app.get("/qr/tracking/{tracking_id}")
    def qr_tracking(request: Request, tracking_id: str):
        if not _user(request):
            return _err("Login required", 401, "LOGIN_REQUIRED")
        con = core.db()
        try:
            ok = con.execute("SELECT 1 FROM unidentified_parts WHERE temp_id=?", (tracking_id,)).fetchone()
        finally:
            con.close()
        if not ok:
            return _err("Unknown temporary ID", 404, "NOT_FOUND")
        return FileResponse(_qr_png(f"SLTMP:{tracking_id}", tracking_id), media_type="image/png")

    @app.get("/labels/print", response_class=HTMLResponse)
    def labels_print(request: Request):
        if (r := _need_login(request, "/labels/print")):
            return r
        ids = [core.safe_text(i) for i in request.query_params.getlist("id")][:200]
        con = core.db(); labels = []
        try:
            for i in ids:
                w = con.execute("SELECT wo_id,production_code,product_code,customer_name,qty,specification FROM work_orders WHERE wo_id=?", (i,)).fetchone()
                if w:
                    labels.append({"id": w["wo_id"], "title": w["production_code"] or w["wo_id"], "lines": [w["product_code"], w["specification"], w["customer_name"], f"Qty {w['qty']:g}" if w["qty"] is not None else ""],
                                   "payload": f"SLWO:{w['wo_id']}", "img": f"/qr/work-order/{w['wo_id']}"})
                    continue
                u = con.execute("SELECT temp_id,description,markings,location FROM unidentified_parts WHERE temp_id=?", (i,)).fetchone()
                if u:
                    labels.append({"id": u["temp_id"], "title": u["temp_id"], "lines": ["TEMPORARY - NOT A WORK ORDER", u["description"], u["markings"], u["location"]],
                                   "payload": f"SLTMP:{u['temp_id']}", "img": f"/qr/tracking/{u['temp_id']}"})
        finally:
            con.close()
        return _html(request, "label_print.html", labels=labels)

    return info


def _qr_png(payload: str, ident: str) -> Path:
    import qrcode
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", ident)[:80]
    out = core.QR_DIR / f"{safe}_{hashlib.sha1(payload.encode()).hexdigest()[:16]}.png"
    if not out.exists():
        _make_qr_png(payload).save(out)
    return out
