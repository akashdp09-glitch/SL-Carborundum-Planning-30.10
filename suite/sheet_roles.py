"""Decide what each worksheet IS by its header signature (and only then by name), never by position.

Used by the Source Manager and by plan_reader so that the master plan is the sheet that carries the master header,
not simply the first sheet in the workbook.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import openpyxl

MASTER_PLAN = "MASTER_PLAN"
CANCELLED_ORDERS = "CANCELLED_ORDERS"
KILN_CALENDAR = "KILN_CALENDAR_BOOKINGS"
SALES_DELIVERY = "SALES_DELIVERY_REQUESTS"
STATUS_SUMMARY = "ORDER_STATUS_SUMMARY"
KPI_ADHERENCE = "KPI_PLAN_ADHERENCE"
MONTHLY_SUMMARY = "MONTHLY_PLAN_SUMMARY"
SECTION_LOG = "SECTION_MOVEMENT_LOG"
NCR_LOG = "REJECT_NCR_LOG"
CAPACITY = "CAPACITY_TABLE"
DAILY_STATUS = "DAILY_STATUS_ENTRIES"
OPEN_JOB = "OPEN_JOB_REGISTER"
CLOSE_JOB = "CLOSE_JOB_REGISTER"
UNCLASSIFIED = "UNCLASSIFIED"

ROLE_NOTES = {
    MASTER_PLAN: "One row per production order (A=ProductionCode ... FC=ปิดของผลิต); the only sheet read for order status/dates.",
    CANCELLED_ORDERS: "Archive of cancelled orders; excluded from open demand.",
    KILN_CALENDAR: "Kiln-by-date grid: existing firing bookings / reservations.",
    SALES_DELIVERY: "Sales delivery requests and warehouse-receipt outcome per Pro.NO.",
    STATUS_SUMMARY: "Closed / not-closed counts per section (derived summary, not a source of order status).",
    KPI_ADHERENCE: "KPI: on-plan vs off-plan per day (derived).",
    MONTHLY_SUMMARY: "Monthly plan summary (derived).",
    SECTION_LOG: "Historic movement log for a section (issue/receipt lines).",
    NCR_LOG: "Reject / NCR register.",
    CAPACITY: "Capacity table (unit and time basis preserved by suite.capacity).",
    DAILY_STATUS: "Daily status lines.",
    OPEN_JOB: "Open Job register.",
    CLOSE_JOB: "Close Job register.",
    UNCLASSIFIED: "No known header signature - shown for review, not used.",
}

CAPACITY_SHEET_NAMES = ("CAP ผสม", "CAP ขึ้นรูป", "Cap เตา", "Cap เจีย", "Cap บรรจุ", "Lead Time", "กำลังคนแผนกผลิต")


@dataclass
class SheetRole:
    sheet: str
    role: str
    evidence: str
    rows: int
    cols: int
    confidence: str          # HEADER (signature matched) | NAME (fallback) | NONE
    note: str = ""

    def as_dict(self):
        return asdict(self)


def _head_text(ws, rows=6, cols=40):
    cells = []
    for row in ws.iter_rows(min_row=1, max_row=rows, max_col=cols, values_only=True):
        cells.extend(str(v).strip() for v in row if v is not None and str(v).strip())
    return cells


def classify_sheet(ws) -> SheetRole:
    t = ws.title
    cells = _head_text(ws)
    joined = " | ".join(cells)
    has = lambda *k: all(any(x in c for c in cells) for x in k)
    rows, cols = ws.max_row or 0, ws.max_column or 0

    def mk(role, ev, conf="HEADER"):
        return SheetRole(t, role, ev, rows, cols, conf, ROLE_NOTES[role])

    if has("ProductionCode", "กำหนดเข้าคลัง", "กำหนดส่งใหม่"):
        return mk(MASTER_PLAN, "header has ProductionCode + กำหนดเข้าคลัง + กำหนดส่งใหม่")
    if has("ProductionCode", "Program") and any(c == "GW" for c in cells):
        return mk(CANCELLED_ORDERS, "header has ProductionCode + GW + Program (no กำหนดส่งใหม่)")
    if has("Month", "WEEK", "Date"):
        return mk(KILN_CALENDAR, "grid header Month / WEEK / Date")
    if has("Pro.NO.", "แผนส่ง"):
        return mk(SALES_DELIVERY, "header has Pro.NO. + แผนส่ง")
    if has("NCR No."):
        return mk(NCR_LOG, "header has NCR No.")
    if has("กลุ่มงาน", "ปิดใบสั่ง", "ยังไม่ปิด"):
        return mk(STATUS_SUMMARY, "header has กลุ่มงาน + ปิดใบสั่ง + ยังไม่ปิด")
    if has("ตามแผน", "ตกแผน") and ("KPI" in joined or has("วันที่")):
        return mk(KPI_ADHERENCE, "header has ตามแผน / ตกแผน by date")
    if has("กลุ่มงาน", "มกราคม") or has("แผนรายวัน", "Made  To  Order") or has("แผนรายวัน", "Made To Order"):
        return mk(MONTHLY_SUMMARY, "monthly summary headers")
    if has("รหัส", "Q.TY") or (has("รหัส", "SPEC") and (has("ว", "ด", "ป") or has("ProductionCode", "Customer Name"))) or has("P/PB", "ProductionCode"):
        return mk(SECTION_LOG, "dated movement lines with รหัส / SPEC / Q.TY")
    if has("Product", "Group") and any(c.lower().startswith("close job") for c in cells):
        return mk(CLOSE_JOB, "header 'Product' + 'Close Job <month>' + 'Group' day columns")
    if has("Product", "Group") and any(c.lower().startswith("input") for c in cells):
        return mk(OPEN_JOB, "header 'Product' + 'Input <month>' + 'Group' day columns")
    if t in CAPACITY_SHEET_NAMES or t.startswith("Set Up Time"):
        return mk(CAPACITY, f"sheet name '{t}' (capacity tables have no common header)", "NAME")
    if has("Daily Status") or (has("Work Order", "Section", "Actual Qty")):
        return mk(DAILY_STATUS, "header has Work Order / Section / Actual Qty")
    return SheetRole(t, UNCLASSIFIED, "no known header signature", rows, cols, "NONE", ROLE_NOTES[UNCLASSIFIED])


def classify_workbook(path) -> list[SheetRole]:
    wb = openpyxl.load_workbook(Path(path), read_only=True, data_only=True)
    try:
        return [classify_sheet(ws) for ws in wb.worksheets]
    finally:
        wb.close()


def find_sheet(path, role: str) -> str | None:
    """Name of the sheet with the given role; if several, the one with the most rows (the authoritative table)."""
    found = [r for r in classify_workbook(path) if r.role == role]
    return max(found, key=lambda r: r.rows).sheet if found else None
