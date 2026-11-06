"""Read previous firing commitments from full plans or operator-print-only XLSX files.

The operator print is the shop-floor issued record. It has one row per WO in a
kiln load, so rows are grouped into load records before applying cutover blocks.
Missing cycle-end evidence is reported and is never replaced with an invented
one-day kiln duration.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
import re

import pandas as pd


def _norm(value):
    return ''.join(c for c in str(value or '').casefold() if c.isalnum())


def _as_date(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        parsed = pd.to_datetime(value, errors='coerce')
        return None if pd.isna(parsed) else parsed.date()
    except Exception:
        return None


def _column(columns, predicate):
    return next((c for c in columns if predicate(_norm(c))), None)


def _read_upload(upload):
    if hasattr(upload, 'getvalue'):
        return upload.getvalue()
    if hasattr(upload, 'getbuffer'):
        return bytes(upload.getbuffer())
    if isinstance(upload, (str, Path)):
        return Path(upload).read_bytes()
    if isinstance(upload, (bytes, bytearray)):
        return bytes(upload)
    raise TypeError('Previous firing source must be an Excel file or uploaded file.')


def validate_firing_source(data):
    """Validate full or operator-print-only workbook headers before activation."""
    try:
        book = pd.ExcelFile(BytesIO(_read_upload(data)))
    except Exception as exc:
        return False, f'Cannot read firing workbook: {exc}'
    try:
        sheets = sorted(book.sheet_names, key=lambda name: (0 if 'operatorprint' in _norm(name) else 1, book.sheet_names.index(name)))
        for sheet in sheets:
            for header_row in range(12):
                try:
                    frame = pd.read_excel(book, sheet_name=sheet, header=header_row, nrows=2)
                except Exception:
                    continue
                if frame is None or frame.empty:
                    continue
                columns = list(frame.columns)
                wo = _column(columns, lambda n: n.startswith(('workorder', 'productioncode')) or n == 'wo')
                kiln = _column(columns, lambda n: n.startswith('kiln') or n == 'เตา')
                load = _column(columns, lambda n: n.startswith(('loadingdate', 'loaddate', 'firingdate', 'firingstartdate')) or n in {'วนทเขาเตา', 'วนทเผา'})
                qty = _column(columns, lambda n: n.startswith(('plannedfiringqty', 'plannedqty', 'firingqty', 'planqty')) or n in {'qtypcs', 'quantity', 'qty', 'จำนวน', 'จำนวนแผน'})
                finish = _column(columns, lambda n: n.startswith(('programfinishdate', 'firingfinishdate', 'firingcomplete', 'unloadtakeoutdate', 'unloaddate')))
                running = _column(columns, lambda n: n.startswith(('runningdays', 'cycledays', 'kilncycledays')))
                if all((wo, kiln, load, qty, finish)):
                    mode = 'Operator Print-only' if 'operatorprint' in _norm(sheet) else 'Firing detail'
                    return True, f'{mode} recognized in sheet “{sheet}”; WO, kiln, date, quantity and cycle/finish fields found.'
        return False, 'Unsupported firing workbook. Upload the full firing plan or an Operator Print sheet with Work Order, Kiln, Loading Date, Qty pcs / Planned Qty, and Firing Complete / finish date.'
    finally:
        try:
            book.close()
        except Exception:
            pass


def previous_kiln_blocks(files, planning_start):
    """Return kiln -> earliest usable next-start date plus a traceable audit.

    The function accepts either full firing workbooks or a workbook containing
    only an Operator Print sheet. It looks for headers in the first 12 rows and
    requires a work-order column, kiln and load date. It uses an explicit finish
    date, or derives one from the sheet's explicit Running Days / Cycle Days.
    """
    blocks = {}
    audit = []
    seen = set()
    if not files:
        return blocks, pd.DataFrame()

    cutover = _as_date(planning_start)
    for upload in files:
        filename = getattr(upload, 'name', None) or (Path(upload).name if isinstance(upload, (str, Path)) else 'Previous issued firing plan')
        try:
            raw = _read_upload(upload)
            book = pd.ExcelFile(BytesIO(raw))
        except Exception as exc:
            audit.append({'Source': filename, 'Kiln': '', 'Previous Load Date': '', 'Previous Finish': '',
                          'Blocked Until': '', 'Status': 'READ ERROR', 'Read Error': str(exc)})
            continue

        found_table = False
        try:
            ordered_sheets = sorted(book.sheet_names, key=lambda name: (0 if 'operatorprint' in _norm(name) else 1, book.sheet_names.index(name)))
            for sheet in ordered_sheets:
                found_header = False
                for header_row in range(12):
                    try:
                        frame = pd.read_excel(book, sheet_name=sheet, header=header_row)
                    except Exception:
                        continue
                    if frame is None or frame.empty:
                        continue
                    columns = list(frame.columns)
                    wo_col = _column(columns, lambda n: n.startswith(('workorder', 'productioncode')) or n == 'wo')
                    kiln_col = _column(columns, lambda n: n.startswith('kiln') or n == 'เตา')
                    load_col = _column(columns, lambda n: n.startswith(('loadingdate', 'loaddate', 'firingdate', 'firingstartdate')) or n in {'วนทเขาเตา', 'วนทเผา'})
                    if wo_col is None or kiln_col is None or load_col is None:
                        continue

                    found_header = True
                    found_table = True
                    finish_col = _column(columns, lambda n: n.startswith(('programfinishdate', 'firingfinishdate', 'firingcomplete', 'unloadtakeoutdate', 'unloaddate')) or n == 'วนทเผาเสรจ')
                    days_col = _column(columns, lambda n: n.startswith(('runningdays', 'cycledays', 'kilncycledays')) or n == 'วนททำงานเตา')
                    load_id_col = _column(columns, lambda n: n.startswith(('loadid', 'loadnumber', 'loadno')) or n == 'รหสโหลด')
                    program_col = _column(columns, lambda n: n.startswith('program') or n == 'โปรแกรม')

                    for _, row in frame.iterrows():
                        wo = str(row.get(wo_col, '') or '').strip()
                        kiln = str(row.get(kiln_col, '') or '').strip().upper()
                        loaded = _as_date(row.get(load_col))
                        if not wo or wo.casefold() in {'nan', 'none'} or not kiln or not loaded:
                            continue
                        if cutover and loaded >= cutover:
                            continue
                        finish = _as_date(row.get(finish_col)) if finish_col else None
                        finish_basis = 'Explicit finish date' if finish else ''
                        if finish is None and days_col:
                            try:
                                days = float(pd.to_numeric(pd.Series([row.get(days_col)]), errors='coerce').iloc[0])
                                if pd.notna(days) and days > 0:
                                    finish = loaded + timedelta(days=max(1, int(round(days))))
                                    finish_basis = f'Explicit running days: {days:g}'
                            except (TypeError, ValueError, OverflowError):
                                pass
                        load_id = str(row.get(load_id_col, '') or '').strip() if load_id_col else ''
                        program = str(row.get(program_col, '') or '').strip() if program_col else ''
                        signature = (str(filename), str(sheet), kiln, loaded, finish, load_id or program)
                        if signature in seen:
                            continue
                        seen.add(signature)
                        if finish is None:
                            audit.append({'Source': filename, 'Sheet': sheet, 'Load ID': load_id, 'Kiln': kiln,
                                          'Previous Load Date': loaded, 'Previous Finish': '', 'Blocked Until': '',
                                          'Status': 'NOT BLOCKED — no finish/cycle evidence', 'Read Error': ''})
                            continue
                        until = finish + timedelta(days=1)
                        blocks[kiln] = max(blocks.get(kiln, until), until)
                        audit.append({'Source': filename, 'Sheet': sheet, 'Load ID': load_id, 'Kiln': kiln,
                                      'Program': program, 'Previous Load Date': loaded, 'Previous Finish': finish,
                                      'Blocked Until': until, 'Finish Evidence': finish_basis,
                                      'Status': 'PROTECTED BEFORE CUTOVER', 'Read Error': ''})
                    break
                if found_header:
                    # Use one authoritative table per workbook. Operator Print is
                    # prioritized so a full file and a print-only file behave alike.
                    break
        finally:
            try:
                book.close()
            except Exception:
                pass
        if not found_table:
            audit.append({'Source': filename, 'Sheet': '', 'Load ID': '', 'Kiln': '', 'Previous Load Date': '',
                          'Previous Finish': '', 'Blocked Until': '', 'Status': 'NO SUPPORTED FIRING TABLE',
                          'Read Error': 'Expected Work Order, Kiln and Loading/Firing Date columns. Operator Print-only workbooks are supported.'})

    return blocks, pd.DataFrame(audit)
