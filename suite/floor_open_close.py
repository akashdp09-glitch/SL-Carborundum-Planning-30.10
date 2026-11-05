"""Shop-floor work-order OPEN / CLOSED by section.

This is the per-WO, per-section entry (scan or type). It is not the monthly
October-2026.xls register (that file is JOB vs Item counts by product category).
Nothing here invents a work order — lookup uses Plan-2026 already on Home.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import sqlite3
import uuid
import math

from .common import bkk_now, bkk_today
from .customer_names import localize_customer_columns, read_ui_language

SECTIONS = [
    "Preparation", "Mixing", "Forming", "Firing", "Grinding",
    "Cutting", "Packing", "QC", "Warehouse", "Dispatch", "Other",
]
STATUSES = ["OPEN", "CLOSED", "RUNNING", "WAITING", "HOLD", "PROBLEM", "COMPLETE"]
CSV_NAME = "daily_status_entries.csv"
DB_NAME = "daily_status_entries.sqlite3"
COLS = ["Time", "Work Order", "Section", "Status", "Actual Qty", "Quantity Unknown", "Remark", "User", "Event ID", "Source reference", "Plan row"]


def confirmed_candidate(query: str, candidates) -> Optional[str]:
    """Auto-confirm only an exact normalized WO; fuzzy matches need explicit selection."""
    from suite.wo_lookup import norm_wo
    q = norm_wo(query)
    exact = [str(wo) for wo in candidates if norm_wo(wo) == q] if q else []
    return exact[0] if len(exact) == 1 else None


def entries_path(data_dir) -> Path:
    return Path(data_dir) / CSV_NAME


def load_entries(data_dir) -> pd.DataFrame:
    root = Path(data_dir)
    db = root / DB_NAME
    if db.exists():
        with sqlite3.connect(db, timeout=10) as c:
            c.execute("PRAGMA busy_timeout=10000")
            c.execute("""CREATE TABLE IF NOT EXISTS section_status(
                id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL UNIQUE,time TEXT NOT NULL,
                wo TEXT NOT NULL,section TEXT NOT NULL,status TEXT NOT NULL,actual_qty REAL,
                quantity_unknown INTEGER NOT NULL DEFAULT 0,remark TEXT,user TEXT)""")
            _cols={r[1] for r in c.execute("PRAGMA table_info(section_status)").fetchall()}
            if "quantity_unknown" not in _cols: c.execute("ALTER TABLE section_status ADD COLUMN quantity_unknown INTEGER NOT NULL DEFAULT 0")
            if "source_ref" not in _cols: c.execute("ALTER TABLE section_status ADD COLUMN source_ref TEXT")
            if "source_row" not in _cols: c.execute("ALTER TABLE section_status ADD COLUMN source_row TEXT")
            rows = c.execute("SELECT time,wo,section,status,actual_qty,quantity_unknown,remark,user,event_id,source_ref,source_row FROM section_status ORDER BY id DESC LIMIT 5000").fetchall()
        if rows:
            return pd.DataFrame(rows, columns=COLS).iloc[::-1].reset_index(drop=True)
    p = entries_path(data_dir)
    if not p.exists() or p.stat().st_size == 0:
        return pd.DataFrame(columns=COLS)
    try:
        df = pd.read_csv(p)
    except Exception:
        return pd.DataFrame(columns=COLS)
    for c in COLS:
        if c not in df.columns:
            df[c] = ""
    return df[COLS]


def save_entry(data_dir, wo: str, section: str, status: str, qty=0.0, remark="", user="", *, canonical_wo: Optional[str] = None, event_id: Optional[str] = None, source_ref: str = "", source_row: str = "", qty_unknown: bool = False) -> dict:
    wo = str(wo or "").strip()
    if not wo:
        raise ValueError("Work Order is required.")
    if not canonical_wo:
        raise ValueError("Confirm the work order against Plan-2026 or the shared WO database before saving.")
    from suite.wo_lookup import norm_wo
    if norm_wo(wo) != norm_wo(canonical_wo):
        raise ValueError("The confirmed work order does not match the scanned or typed value.")
    if section not in SECTIONS:
        raise ValueError("Choose a valid production section.")
    if status not in set(STATUSES) | {"UNIDENTIFIED"}:
        raise ValueError("Choose a valid status.")
    if qty is not None and (not math.isfinite(float(qty)) or float(qty) < 0):
        raise ValueError("Quantity must be blank/unknown or a finite non-negative number.")
    row = {
        "Time": bkk_now().isoformat(timespec="seconds"),
        "Work Order": wo,
        "Section": section,
        "Status": status,
        "Actual Qty": None if qty_unknown else qty,
        "Quantity Unknown": bool(qty_unknown or qty is None),
        "Remark": remark,
        "User": user,
        "Event ID": str(event_id or uuid.uuid4().hex),
        "Source reference": str(source_ref or ""),
        "Plan row": str(source_row or ""),
    }
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(root / DB_NAME, timeout=15) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=FULL")
        c.execute("PRAGMA busy_timeout=15000")
        c.execute("""CREATE TABLE IF NOT EXISTS section_status(
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
            time TEXT NOT NULL, wo TEXT NOT NULL, section TEXT NOT NULL, status TEXT NOT NULL,
            actual_qty REAL, quantity_unknown INTEGER NOT NULL DEFAULT 0, remark TEXT, user TEXT,
            source_ref TEXT, source_row TEXT)""")
        _cols={r[1] for r in c.execute("PRAGMA table_info(section_status)").fetchall()}
        if "quantity_unknown" not in _cols: c.execute("ALTER TABLE section_status ADD COLUMN quantity_unknown INTEGER NOT NULL DEFAULT 0")
        if "source_ref" not in _cols: c.execute("ALTER TABLE section_status ADD COLUMN source_ref TEXT")
        if "source_row" not in _cols: c.execute("ALTER TABLE section_status ADD COLUMN source_row TEXT")
        c.execute("CREATE INDEX IF NOT EXISTS ix_section_status_time ON section_status(time)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_section_status_wo ON section_status(wo,id DESC)")
        legacy = entries_path(root)
        imported = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='legacy_status_import'").fetchone()
        if not imported and legacy.exists():
            c.execute("CREATE TABLE legacy_status_import(done INTEGER NOT NULL)")
            try:
                old = pd.read_csv(legacy).fillna("")
                for _, item in old.iterrows():
                    vals = {k: item.get(k, "") for k in COLS}
                    _qty = float(vals["Actual Qty"]) if str(vals["Actual Qty"]).strip() else None
                    c.execute("INSERT OR IGNORE INTO section_status(event_id,time,wo,section,status,actual_qty,quantity_unknown,remark,user,source_ref,source_row) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                              ("legacy-" + uuid.uuid4().hex,str(vals["Time"]),str(vals["Work Order"]),str(vals["Section"]),str(vals["Status"]),_qty,int(str(vals.get("Quantity Unknown","")).lower() in {"true","1","yes"}),str(vals["Remark"]),str(vals["User"]),str(vals.get("Source reference","")),str(vals.get("Plan row",""))))
            except Exception:
                # Preserve the original CSV untouched if its format needs manual recovery.
                pass
            c.execute("INSERT INTO legacy_status_import(done) VALUES(1)")
        inserted = c.execute("INSERT OR IGNORE INTO section_status(event_id,time,wo,section,status,actual_qty,quantity_unknown,remark,user,source_ref,source_row) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (row["Event ID"],row["Time"],row["Work Order"],row["Section"],row["Status"],row["Actual Qty"],int(row["Quantity Unknown"]),row["Remark"],row["User"],row["Source reference"],row["Plan row"]))
        if inserted.rowcount == 0:
            saved = c.execute("SELECT time,wo,section,status,actual_qty,quantity_unknown,remark,user,event_id,source_ref,source_row FROM section_status WHERE event_id=?", (row["Event ID"],)).fetchone()
            if saved:
                previous = dict(zip(COLS, saved))
                fields = ["Work Order", "Section", "Status", "Actual Qty", "Quantity Unknown", "Remark", "User"]
                if any(previous[k] != row[k] for k in fields):
                    raise ValueError("Submission ID already used with different data. Review the saved event before creating a new submission.")
                row = previous
    return row


def render(st, *, plan_path: Optional[str] = None, db_file=None, data_dir, raw_df=None,
           can_edit: bool = True, user: str = "", show_customer: bool = False, key: str = "floor",
           qr_scan_dir=None):
    st.markdown("### 📋 Update one WO section status / บันทึกสถานะแผนกของใบสั่งผลิต")
    st.caption(
        "Type the work order, scan it with a USB QR scanner, or take/upload a QR photo. Then select the section and save its status. "
        "This records a section event only; it does not close the whole work order. No process-close workbook is needed."
    )
    if not can_edit:
        st.warning("Read-only access. Sign in with an editing role to save a section-status event.")
    qr_raw = b""
    qr_value = ""
    qr_source = ""
    with st.expander("📷 Scan a QR with this device / choose a QR photo", expanded=False):
        st.caption("On a phone, use Choose QR photo if this page is opened over factory Wi-Fi without HTTPS. Live camera access may require HTTPS. A USB handheld QR scanner can type directly in the work-order box below.")
        cam = st.camera_input("Take QR photo", key=f"{key}_qr_camera")
        photo = st.file_uploader("Or choose / capture QR image", type=["png", "jpg", "jpeg", "webp", "heic"], key=f"{key}_qr_photo")
    qr_file = cam if cam is not None else photo
    if qr_file is not None:
        qr_raw = qr_file.getvalue()
        try:
            from apps.mobile.qr_decode import decode_qr
            result = decode_qr(qr_raw)
            if result.status == "OK":
                qr_value = result.value
                qr_source = "QR photo"
                st.success(f"QR read ({result.strategy}): {qr_value}")
            elif result.status == "AMBIGUOUS":
                st.error("More than one different QR code is visible. Keep one work-order QR in frame and try again.")
            else:
                st.warning(f"QR not read: {result.detail or result.status}. Retake the photo or type/USB-scan the work order.")
        except Exception as exc:
            st.warning(f"QR photo decoder is unavailable: {exc}. Type or USB-scan the work order below.")
    wo_key = f"{key}_wo"
    if qr_value and qr_raw:
        import hashlib
        _qr_sha = hashlib.sha256(qr_raw).hexdigest()
        if st.session_state.get(f"{key}_qr_applied_sha") != _qr_sha:
            st.session_state[wo_key] = qr_value
            st.session_state[f"{key}_qr_applied_sha"] = _qr_sha
    typed = st.text_input("🔫 USB scanner or type Work Order", key=wo_key, placeholder="P005-110826 / p005110826")
    suggestions = pd.DataFrame()
    src = ""
    found_wo = ""
    found_source_row = ""
    if typed.strip():
        try:
            from suite.wo_lookup import lookup as _wo_lookup
            suggestions, src = _wo_lookup(typed, plan_path=plan_path, raw_df=raw_df, db_file=db_file)
        except Exception as exc:
            st.error(f"Work-order lookup failed: {exc}")
            suggestions = pd.DataFrame()
        if suggestions is None:
            suggestions = pd.DataFrame()
        if suggestions.empty:
            st.error(
                f"This work order does not exist in Plan-2026{(' (' + Path(src).name + ')') if src else ''} "
                "or the phone database. Upload / replace Plan-2026 on Home, then try again."
            )
        else:
            show = [c for c in ["Plan row", "Work Order", "Customername", "รหัสสินค้า", "Specification", "QTY", "กำหนดส่งใหม่"] if c in suggestions.columns]
            if not show_customer:
                show=[c for c in show if "customer" not in str(c).lower() and "ลูกค้า" not in str(c)]
            shown = suggestions[show] if show else suggestions
            if show_customer: shown = localize_customer_columns(shown, read_ui_language())
            st.dataframe(shown, use_container_width=True, hide_index=True, height=180)
            wos = suggestions["Work Order"].astype(str).tolist() if "Work Order" in suggestions.columns else []
            found_wo = confirmed_candidate(typed, wos)
            if found_wo:
                _match=suggestions[suggestions["Work Order"].astype(str).eq(str(found_wo))]
                found_source_row=str(_match.iloc[0].get("Plan row","")) if not _match.empty else ""
                st.success(f"Exact work order confirmed: `{found_wo}`" + (f" from `{Path(src).name}`" if src else ""))
            else:
                st.warning("The scan/text is not an exact work order. Choose the correct work order below before saving.")
                found_wo = st.selectbox("Confirm work order", [""] + wos, key=f"{key}_confirm_wo")
                _match=suggestions[suggestions["Work Order"].astype(str).eq(str(found_wo))] if found_wo else pd.DataFrame()
                found_source_row=str(_match.iloc[0].get("Plan row","")) if not _match.empty else ""

    c1, c2, c3 = st.columns(3)
    from .demo_accounts import USER_SECTIONS
    st.session_state.setdefault(f"{key}_sec", USER_SECTIONS.get(str(user).lower(),SECTIONS[0]))
    section = c1.selectbox("Section / แผนก", SECTIONS, key=f"{key}_sec")
    status = c2.radio("OPEN / CLOSED", ["OPEN", "CLOSED"], horizontal=True, key=f"{key}_st")
    qty_unknown = st.checkbox("Quantity unknown / not provided", value=False, key=f"{key}_qty_unknown")
    if qty_unknown:
        qty = None
        st.caption("Quantity will be saved as unknown, not as zero.")
    else:
        qty = st.number_input("Actual Qty", min_value=0.0, value=0.0, step=1.0, key=f"{key}_qty")
    remark = st.text_input("Remark / หมายเหตุ", key=f"{key}_rk")
    wo_save = found_wo
    if can_edit and st.button("💾 SAVE section OPEN / CLOSED", type="primary", use_container_width=True, key=f"{key}_save"):
        if not wo_save:
            st.error("Select a work order confirmed from Plan-2026 or the shared work-order database. Nothing was saved.")
        else:
            try:
                _event_id = st.session_state.setdefault(f"{key}_event_id", uuid.uuid4().hex)
                source_parts = [str(src or plan_path or "")]
                if qr_raw and qr_value:
                    import hashlib
                    from datetime import datetime
                    from suite.qr_labels import photo_stem
                    from suite.common import bkk_now
                    folder = Path(qr_scan_dir) if qr_scan_dir else Path(data_dir) / "QR_SCANS"
                    folder.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256(qr_raw).hexdigest()
                    ext = Path(getattr(qr_file, "name", "qr.jpg")).suffix.lower()
                    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".heic"}: ext = ".jpg"
                    stamp = bkk_now().strftime("%Y%m%d_%H%M%S")
                    scan_path = folder / f"{photo_stem(wo_save, section, bkk_now())}_QR_{stamp}_{digest[:8]}{ext}"
                    if not scan_path.exists(): scan_path.write_bytes(qr_raw)
                    source_parts.append(f"QR image={scan_path.resolve()}; SHA256={digest}")
                if qr_source:
                    source_parts.append(qr_source)
                save_entry(data_dir, wo_save, section, status, qty, remark, user, canonical_wo=found_wo, event_id=_event_id, source_ref=" | ".join(p for p in source_parts if p), source_row=found_source_row, qty_unknown=qty_unknown)
                st.session_state[f"{key}_event_id"] = uuid.uuid4().hex
                st.success(f"Saved section status: {status} · {wo_save} · {section} · event { _event_id } · {bkk_now():%Y-%m-%d %H:%M} Thailand local time — Phan Thong, Chonburi.")
            except Exception as exc:
                st.error(f"Save failed: {exc}")

    today = load_entries(data_dir)
    if not today.empty:
        today["Time"] = pd.to_datetime(today["Time"], errors="coerce")
        day = today[today["Time"].dt.date == bkk_today()].copy()
        st.caption(f"Today's section status events (with saved event IDs): {len(day)}")
        if not day.empty:
            st.dataframe(day.tail(50), use_container_width=True, hide_index=True, height=240)
    else:
        st.caption("Today's section status events (with saved event IDs): 0")
