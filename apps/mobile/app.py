from __future__ import annotations

import csv
import json
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import socket
import sys
import threading
import time
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import qrcode
from fastapi import FastAPI, File, Form, Request, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from openpyxl import load_workbook, Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from starlette.middleware.sessions import SessionMiddleware

BASE = Path(__file__).resolve().parent
PROGRAM_ROOT = BASE.parent.parent
if str(PROGRAM_ROOT) not in sys.path:
    sys.path.insert(0, str(PROGRAM_ROOT))
DATA = BASE / "data"
UPLOADS = BASE / "uploads"
QR_DIR = BASE / "qr"
SHARED_ROOT = Path(os.environ.get("SL_SHARED_ROOT", str(PROGRAM_ROOT / "CENTRAL_DATA"))).resolve()
SHARED_DATA = Path(os.environ.get("SL_DB_PATH", str(SHARED_ROOT / "DATABASE" / "sl_planning.db"))).resolve().parent
SHARED_DATA.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("SL_DB_PATH", str(SHARED_ROOT / "DATABASE" / "sl_planning.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
from suite.qr_png import make as _make_qr_png
from suite.storage_migration import migrate_legacy_database, default_legacy_paths, restore_missing_photo_files, default_legacy_photo_roots
LEGACY_DB_RECOVERY = migrate_legacy_database(DB_PATH, default_legacy_paths(PROGRAM_ROOT))
DATA.mkdir(exist_ok=True)
UPLOADS.mkdir(exist_ok=True)
QR_DIR.mkdir(exist_ok=True)

APP_SECRET = os.environ.get("SL_APP_SECRET", "change-this-secret-in-production")
UNCONFIRMED_HOURS = float(os.environ.get("SL_UNCONFIRMED_HOURS", "8"))
DEFAULT_PORT = int(os.environ.get("SL_PORT", "8000"))
MOBILE_AUDIT_MAX_PHOTO_BYTES = int(os.environ.get("SL_MAX_AUDIT_PHOTO_MB", "8")) * 1024 * 1024
NORMALIZED_WO_SQL="REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER({}),'-',''),' ',''),'/',''),'.',''),'_','')"
PHOTO_ROOT = Path(os.environ.get("SL_PHOTO_ROOT", str(SHARED_ROOT / "PHOTOS"))).resolve()
MOBILE_AUDIT_DIR = PHOTO_ROOT / "MOBILE_AUDITS"
MOBILE_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
PHOTO_RECOVERY = restore_missing_photo_files(DB_PATH, PHOTO_ROOT, default_legacy_photo_roots(PROGRAM_ROOT, PHOTO_ROOT))
QR_SCAN_DIR = PHOTO_ROOT / "QR_SCANS"
QR_SCAN_DIR.mkdir(parents=True, exist_ok=True)
SOURCE_COPY_ROOT = Path(os.environ.get("SL_SOURCE_COPY_ROOT", str(SHARED_ROOT / "SOURCE_COPIES"))).resolve()
SOURCE_COPY_ROOT.mkdir(parents=True, exist_ok=True)
REPORT_ROOT = Path(os.environ.get("SL_REPORT_ROOT", str(SHARED_ROOT / "REPORTS"))).resolve()
REPORT_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SL Planning Center", version="1.7")
app.add_middleware(SessionMiddleware, secret_key=APP_SECRET, max_age=30 * 24 * 3600)  # login once; remember this device for 30 days
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

templates = Environment(
    loader=FileSystemLoader(str(BASE / "templates")),
    autoescape=select_autoescape(["html", "xml"]),
)

ROLES = {
    "admin": {"label": "Admin", "permissions": {"all"}},
    "planning": {"label": "Planning", "permissions": {"workorder", "planning", "dashboard", "export", "audit"}},
    "supervisor": {"label": "Production Supervisor", "permissions": {"scan", "supervisor", "dashboard", "export", "audit"}},
    "operator": {"label": "Production Operator", "permissions": {"scan"}},
    "production": {"label": "Production / ฝ่ายผลิต", "permissions": {"scan", "dashboard", "export", "audit"}},
    "management": {"label": "Management", "permissions": {"dashboard", "export", "audit"}},
    "viewer": {"label": "View Only", "permissions": {"dashboard", "export"}},
}

EVENT_LABELS = {
    "RECEIVE": "Receive",
    "START": "Start",
    "MOVE": "Move",
    "PARTIAL_COMPLETE": "Partial Complete",
    "COMPLETE": "Complete",
    "HOLD": "Hold",
    "RESUME": "Resume",
    "REWORK": "Rework",
    "QC_HOLD": "QC Hold",
    "QC_ACCEPT": "QC Accepted",
    "MANUAL": "Manual Update",
}

STATUS_LABELS = {
    "RELEASED": "Released",
    "RECEIVED": "Received",
    "RUNNING": "Running",
    "MOVE": "Moved",
    "PARTIAL": "Partial",
    "HOLD": "Hold",
    "REWORK": "Rework",
    "QC_PENDING": "QC Pending",
    "QC_ACCEPTED": "QC Accepted",
    "COMPLETE": "Packed quantity complete",
    "SECTION_COMPLETE": "Section complete / whole WO remains separate",
    "FINAL_COMPLETE": "Final Complete",
    "UNCONFIRMED": "Unconfirmed",
    "CANCELLED": "Cancelled",
}

VALID_EVENT_TYPES = set(EVENT_LABELS)


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    con.row_factory = sqlite3.Row
    # Older installations may still have a functional index created with
    # norm_wo(). SQLite requires every connection that writes to that table to
    # register the function, even before init_db can migrate the old index.
    con.create_function("norm_wo", 1, norm_wo, deterministic=True)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=15000")
    return con


try:
    FACTORY_TZ = ZoneInfo("Asia/Bangkok")
except Exception:  # tzdata missing (some Windows installs): fall back to the server clock
    FACTORY_TZ = None


def bkk_now() -> datetime:
    """Factory wall-clock time (Asia/Bangkok) as a naive datetime, the format already stored in the database."""
    return (datetime.now(FACTORY_TZ).replace(tzinfo=None) if FACTORY_TZ else datetime.now())


def now_iso() -> str:
    return bkk_now().replace(microsecond=0).isoformat(sep=" ")


def detected_server_urls(port: Optional[int] = None) -> list[str]:
    """Return reachable-looking IPv4 URLs plus loopback; configured URL is first when supplied."""
    port = port or DEFAULT_PORT
    urls = []
    configured = os.environ.get("SL_PUBLIC_URL", "").strip().rstrip("/")
    if configured:
        urls.append(configured)
    seen = set(urls)
    try:
        hostname = socket.gethostname()
        addrs = socket.gethostbyname_ex(hostname)[2]
        for ip in addrs:
            if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                u = f"http://{ip}:{port}"
                if u not in seen:
                    urls.append(u); seen.add(u)
    except Exception:
        pass
    if not urls:
        urls.append(f"http://127.0.0.1:{port}")
    return urls


def detected_server_url(port: Optional[int] = None) -> str:
    return detected_server_urls(port)[0]


def safe_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


def norm_wo(value) -> str:
    return re.sub(r'[^A-Z0-9]','',safe_text(value).upper())


def safe_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_date(value) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180_000)
    return f"pbkdf2_sha256$180000${salt.hex()}${dk.hex()}"


def check_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = encoded.split("$")
        salt = bytes.fromhex(salt_hex)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return secrets.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def ensure_wo_lookup_indexes(con):
    # Earlier releases used a Python-only norm_wo() expression index. The
    # current SQL normalizer is built from SQLite functions so other clients
    # (including the desktop audit) can safely use the shared database. Drop
    # only those two known stale indexes, then recreate them without data loss.
    for _idx in ("idx_work_orders_norm_wo", "idx_work_orders_norm_code"):
        _sql = con.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (_idx,)).fetchone()
        if _sql and _sql[0] and "norm_wo(" in _sql[0].lower():
            con.execute(f"DROP INDEX {_idx}")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_work_orders_norm_wo ON work_orders({NORMALIZED_WO_SQL.format('wo_id')})")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_work_orders_norm_code ON work_orders({NORMALIZED_WO_SQL.format('production_code')})")


def init_db() -> None:
    con = db()
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            display_name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT UNIQUE,
            thai_name TEXT,
            english_name TEXT,
            short_name TEXT
        );
        CREATE TABLE IF NOT EXISTS work_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wo_id TEXT UNIQUE NOT NULL,
            production_code TEXT,
            order_no TEXT,
            po_no TEXT,
            customer_id TEXT,
            customer_name TEXT,
            product_code TEXT,
            specification TEXT,
            real_spec TEXT,
            qty REAL NOT NULL DEFAULT 0,
            due_date TEXT,
            order_date TEXT,
            machine TEXT,
            program TEXT,
            drawing_no TEXT,
            shape TEXT,
            source_file TEXT,
            imported_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'RELEASED',
            created_by TEXT
        );
        CREATE TABLE IF NOT EXISTS work_order_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wo_id TEXT NOT NULL,
            material_code TEXT NOT NULL,
            required_qty REAL,
            unit TEXT DEFAULT 'g',
            FOREIGN KEY (wo_id) REFERENCES work_orders(wo_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wo_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            process_name TEXT NOT NULL,
            planned_date TEXT,
            FOREIGN KEY (wo_id) REFERENCES work_orders(wo_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS terminals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            terminal_code TEXT UNIQUE NOT NULL,
            process_name TEXT,
            location TEXT,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wo_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            qty REAL,
            process_name TEXT,
            location TEXT,
            terminal_code TEXT,
            user_name TEXT,
            source TEXT NOT NULL DEFAULT 'QR_SCAN',
            reason TEXT,
            notes TEXT,
            event_time TEXT NOT NULL,
            FOREIGN KEY (wo_id) REFERENCES work_orders(wo_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ncr_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wo_id TEXT NOT NULL,
            qty REAL,
            process_name TEXT,
            problem TEXT,
            disposition TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (wo_id) REFERENCES work_orders(wo_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS rework_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wo_id TEXT NOT NULL,
            qty REAL,
            process_name TEXT,
            reason TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (wo_id) REFERENCES work_orders(wo_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            stored_path TEXT,
            sha256 TEXT,
            uploaded_by TEXT,
            uploaded_at TEXT,
            imported_count INTEGER DEFAULT 0,
            rejected_count INTEGER DEFAULT 0,
            error_text TEXT
        );
        CREATE TABLE IF NOT EXISTS qr_scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scanned_by TEXT NOT NULL,
            payload TEXT NOT NULL,
            wo_id TEXT,
            result TEXT NOT NULL,
            scan_method TEXT NOT NULL,
            photo_path TEXT,
            photo_sha256 TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mobile_audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wo_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            verified_qty REAL,
            physical_status TEXT NOT NULL DEFAULT 'OK',
            physical_location TEXT,
            observed_process TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (wo_id) REFERENCES work_orders(wo_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS mobile_audit_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT,
            content_type TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (audit_id) REFERENCES mobile_audits(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS unidentified_parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            temp_id TEXT UNIQUE NOT NULL,
            qty REAL,
            process_name TEXT,
            location TEXT,
            issue_type TEXT,
            notes TEXT,
            reporter TEXT,
            created_at TEXT NOT NULL,
            resolved_wo_id TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT,
            action TEXT,
            entity TEXT,
            entity_id TEXT,
            details TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    # Forward-compatible columns used by the shared Plan-2026 audit view.
    cols = {r[1] for r in con.execute("PRAGMA table_info(work_orders)").fetchall()}
    if "product_category" not in cols:
        con.execute("ALTER TABLE work_orders ADD COLUMN product_category TEXT")
    upload_cols = {r[1] for r in con.execute("PRAGMA table_info(uploads)").fetchall()}
    if "stored_path" not in upload_cols:
        con.execute("ALTER TABLE uploads ADD COLUMN stored_path TEXT")
    con.execute("CREATE INDEX IF NOT EXISTS idx_work_orders_wo_id ON work_orders(wo_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_work_orders_production_code ON work_orders(production_code)")
    ensure_wo_lookup_indexes(con)
    con.execute("CREATE INDEX IF NOT EXISTS idx_events_wo_id_time ON events(wo_id,id DESC)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_qr_scan_wo_time ON qr_scan_log(wo_id,created_at DESC)")
    for _c,_t in [("initial_due_date","TEXT"),("revised_due_date","TEXT"),("sales_delivery_date","TEXT"),("plan_location","TEXT"),("plan_marker","TEXT"),("mill_batches","REAL"),("section_status_json","TEXT"),("plan_source_row","INTEGER")]:
        if _c not in cols: con.execute(f"ALTER TABLE work_orders ADD COLUMN {_c} {_t}")

    defaults = [
        ("admin", "admin123", "admin", "Administrator"),
        ("planning", "planning123", "planning", "Planning"),
        ("supervisor", "supervisor123", "supervisor", "Production Supervisor"),
        ("operator", "operator123", "operator", "Production Operator"),
        ("management", "management123", "management", "Management"),
    ]
    from suite.demo_accounts import DEMO_USERS
    defaults = list(DEMO_USERS)
    for username, password, role, display in defaults:
        if con.execute("SELECT 1 FROM users WHERE lower(username)=lower(?)", (username,)).fetchone() is None:
            con.execute(
                "INSERT INTO users(username,password_hash,role,display_name,created_at) VALUES(?,?,?,?,?)",
                (username, hash_password(password), role, display, now_iso()),
            )
    # Standard PPC sections. Curing is tracked as a location within Firing WIP, not as a separate main section.
    standard_terms = [
        ("PREP-01", "Preparation", "Preparation 01"),
        ("MIX-01", "Mixing", "Mixing 01"),
        ("FORM-01", "Forming", "Forming 01"),
        ("FIRE-WAIT", "Firing", "Waiting / Curing"),
        ("FIRE-01", "Firing", "Firing 01"),
        ("GR-01", "Grinding", "Grinding 01"),
        ("CUT-01", "Cutting", "Cutting 01"),
        ("PACK-01", "Packing", "Packing 01"),
        ("OTHER-01", "Other", "Other / Found elsewhere"),
    ]
    # Retire obsolete defaults but preserve historical events that referenced them.
    con.execute("UPDATE terminals SET active=0 WHERE terminal_code IN ('PRESS-01','CURE-01','QC-01')")
    for term, process, location in standard_terms:
        con.execute(
            "INSERT OR IGNORE INTO terminals(terminal_code,process_name,location) VALUES(?,?,?)",
            (term, process, location),
        )
    con.commit()
    con.close()


def log_audit(user_name: str, action: str, entity: str, entity_id: str, details: str = "") -> None:
    con = db()
    con.execute(
        "INSERT INTO audit_log(user_name,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
        (user_name, action, entity, entity_id, details, now_iso()),
    )
    con.commit()
    con.close()


def current_user(request: Request):
    uid = request.session.get("user")
    if not uid:
        return None
    con = db()
    row = con.execute("SELECT * FROM users WHERE username=? AND active=1", (uid,)).fetchone()
    con.close()
    return row


def require_login(request: Request):
    user = current_user(request)
    if not user:
        return None
    return user


def can(user, perm: str) -> bool:
    if not user:return False
    # RC29.5: every authenticated account can search, scan and submit across sections.
    # Login stays required so each observation retains operator identity.
    if perm in {"scan", "mobile_capture", "audit"}: return True
    # V12: all authenticated users can VIEW dashboards/plans and download evidence.
    if perm in {'dashboard','export','view_planning'}: return True
    return "all" in ROLES.get(user["role"], {}).get("permissions", set()) or perm in ROLES.get(user["role"], {}).get("permissions", set())


templates.globals["can"] = can


def render(request: Request, template: str, **context):
    user = current_user(request)
    context["user"] = user
    context["role_label"] = ROLES.get(user["role"], {}).get("label", "") if user else ""
    context["request"] = request
    context["status_labels"] = STATUS_LABELS
    context["event_labels"] = EVENT_LABELS
    if "plan_banner" not in context:
        context["plan_banner"] = plan_sync_banner()
    if "wo_count" not in context:
        context["wo_count"] = work_orders_in_db()
    return templates.get_template(template).render(**context)


def next_wo_id(con: sqlite3.Connection, seq: int) -> str:
    prefix = bkk_now().strftime("WO%y%m%d")
    candidate = f"{prefix}-{seq:04d}"
    while con.execute("SELECT 1 FROM work_orders WHERE wo_id=?", (candidate,)).fetchone():
        seq += 1
        candidate = f"{prefix}-{seq:04d}"
    return candidate


def normalize_header(v) -> str:
    return safe_text(v).strip().lower()


def import_workbook(path: Path, original_filename: str, username: str):
    """Import Work Orders from the real P280526-style workbook.

    Primary source: Cover Detial row 4 headers.
    Fallback: ใบorder.
    """
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    con = db()
    imported = 0
    rejected = 0
    errors = []
    created_wos = []
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
        if "Cover Detial" not in wb.sheetnames:
            raise ValueError("Workbook does not contain 'Cover Detial' sheet")
        ws = wb["Cover Detial"]
        headers = {normalize_header(ws.cell(4, c).value): c for c in range(1, min(ws.max_column, 105) + 1) if ws.cell(4, c).value not in (None, "")}
        col = lambda name: headers.get(normalize_header(name))
        required = ["ProductionCode", "Order NO.", "QTY", "รหัสสินค้า"]
        missing = [x for x in required if col(x) is None]
        if missing:
            raise ValueError("Missing Cover Detial columns: " + ", ".join(missing))
        # Native P280 draft packets carry explicit state metadata. Never promote those
        # rows to RELEASED when a mobile operator uploads the workbook for tracing.
        order_states = {}
        if "SL_ORDER_STATUS" in wb.sheetnames:
            sws = wb["SL_ORDER_STATUS"]
            sh = {normalize_header(safe_text(sws.cell(1, c).value)): c for c in range(1, min(sws.max_column, 20) + 1)}
            pc = sh.get(normalize_header("ProductionCode")); sc = sh.get(normalize_header("Status"))
            if pc and sc:
                for sr in range(2, sws.max_row + 1):
                    code = safe_text(sws.cell(sr, pc).value); state = safe_text(sws.cell(sr, sc).value).upper()
                    if code and state: order_states[code] = state

        prefix = bkk_now().strftime("WO%y%m%d")
        existing = con.execute("SELECT COUNT(*) c FROM work_orders WHERE wo_id LIKE ?", (prefix + "%",)).fetchone()["c"]
        wo_seq = int(existing) + 1
        process_cols = []
        for idx in range(95, 106):  # CR:DA; actual columns in current workbook
            h = safe_text(ws.cell(4, idx).value)
            if h and h not in ("ProductionCode",):
                process_cols.append((idx, h))

        material_pairs = [(78, 79), (80, 81), (82, 83), (84, 85), (86, 87)]  # BZ/CA, CB/CC, ...
        for r in range(5, ws.max_row + 1):
            production_code = safe_text(ws.cell(r, col("ProductionCode")).value)
            if not production_code or production_code.startswith("P00") is False:
                continue
            # Explicitly reject formula error placeholders.
            row_values = [ws.cell(r, c).value for c in range(1, min(ws.max_column, 105) + 1)]
            if any(v == "#N/A" for v in row_values[:20]):
                # Source placeholder row: ignore silently; it is not a Work Order import error.
                continue
            qty = safe_float(ws.cell(r, col("QTY")).value) or 0
            row_state = order_states.get(production_code, "RELEASED")
            if qty <= 0 and row_state != "DRAFT":
                rejected += 1
                errors.append(f"Row {r}: invalid quantity")
                continue
            order_no = safe_text(ws.cell(r, col("Order NO.")).value)
            po_no = safe_text(ws.cell(r, col("PO.NO.")).value)
            customer_name = safe_text(ws.cell(r, col("Customername")).value)
            customer_id = safe_text(ws.cell(r, col("Customername ID")).value)
            product_code = safe_text(ws.cell(r, col("รหัสสินค้า")).value)
            specification = safe_text(ws.cell(r, col("Specification")).value)
            real_spec = safe_text(ws.cell(r, col("Real Spec")).value)
            due_date = parse_date(ws.cell(r, col("กำหนดส่ง")).value)
            order_date = parse_date(ws.cell(r, col("วันที่สั่งผลิต")).value)
            machine = safe_text(ws.cell(r, 53).value)  # BA
            program = safe_text(ws.cell(r, 54).value)  # BB
            drawing_no = safe_text(ws.cell(r, 55).value)  # BC
            shape = safe_text(ws.cell(r, 75).value)  # BW
            wo_id = next_wo_id(con, wo_seq)
            wo_seq += 1
            try:
                con.execute(
                    """INSERT INTO work_orders(wo_id,production_code,order_no,po_no,customer_id,customer_name,product_code,
                    specification,real_spec,qty,due_date,order_date,machine,program,drawing_no,shape,source_file,imported_at,status,created_by)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (wo_id, production_code, order_no, po_no, customer_id, customer_name, product_code,
                     specification, real_spec, qty, due_date, order_date, machine, program, drawing_no, shape,
                     original_filename, now_iso(), row_state, username),
                )
            except sqlite3.IntegrityError:
                rejected += 1
                errors.append(f"Row {r}: duplicate ProductionCode {production_code}")
                continue

            # Route dates from CR:DA (95..105 in Excel 1-indexed)
            seq = 1
            for c, h in process_cols:
                val = parse_date(ws.cell(r, c).value)
                if val:
                    con.execute("INSERT INTO routes(wo_id,seq,process_name,planned_date) VALUES(?,?,?,?)", (wo_id, seq, h, val))
                    seq += 1

            for code_col, qty_col in material_pairs:
                mcode = safe_text(ws.cell(r, code_col).value)
                mqty = safe_float(ws.cell(r, qty_col).value)
                if mcode and not mcode.startswith("#") and mqty is not None and mqty > 0:
                    con.execute(
                        "INSERT INTO work_order_materials(wo_id,material_code,required_qty,unit) VALUES(?,?,?,?)",
                        (wo_id, mcode, mqty, "g"),
                    )
            imported += 1
            created_wos.append(wo_id)
        con.execute(
            "INSERT INTO uploads(filename,stored_path,sha256,uploaded_by,uploaded_at,imported_count,rejected_count,error_text) VALUES(?,?,?,?,?,?,?,?)",
            (original_filename, str(path.resolve()), sha, username, now_iso(), imported, rejected, "\n".join(errors[:200])),
        )
        con.commit()
    finally:
        con.close()
        try:
            wb.close()
        except Exception:
            pass
    return imported, rejected, errors, created_wos


def qr_payload(wo_id: str, base_url: str = "", mode: str = "code") -> str:
    """Stable, IP-independent QR by default. Direct links require explicit stable URL configuration."""
    key = safe_text(wo_id)
    if mode == "url":
        stable = (base_url or os.environ.get("SL_PUBLIC_URL", "")).strip().rstrip("/")
        if not stable:
            raise ValueError("Configure SL_PUBLIC_URL with a stable server URL before creating direct-open QR labels")
        return f"{stable}/q/{key}"
    return f"SLWO:{key}"


def qr_value_to_wo(value: str) -> str:
    """Accept this app's stable code, plain WO labels and historical URL QR labels."""
    raw = safe_text(value)
    if raw.upper().startswith("SLWO:"):
        return raw.split(":", 1)[1].strip()
    try:
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2 and parts[-2] == "q":
                return parts[-1]
            if parts:
                return parts[-1]
    except Exception:
        pass
    return raw


def resolve_work_order_code(value: str):
    """Only one exact/normalized database identity may resolve a scan."""
    from suite.scanner_lookup import exact_work_orders
    con = db()
    try:
        rows = exact_work_orders(con, qr_value_to_wo(value))
        return rows[0]["wo_id"] if len(rows) == 1 else None
    finally:
        con.close()


def record_qr_scan(user_name: str, payload: str, wo_id: Optional[str], result: str,
                   method: str, photo_path: Optional[Path] = None, photo_sha256: Optional[str] = None):
    con = db()
    try:
        con.execute("INSERT INTO qr_scan_log(scanned_by,payload,wo_id,result,scan_method,photo_path,photo_sha256,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (user_name, safe_text(payload)[:2048], wo_id, result, method,
                     str(photo_path) if photo_path else None, photo_sha256, now_iso()))
        con.commit()
    finally:
        con.close()


def create_qr_png(wo_id: str, base_url: str = "", mode: str = "code") -> Path:
    payload = qr_payload(wo_id, base_url, mode)
    safe_key = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", safe_text(wo_id))[:80] or "WO"
    out = QR_DIR / f"{safe_id}_{safe_key}.png"
    if not out.exists():
        img = _make_qr_png(payload)
        img.save(out)
    return out


def create_qr_workbook(source_path: Path, out_path: Path, wo_ids: list[str], base_url: str = "", mode: str = "code") -> None:
    """Create a safe QR-enabled companion by appending a printable QR index sheet."""
    wb = load_workbook(source_path)
    if "QR_LABELS" in wb.sheetnames:
        del wb["QR_LABELS"]
    ws = wb.create_sheet("QR_LABELS")
    ws["A1"] = "SL WORK ORDER QR LABELS"
    ws["A1"].font = Font(size=18, bold=True)
    ws.merge_cells("A1:F1")
    ws["A2"] = "IP-independent SLWO labels: scan inside SL Part Tracking. The original sheets are preserved."
    ws.merge_cells("A2:F2")
    ws["A2"].alignment = Alignment(wrap_text=True)
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 18
    ws.column_dimensions["F"].width = 20
    con = db()
    rows = []
    for wid in wo_ids:
        r = con.execute("SELECT * FROM work_orders WHERE wo_id=?", (wid,)).fetchone()
        if r:
            rows.append(r)
    con.close()
    start = 4
    for i, r in enumerate(rows):
        row = start + i * 8
        ws.cell(row, 1, "WORK ORDER")
        ws.cell(row + 1, 1, r["wo_id"])
        ws.cell(row + 2, 1, "Production Code")
        ws.cell(row + 3, 1, r["production_code"])
        ws.cell(row + 4, 1, "Product")
        ws.cell(row + 5, 1, r["product_code"])
        ws.cell(row + 6, 1, "Qty")
        ws.cell(row + 7, 1, r["qty"])
        img = XLImage(str(create_qr_png(r["wo_id"], base_url, mode)))
        img.width = 150
        img.height = 150
        ws.add_image(img, f"C{row}")
        ws.cell(row, 5, "Customer")
        ws.cell(row + 1, 5, r["customer_name"])
        ws.cell(row + 2, 5, "Due")
        ws.cell(row + 3, 5, r["due_date"] or "")
        ws.cell(row + 4, 5, "Machine / Program")
        ws.cell(row + 5, 5, f"{r['machine'] or ''} / {r['program'] or ''}")
        for rr in range(row, row + 8):
            ws.cell(rr, 1).font = Font(bold=(rr in (row, row + 2, row + 4, row + 6)))
    ws.freeze_panes = "A4"
    ws.print_title_rows = "1:3"
    wb.save(out_path)
    wb.close()


def seed_from_real_workbook(path: Path) -> int:
    """Import first 8 valid WOs once for demo. Safe to skip if DB already has WOs."""
    con = db()
    count = con.execute("SELECT COUNT(*) c FROM work_orders").fetchone()["c"]
    con.close()
    if count:
        return 0
    try:
        imported, _, _, _ = import_workbook(path, path.name, "system")
        return imported
    except Exception:
        return 0


def get_current_snapshot(wo_id: str):
    con = db()
    wo = con.execute("SELECT * FROM work_orders WHERE wo_id=?", (wo_id,)).fetchone()
    events = con.execute("SELECT * FROM events WHERE wo_id=? ORDER BY id", (wo_id,)).fetchall()
    route = con.execute("SELECT * FROM routes WHERE wo_id=? ORDER BY seq", (wo_id,)).fetchall()
    materials = con.execute("SELECT * FROM work_order_materials WHERE wo_id=?", (wo_id,)).fetchall()
    con.close()
    if not wo:
        return None
    produced = 0.0
    accepted = 0.0
    rework = 0.0
    current_process = None
    current_location = None
    last_event = None
    status = "RELEASED"
    for e in events:
        last_event = e
        if e["event_type"] in ("RECEIVE", "START", "MOVE", "RESUME", "PARTIAL_COMPLETE", "COMPLETE", "HOLD", "REWORK", "QC_HOLD", "QC_ACCEPT"):
            current_process = e["process_name"] or current_process
            current_location = e["location"] or current_location
        if e["event_type"] in ("PARTIAL_COMPLETE", "COMPLETE") and e["qty"] is not None and str(e["process_name"] or "").strip().upper() in {"PACKING","PACK","บรรจุ"}:
            produced = max(produced, float(e["qty"]))
        if e["event_type"] == "QC_ACCEPT" and e["qty"] is not None:
            accepted = max(accepted, float(e["qty"]))
        if e["event_type"] == "REWORK" and e["qty"] is not None:
            rework = max(rework, float(e["qty"]))
        mapping = {
            "RECEIVE": "RECEIVED", "START": "RUNNING", "MOVE": "MOVE", "RESUME": "RUNNING",
            "PARTIAL_COMPLETE": "PARTIAL", "COMPLETE": "COMPLETE", "HOLD": "HOLD", "REWORK": "REWORK",
            "QC_HOLD": "QC_PENDING", "QC_ACCEPT": "QC_ACCEPTED",
        }
        if e["event_type"] in mapping:
            status = mapping[e["event_type"]]
            if e["event_type"]=="COMPLETE" and str(e["process_name"] or "").strip().upper() not in {"PACKING","PACK","บรรจุ"}:
                status="SECTION_COMPLETE"
    remaining = max(float(wo["qty"] or 0) - produced, 0)
    if status == "COMPLETE" and accepted >= float(wo["qty"] or 0) and wo["qty"]:
        status = "FINAL_COMPLETE"
    if last_event:
        try:
            dt = datetime.fromisoformat(last_event["event_time"])
            if bkk_now() - dt > timedelta(hours=UNCONFIRMED_HOURS) and status not in ("FINAL_COMPLETE", "CANCELLED"):
                status = "UNCONFIRMED"
        except Exception:
            pass
    audit_con = db()
    last_audit = audit_con.execute("SELECT * FROM mobile_audits WHERE wo_id=? ORDER BY id DESC LIMIT 1", (wo_id,)).fetchone()
    last_audit_photo = None
    if last_audit:
        last_audit_photo = audit_con.execute("SELECT * FROM mobile_audit_photos WHERE audit_id=? ORDER BY id DESC LIMIT 1", (last_audit["id"],)).fetchone()
    audit_count = audit_con.execute("SELECT COUNT(*) c FROM mobile_audits WHERE wo_id=?", (wo_id,)).fetchone()["c"]
    # Physical audit comparison uses the best available system reference quantity:
    # cumulative production when available; otherwise the WO quantity before any output is recorded.
    audit_reference_qty = produced if produced > 0 else float(wo["qty"] or 0)
    audit_mismatch_count = 0
    if last_audit and last_audit["verified_qty"] is not None and abs(float(last_audit["verified_qty"]) - audit_reference_qty) > 0.000001:
        audit_mismatch_count = 1
    audit_con.close()
    whole_decision=None
    with db() as status_con:
        if status_con.execute("SELECT 1 FROM sqlite_master WHERE name='wo_status_events'").fetchone():
            decision=status_con.execute('SELECT status,reason,user,recorded_at,source FROM wo_status_events WHERE wo=? ORDER BY id DESC LIMIT 1',(wo_id,)).fetchone()
            whole_decision=dict(decision) if decision else None
    try: section_status=json.loads(wo["section_status_json"] or "[]")
    except Exception: section_status=[]
    # Planned route dates and actual events are separate evidence streams.
    from apps.mobile.work_order_timeline import build_process_timeline, completion_percent
    _today=bkk_now().date()
    process_timeline=build_process_timeline(route,events,_today)
    _order_qty=float(wo['qty'] or 0)
    _completed_pct=completion_percent(_order_qty,events)
    _qty_event_recorded=_completed_pct is not None
    return {
        "wo": wo, "events": events, "route": route, "materials": materials,"whole_order_decision":whole_decision,
        "process_timeline": process_timeline, "completed_percent": _completed_pct,
        "production_qty_recorded": _qty_event_recorded,
        "section_status": section_status,
        "status": status, "current_process": current_process, "current_location": current_location,
        "last_event": last_event, "produced": produced, "accepted": accepted, "rework": rework,
        "remaining": remaining, "last_audit": last_audit, "last_audit_photo": last_audit_photo, "audit_count": audit_count,
        "audit_mismatch_count": audit_mismatch_count, "audit_reference_qty": audit_reference_qty,
    }


def all_snapshots(search: str = ""):
    con = db()
    params = []
    where = ""
    if search:
        where = "WHERE wo_id LIKE ? OR production_code LIKE ? OR order_no LIKE ? OR product_code LIKE ? OR customer_name LIKE ?"
        term = f"%{search}%"
        params = [term] * 5
    rows = con.execute(f"SELECT * FROM work_orders {where} ORDER BY due_date IS NULL, due_date, id DESC", params).fetchall()
    con.close()
    return [get_current_snapshot(r["wo_id"]) for r in rows]



def dashboard_stats(snaps=None):
    snaps = all_snapshots() if snaps is None else snaps
    today = bkk_now().date().isoformat()
    stats = {k: 0 for k in ["active", "running", "waiting", "hold", "production_complete", "qc_pending", "rework", "unconfirmed", "due_today", "overdue", "due_3", "audits_today", "audit_mismatch"]}
    wip = {}
    exceptions = []
    for s in snaps:
        status = s["status"]
        if status != "FINAL_COMPLETE":
            stats["active"] += 1
        if status == "RUNNING": stats["running"] += 1
        if status in ("RECEIVED", "MOVE", "RELEASED"): stats["waiting"] += 1
        if status == "HOLD": stats["hold"] += 1
        if status == "COMPLETE": stats["production_complete"] += 1
        if status in ("QC_PENDING", "QC_ACCEPTED"): stats["qc_pending"] += 1
        if status == "REWORK": stats["rework"] += 1
        if status == "UNCONFIRMED": stats["unconfirmed"] += 1
        due = s["wo"]["due_date"]
        if due:
            if due == today and status != "FINAL_COMPLETE": stats["due_today"] += 1
            if due < today and status != "FINAL_COMPLETE":
                stats["overdue"] += 1
                exceptions.append(("Overdue", s))
            try:
                d = date.fromisoformat(due)
                if today <= due <= (bkk_now().date() + timedelta(days=3)).isoformat() and status != "FINAL_COMPLETE":
                    stats["due_3"] += 1
                    exceptions.append(("Due soon", s))
            except ValueError:
                pass
        if status != "FINAL_COMPLETE" and s["current_process"]:
            wip[s["current_process"]] = wip.get(s["current_process"], 0) + max(float(s.get("remaining") or 0), 0)
        if status == "UNCONFIRMED":
            exceptions.append(("No recent scan", s))
        if s["rework"] > 0:
            exceptions.append(("Rework", s))
        if s.get("audit_mismatch_count", 0) > 0:
            stats["audit_mismatch"] += 1
            exceptions.append(("Physical audit mismatch", s))
        if s.get("last_audit"):
            try:
                if s["last_audit"]["created_at"][:10] == today:
                    stats["audits_today"] += 1
            except Exception:
                pass
    return stats, sorted(wip.items(), key=lambda x: x[0]), exceptions[:30]


import audit_v2  # noqa: E402
init_db()
seed_candidate = BASE.parent / "P280526.xlsx"
if seed_candidate.exists():
    seed_from_real_workbook(seed_candidate)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if not current_user(request):
        return RedirectResponse("/login", 303)
    return RedirectResponse("/dashboard", 303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/dashboard"):
    request.session["login_next"] = next if next.startswith("/") else "/dashboard"
    return HTMLResponse(render(request, "login.html", error=None))


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    con = db()
    row = con.execute("SELECT * FROM users WHERE username=? AND active=1", (username.strip(),)).fetchone()
    con.close()
    if not row or not check_password(password, row["password_hash"]):
        return HTMLResponse(render(request, "login.html", error="Invalid username or password"), status_code=401)
    request.session["user"] = row["username"]
    next_url = request.session.pop("login_next", "/dashboard")
    log_audit(row["username"], "LOGIN", "USER", row["username"])
    return RedirectResponse(next_url if next_url.startswith("/") else "/dashboard", 303)


@app.get("/logout")
def logout(request: Request):
    user = current_user(request)
    if user:
        log_audit(user["username"], "LOGOUT", "USER", user["username"])
    request.session.clear()
    return RedirectResponse("/login", 303)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = require_login(request)
    if not user or not can(user, "dashboard"):
        return RedirectResponse("/login", 303)
    snapshots = all_snapshots()
    stats, wip, exceptions = dashboard_stats(snapshots)
    wip_max = max((float(q or 0) for _, q in wip), default=0)
    status_keys = ["running", "waiting", "hold", "production_complete", "qc_pending", "rework"]
    status_graph = [(k.replace("_", " ").title(), int(stats.get(k, 0))) for k in status_keys]
    status_max = max((v for _, v in status_graph), default=0)
    return HTMLResponse(render(request, "dashboard.html", stats=stats, wip=wip, wip_max=wip_max,
                               status_graph=status_graph, status_max=status_max, exceptions=exceptions,
                               snapshots=snapshots[:50]))


@app.get("/q/{wo_id}", response_class=HTMLResponse)
def qr_open(request: Request, wo_id: str):
    kick_shared_plan_sync(wait_s=1.5)
    canonical=resolve_work_order_code(wo_id) or wo_id
    if not current_user(request):
        return RedirectResponse(f"/login?next=/mobile/wo/{canonical}", 303)
    return RedirectResponse(f"/mobile/wo/{canonical}", 303)


@app.get("/mobile-access", response_class=HTMLResponse)
def mobile_access(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse("/login?next=/mobile-access", 303)
    urls = detected_server_urls(request.url.port)
    access_items = [(u, create_access_qr(u)) for u in urls]
    return HTMLResponse(render(request, "mobile_access.html", server_url=urls[0], access_items=access_items))


def create_access_qr(server_url: str) -> str:
    payload = f"{server_url.rstrip('/')}/mobile"
    safe_key = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    out = QR_DIR / f"mobile_access_{safe_key}.png"
    if not out.exists():
        _make_qr_png(payload).save(out)
    return f"/qr/{out.name}"


@app.get("/qr/{filename}")
def qr_media(request: Request, filename: str):
    user = require_login(request)
    if not user:
        return RedirectResponse("/login", 303)
    safe_name = Path(filename).name
    path = QR_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="QR not found")
    return FileResponse(path)




@app.get("/operator", response_class=HTMLResponse)
def operator_page(request: Request):
    user=require_login(request)
    if not user:
        return RedirectResponse("/login?next=/operator",303)
    return RedirectResponse("/scan",303)


@app.post("/api/decode-qr-photo")
async def decode_qr_photo(request: Request, photo: UploadFile = File(...)):
    user = require_login(request)
    if not user: return {"ok":False,"error":"Not logged in"}
    _ct = (photo.content_type or "").split(";")[0].strip().lower()
    if _ct and _ct not in {"image/jpeg","image/jpg","image/png","image/webp","image/heic","image/heif","application/octet-stream"}:
        return {"ok":False,"error":"Choose a JPG, PNG, WEBP or HEIC phone photo"}
    raw = await photo.read()
    if not raw or len(raw) > MOBILE_AUDIT_MAX_PHOTO_BYTES:
        return {"ok":False,"error":f"Photo must be present and no larger than {MOBILE_AUDIT_MAX_PHOTO_BYTES // (1024*1024)} MB"}
    digest = hashlib.sha256(raw).hexdigest()
    scan_day = bkk_now().strftime("%Y/%m/%d")
    scan_dir = QR_SCAN_DIR / scan_day
    scan_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(photo.filename or "scan.jpg").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}: suffix = ".jpg"
    saved_photo = scan_dir / f"scan_{bkk_now().strftime('%H%M%S')}_{secrets.token_hex(5)}{suffix}"
    saved_photo.write_bytes(raw)
    try:
        import qr_decode
        res = qr_decode.decode_qr(raw)
        if res.status == "HEIC_UNSUPPORTED":
            record_qr_scan(user["username"], "", None, "IMAGE_READ_ERROR", "PHOTO", saved_photo, digest)
            return {"ok":False,"error":"This HEIC photo cannot be read by the server. Take the photo as JPG (iPhone: Settings > Camera > Formats > Most Compatible) or install pillow-heif on the server.","photo_path":str(saved_photo)}
        if res.status == "IMAGE_UNREADABLE":
            record_qr_scan(user["username"], "", None, "IMAGE_READ_ERROR", "PHOTO", saved_photo, digest)
            return {"ok":False,"error":"Camera image could not be read","photo_path":str(saved_photo)}
        if res.status == "AMBIGUOUS":
            record_qr_scan(user["username"], " | ".join(res.values)[:2048], None, "MULTIPLE_QR_IN_PHOTO", "PHOTO", saved_photo, digest)
            return {"ok":False,"error":"More than one different QR code is visible. Frame only one label and retake.","values":res.values,"photo_path":str(saved_photo)}
        value = res.value
        if not value:
            record_qr_scan(user["username"], "", None, "NOT_DETECTED", "PHOTO", saved_photo, digest)
            return {"ok":False,"error":"QR not detected. Move closer, keep QR flat and retake.","photo_path":str(saved_photo)}
        cands = audit_v2.find_candidates(value)
        if len(cands) > 1:
            record_qr_scan(user["username"], value, None, "AMBIGUOUS", "PHOTO", saved_photo, digest)
            return {"ok":True,"ambiguous":True,"candidates":cands,"value":value,"photo_path":str(saved_photo)}
        wo = resolve_work_order_code(value)
        record_qr_scan(user["username"], value, wo, "FOUND" if wo else "UNKNOWN_WO", "PHOTO", saved_photo, digest)
        if not wo and cands:
            return {"ok":True,"value":value,"tracking_id":cands[0]["tracking_id"],"kind":cands[0]["kind"],"photo_path":str(saved_photo)}
        return {"ok":True,"value":value,"wo_id":wo,"photo_path":str(saved_photo)}
    except ImportError:
        record_qr_scan(user["username"], "", None, "DECODER_MISSING", "PHOTO", saved_photo, digest)
        return {"ok":False,"error":"Server QR decoder is not installed. Install packages from apps/mobile/requirements.txt and restart the server.","photo_path":str(saved_photo)}
    except Exception as e:
        record_qr_scan(user["username"], "", None, "DECODE_ERROR", "PHOTO", saved_photo, digest)
        return {"ok":False,"error":"QR decode failed: "+str(e),"photo_path":str(saved_photo)}


@app.post("/api/qr-scan")
async def qr_scan(request: Request):
    user = require_login(request)
    if not user: return {"ok":False,"error":"Session expired — please login once again"}
    payload = await request.json()
    value = safe_text(payload.get("value"))[:2048]
    method = safe_text(payload.get("method")).upper()
    if method not in {"LIVE_CAMERA", "MANUAL", "PHOTO", "USB_SCANNER"}: method = "LIVE_CAMERA"
    if not value: return {"ok":False,"error":"Empty QR value"}
    cands = audit_v2.find_candidates(value)
    if len(cands) > 1:
        record_qr_scan(user["username"], value, None, "AMBIGUOUS", method)
        return {"ok":True,"ambiguous":True,"candidates":cands}
    wo = resolve_work_order_code(value)
    record_qr_scan(user["username"], value, wo, "FOUND" if wo else "UNKNOWN_WO", method)
    if not wo and cands: return {"ok":True,"tracking_id":cands[0]["tracking_id"],"kind":cands[0]["kind"]}
    if not wo: return {"ok":False,"error":"QR read successfully but Work Order is not in the system","value":value}
    return {"ok":True,"wo_id":wo}


@app.post("/api/record-qr-photo")
async def record_qr_photo(request: Request, photo: UploadFile = File(...), value: str = Form(...)):
    user=require_login(request)
    if not user:return {"ok":False,"error":"Session expired — please login once again"}
    _ct=(photo.content_type or "").split(";")[0].strip().lower()
    if _ct and _ct not in {"image/jpeg","image/jpg","image/png","image/webp","image/heic","image/heif","application/octet-stream"}:return {"ok":False,"error":"Choose a JPG, PNG, WEBP or HEIC phone photo"}
    raw=await photo.read()
    if not raw or len(raw)>MOBILE_AUDIT_MAX_PHOTO_BYTES:return {"ok":False,"error":"Photo must be present and within the configured size limit"}
    digest=hashlib.sha256(raw).hexdigest(); day=bkk_now().strftime("%Y/%m/%d"); target_dir=QR_SCAN_DIR/day; target_dir.mkdir(parents=True,exist_ok=True)
    suffix=Path(photo.filename or "scan.jpg").suffix.lower()
    if suffix not in {".jpg",".jpeg",".png",".webp",".heic",".heif"}:suffix=".jpg"
    target=target_dir/f"scan_{bkk_now().strftime('%H%M%S')}_{secrets.token_hex(5)}{suffix}";target.write_bytes(raw)
    cands=audit_v2.find_candidates(value)
    if len(cands)>1:
        record_qr_scan(user["username"],value,None,"AMBIGUOUS","PHOTO",target,digest)
        return {"ok":True,"ambiguous":True,"candidates":cands,"photo_path":str(target)}
    wo=resolve_work_order_code(value)
    record_qr_scan(user["username"],value,wo,"FOUND" if wo else "UNKNOWN_WO","PHOTO",target,digest)
    if not wo and cands:return {"ok":True,"tracking_id":cands[0]["tracking_id"],"kind":cands[0]["kind"],"photo_path":str(target)}
    if not wo:return {"ok":False,"error":"QR read, but Work Order was not found","photo_path":str(target)}
    return {"ok":True,"wo_id":wo,"photo_path":str(target)}

@app.post("/api/operator-event")
async def operator_event(request: Request):
    user=require_login(request)
    if not user: return {"ok":False,"error":"Session expired — please login once again"}
    if not can(user,"mobile_capture"): return JSONResponse({"ok":False,"error":"Your role is not allowed to record events","code":"FORBIDDEN"},status_code=403)
    payload=await request.json()
    wo_id=safe_text(payload.get("wo_id")); action=safe_text(payload.get("action")).upper()
    terminal_code=safe_text(payload.get("terminal_code")); reporter=user["username"]
    qty=safe_float(payload.get("qty")); issue=safe_text(payload.get("issue")); notes=safe_text(payload.get("notes"))
    if action not in {"RECEIVE","COMPLETE","HOLD","REWORK","QC_HOLD"}: return {"ok":False,"error":"Invalid action"}
    con=db(); wo=con.execute("SELECT * FROM work_orders WHERE wo_id=? OR production_code=?",(wo_id,wo_id)).fetchone()
    if not wo: con.close(); return {"ok":False,"error":"Work Order not found — use UNIDENTIFIED PART"}
    term=con.execute("SELECT * FROM terminals WHERE terminal_code=? AND active=1",(terminal_code,)).fetchone() if terminal_code else None
    process=term["process_name"] if term else safe_text(payload.get("process")); location=term["location"] if term else safe_text(payload.get("location"))
    real_id=wo["wo_id"]
    con.execute("INSERT INTO events(wo_id,event_type,qty,process_name,location,terminal_code,user_name,source,reason,notes,event_time) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(real_id,action,qty,process,location,terminal_code,reporter,"OPERATOR_FAST",issue,notes,now_iso()))
    con.commit(); con.close(); snap=get_current_snapshot(real_id)
    return {"ok":True,"wo_id":real_id,"status":snap["status"],"process":snap["current_process"],"location":snap["current_location"]}

@app.post("/api/unidentified")
async def unidentified(request: Request):
    user=require_login(request)
    if not user: return {"ok":False,"error":"Session expired — please login once again"}
    if not can(user,"mobile_capture"): return JSONResponse({"ok":False,"error":"Your role is not allowed to record unidentified parts","code":"FORBIDDEN"},status_code=403)
    payload=await request.json(); reporter=user["username"]
    temp_id="UNID-"+bkk_now().strftime("%Y%m%d-%H%M%S")+"-"+secrets.token_hex(2).upper()
    con=db(); con.execute("INSERT INTO unidentified_parts(temp_id,qty,process_name,location,issue_type,notes,reporter,created_at) VALUES(?,?,?,?,?,?,?,?)",(temp_id,safe_float(payload.get("qty")),safe_text(payload.get("process")),safe_text(payload.get("location")),safe_text(payload.get("issue")),safe_text(payload.get("notes")),reporter,now_iso())); con.commit(); con.close()
    return {"ok":True,"temp_id":temp_id}


def work_orders_in_db() -> int:
    try:
        con = db()
        try:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='work_orders'").fetchone():
                return 0
            return int(con.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])
        finally:
            con.close()
    except Exception:
        return 0


_SYNC_LOCK = threading.Lock()
_SYNC_STATE = {"running": False, "last_ok": None, "last_msg": "", "last_source_stamp": None}


def ensure_shared_plan_sync():
    """Keep mobile WO database synchronized with the one active central Plan-2026 file."""
    try:
        shared = None
        try:
            if str(PROGRAM_ROOT) not in sys.path:
                sys.path.insert(0, str(PROGRAM_ROOT))
            from suite.central_paths import resolve_plan
            shared = resolve_plan()
        except Exception:
            shared = None
        if shared is None:
            shared = Path(os.environ.get("SL_COMPANY_DATA", str(SHARED_ROOT / "COMPANY_DATA"))).resolve() / "Plan-2026-LATEST.xlsx"
        if not Path(shared).exists():
            return False, "Plan-2026-LATEST.xlsx not loaded"
        shared = Path(shared)
        stamp = shared.stat().st_mtime
        marker = DATA / "shared_plan_mtime_v62.txt"
        old = float(marker.read_text().strip()) if marker.exists() else -1
        if stamp != old:
            import_plan2026(shared, shared.name, "SYSTEM-SHARED")
            marker.write_text(str(stamp))
        return True, shared.name
    except Exception as e:
        return False, str(e)


def kick_shared_plan_sync(wait_s: float = 0.0):
    """Start Plan-2026 import in the background so /mobile can open immediately."""
    def _run():
        if not _SYNC_LOCK.acquire(blocking=False):
            return
        try:
            _SYNC_STATE["running"] = True
            ok, msg = ensure_shared_plan_sync()
            _SYNC_STATE["last_ok"] = ok
            _SYNC_STATE["last_msg"] = str(msg)
            if ok:
                try:
                    from suite.central_paths import resolve_plan
                    _p=resolve_plan()
                    _SYNC_STATE["last_source_stamp"]=_p.stat().st_mtime if _p else None
                except Exception:_SYNC_STATE["last_source_stamp"]=None
        except Exception as exc:
            _SYNC_STATE["last_ok"] = False
            _SYNC_STATE["last_msg"] = str(exc)
        finally:
            _SYNC_STATE["running"] = False
            _SYNC_LOCK.release()

    # Fast path for thousands of operator searches: don't launch a background
    # workbook-check thread on every keystroke when the active source is unchanged.
    if not _SYNC_STATE["running"] and _SYNC_STATE.get("last_ok") is True:
        try:
            from suite.central_paths import resolve_plan
            _current=resolve_plan()
            if _current and _current.is_file() and _SYNC_STATE.get("last_source_stamp")==_current.stat().st_mtime and DB_PATH.is_file():
                return _SYNC_STATE
        except Exception:pass
    if not _SYNC_STATE["running"]:
        threading.Thread(target=_run, daemon=True, name="sl-plan-sync").start()
    if wait_s > 0:
        deadline = time.time() + wait_s
        while time.time() < deadline and _SYNC_STATE["running"] and work_orders_in_db() == 0:
            time.sleep(0.15)
    return _SYNC_STATE


def plan_sync_banner():
    n = work_orders_in_db()
    if n > 0:
        return ""
    if _SYNC_STATE["running"]:
        return "Loading Plan-2026 into the phone database. Scan or type the work order again in a moment."
    msg = _SYNC_STATE.get("last_msg") or ""
    if _SYNC_STATE.get("last_ok") is False:
        return f"Plan-2026 is not in the phone database yet: {msg}. Upload it once on Home, then open this page again."
    return "Plan-2026 is not in the phone database yet. Upload it once on Home. Scan will find a work order after that file is loaded."


@app.on_event("startup")
def _boot_plan_sync():
    try:
        kick_shared_plan_sync()
    except Exception:
        pass


@app.get("/mobile", response_class=HTMLResponse)
def mobile_home(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse("/login?next=/mobile", 303)
    kick_shared_plan_sync()
    return HTMLResponse(render(request, "mobile.html", recent=audit_v2.recent_submissions(user["username"], 5), can_capture=can(user, "mobile_capture")))


@app.get("/mobile/wo/{wo_id}", response_class=HTMLResponse)
def mobile_wo(request: Request, wo_id: str):
    user=require_login(request)
    if not user:
        return RedirectResponse(f"/login?next=/mobile/wo/{wo_id}",303)
    kick_shared_plan_sync(wait_s=1.5)
    con=db(); row=con.execute("SELECT wo_id FROM work_orders WHERE wo_id=? LIMIT 1",(wo_id,)).fetchone()
    canonical=row["wo_id"] if row else None
    if not canonical:
        key=norm_wo(wo_id); rows=con.execute("SELECT wo_id FROM work_orders").fetchall()
        canonical=next((r["wo_id"] for r in rows if norm_wo(r["wo_id"])==key),wo_id)
    con.close()
    snap = get_current_snapshot(canonical)
    if not snap:
        found = resolve_work_order_code(wo_id)
        if found:
            snap = get_current_snapshot(found)
    if not snap:
        return HTMLResponse("Work Order not found in active Plan-2026", status_code=404)
    return HTMLResponse(render(request, "mobile_wo.html", snap=snap))


@app.get("/mobile/scan", response_class=HTMLResponse)
def mobile_scan(request: Request):
    if not require_login(request):return RedirectResponse("/login?next=/mobile/scan",303)
    kick_shared_plan_sync()
    return HTMLResponse(render(request, "mobile_scan.html"))


@app.get("/work-orders", response_class=HTMLResponse)
def work_orders(request: Request, search: str = ""):
    user = require_login(request)
    if not user:
        return RedirectResponse("/login", 303)
    rows = all_snapshots(search)[:250]
    return HTMLResponse(render(request, "work_orders.html", rows=rows, search=search))


@app.get("/work-orders/{wo_id}", response_class=HTMLResponse)
def work_order_detail(request: Request, wo_id: str):
    user = require_login(request)
    if not user:
        return RedirectResponse("/login", 303)
    snap = get_current_snapshot(wo_id)
    if not snap:
        return HTMLResponse("Work Order not found", status_code=404)
    return HTMLResponse(render(request, "work_order.html", snap=snap))


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request):
    user = require_login(request)
    if not user or not can(user, "workorder"):
        return RedirectResponse("/dashboard", 303)
    return HTMLResponse(render(request, "upload.html", result=None))


@app.post("/upload")
def upload(request: Request, file: UploadFile = File(...)):
    user = require_login(request)
    if not user or not can(user, "workorder"):
        return RedirectResponse("/dashboard", 303)
    suffix = Path(file.filename or "upload.xlsx").suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        return HTMLResponse(render(request, "upload.html", result={"error": "Upload .xlsx or .xlsm only"}), status_code=400)
    dest = UPLOADS / f"{bkk_now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(3)}_{Path(file.filename).name}"
    dest.write_bytes(file.file.read())
    try:
        imported, rejected, errors, wo_ids = import_workbook(dest, Path(file.filename).name, user["username"])
        qr_out = None
        log_audit(user["username"], "IMPORT", "WORKBOOK", Path(file.filename).name, f"imported={imported},rejected={rejected}")
        return HTMLResponse(render(request, "upload.html", result={"imported": imported, "rejected": rejected, "errors": errors[:20], "qr_file": qr_out.name if qr_out else None,"source_file":str(dest),"source_sha":hashlib.sha256(dest.read_bytes()).hexdigest(),"imported_at":now_iso()}))
    except Exception as e:
        return HTMLResponse(render(request, "upload.html", result={"error": str(e)}), status_code=400)


@app.get("/download/{filename}")
def download_file(request: Request, filename: str):
    user = require_login(request)
    if not user or not can(user, "export"):
        return RedirectResponse("/dashboard", 303)
    path = UPLOADS / Path(filename).name
    if not path.exists():
        return HTMLResponse("File not found", status_code=404)
    return FileResponse(path, filename=path.name)


@app.get("/scan", response_class=HTMLResponse)
def scan_page(request: Request, station: str = ""):
    user = require_login(request)
    if not user or not can(user, "scan"):
        return RedirectResponse("/dashboard", 303)
    con = db()
    terminal = con.execute("SELECT * FROM terminals WHERE terminal_code=? AND active=1", (station,)).fetchone() if station else None
    terminals = con.execute("SELECT * FROM terminals WHERE active=1 ORDER BY terminal_code").fetchall()
    con.close()
    from suite.demo_accounts import USER_SECTIONS
    account_section=USER_SECTIONS.get(user["username"].lower())
    default_station=terminal['terminal_code'] if terminal else next((t['terminal_code'] for t in terminals if account_section and t['process_name']==account_section),'')
    from urllib.parse import urlencode
    from suite.hub_auth import issue
    root=Path(os.environ.get('SL_COMPANY_DATA',str(SHARED_ROOT/'COMPANY_DATA')))
    hub=os.environ.get('SL_HUB_URL',str(request.url.replace(scheme='http',port=8510,path='/',query=''))).rstrip('/')
    ticket=issue(root,user['username'],user['role'])
    plans=[('🔥','แผนเผา','Firing plan','firing'),('📅','แผนรายวันและแผนก','Daily / section plans','daily'),('🏭','สถานะการผลิต','Production status','production_analysis'),('📊','WIP และ Plan 2026','Plan 2026 / WIP','wip')]
    links=[dict(icon=i,thai=th,english=en,url=hub+'/?'+urlencode({'page':page,'auth_ticket':ticket})) for i,th,en,page in plans]
    links.extend([dict(icon='📘',thai='ไฟล์ Plan 2026',english='Download Plan 2026 source',url='/source/plan2026'),dict(icon='📗',thai='ไฟล์สถานะการผลิต',english='Download Production status source',url='/source/production-status')])
    sections=[dict(thai=th,english=sec,url=hub+'/?'+urlencode({'page':'daily','focus':'section','section':sec,'auth_ticket':ticket})) for sec,th in [('Preparation','เตรียม'),('Mixing','ผสม'),('Forming','ขึ้นรูป'),('Firing','เผา'),('Grinding','เจียร'),('Cutting','ตัด'),('Packing','บรรจุ')]]
    return HTMLResponse(render(request, "scan.html", terminal=terminal, terminals=terminals,plan_links=links,section_links=sections,mobile_view=request.query_params.get('mode')=='mobile',
        default_section=account_section or "Preparation",default_station=default_station))


@app.post("/api/scan")
async def api_scan(request: Request):
    user = require_login(request)
    if not user or not can(user, "scan"):
        return {"ok": False, "error": "Not authorized"}
    payload=await request.json()
    wo_id=safe_text(payload.get("wo_id"));event_type=safe_text(payload.get("event_type")).upper()
    terminal_code=safe_text(payload.get("terminal_code"));sid=safe_text(payload.get("client_submission_id"))
    reason=safe_text(payload.get("reason"));notes=safe_text(payload.get("notes"))
    if not sid or len(sid)>128:return JSONResponse({"ok":False,"error":"Submission ID required for safe retry"},status_code=400)
    if event_type not in VALID_EVENT_TYPES:return JSONResponse({"ok":False,"error":"Invalid event"},status_code=400)
    raw=payload.get("qty")
    try:qty=None if raw in (None,"") else float(raw)
    except (TypeError,ValueError):return JSONResponse({"ok":False,"error":"Invalid quantity"},status_code=400)
    if qty is not None and (not __import__('math').isfinite(qty) or qty<0):return JSONResponse({"ok":False,"error":"Invalid quantity"},status_code=400)
    con=db()
    try:
        con.execute("BEGIN IMMEDIATE")
        wo=con.execute("SELECT * FROM work_orders WHERE wo_id=?",(wo_id,)).fetchone()
        term=con.execute("SELECT * FROM terminals WHERE terminal_code=? AND active=1",(terminal_code,)).fetchone()
        if not wo or not term:raise ValueError("Confirm the exact work order and an active station")
        if event_type in {"COMPLETE","PARTIAL_COMPLETE","REWORK"} and (qty is None or qty<=0):raise ValueError("Enter the actual quantity explicitly")
        if event_type in {"COMPLETE","PARTIAL_COMPLETE"} and qty>float(wo['qty']):raise ValueError("Quantity exceeds the work order")
        if event_type=="COMPLETE" and qty<float(wo['qty']):raise ValueError("Use PARTIAL for less than full order quantity")
        if event_type in {"HOLD","STOP","REWORK","QC_HOLD"} and not reason:raise ValueError("Enter the hold/rework reason")
        signature=json.dumps([wo_id,event_type,terminal_code,qty,reason,notes,user['username']],ensure_ascii=False)
        con.execute("CREATE TABLE IF NOT EXISTS production_submissions(request_id TEXT PRIMARY KEY,signature TEXT NOT NULL,event_id INTEGER NOT NULL)")
        old=con.execute("SELECT signature,event_id FROM production_submissions WHERE request_id=?",(sid,)).fetchone()
        if old:
            if old['signature']!=signature:raise ValueError("Submission ID reused with different data")
            event_id=old['event_id']
        else:
            now=now_iso()
            cur=con.execute("INSERT INTO events(wo_id,event_type,qty,process_name,location,terminal_code,user_name,source,reason,notes,event_time) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (wo_id,'HOLD' if event_type=='STOP' else event_type,qty,term['process_name'],term['location'],terminal_code,user['username'],'USB_OR_KEYBOARD',reason,notes,now))
            event_id=cur.lastrowid
            con.execute("INSERT INTO production_submissions VALUES(?,?,?)",(sid,signature,event_id))
            con.execute("INSERT INTO audit_log(user_name,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",(user['username'],'EVENT','WORK_ORDER',wo_id,signature,now))
        con.commit()
    except ValueError as exc:
        con.rollback();return JSONResponse({"ok":False,"error":str(exc)},status_code=400)
    finally:con.close()
    return {"ok":True,"event_id":event_id,"work_order":wo_id,"event_type":event_type,"client_submission_id":sid}



@app.get("/api/wo-search")
def api_wo_search(request: Request, q: str = ""):
    if not require_login(request):return {"ok":False,"rows":[],"error":"Login required"}
    # Never block every operator lookup while a background Plan-2026 sync runs.
    # Indexed DB lookup is immediate; the sync is started at app/page startup.
    kick_shared_plan_sync()
    q=safe_text(q); key=norm_wo(q)
    if not q:return {"ok":True,"rows":[]}
    fields="wo_id,production_code,order_no,po_no,customer_name,product_code,qty,due_date,initial_due_date,revised_due_date,sales_delivery_date,status,plan_location,plan_marker,mill_batches,section_status_json,plan_source_row"
    latest="(SELECT event_type FROM events e WHERE e.wo_id=work_orders.wo_id ORDER BY e.id DESC LIMIT 1) AS last_event_type,(SELECT process_name FROM events e WHERE e.wo_id=work_orders.wo_id ORDER BY e.id DESC LIMIT 1) AS event_process,(SELECT location FROM events e WHERE e.wo_id=work_orders.wo_id ORDER BY e.id DESC LIMIT 1) AS event_location,(SELECT event_time FROM events e WHERE e.wo_id=work_orders.wo_id ORDER BY e.id DESC LIMIT 1) AS last_event_time"
    con=db()
    exact=con.execute(f"SELECT {fields},{latest} FROM work_orders WHERE wo_id=? OR production_code=? LIMIT 15",(q,q)).fetchall()
    if exact: rows=[dict(r) for r in exact]
    else:
        prefix=q.replace("%","\\%").replace("_","\\_")+"%"
        rows=[dict(r) for r in con.execute(f"SELECT {fields},{latest} FROM work_orders WHERE wo_id LIKE ? ESCAPE '\\' OR production_code LIKE ? ESCAPE '\\' ORDER BY due_date IS NULL,due_date,id DESC LIMIT 15",(prefix,prefix)).fetchall()]
        if not rows and key:
            # Match typed/scanned WOs even when the operator omits hyphens, spaces or slashes.
            nwo=NORMALIZED_WO_SQL.format('wo_id'); npc=NORMALIZED_WO_SQL.format('production_code')
            rows=[dict(r) for r in con.execute(f"SELECT {fields},{latest} FROM work_orders WHERE {nwo}=? OR {npc}=? ORDER BY due_date IS NULL,due_date,id DESC LIMIT 15",(key,key)).fetchall()]
            if not rows:rows=[dict(r) for r in con.execute(f"SELECT {fields},{latest} FROM work_orders WHERE ({nwo}>=? AND {nwo}<?) OR ({npc}>=? AND {npc}<?) ORDER BY due_date IS NULL,due_date,id DESC LIMIT 15",(key,key+'\U0010ffff',key,key+'\U0010ffff')).fetchall()]
        if not rows:
            term="%"+q.replace("%","\\%").replace("_","\\_")+"%"
            rows=[dict(r) for r in con.execute(f"SELECT {fields},{latest} FROM work_orders WHERE order_no LIKE ? ESCAPE '\\' OR po_no LIKE ? ESCAPE '\\' OR product_code LIKE ? ESCAPE '\\' OR customer_name LIKE ? ESCAPE '\\' ORDER BY due_date IS NULL,due_date,id DESC LIMIT 15",(term,term,term,term)).fetchall()]
    con.close()
    if not rows:
        try:
            if str(PROGRAM_ROOT) not in sys.path:
                sys.path.insert(0, str(PROGRAM_ROOT))
            from suite.wo_lookup import candidate_rows
            for c in candidate_rows(q, db_file=DB_PATH, limit=15):
                rows.append({
                    "wo_id": c["wo_id"], "production_code": c["title"], "order_no": "", "po_no": "",
                    "customer_name": c.get("customer") or "", "product_code": c.get("part") or "",
                    "qty": c.get("qty"), "due_date": "", "status": "RELEASED",
                    "plan_location": "", "last_event_type": None, "event_process": None,
                    "event_location": None, "last_event_time": None, "section_status_json": "[]",
                })
        except Exception:
            pass
    event_status={"RECEIVE":"RECEIVED","START":"RUNNING","RESUME":"RUNNING","MOVE":"MOVED","PARTIAL_COMPLETE":"PARTIAL","COMPLETE":"COMPLETE","HOLD":"HOLD","REWORK":"REWORK","QC_HOLD":"QC PENDING","QC_ACCEPT":"QC ACCEPTED"}
    for row in rows:
        row['current_process']=row.get('event_process') or row.get('plan_location') or ''
        row['current_location']=row.get('event_location') or ''
        row['display_status']=event_status.get(row.get('last_event_type'),row.get('status') or 'RELEASED')
        try:
            _sec=json.loads(row.get('section_status_json') or '[]')
            row['section_summary']=' · '.join(f"{x.get('section')}: {x.get('status')}" for x in _sec[:6])
        except Exception:row['section_summary']='Plan section status unavailable'
        row['last_event_time']=row.get('last_event_time') or ''
    return {"ok":True,"rows":rows}


@app.get("/media/mobile-audits/{filename}")
def mobile_audit_media(request: Request, filename: str):
    user = require_login(request)
    if not user:
        return RedirectResponse("/login", 303)
    safe_name = Path(filename).name
    path = MOBILE_AUDIT_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(path)


@app.get("/media/qr-scans/{rel_path:path}")
def qr_scan_media(request: Request, rel_path: str):
    if not require_login(request): raise HTTPException(status_code=401,detail="Login required")
    path=(QR_SCAN_DIR/rel_path).resolve()
    if not path.is_relative_to(QR_SCAN_DIR) or not path.is_file(): raise HTTPException(status_code=404,detail="Scan image not found")
    return FileResponse(path)


@app.post("/api/mobile-audit")
async def api_mobile_audit(request: Request,
                           wo_id: str = Form(...),
                           verified_qty: Optional[float] = Form(None),
                           physical_status: str = Form("OK"),
                           physical_location: str = Form(""),
                           observed_process: str = Form(""),
                           notes: str = Form(""),
                           photo: Optional[UploadFile] = File(None)):
    user = require_login(request)
    if not user:
        return {"ok": False, "error": "Session expired — please login once again"}
    if not can(user, "mobile_capture"):
        return JSONResponse({"ok": False, "error": "Your role is not allowed to record audits", "code": "FORBIDDEN"}, status_code=403)
    audit_user = user["username"]
    wo_id = safe_text(wo_id)
    physical_status = safe_text(physical_status).upper() or "OK"
    physical_location = safe_text(physical_location)
    observed_process = safe_text(observed_process)
    notes = safe_text(notes)
    allowed = {"OK", "SHORT", "EXCESS", "NOT_FOUND", "WRONG_LOCATION", "DAMAGE", "HOLD", "OTHER"}
    if physical_status not in allowed:
        return {"ok": False, "error": "Invalid physical status"}
    if verified_qty is not None:
        try:
            verified_qty = float(verified_qty)
        except (TypeError, ValueError):
            return {"ok": False, "error": "Invalid verified quantity"}
        if verified_qty < 0:
            return {"ok": False, "error": "Verified quantity cannot be negative"}
    con = db()
    try:
        wo = con.execute("SELECT * FROM work_orders WHERE wo_id=?", (wo_id,)).fetchone()
        if not wo:
            return {"ok": False, "error": "Work Order not found"}
        created_at = now_iso()
        cur = con.execute(
            "INSERT INTO mobile_audits(wo_id,user_name,verified_qty,physical_status,physical_location,observed_process,notes,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (wo_id, audit_user, verified_qty, physical_status, physical_location, observed_process, notes, created_at),
        )
        audit_id = cur.lastrowid
        photo_name = None
        if photo and photo.filename:
            original = Path(photo.filename).name
            content_type = photo.content_type or "application/octet-stream"
            allowed_types = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
            if content_type not in allowed_types:
                con.rollback()
                return {"ok": False, "error": "Photo must be JPG, PNG, WEBP or HEIC/HEIF"}
            data = await photo.read()
            if len(data) > MOBILE_AUDIT_MAX_PHOTO_BYTES:
                con.rollback()
                return {"ok": False, "error": f"Photo is too large (maximum {MOBILE_AUDIT_MAX_PHOTO_BYTES // (1024*1024)} MB)"}
            ext = Path(original).suffix.lower()
            if ext not in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}:
                ext = ".jpg"
            photo_name = f"audit_{audit_id}_{secrets.token_hex(5)}{ext}"
            (MOBILE_AUDIT_DIR / photo_name).write_bytes(data)
            con.execute(
                "INSERT INTO mobile_audit_photos(audit_id,filename,original_name,content_type,created_at) VALUES(?,?,?,?,?)",
                (audit_id, photo_name, original, content_type, created_at),
            )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    log_audit(audit_user, "PHYSICAL_AUDIT", "WORK_ORDER", wo_id, f"status={physical_status};qty={verified_qty};location={physical_location};photo={photo_name or ''}")
    snap = get_current_snapshot(wo_id)
    return {"ok": True, "message": "Physical audit saved", "last_audit": dict(snap["last_audit"]) if snap["last_audit"] else None, "photo_url": f"/media/mobile-audits/{photo_name}" if photo_name else None, "audit_mismatch_count": snap["audit_mismatch_count"]}



def import_plan2026(path: Path, source_name: str, user_name: str):
    wb = load_workbook(path, read_only=True, data_only=True)
    if "แผนการเผา" not in wb.sheetnames:
        raise ValueError("Plan-2026 must contain sheet: แผนการเผา")
    ws = wb["แผนการเผา"]
    _source_max_col=235  # Through IA: all confirmed Plan-2026 fields used by mobile are at or before this column.
    _header_values=next(ws.iter_rows(min_row=3,max_row=3,max_col=_source_max_col,values_only=True))
    headers = [safe_text(v) for v in _header_values]
    def idx(name):
        try: return headers.index(name)
        except ValueError: return None
    ix={k:idx(v) for k,v in {"prod":"ProductionCode","orig":"กำหนดเข้าคลัง","order":"ORDER","rev":"กำหนดส่งใหม่","sales":"กำหนดส่งมอบขาย","cust":"Customername","custid":"CustomernameID","spec":"Specification","qty":"QTY","product":"รหัสสินค้า","real":"RealSpec","machine":"Machine","program":"Program","drawing":"DrawingNo.","cat":"ประเภทสินค้า","mills":"จำนวนโม่"}.items()}
    required=["prod","qty","product"]
    if any(ix[k] is None for k in required): raise ValueError("Required Plan-2026 columns not found: ProductionCode / QTY / รหัสสินค้า")
    con=db(); imported=updated=rejected=0; errors=[]
    try:
        ensure_wo_lookup_indexes(con)
        status_columns=[("Preparation","CY"),("Mixing","DH"),("Forming","DR"),("Firing","EC"),("Grinding","EL"),("Packing","EU"),("Production","FC"),("Planning","IA")]
        def _excel_zero_col(label):
            n=0
            for ch in label.upper():n=n*26+ord(ch)-64
            return n-1
        for rn,row in enumerate(ws.iter_rows(min_row=4,max_col=_source_max_col,values_only=True), start=4):
            prod=safe_text(row[ix["prod"]])
            product=safe_text(row[ix["product"]])
            qty=safe_float(row[ix["qty"]])
            if not prod or not product or qty is None:
                if prod or product: rejected+=1
                continue
            rev=row[ix["rev"]] if ix["rev"] is not None else None
            orig=row[ix["orig"]] if ix["orig"] is not None else None
            sales=row[ix["sales"]] if ix.get("sales") is not None else None
            due=orig
            due_text=due.date().isoformat() if isinstance(due,datetime) else (due.isoformat() if isinstance(due,date) else "")
            rev_text=rev.date().isoformat() if isinstance(rev,datetime) else (rev.isoformat() if isinstance(rev,date) else "")
            sales_text=sales.date().isoformat() if isinstance(sales,datetime) else (sales.isoformat() if isinstance(sales,date) else "")
            mills=safe_float(row[ix["mills"]]) if ix.get("mills") is not None else None
            _mil=[("วันที่เริ่มออกใบผลิต","Production order issued"),("Planning","Planning"),("วันที่เริ่มเตรียม","Preparation"),("รอผสม","Waiting for Mixing"),("วันที่เริ่มผสม","Mixing"),("รอขึ้นรูป","Waiting for Forming"),("วันที่เริ่มขึ้นรูป","Forming"),("รอโหลดเข้าเตา","Waiting for Kiln"),("โหลดเข้า","Kiln Loaded"),("เผา","Firing"),("โหลดออก","Kiln Unloaded"),("รอคัดกรอง","Waiting for Screening"),("วันที่เริ่มเจียร","Grinding"),("รอแพ็ค","Waiting for Packing"),("วันที่เริ่มแพ็ค","Packing"),("รอส่ง","Waiting for Dispatch"),("วันที่เริ่มส่ง","Dispatch")]
            plan_location="Planning"; plan_marker=""
            for _hn,_lab in _mil:
                _ci=idx(_hn)
                if _ci is not None and row[_ci] not in (None,"",0,0.0,False): plan_location=_lab;plan_marker=safe_text(row[_ci])
            _issued=row[1] if len(row)>1 else None
            order_date=_issued.isoformat() if isinstance(_issued,(date,datetime)) else (_issued if isinstance(_issued,str) and any(c in _issued for c in ('/','-')) else '')
            vals={k:(safe_text(row[v]) if v is not None else "") for k,v in ix.items() if k not in {"qty","orig","rev"}}
            section_status=[]
            for _sec,_col in status_columns:
                _ci=_excel_zero_col(_col);_raw=row[_ci] if _ci<len(row) else None;_value=safe_text(_raw)
                _low=_value.lower()
                _closed=bool(_value and any(k in _low for k in ("ปิด","closed","close","complete","ยกเลิก","cancel")))
                _closed=_closed or _low.strip() in {'fc','eu','closed','complete','completed','close','ปิด'}
                if any(x in _low for x in ('ยังไม่','not closed','open')):_closed=False
                from suite.plan_reader import SECTIONS
                _mapping=SECTIONS.get(_sec,{})
                _detail={}
                for _field,_letter in [('planned_date',_mapping.get('plan')),('planned_qty',_mapping.get('plan_qty')),('actual_qty',_mapping.get('done')),('actual_date',_mapping.get('actual'))]:
                    _v=row[_excel_zero_col(_letter)] if _letter and _excel_zero_col(_letter)<len(row) else None
                    _detail[_field]=_v.isoformat() if isinstance(_v,(date,datetime)) else _v
                section_status.append(dict(section=_sec,field=_col,value=_value,status='CLOSED' if _closed else 'OPEN',**_detail))
            section_status_json=json.dumps(section_status,ensure_ascii=False)
            exists=con.execute("SELECT 1 FROM work_orders WHERE wo_id=?",(prod,)).fetchone()
            if exists:
                con.execute("""UPDATE work_orders SET production_code=?,order_no=?,customer_id=?,customer_name=?,product_code=?,specification=?,real_spec=?,qty=?,due_date=?,initial_due_date=?,revised_due_date=?,sales_delivery_date=?,machine=?,program=?,drawing_no=?,product_category=?,plan_location=?,plan_marker=?,mill_batches=?,source_file=?,imported_at=?,section_status_json=?,plan_source_row=? WHERE wo_id=?""",
                    (prod,vals.get("order"),vals.get("custid"),vals.get("cust"),product,vals.get("spec"),vals.get("real"),qty,due_text,due_text,rev_text,sales_text,vals.get("machine"),vals.get("program"),vals.get("drawing"),(vals.get("cat").upper() if vals.get("cat") and vals.get("cat").upper() not in {"#N/A","N/A","NAN"} else ""),plan_location,plan_marker,mills,source_name,now_iso(),section_status_json,rn,prod)); updated+=1
            else:
                con.execute("""INSERT INTO work_orders(wo_id,production_code,order_no,customer_id,customer_name,product_code,specification,real_spec,qty,due_date,initial_due_date,revised_due_date,sales_delivery_date,order_date,machine,program,drawing_no,product_category,plan_location,plan_marker,mill_batches,source_file,imported_at,status,created_by,section_status_json,plan_source_row) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (prod,prod,vals.get("order"),vals.get("custid"),vals.get("cust"),product,vals.get("spec"),vals.get("real"),qty,due_text,due_text,rev_text,sales_text,order_date,vals.get("machine"),vals.get("program"),vals.get("drawing"),(vals.get("cat").upper() if vals.get("cat") and vals.get("cat").upper() not in {"#N/A","N/A","NAN"} else ""),plan_location,plan_marker,mills,source_name,now_iso(),"RELEASED",user_name,section_status_json,rn)); imported+=1
        con.commit()
    except Exception:
        con.rollback(); raise
    finally: con.close(); wb.close()
    return imported,updated,rejected,errors

@app.get("/plan-upload", response_class=HTMLResponse)
def plan_upload_page(request: Request):
    user=require_login(request)
    if not user or not can(user,"workorder"): return RedirectResponse("/login?next=/plan-upload",303)
    return HTMLResponse(render(request,"plan_upload.html",result=None))

@app.post("/plan-upload", response_class=HTMLResponse)
def plan_upload(request: Request, file: UploadFile=File(...)):
    user=require_login(request)
    if not user or not can(user,"workorder"): return RedirectResponse("/login?next=/plan-upload",303)
    if Path(file.filename or "").suffix.lower() not in {".xlsx",".xlsm"}:
        return HTMLResponse(render(request,"plan_upload.html",result={"error":"Please upload Plan-2026 .xlsx/.xlsm only"}),status_code=400)
    dest=UPLOADS/f"PLAN_{bkk_now().strftime('%Y%m%d_%H%M%S')}_{Path(file.filename).name}"
    dest.write_bytes(file.file.read())
    try:
        a,b,c,e=import_plan2026(dest,Path(file.filename).name,user["username"])
        shared_company=Path(os.environ.get("SL_COMPANY_DATA",str(SHARED_ROOT/"COMPANY_DATA"))).resolve();shared_company.mkdir(parents=True,exist_ok=True)
        shared=shared_company/"Plan-2026-LATEST.xlsx"
        shared.write_bytes(dest.read_bytes())
        # Keep a software-owned evidence copy; never modify the user's original source file.
        stamp=bkk_now().strftime('%Y%m%d_%H%M%S')
        source_copy=SOURCE_COPY_ROOT/f"{stamp}_{Path(file.filename).name}"
        source_copy.write_bytes(dest.read_bytes())
        qr_out=None
        log_audit(user["username"],"IMPORT_PLAN2026","WORKBOOK",Path(file.filename).name,f"new={a};updated={b};rejected={c};source_copy={source_copy}")
        return HTMLResponse(render(request,"plan_upload.html",result={"imported":a,"updated":b,"rejected":c,"errors":e,"qr_report":str(qr_out) if qr_out else None,"source_copy":str(source_copy)}))
    except Exception as ex:
        return HTMLResponse(render(request,"plan_upload.html",result={"error":str(ex)}),status_code=400)


@app.get("/qr/work-order/{wo_id}")
def qr_work_order(request: Request, wo_id: str):
    user=require_login(request)
    if not user:return RedirectResponse('/login',303)
    con=db(); row=con.execute("SELECT wo_id FROM work_orders WHERE wo_id=? OR production_code=?",(wo_id,wo_id)).fetchone();con.close()
    if not row: raise HTTPException(status_code=404,detail='Work Order not found')
    mode = request.query_params.get("mode", "code")
    if mode not in {"code", "url"}: raise HTTPException(status_code=400,detail="Invalid QR mode")
    try: path=create_qr_png(row['wo_id'],mode=mode)
    except ValueError as ex: raise HTTPException(status_code=400,detail=str(ex))
    return FileResponse(path,media_type='image/png',filename=f"{row['wo_id']}_QR.png")


@app.get("/qr-generator", response_class=HTMLResponse)
def qr_generator(request: Request):
    user=require_login(request)
    if not user:return RedirectResponse('/login?next=/qr-generator',303)
    configured=bool(os.environ.get("SL_PUBLIC_URL", "").strip())
    con=db(); rows=con.execute("SELECT wo_id,production_code,product_code,customer_name,qty FROM work_orders ORDER BY id DESC LIMIT 250").fetchall();con.close()
    return HTMLResponse(render(request,"qr_generator.html",rows=rows,configured=configured,stable_url=os.environ.get("SL_PUBLIC_URL", ""),qr_root=str(QR_DIR)))


@app.get("/qr-label-pack")
def qr_label_pack(request: Request, mode: str = "code"):
    user=require_login(request)
    if not user:return RedirectResponse('/login',303)
    if mode not in {"code", "url"}: raise HTTPException(status_code=400,detail="Invalid QR mode")
    con=db(); all_rows=con.execute("SELECT wo_id,production_code,product_code,customer_name,qty FROM work_orders ORDER BY wo_id").fetchall(); con.close()
    ids=[r["wo_id"] for r in all_rows]
    if not ids: raise HTTPException(status_code=404,detail="No work orders found")
    base=os.environ.get("SL_PUBLIC_URL", "") if mode == "url" else ""
    if mode == "url" and not base: raise HTTPException(status_code=400,detail="Set SL_PUBLIC_URL to a stable URL first")
    out=REPORT_ROOT/f"QR_LABELS_{bkk_now().strftime('%Y%m%d_%H%M%S')}_{mode}.xlsx"
    wb=Workbook(); ws=wb.active; ws.title="QR LABELS"
    ws.append(["WORK ORDER","Production Code","Product","Customer","Qty","QR payload","QR label","PNG server path"])
    ws.freeze_panes="A2"; ws.auto_filter.ref=f"A1:H{len(all_rows)+1}"
    for col,width in {"A":22,"B":24,"C":32,"D":28,"E":12,"F":30,"G":18,"H":72}.items():ws.column_dimensions[col].width=width
    for row in all_rows:
        wid=row["wo_id"]
        png=create_qr_png(wid,base,mode)
        ws.append([row["wo_id"],row["production_code"],row["product_code"],row["customer_name"],row["qty"],qr_payload(wid,base,mode),"",str(png)])
        excel_row=ws.max_row; ws.row_dimensions[excel_row].height=82
        image=XLImage(str(png)); image.width=105;image.height=105;ws.add_image(image,f"G{excel_row}")
    wb.save(out)
    log_audit(user["username"],"GENERATE_QR_PACK","WORK_ORDER","ALL",f"count={len(ids)};mode={mode};path={out}")
    return FileResponse(out,filename=out.name)

@app.get("/audit-history", response_class=HTMLResponse)
def audit_history(request: Request):
    user=require_login(request)
    if not user:return RedirectResponse('/login?next=/audit-history',303)
    con=db(); audits=con.execute("SELECT a.*,p.filename photo_file FROM mobile_audits a LEFT JOIN mobile_audit_photos p ON p.audit_id=a.id ORDER BY a.created_at DESC LIMIT 1000").fetchall();events=con.execute("SELECT * FROM events ORDER BY event_time DESC LIMIT 1000").fetchall();unknown=con.execute("SELECT * FROM unidentified_parts ORDER BY created_at DESC LIMIT 500").fetchall(); scans=con.execute("SELECT * FROM qr_scan_log ORDER BY created_at DESC,id DESC LIMIT 1000").fetchall();con.close()
    scans=[dict(s)|{"photo_rel":Path(s["photo_path"]).relative_to(QR_SCAN_DIR).as_posix() if s["photo_path"] and Path(s["photo_path"]).is_relative_to(QR_SCAN_DIR) else None} for s in scans]
    return HTMLResponse(render(request,'audit_history.html',audits=audits,events=events,unknown=unknown,scans=scans,db_path=str(DB_PATH),photo_root=str(PHOTO_ROOT)))

@app.get("/audit-history/report.xlsx")
def audit_history_report(request: Request):
    user=require_login(request)
    if not user or not can(user,"export"):
        return RedirectResponse('/login?next=/audit-history/report.xlsx',303)
    con=db()
    audits=con.execute("SELECT a.*,p.filename photo_file,p.original_name photo_original,p.content_type photo_type FROM mobile_audits a LEFT JOIN mobile_audit_photos p ON p.audit_id=a.id ORDER BY a.created_at DESC").fetchall()
    scans=con.execute("SELECT * FROM qr_scan_log ORDER BY created_at DESC,id DESC").fetchall()
    con.close()
    wb=Workbook(); ws=wb.active; ws.title='Physical audit report'
    ws.append(['Audit ID','Date/time','Work Order','Auditor','Verified qty','Status','Physical location / GPS','Observed process','Notes','Photo','Photo stored path','Photo URL','Photo SHA-256'])
    ws.freeze_panes='A2'; ws.auto_filter.ref=f'A1:M{len(audits)+1}'
    for col,width in {'A':12,'B':23,'C':24,'D':18,'E':14,'F':18,'G':45,'H':22,'I':45,'J':24,'K':70,'L':48,'M':68}.items(): ws.column_dimensions[col].width=width
    for a in audits:
        photo_file=a['photo_file']
        photo_path=(MOBILE_AUDIT_DIR/Path(photo_file).name) if photo_file else None
        digest=hashlib.sha256(photo_path.read_bytes()).hexdigest() if photo_path and photo_path.is_file() else ''
        row=[a['id'],a['created_at'],a['wo_id'],a['user_name'],a['verified_qty'],a['physical_status'],a['physical_location'],a['observed_process'],a['notes'],photo_file or 'No photo',str(photo_path.resolve()) if photo_path and photo_path.is_file() else '',f'/media/mobile-audits/{Path(photo_file).name}' if photo_file else '',digest]
        ws.append(row); rn=ws.max_row
        if photo_path and photo_path.is_file():
            try:
                from PIL import Image as PILImage
                im=PILImage.open(photo_path); im.thumbnail((240,150)); buf=io.BytesIO(); im.convert('RGB').save(buf,format='JPEG',quality=72,optimize=True); buf.seek(0)
                xl=XLImage(buf); xl.width=120; xl.height=max(1,int(120*im.height/max(im.width,1))); ws.add_image(xl,f'J{rn}'); ws.row_dimensions[rn].height=82
            except Exception: pass
        if photo_file: ws.cell(rn,12).hyperlink=f'/media/mobile-audits/{Path(photo_file).name}'; ws.cell(rn,12).style='Hyperlink'
    scan_ws=wb.create_sheet('QR scan log'); scan_ws.append(['Date/time','Work Order','Payload','Operator','Method','Result','Photo stored path','Photo URL','Photo SHA-256'])
    scan_ws.freeze_panes='A2'; scan_ws.auto_filter.ref=f'A1:I{len(scans)+1}'
    for s in scans:
        pp=Path(s['photo_path']) if s['photo_path'] else None
        scan_ws.append([s['created_at'],s['wo_id'],s['payload'],s['scanned_by'],s['scan_method'],s['result'],str(pp) if pp else '',f"/media/qr-scans/{pp.relative_to(QR_SCAN_DIR).as_posix()}" if pp and pp.is_relative_to(QR_SCAN_DIR) else '',s['photo_sha256'] or ''])
    for sheet in [ws,scan_ws]:
        for cell in sheet[1]: cell.font=Font(bold=True,color='FFFFFF'); cell.fill=PatternFill('solid',fgColor='E76613'); cell.alignment=Alignment(wrap_text=True)
        sheet.sheet_view.showGridLines=False
    out=io.BytesIO(); wb.save(out); out.seek(0)
    return StreamingResponse(io.BytesIO(out.getvalue()),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="SL_Audit_Photo_Trace_{bkk_now():%Y%m%d_%H%M%S}.xlsx"'})

def _tls_files():
    repo = BASE.parent.parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from suite.tls_certs import ensure_certs
    return ensure_certs(SHARED_ROOT)


@app.get("/tls/ca.crt")
def tls_ca():
    info = _tls_files()
    return FileResponse(str(info["ca"]), media_type="application/x-x509-ca-cert", filename="sl-carborundum-ca.crt")


@app.get("/tls/server.crt")
def tls_server():
    info = _tls_files()
    return FileResponse(str(info["cert"]), media_type="application/x-x509-ca-cert", filename="sl-carborundum-server.crt")


@app.get("/export/control-pack")
def export_control_pack(request: Request):
    user = require_login(request)
    if not user or not can(user, "export"):
        return RedirectResponse("/dashboard", 303)
    snaps = all_snapshots()
    wb = Workbook()
    ws = wb.active
    ws.title = "WO_STATUS"
    headers = ["WO ID","Production Code","Order No","PO","Customer","Product","Order Qty","Produced","Accepted","Rework","Remaining","Status","Current Process","Current Location","Due Date","Last Scan","Last Audit","Verified Qty","Audit Status","Audit Location","Audit Photo"]
    ws.append(headers)
    for c in ws[1]: c.font=Font(bold=True,color="FFFFFF"); c.fill=PatternFill("solid",fgColor="1F4E78")
    for s in snaps:
        la=s.get("last_audit")
        ws.append([s["wo"]["wo_id"],s["wo"]["production_code"],s["wo"]["order_no"],s["wo"]["po_no"],s["wo"]["customer_name"],s["wo"]["product_code"],s["wo"]["qty"],s["produced"],s["accepted"],s["rework"],s["remaining"],STATUS_LABELS.get(s["status"],s["status"]),s["current_process"],s["current_location"],s["wo"]["due_date"],s["last_event"]["event_time"] if s["last_event"] else "",la["created_at"] if la else "",la["verified_qty"] if la else "",la["physical_status"] if la else "",la["physical_location"] if la else "",f"/media/mobile-audits/{s['last_audit_photo']['filename']}" if s.get('last_audit_photo') else ""])
    for i in range(1,len(headers)+1): ws.column_dimensions[get_column_letter(i)].width=min(max(len(headers[i-1])+2,12),28)

    ev = wb.create_sheet("EVENT_HISTORY")
    evh=["Time","WO ID","Event","Qty","Process","Location","Terminal","User","Source","Reason","Notes"]
    ev.append(evh)
    for c in ev[1]: c.font=Font(bold=True,color="FFFFFF"); c.fill=PatternFill("solid",fgColor="1F4E78")
    con=db(); events=con.execute("SELECT * FROM events ORDER BY event_time,id").fetchall(); audits=con.execute("SELECT * FROM mobile_audits ORDER BY created_at,id").fetchall(); audit_photos=con.execute("SELECT * FROM mobile_audit_photos ORDER BY id").fetchall(); con.close()
    photo_by_audit={a["audit_id"]: a for a in audit_photos}
    for e in events: ev.append([e["event_time"],e["wo_id"],EVENT_LABELS.get(e["event_type"],e["event_type"]),e["qty"],e["process_name"],e["location"],e["terminal_code"],e["user_name"],e["source"],e["reason"],e["notes"]])
    for i in range(1,len(evh)+1): ev.column_dimensions[get_column_letter(i)].width=min(max(len(evh[i-1])+2,12),28)

    au=wb.create_sheet("PHYSICAL_AUDIT")
    auh=["Audit ID","Audit Time","WO ID","User","Verified Qty","Physical Status","Physical Location","Observed Process","Notes","Photo File","Photo URL"]
    au.append(auh)
    for c in au[1]: c.font=Font(bold=True,color="FFFFFF"); c.fill=PatternFill("solid",fgColor="1F4E78")
    for a in audits:
        ph=photo_by_audit.get(a["id"])
        au.append([a["id"],a["created_at"],a["wo_id"],a["user_name"],a["verified_qty"],a["physical_status"],a["physical_location"],a["observed_process"],a["notes"],ph["filename"] if ph else "",f"/media/mobile-audits/{ph['filename']}" if ph else ""])
    for i in range(1,len(auh)+1): au.column_dimensions[get_column_letter(i)].width=min(max(len(auh[i-1])+2,14),32)

    wi=wb.create_sheet("WIP_SUMMARY")
    wi.append(["Current Process","WIP pcs"])
    for c in wi[1]: c.font=Font(bold=True,color="FFFFFF"); c.fill=PatternFill("solid",fgColor="1F4E78")
    _,wip,_=dashboard_stats()
    for p,q in wip: wi.append([p,q])
    wi.column_dimensions["A"].width=24; wi.column_dimensions["B"].width=14

    ex=wb.create_sheet("EXCEPTIONS")
    ex.append(["Type","WO ID","Product","Status","Current Process","Due Date","Last Scan","Last Audit"])
    for c in ex[1]: c.font=Font(bold=True,color="FFFFFF"); c.fill=PatternFill("solid",fgColor="1F4E78")
    _,_,exceptions=dashboard_stats()
    for typ,s in exceptions:
        ex.append([typ,s["wo"]["wo_id"],s["wo"]["product_code"],STATUS_LABELS.get(s["status"],s["status"]),s["current_process"],s["wo"]["due_date"],s["last_event"]["event_time"] if s["last_event"] else "",s["last_audit"]["created_at"] if s.get("last_audit") else ""])
    for i,w in enumerate([20,20,24,20,20,16,22,22],1): ex.column_dimensions[get_column_letter(i)].width=w

    out=UPLOADS/f"SL_CONTROL_PACK_{bkk_now().strftime('%Y%m%d_%H%M%S')}.xlsx"; wb.save(out); wb.close()
    log_audit(user["username"],"EXPORT","CONTROL_PACK",out.name)
    return FileResponse(out,filename=out.name)

@app.get('/source/plan2026')
def floor_plan_source(request: Request):
    if not require_login(request):return RedirectResponse('/login',303)
    from suite.central_paths import resolve_plan
    path=resolve_plan()
    if not path or not Path(path).is_file():raise HTTPException(404,'Plan 2026 source not loaded')
    return FileResponse(path,filename='Plan-2026.xlsx')


@app.get('/source/production-status')
def floor_production_source(request: Request):
    if not require_login(request):return RedirectResponse('/login',303)
    path=DB_PATH.parent/'production_analytics.sqlite'
    if not path.exists():raise HTTPException(404,'Production status source not loaded')
    with sqlite3.connect(path) as con:
        exists=con.execute("SELECT 1 FROM sqlite_master WHERE name='evidence_documents'").fetchone()
        row=con.execute("SELECT original FROM evidence_documents WHERE role='production_status' ORDER BY revision DESC,id DESC LIMIT 1").fetchone() if exists else None
    if not row:raise HTTPException(404,'Production status source not loaded')
    return StreamingResponse(io.BytesIO(row[0]),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="Production-Status.xlsx"'})


@app.get("/api/wo/{wo_id:path}")
def api_wo(request: Request, wo_id: str):
    _sync=kick_shared_plan_sync(wait_s=1.5)
    user = require_login(request)
    if not user:
        return {"ok": False, "error": "Not logged in"}
    from suite.scanner_lookup import exact_work_orders
    con=db()
    try: rows=exact_work_orders(con,qr_value_to_wo(wo_id))
    finally: con.close()
    if len(rows)>1:
        return JSONResponse({"ok":False,"error":"Several orders match. Scan the full WO identity.","code":"AMBIGUOUS"},status_code=409)
    if not rows: return JSONResponse({"ok":False,"error":"Work Order not found"},status_code=404)
    snap=get_current_snapshot(rows[0]["wo_id"])
    w=dict(snap["wo"])
    from suite.wo_evidence import production_rows
    evidence=production_rows(DB_PATH.parent/'production_analytics.sqlite',w['wo_id'])
    con=db()
    route=[dict(r) for r in con.execute('SELECT process_name,planned_date FROM routes WHERE wo_id=? ORDER BY seq',(w['wo_id'],))]
    con.close()
    if snap.get('last_audit') and snap.get('last_audit_photo'):
        _photo=snap['last_audit_photo']['filename']
        _audit=dict(snap['last_audit']);_audit['photo_url']='/media/mobile-audits/'+_photo
    else:_audit=dict(snap['last_audit']) if snap.get('last_audit') else None
    # Read imported and indexed records, not a full workbook per scan.
    return {'source_sync':dict(_sync or {}),'production_evidence':evidence,'route':route,"ok":True,"wo":w,"status":snap["status"],"whole_order_decision":snap.get("whole_order_decision"),"plan_status":w.get("plan_location") or "Planning",
        "section_status":snap["section_status"],"current_process":snap["current_process"],
        "current_location":snap["current_location"],"produced":snap["produced"],"accepted":snap["accepted"],
        "rework":snap["rework"],"remaining":snap["remaining"],
        "last_event":dict(snap["last_event"]) if snap["last_event"] else None,
        "last_audit":_audit}


@app.post("/api/order-status")
async def whole_order_status(request: Request):
    user=require_login(request)
    if not user:return JSONResponse({"ok":False,"error":"Sign in first"},status_code=401)
    payload=await request.json()
    try:
        from suite.order_status import save
        wo=safe_text(payload.get('wo_id'));status=safe_text(payload.get('status')).upper()
        sid=safe_text(payload.get('client_submission_id'))
        if not sid or len(sid)>128:raise ValueError('Valid submission ID required')
        event=save(DB_PATH,wo,status,safe_text(payload.get('remark')),user['username'],sid)
        return {'ok':True,'work_order':wo,'section':'WHOLE WO','status':status,'event_id':sid,'saved_at':now_iso(),'record_id':event}
    except ValueError as exc:return JSONResponse({'ok':False,'error':str(exc)},status_code=400)


@app.get('/tracking-reports',response_class=HTMLResponse)
def tracking_reports_page(request: Request):
    if not require_login(request):return RedirectResponse('/login?next=/tracking-reports',303)
    return HTMLResponse(render(request,'tracking_reports.html',today=bkk_now().date().isoformat()))


@app.get('/tracking-reports.xlsx')
def tracking_report_excel(request: Request,start: str,end: str):
    user=require_login(request)
    if not user:return JSONResponse({'ok':False,'error':'Sign in first'},status_code=401)
    try:
        first=date.fromisoformat(start);last=date.fromisoformat(end)
        if first>last:raise ValueError('Start must be before end')
        from suite.tracking_reports import excel
        root=Path(os.environ.get('SL_COMPANY_DATA',str(SHARED_ROOT/'COMPANY_DATA')))
        data=excel(DB_PATH,root,first,last)
        target=REPORT_ROOT/('WIP_Status_'+bkk_now().strftime('%Y%m%d_%H%M%S_%f')+'.xlsx')
        target.write_bytes(data)
        log_audit(user['username'],'EXPORT','TRACKING_REPORT',target.name)
        return FileResponse(target,filename=target.name)
    except ValueError as exc:return JSONResponse({'ok':False,'error':str(exc)},status_code=400)


@app.get("/api/section-history")
def section_history(request: Request, wo_id: str):
    user=require_login(request)
    if not user:return JSONResponse({"ok":False,"error":"Sign in first"},status_code=401)
    con=db()
    try:
        from suite.scanner_lookup import exact_work_orders
        matches=exact_work_orders(con,qr_value_to_wo(wo_id))
    finally:con.close()
    if len(matches)!=1:return JSONResponse({"ok":False,"error":"Confirm one exact WO"},status_code=400)
    from suite.floor_open_close import DB_NAME, COLS
    root=Path(os.environ.get("SL_COMPANY_DATA",str(SHARED_ROOT/"COMPANY_DATA"))).resolve()
    rows=[]
    if (root/DB_NAME).exists():
        with sqlite3.connect(root/DB_NAME,timeout=15) as con:
            rows=con.execute("SELECT time,wo,section,status,actual_qty,quantity_unknown,remark,user,event_id,source_ref,source_row FROM section_status WHERE wo=? ORDER BY id DESC LIMIT 100",(matches[0]["wo_id"],)).fetchall()
    whole=[]
    with db() as con:
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='wo_status_events'").fetchone():
            items=con.execute('SELECT * FROM wo_status_events WHERE wo=? ORDER BY id DESC LIMIT 100',(matches[0]['wo_id'],)).fetchall()
            whole=[{'Time':r['recorded_at'],'Section':'WHOLE WO','Status':r['status'],'Actual Qty':None,'User':r['user'],'Event ID':r['submission_id'],'Remark':r['reason'],'Source reference':r['source'],'Plan row':''} for r in items]
    return {"ok":True,"rows":[dict(zip(COLS,row)) for row in rows],"whole_rows":whole,"limit":100}


@app.post("/api/section-status")
async def mobile_section_status(request: Request):
    """Append a mobile OPEN/CLOSED event to the same CENTRAL_DATA ledger as desktop."""
    user=require_login(request)
    if not user:return JSONResponse({"ok":False,"error":"Session expired — please login once again"},status_code=401)
    if not can(user,"mobile_capture"):return JSONResponse({"ok":False,"error":"Not allowed to record status"},status_code=403)
    payload=await request.json()
    wo_id=safe_text(payload.get("wo_id")); section=safe_text(payload.get("section")); status=safe_text(payload.get("status")).upper()
    if status not in {"OPEN","CLOSED"}:return JSONResponse({"ok":False,"error":"Status must be OPEN or CLOSED"},status_code=400)
    con=db()
    try:
        from suite.scanner_lookup import exact_work_orders
        rows=exact_work_orders(con,qr_value_to_wo(wo_id))
        row=rows[0] if len(rows)==1 else None
    finally:con.close()
    if not row:return JSONResponse({"ok":False,"error":"Work Order not found in active Plan-2026"},status_code=404)
    from suite.floor_open_close import save_entry, SECTIONS
    from suite.wo_lookup import norm_wo
    canonical=row["wo_id"]
    section_match=next((s for s in SECTIONS if s.casefold()==section.casefold()),None)
    if not section_match:return JSONResponse({"ok":False,"error":"Choose a valid production section"},status_code=400)
    request_id=safe_text(payload.get("client_submission_id"))
    if not request_id or len(request_id)>128:return JSONResponse({"ok":False,"error":"A submission ID is required for safe retry"},status_code=400)
    qty_raw=payload.get("actual_qty")
    try:qty=None if qty_raw is None or str(qty_raw).strip()=="" else float(qty_raw)
    except (TypeError,ValueError):return JSONResponse({"ok":False,"error":"Actual quantity must be numeric or blank"},status_code=400)
    if qty is not None and (qty<0 or not __import__('math').isfinite(qty)):return JSONResponse({"ok":False,"error":"Actual quantity must be a non-negative finite number"},status_code=400)
    data_root=Path(os.environ.get("SL_COMPANY_DATA",str(SHARED_ROOT/"COMPANY_DATA"))).resolve()
    try:
        saved=save_entry(data_root,canonical,section_match,status,qty,safe_text(payload.get("remark")),user["username"],canonical_wo=canonical,
            event_id=request_id,source_ref=f"Shared USB / search; source={row['source_file'] or 'shared WO database'}; imported={row['imported_at'] or 'unrecorded'}",source_row=str(row["plan_source_row"] or ""),qty_unknown=qty is None)
        return {"ok":True,"work_order":canonical,"section":section_match,"status":status,"saved_at":saved.get("Time"),"event_id":saved.get("Event ID"),"ledger":str(data_root/"daily_status_entries.sqlite3")}
    except Exception as exc:
        return JSONResponse({"ok":False,"error":str(exc)},status_code=400)


@app.get("/2026-plan", response_class=HTMLResponse)
def plan_2026(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse("/dashboard", 303)
    con = db()
    rows = con.execute("SELECT * FROM work_orders WHERE due_date IS NOT NULL ORDER BY due_date, customer_name, product_code").fetchall()
    con.close()
    monthly = {}
    for r in rows:
        month = r["due_date"][:7]
        monthly.setdefault(month, {"orders":0, "qty":0.0})
        monthly[month]["orders"] += 1
        monthly[month]["qty"] += float(r["qty"] or 0)
    return HTMLResponse(render(request, "plan.html", rows=[get_current_snapshot(r["wo_id"]) for r in rows], monthly=sorted(monthly.items())))


@app.get("/mps", response_class=HTMLResponse)
def mps(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse("/login", 303)
    con = db()
    rows = con.execute("SELECT customer_name,product_code,due_date,qty FROM work_orders WHERE due_date IS NOT NULL ORDER BY due_date").fetchall()
    con.close()
    agg = {}
    for r in rows:
        key = (r["due_date"][:7], r["customer_name"] or "", r["product_code"] or "")
        agg[key] = agg.get(key, 0) + float(r["qty"] or 0)
    return HTMLResponse(render(request, "mps.html", rows=[(*k,v) for k,v in sorted(agg.items())]))


@app.get("/mrp", response_class=HTMLResponse)
def mrp(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse("/login", 303)
    con = db()
    rows = con.execute(
        """SELECT substr(w.due_date,1,7) month, m.material_code, SUM(m.required_qty) required_qty, COUNT(DISTINCT w.wo_id) wo_count
           FROM work_order_materials m JOIN work_orders w ON w.wo_id=m.wo_id
           WHERE w.due_date IS NOT NULL GROUP BY substr(w.due_date,1,7),m.material_code ORDER BY month,m.material_code"""
    ).fetchall()
    con.close()
    return HTMLResponse(render(request, "mrp.html", rows=rows))


@app.get("/export/work-orders")
def export_workorders(request: Request):
    user = require_login(request)
    if not user or not can(user, "export"):
        return RedirectResponse("/dashboard", 303)
    snaps = all_snapshots()
    wb = Workbook()
    ws = wb.active
    ws.title = "Work Orders"
    headers = ["WO ID", "Production Code", "Customer", "Product", "Order Qty", "Produced", "Accepted", "Rework", "Remaining", "Status", "Current Process", "Location", "Due Date", "Machine", "Program", "Last Event"]
    ws.append(headers)
    for h in ws[1]:
        h.font = Font(bold=True, color="FFFFFF")
        h.fill = PatternFill("solid", fgColor="1F4E78")
    for s in snaps:
        ws.append([
            s["wo"]["wo_id"], s["wo"]["production_code"], s["wo"]["customer_name"], s["wo"]["product_code"], s["wo"]["qty"],
            s["produced"], s["accepted"], s["rework"], s["remaining"], STATUS_LABELS.get(s["status"], s["status"]),
            s["current_process"], s["current_location"], s["wo"]["due_date"], s["wo"]["machine"], s["wo"]["program"],
            s["last_event"]["event_time"] if s["last_event"] else "",
        ])
    for i in range(1, len(headers)+1):
        ws.column_dimensions[get_column_letter(i)].width = min(max(len(headers[i-1]) + 2, 12), 28)
    out = UPLOADS / f"WO_STATUS_{bkk_now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    wb.save(out)
    wb.close()
    log_audit(user["username"], "EXPORT", "WORK_ORDERS", out.name)
    return FileResponse(out, filename=out.name)


@app.get("/admin/terminals", response_class=HTMLResponse)
def terminals_page(request: Request):
    user = require_login(request)
    if not user or not can(user, "all"):
        return RedirectResponse("/dashboard", 303)
    con = db(); rows = con.execute("SELECT * FROM terminals ORDER BY terminal_code").fetchall(); con.close()
    return HTMLResponse(render(request, "terminals.html", rows=rows))


@app.post("/admin/terminals")
def terminals_create(request: Request, terminal_code: str = Form(...), process_name: str = Form(...), location: str = Form(...)):
    user = require_login(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/dashboard", 303)
    con = db()
    con.execute("INSERT OR REPLACE INTO terminals(terminal_code,process_name,location,active) VALUES(?,?,?,1)", (terminal_code.strip(), process_name.strip(), location.strip()))
    con.commit(); con.close()
    log_audit(user["username"], "CREATE", "TERMINAL", terminal_code)
    return RedirectResponse("/admin/terminals", 303)


@app.get("/health")
def health():
    return {
        "ok": True,
        "work_orders": work_orders_in_db(),
        "db": str(DB_PATH),
        "http": True,
        "plan_sync_running": bool(_SYNC_STATE.get("running")),
    }


import audit_v2  # noqa: E402  (needs the routes/helpers above)
AUDIT_V2_MIGRATION = audit_v2.install(sys.modules[__name__])
