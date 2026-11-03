"""Monthly Open Job / Close Job register — e.g. October-2026.xls, revised every day.

The factory file name is the month (October-2026.xls). Planning replaces it each day.
This module only *parses the name and the sheets*. It does not invent counts.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
    "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5, "มิถุนายน": 6,
    "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12,
}


def parse_month_filename(name) -> Optional[tuple[int, int]]:
    """Return (year, month) from 'October-2026.xls' / 'October-2026.xlsx'. None if unknown."""
    stem = Path(str(name or "")).stem.replace("_", "-").replace(" ", "-")
    m = re.match(r"^([A-Za-zก-๙]+)-(\d{4})$", stem)
    if not m:
        m = re.match(r"^([A-Za-zก-๙]+)(\d{4})$", stem)
    if not m:
        return None
    month = MONTHS.get(m.group(1).casefold())
    if not month:
        return None
    year = int(m.group(2))
    if year < 2000 or year > 2100:
        return None
    return year, month


def is_xls(name: str) -> bool:
    n = str(name or "").lower()
    return n.endswith(".xls") and not n.endswith(".xlsx") and not n.endswith(".xlsm")


def xls_to_xlsx_bytes(data: bytes) -> bytes:
    """Convert a BIFF .xls workbook to .xlsx bytes so openpyxl/Daily can read today's revision."""
    try:
        import xlrd
    except ImportError as exc:
        raise ValueError("October-2026.xls needs the xlrd reader. Run INSTALL_REQUIREMENTS.bat once, then upload again.") from exc
    book = xlrd.open_workbook(file_contents=data)
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for sheet in book.sheets():
        ws = wb.create_sheet(title=(sheet.name or "Sheet")[:31])
        for r in range(sheet.nrows):
            for c in range(sheet.ncols):
                cell = sheet.cell(r, c)
                val = cell.value
                if cell.ctype == xlrd.XL_CELL_DATE:
                    try:
                        val = xlrd.xldate_as_datetime(val, book.datemode)
                    except Exception:
                        pass
                elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                    val = bool(val)
                elif cell.ctype == xlrd.XL_CELL_EMPTY:
                    val = None
                ws.cell(r + 1, c + 1, val)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def prepare_upload_bytes(original_name: str, data: bytes) -> bytes:
    if is_xls(original_name):
        return xls_to_xlsx_bytes(data)
    return data


def parse_month_from_workbook(path) -> Optional[tuple[int, int]]:
    """Read (year, month) from 'Input October (JOB)' / 'Close Job October (Item)' headers."""
    try:
        import pandas as pd
        x = pd.ExcelFile(path)
    except Exception:
        return None
    found_month = None
    found_year = None
    names = sorted(MONTHS, key=len, reverse=True)
    for sheet in x.sheet_names:
        try:
            d = pd.read_excel(x, sheet_name=sheet, header=None, nrows=2)
        except Exception:
            continue
        for val in d.to_numpy().ravel():
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            text = str(val)
            low = text.casefold()
            for name in names:
                if len(name) < 3:
                    continue
                if name in low:
                    found_month = MONTHS[name]
                    break
            y = re.search(r"(20\d{2})", text)
            if y:
                found_year = int(y.group(1))
    if found_month:
        return (found_year or 2026), found_month
    return None


def infer_register_month(original_name=None, path=None) -> Optional[tuple[int, int]]:
    """Filename first (October-2026.xls), then workbook headers. None if unknown — never invent a month."""
    parsed = parse_month_filename(original_name) if original_name else None
    if parsed:
        return parsed
    if path:
        return parse_month_from_workbook(path)
    return None
