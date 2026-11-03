"""September job-register analysis (Open Job / Close Job sheets of JOB_REGISTER_REFERENCE_SEP2026.xlsx).

Four DIFFERENT measures are read and kept apart - they are never added, netted or substituted for one another:
  1. sales requests received (RP / 'Input September (JOB)')            - Open Job, first block
  2. production orders (WOs) issued ('Output September (JOB)')          - Open Job, second block
  3. requests not yet issued as WOs ('ค้างออกใบผลิต September (Item)')   - Open Job, third block
  4. production item closures ('Close Job September (Item)')            - Close Job sheet
Every figure carries sheet/cell. Day cells are re-added and compared with the sheet's own Total cells.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.utils import column_index_from_string as CI, get_column_letter as GL

from . import sheet_roles as SR

MEASURES = {
    "sales_requests": ("Sales requests received (Input, JOB)", SR.OPEN_JOB, 1),
    "wos_issued": ("Production orders issued (Output, JOB)", SR.OPEN_JOB, 2),
    "unissued_items": ("Requests not yet issued as production orders (Item)", SR.OPEN_JOB, 3),
    "production_closures": ("Production item closures (Close Job, Item)", SR.CLOSE_JOB, 1),
}


@dataclass
class SeptResult:
    source: str
    long: pd.DataFrame                 # measure, order_type, product, day, value, sheet, cell
    totals: pd.DataFrame               # measure, order_type, product, day_sum, sheet_total, sheet_total_cell, matches
    measures: pd.DataFrame             # one row per measure with the grand totals
    notes: list = field(default_factory=list)
    issues: list = field(default_factory=list)


def _blocks(ws):
    """Header row 1 text cells mark the start of each block; the cell 'Input'/'Output' marks the block's total column."""
    heads = [(c.column, str(c.value)) for c in ws[1] if c.value is not None]
    starts = [(col, txt) for col, txt in heads if not txt.strip().lower() in ("input", "output", "product")]
    totals = [col for col, txt in heads if txt.strip().lower() in ("input", "output")]
    return starts, totals


def read_sept(path) -> SeptResult:
    path = Path(path)
    wb = openpyxl.load_workbook(path, data_only=True)
    roles = {r.sheet: r.role for r in SR.classify_workbook(path)}
    open_ws = next((wb[s] for s, r in roles.items() if r == SR.OPEN_JOB), None)
    close_ws = next((wb[s] for s, r in roles.items() if r == SR.CLOSE_JOB), None)
    long, tot, issues, notes = [], [], [], []

    def read_block(ws, measure, first_col, total_col):
        otype = None
        for r in range(3, ws.max_row + 1):
            a, product = ws.cell(r, 1).value, ws.cell(r, 2).value
            if a in ("MTO", "MTS"):
                otype = a
            if a == "Total" or product is None:
                continue
            # MTO / MTS label sits on the 3rd row of its 5-row group; rows 3-7 are MTO, 8-12 MTS in this layout
            group_type = "MTO" if r <= 7 else "MTS"
            day_sum = 0.0
            for d in range(1, 31):
                v = ws.cell(r, first_col + d - 1).value
                if isinstance(v, (int, float)) and v != 0:
                    long.append({"measure": measure, "order_type": group_type, "product": str(product).strip(), "day": d, "value": float(v), "sheet": ws.title,
                                 "cell": f"{GL(first_col + d - 1)}{r}"})
                    day_sum += float(v)
            sheet_total = ws.cell(r, total_col).value
            st = float(sheet_total) if isinstance(sheet_total, (int, float)) else None
            tot.append({"measure": measure, "order_type": group_type, "product": str(product).strip(), "day_sum": day_sum, "sheet_total": st,
                        "sheet_total_cell": f"{ws.title}!{GL(total_col)}{r}", "matches": (st is None) or abs(st - day_sum) < 1e-9})

    if open_ws is not None:
        starts, totals = _blocks(open_ws)
        # blocks: Input (C..AF, total AG), Output (AH..BK, total BL), Unissued (BM..CP, total CQ)
        for (col, txt), key in zip(starts, ("sales_requests", "wos_issued", "unissued_items")):
            tcol = next((t for t in totals if t > col), None)
            if tcol is None:
                tcol = col + 30
            read_block(open_ws, key, col, tcol)
        # the 3rd block's total column header is also 'Output' in this file; fall back to +30
        for row in range(14, open_ws.max_row + 1):
            for c in range(1, open_ws.max_column + 1):
                v = open_ws.cell(row, c).value
                if isinstance(v, str) and v.strip():
                    notes.append(f"{open_ws.title}!{GL(c)}{row}: {v.strip()}")
    else:
        issues.append("No sheet with the Open Job header found.")
    if close_ws is not None:
        read_block(close_ws, "production_closures", CI("C"), CI("AG"))
    else:
        issues.append("No sheet with the Close Job header found.")
    L = pd.DataFrame(long)
    T = pd.DataFrame(tot)
    if not T.empty:
        for _, r in T[~T.matches].iterrows():
            issues.append(f"{r.measure} {r.order_type}/{r['product']}: day cells add to {r.day_sum:g} but {r.sheet_total_cell} says {r.sheet_total:g}")
    rows = []
    for key, (label, _role, _n) in MEASURES.items():
        t = T[T.measure == key] if not T.empty else pd.DataFrame()
        rows.append({"measure": key, "meaning": label, "total_by_day_cells": float(t.day_sum.sum()) if not t.empty else None,
                     "total_by_sheet_total_cells": float(t.sheet_total.sum()) if not t.empty else None,
                     "total_cells": ", ".join(t.sheet_total_cell) if not t.empty else ""})
    M = pd.DataFrame(rows)
    return SeptResult(path.name, L, T, M, notes, issues)


def by_product(res: SeptResult) -> pd.DataFrame:
    """Measures side by side per order type and product - columns stay separate (no cross-measure arithmetic)."""
    if res.totals.empty:
        return pd.DataFrame()
    p = res.totals.pivot_table(index=["order_type", "product"], columns="measure", values="day_sum", aggfunc="sum", fill_value=0).reset_index()
    for k in MEASURES:
        if k not in p:
            p[k] = 0.0
    return p[["order_type", "product", *MEASURES]]
