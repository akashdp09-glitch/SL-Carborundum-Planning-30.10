"""IP-independent Work Order QR labels (payload SLWO:<WO>).

Labels are built from the planning database when it has work orders, otherwise
from the loaded Plan-2026 frame. No work-order numbers are invented.
"""
from __future__ import annotations

import json
import re
import sqlite3
import urllib.parse
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage


def norm_wo(value) -> str:
    """Compare typed, scanned and Plan WOs without dashes, spaces or case."""
    s = urllib.parse.unquote(str(value or "")).strip()
    s = s.rstrip("/").split("/")[-1].strip()
    s = re.sub(r"^(?:SLWO|WO)\s*[:#=-]\s*", "", s, flags=re.I)
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def photo_stem(wo_id: str, location: str, when: datetime) -> str:
    """Owner OD-10: file name = work order + location + date-time."""
    def slug(text, n):
        s = re.sub(r"[^\w\-]+", "-", str(text or "").strip(), flags=re.UNICODE)
        s = re.sub(r"-{2,}", "-", s).strip("-._")
        return (s or "nloc")[:n]
    stamp = when.strftime("%Y%m%d-%H%M%S") if hasattr(when, "strftime") else re.sub(r"[^\d\-]", "", str(when))[:15]
    return f"{slug(wo_id, 40)}_{slug(location, 36)}_{stamp}"


def _row(wo_id, product="", customer="", qty="", due="", section="", closed=False, source_row="", order_date="", order_qty="") -> dict:
    wo = str(wo_id or "").strip()
    if not wo or wo.lower() in {"nan", "none", "#n/a"}:
        return {}
    try:
        missing_close = closed is None or (not isinstance(closed, str) and bool(__import__('pandas').isna(closed)))
    except Exception:
        missing_close = False
    is_closed = False if missing_close else ((str(closed).strip().casefold() in {"1", "true", "yes", "y", "closed", "complete", "completed"}) if isinstance(closed, str) else bool(closed))
    return {
        "wo_id": wo,
        "product_code": "" if product is None else str(product).strip(),
        "customer_name": "" if customer is None else str(customer).strip(),
        "qty": qty,
        "order_qty": order_qty if order_qty not in (None, "") else qty,
        "due_date": due,
        "order_date": order_date,
        "section": "" if section is None else str(section).strip(),
        "closed": is_closed,
        "source_row": source_row,
    }


def rows_from_sqlite(db_path) -> list[dict]:
    path = Path(db_path) if db_path else None
    if not path or not path.exists():
        return []
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "work_orders" not in tables:
            return []
        rows = con.execute(
            "SELECT wo_id,product_code,customer_name,qty,due_date FROM work_orders ORDER BY wo_id"
        ).fetchall()
        return [r for r in (_row(x["wo_id"], x["product_code"], x["customer_name"], x["qty"], x["due_date"]) for x in rows) if r]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def rows_from_plan_frame(df) -> list[dict]:
    """Accept the hub master frame or a raw Plan-2026 sheet. Never invent WOs."""
    if df is None:
        return []
    try:
        empty = df.empty
    except Exception:
        return []
    if empty:
        return []
    cols = {str(c).strip(): c for c in df.columns}
    wo_col = next((cols[k] for k in ("Work Order", "ProductionCode", "production_code", "wo_id") if k in cols), None)
    if wo_col is None:
        return []
    prod_col = next((cols[k] for k in ("Product Code", "รหัสสินค้า", "product_code") if k in cols), None)
    cust_col = next((cols[k] for k in ("Customer", "Customername", "Customer English", "customer_name") if k in cols), None)
    qty_col = next((cols[k] for k in ("pcs", "QTY", "qty", "Order Qty") if k in cols), None)
    due_col = next((cols[k] for k in ("Due Date", "กำหนดส่งใหม่", "กำหนดเข้าคลัง", "due_date") if k in cols), None)
    order_date_col = next((cols[k] for k in ("Work Order Creation Date", "Order Date", "Creation Date", "วันที่ออกใบสั่งงาน", "วันที่ออกใบผลิต", "วันที่เริ่มออกใบผลิต", "order_date") if k in cols), None)
    section_col = next((cols[k] for k in ("Section", "Plan Location / Status", "Process", "แผนก") if k in cols), None)
    close_col = next((cols[k] for k in ("Authoritative Closed", "Strict Closed", "Overall Closed", "Closed") if k in cols), None)
    source_col = next((cols[k] for k in ("Plan Source Row", "Source Row", "Excel Source Row") if k in cols), None)
    open_col = next((cols[k] for k in ("Open Qty", "Open quantity (pcs)", "pcs") if k in cols), None)
    order_qty_col = next((cols[k] for k in ("Order Qty", "QTY", "qty") if k in cols), None)
    seen, out = set(), []
    for _, rec in df.iterrows():
        row = _row(
            rec.get(wo_col),
            rec.get(prod_col) if prod_col else "",
            rec.get(cust_col) if cust_col else "",
            rec.get(qty_col) if qty_col else "",
            rec.get(due_col) if due_col else "",
            rec.get(section_col) if section_col else "",
            rec.get(close_col) if close_col else False,
            rec.get(source_col) if source_col else "",
            rec.get(order_date_col) if order_date_col else "",
            rec.get(order_qty_col) if order_qty_col else "",
        )
        if row and open_col:
            try:
                row["qty"] = float(rec.get(open_col) or 0)
            except (TypeError, ValueError):
                row["qty"] = 0
        key = norm_wo(row.get("wo_id"))
        if not row or not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def collect_wo_rows(db_path=None, plan_df=None) -> tuple[list[dict], str]:
    rows = rows_from_sqlite(db_path)
    if rows:
        return rows, "work_orders"
    rows = rows_from_plan_frame(plan_df)
    if rows:
        return rows, "plan"
    return [], "none"


def filter_open_plan_rows(rows, section="All sections", date_from=None, date_to=None,
                          status_filter="Open orders", date_field="due_date", include_undated=False):
    """Filter Plan-2026 WOs by status, section, and due/creation date range."""
    from .backorder_views import local_date
    out = []
    for row in rows:
        is_closed = bool(row.get("closed"))
        if status_filter == "Open orders" and is_closed:
            continue
        if status_filter == "Closed orders" and not is_closed:
            continue
        try:
            qty = float(row.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0
        if status_filter == "Open orders" and qty <= 0:
            continue
        sec = str(row.get("section") or "Unassigned").strip() or "Unassigned"
        if section and section != "All sections" and sec != section:
            continue
        due = local_date(row.get("due_date"))
        date_value = local_date(row.get("order_date" if date_field == "order_date" else "due_date"))
        if date_from is not None or date_to is not None:
            if pd_isna(date_value):
                if not include_undated:
                    continue
            elif (date_from is not None and date_value.date() < date_from) or (date_to is not None and date_value.date() > date_to):
                continue
        item = dict(row)
        item["section"] = sec
        item["due_date"] = due.date().isoformat() if not pd_isna(due) else ""
        item["wo_id"] = str(item["wo_id"]).strip().upper()
        out.append(item)
    return out


def pd_isna(value):
    try:
        import pandas as pd
        return pd.isna(value)
    except Exception:
        return value is None


def write_label_pack(rows, out_xlsx, png_dir, existing=None, all_work_orders=True, generated_at=None, provenance=None):
    """Write an Excel pack and A4 sticker sheet with uppercase WO under each QR."""
    import qrcode
    existing = set(existing or [])
    selected = list(rows) if all_work_orders else [r for r in rows if str(r["wo_id"]).strip() not in existing]
    if not selected:
        return None, 0
    out = Path(out_xlsx)
    qdir = Path(png_dir)
    qdir.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "QR_LABELS"
    ws.append(["Work Order (uppercase; printed under QR)", "Product Code", "Customer", "Order Qty (pcs)", "Open Qty (pcs)", "Status", "WO Creation Date", "Current Due Date", "Plan Section", "Source Excel Row", "QR payload", "QR"])
    ws["M1"] = "QR Mode"
    ws["M2"] = "IP-independent app code"
    ws["M3"] = "Generated"
    ws["M4"] = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    for idx, (label, value) in enumerate((provenance or {}).items(), 6):
        ws.cell(idx, 13, f"{label}: {value}")
    for letter, width in (("A", 27), ("B", 24), ("C", 38), ("D", 16), ("E", 16), ("F", 12), ("G", 18), ("H", 18), ("I", 24), ("J", 18), ("K", 26), ("L", 18), ("M", 62)):
        ws.column_dimensions[letter].width = width
    for i, r in enumerate(selected, 2):
        wo = str(r["wo_id"]).strip().upper()
        vals = [wo, r.get("product_code"), r.get("customer_name"), r.get("order_qty", r.get("qty")), r.get("qty"), "CLOSED" if r.get("closed") else "OPEN", r.get("order_date"), r.get("due_date"), r.get("section"), r.get("source_row")]
        for j, v in enumerate(vals, 1):
            ws.cell(i, j, v)
        payload = "SLWO:" + wo
        ws.cell(i, 11, payload)
        qpath = qdir / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', wo)}_stable.png"
        qrcode.make(payload).save(qpath)
        im = XLImage(str(qpath))
        im.width = 105
        im.height = 105
        ws.add_image(im, f"L{i}")
        ws.row_dimensions[i].height = 82
        existing.add(str(r["wo_id"]).strip())

    # Print-ready A4 layout: each WO is physically grouped with its QR.
    from openpyxl.styles import Alignment, Border, Font, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.pagebreak import Break

    stickers = wb.create_sheet("Sticker Print")
    stickers.sheet_view.showGridLines = False
    stickers.sheet_properties.pageSetUpPr.fitToPage = True
    stickers.page_setup.orientation = "portrait"
    stickers.page_setup.paperSize = stickers.PAPERSIZE_A4
    stickers.page_setup.fitToWidth = 1
    stickers.page_setup.fitToHeight = 0
    stickers.page_margins.left = stickers.page_margins.right = 0.22
    stickers.page_margins.top = stickers.page_margins.bottom = 0.25
    stickers.page_margins.header = stickers.page_margins.footer = 0
    labels_per_page = 12  # 3 columns x 4 rows on A4
    rows_per_label = 3
    pages = max(1, (len(selected) + labels_per_page - 1) // labels_per_page)
    stickers.print_area = f"A1:L{pages * 4 * rows_per_label}"
    for col in range(1, 13):
        stickers.column_dimensions[get_column_letter(col)].width = 8
    for idx, r in enumerate(selected):
        label_row = (idx // 3) * 3 + 1
        block_col = (idx % 3) * 4 + 1
        for rr in range(label_row, label_row + 3):
            stickers.row_dimensions[rr].height = 56
        for rr in range(label_row, label_row + 3):
            for cc in range(block_col, block_col + 4):
                cut = Side(style="dashed", color="87939E")
                stickers.cell(rr, cc).border = Border(left=cut if cc == block_col else Side(None),
                    right=cut if cc == block_col + 3 else Side(None),
                    top=cut if rr == label_row else Side(None),
                    bottom=cut if rr == label_row + 2 else Side(None))
        wo = str(r["wo_id"]).strip().upper()
        code_cell = stickers.cell(label_row + 2, block_col, wo)
        code_cell.font = Font(name="Arial", size=14, bold=True, color="172B4D")
        code_cell.alignment = Alignment(horizontal="center", vertical="center", shrink_to_fit=True)
        stickers.merge_cells(start_row=label_row + 2, start_column=block_col,
                             end_row=label_row + 2, end_column=block_col + 3)
        qpath = qdir / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', wo)}_stable.png"
        sticker_qr = XLImage(str(qpath))
        sticker_qr.width = sticker_qr.height = 108
        stickers.add_image(sticker_qr, f"{get_column_letter(block_col + 1)}{label_row}")
        if idx and idx % labels_per_page == 0:
            stickers.row_breaks.append(Break(id=label_row - 1))
    wb.save(out)
    return out, len(selected)


def load_registry(path) -> set:
    p = Path(path) if path else None
    if not p or not p.exists():
        return set()
    try:
        reg = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(reg, dict) and reg.get("mode") == "SLWO:v1":
            return set(reg.get("work_orders", []))
    except Exception:
        return set()
    return set()


def save_registry(path, work_orders):
    Path(path).write_text(
        json.dumps({"mode": "SLWO:v1", "work_orders": sorted(work_orders)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
