"""Single shared definition of order closure and backorder (used by hub, shared analytics, planners, September analysis).

Approved rule (documented in apps/daily/README_V1_9_30_PLAN2026_KPI_VERTICAL_NAV.txt and the engines, retained by F12V):
    WHOLE ORDER (WO) closed  =  Packing Status (column EU) is closed  OR  Overall WO closure 'ปิดของผลิต' (column FC) is closed / cancelled.
Preparation, Mixing, Forming, Firing and Grinding/Cutting closures are SECTION completion only and never close the order.
Dated evidence (today's date, remaining quantities) is computed per call; nothing here is a stored constant.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from .common import bkk_today
from .plan_reader import ORDER, SECTIONS

FC_OPEN_WORDS = ("ยังไม่ปิด",)


def is_closed_text(v) -> bool:
    """ยังไม่ปิด = open; ปิด / ปิดใบสั่ง / ยกเลิก / closed / cancel = closed. Blank / None / #N/A = not recorded (not closed)."""
    t = str(v or "").strip().lower()
    if not t or t in {"nan", "none", "#n/a"}:
        return False
    if "ยังไม่ปิด" in t or "ไม่ปิด" in t or "not closed" in t:
        return False
    return t == "ปิด" or "ปิดใบสั่ง" in t or "ยกเลิก" in t or "cancel" in t or "closed" in t


def is_blank_status(v) -> bool:
    return str(v or "").strip().lower() in {"", "nan", "none", "#n/a"}


STATE_CLOSED_FC = "CLOSED (FC production closure)"
STATE_CLOSED_PACKING = "CLOSED (Packing EU closed; FC not closed)"
STATE_OPEN = "OPEN"


def classify(plan: pd.DataFrame, today: Optional[dt.date] = None) -> pd.DataFrame:
    """plan = suite.plan_reader.load_plan() frame. One row per WO."""
    today = today or bkk_today()
    x = plan.copy()
    fc_closed = x["prod_closed"].map(is_closed_text)
    fc_blank = x["prod_closed"].map(is_blank_status)
    eu_closed = x["Packing.closed"].astype(bool)
    out = pd.DataFrame({"wo": x["wo"], "due": x["due"], "qty": x["qty"], "packing_done": x["Packing.done"]})
    out["fc_closed"], out["fc_blank"], out["packing_closed"] = fc_closed, fc_blank, eu_closed
    out["state"] = STATE_OPEN
    out.loc[eu_closed & ~fc_closed, "state"] = STATE_CLOSED_PACKING
    out.loc[fc_closed, "state"] = STATE_CLOSED_FC
    out["whole_closed"] = fc_closed | eu_closed
    if 'Manual Whole WO status' in x:
        manual=x['Manual Whole WO status'];known=manual.isin(['OPEN','CLOSED'])
        out['source_whole_closed']=out['whole_closed']
        out.loc[known,'whole_closed']=manual[known].eq('CLOSED')
        out.loc[known,'state']='MANUAL '+manual[known]+' (reasoned whole-WO decision)'
    for s in ORDER:
        out[f"{s} closed"] = x[f"{s}.closed"].astype(bool)
    pre = [f"{s} closed" for s in ORDER[:-1]]
    out["sections_closed_n"] = out[[f"{s} closed" for s in ORDER]].sum(axis=1)
    out["section_closed_but_order_open"] = (~out["whole_closed"]) & (out[pre].any(axis=1))
    out["remaining_qty"] = (out["qty"] - out["packing_done"]).clip(lower=0)
    due = pd.to_datetime(out["due"], errors="coerce")
    t = pd.Timestamp(today)
    out["late_days"] = (t - due).dt.days
    out["backorder"] = (~out["whole_closed"]) & (out["remaining_qty"] > 0) & due.notna() & (due < t)
    out.loc[~out["backorder"], "late_days"] = pd.NA
    out["as_of"] = pd.Timestamp(today)
    return out


def summary(cl: pd.DataFrame) -> pd.DataFrame:
    rows = [
        ("WO rows in Plan workbook", len(cl)),
        ("Whole-order CLOSED (EU or FC)", int(cl["whole_closed"].sum())),
        ("  of which FC closed", int(cl["fc_closed"].sum())),
        ("  of which Packing (EU) closed but FC NOT closed", int((cl["packing_closed"] & ~cl["fc_closed"]).sum())),
        ("Whole-order OPEN", int((~cl["whole_closed"]).sum())),
        ("  open with FC blank / #N/A (closure not recorded)", int(((~cl["whole_closed"]) & cl["fc_blank"]).sum())),
        ("  open with at least one EARLIER section closed (section completion only)", int(cl["section_closed_but_order_open"].sum())),
        (f"Backorder (open, remaining qty > 0, due before {cl['as_of'].iloc[0].date() if len(cl) else ''})", int(cl["backorder"].sum())),
    ]
    return pd.DataFrame(rows, columns=["measure", "count"])
