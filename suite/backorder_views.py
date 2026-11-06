"""Shared, date-correct definitions for past-due open work orders."""
from __future__ import annotations

import pandas as pd
import numpy as np
import re


def _local_date(value):
    if isinstance(value, (pd.Timestamp,)):
        return value.normalize() if pd.notna(value) else pd.NaT
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        try:
            return pd.Timestamp(value).normalize()
        except Exception:
            return pd.NaT
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "nat", "none"}:
        return pd.NaT
    # Preserve ISO year-first source dates; dayfirst=True would silently turn
    # 2026-10-08 into 2026-08-10 on some pandas versions.
    year_first = bool(re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", text))
    try:
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=not year_first)
        return parsed.normalize() if pd.notna(parsed) else pd.NaT
    except Exception:
        return pd.NaT


def local_date(value):
    """Public scalar parser for source due dates, preserving ISO and Thai dates."""
    return _local_date(value)


def _truth(value):
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y", "closed", "complete", "completed"}
    try:
        return bool(value) if pd.notna(value) else False
    except Exception:
        return False


def effective_closed(frame,columns):
    result=frame[columns].apply(lambda col:col.map(_truth)).any(axis=1) if columns else pd.Series(False,index=frame.index)
    if 'Manual Whole WO status' in frame:
        status=frame['Manual Whole WO status'];known=status.isin(['OPEN','CLOSED'])
        result.loc[known]=status[known].eq('CLOSED')
    return result


def overdue_backorders(master, as_of):
    """Return only WOs that are open, have positive balance, and were due before as_of.

    Due today is not overdue. Dates are interpreted as local calendar dates; callers
    pass the Thailand/Phan Thong as-of date explicitly. Original source columns remain.
    """
    if not isinstance(master, pd.DataFrame) or master.empty:
        return pd.DataFrame()
    x = master.copy()
    wo_col = "Work Order" if "Work Order" in x else ("WO" if "WO" in x else None)
    if wo_col is None or "Due Date" not in x:
        return pd.DataFrame()
    if wo_col != "Work Order":
        x["Work Order"] = x[wo_col]
    x["Work Order"] = x["Work Order"].astype(str).str.strip()
    x["Due Date"] = x["Due Date"].map(_local_date)

    closed_cols = [c for c in ("Authoritative Closed", "Strict Closed", "Overall Closed", "Packing Closed", "Final Closed") if c in x]
    if closed_cols:
        x["_closed"] = effective_closed(x,closed_cols)
    else:
        x["_closed"] = False

    qty_col = next((c for c in ("pcs", "Open quantity (pcs)", "Open Qty", "Open Qty pcs") if c in x), None)
    if qty_col:
        x["_open_qty"] = pd.to_numeric(x[qty_col], errors="coerce").fillna(0).clip(lower=0)
    else:
        order = pd.to_numeric(x.get("Order Qty", 0), errors="coerce")
        if not isinstance(order, pd.Series):
            order = pd.Series(float(order or 0), index=x.index)
        packed = pd.to_numeric(x.get("Packing Actual Qty", x.get("Packing Actual", 0)), errors="coerce")
        if not isinstance(packed, pd.Series):
            packed = pd.Series(float(packed or 0), index=x.index)
        x["_open_qty"] = (order.fillna(0) - packed.fillna(0)).clip(lower=0)

    x = x[x["Work Order"].ne("")].copy()
    if x.empty:
        return x
    # Production masters may repeat a WO across source/process rows. Keep one
    # delivery row per WO: earliest due date, largest reported remaining balance,
    # and closed if any authoritative closure flag says the whole WO is closed.
    _closed_by_wo = x.groupby("Work Order")["_closed"].any()
    _qty_by_wo = x.groupby("Work Order")["_open_qty"].max()
    _due_by_wo = x.groupby("Work Order")["Due Date"].min()
    x = x.drop_duplicates("Work Order", keep="first").set_index("Work Order", drop=False)
    x["_closed"] = _closed_by_wo.reindex(x.index).fillna(False)
    x["_open_qty"] = _qty_by_wo.reindex(x.index).fillna(0)
    x["Due Date"] = _due_by_wo.reindex(x.index)
    x = x[(~x["_closed"]) & (x["_open_qty"] > 0) & x["Due Date"].notna()]
    x = x[x["Due Date"] < pd.Timestamp(as_of).normalize()].copy()
    if x.empty:
        return x.assign(**{"Late days": pd.Series(dtype="int64")})

    x["pcs"] = x["_open_qty"]
    x["Late days"] = (pd.Timestamp(as_of).normalize() - x["Due Date"]).dt.days
    category_col = "Product Category" if "Product Category" in x else ("Category" if "Category" in x else None)
    x["Product Category"] = x[category_col].astype(str).str.strip().str.upper() if category_col else "UNKNOWN"
    x["Product Category"] = x["Product Category"].replace({"F": "P", "": "UNKNOWN", "NAN": "UNKNOWN", "NONE": "UNKNOWN"})

    if "ton" not in x:
        if "Plan2026 kg/pc" in x:
            kgpc = pd.to_numeric(x["Plan2026 kg/pc"], errors="coerce").fillna(0)
            x["ton"] = x["pcs"] * kgpc / 1000.0
        elif "Net Weight g/pc" in x:
            gpc = pd.to_numeric(x["Net Weight g/pc"], errors="coerce").fillna(0)
            x["ton"] = x["pcs"] * gpc / 1_000_000.0
        else:
            x["ton"] = 0.0
    else:
        x["ton"] = pd.to_numeric(x["ton"], errors="coerce").fillna(0)
    x["Due Month"] = x["Due Date"].dt.to_period("M").astype(str)
    return x.drop(columns=["_closed", "_open_qty"], errors="ignore").reset_index(drop=True)


def overdue_month_category(master, as_of):
    """Aggregate shared overdue definition by month/category; never includes future demand."""
    x = overdue_backorders(master, as_of)
    if x.empty:
        return pd.DataFrame(columns=["Due Month", "Product Category", "Status", "Qty pcs", "Weight ton", "WOs"])
    return x.groupby(["Due Month", "Product Category"], as_index=False).agg(
        **{"Qty pcs": ("pcs", "sum"), "Weight ton": ("ton", "sum"), "WOs": ("Work Order", "nunique")}
    ).assign(Status="OVERDUE OPEN")


def overdue_backorder_totals(master, as_of):
    """Authoritative dashboard totals, computed from the same deduplicated WO list."""
    rows = overdue_backorders(master, as_of)
    if rows.empty:
        return {"WOs": 0, "Qty pcs": 0.0, "Weight ton": 0.0}
    return {
        "WOs": int(rows["Work Order"].astype(str).nunique()),
        "Qty pcs": float(pd.to_numeric(rows["pcs"], errors="coerce").fillna(0).sum()),
        "Weight ton": float(pd.to_numeric(rows["ton"], errors="coerce").fillna(0).sum()),
    }


def recent_open_closed_month_category(master, as_of, months=3):
    """Current WO open/closed snapshot by due month and category, bounded to recent months.

    Open rows use current remaining quantity; closed rows use total order quantity.
    This is a current-status view grouped by due month, not a historical month-end
    snapshot. Strict past-due backorder totals should still use overdue_backorders.
    """
    cols=["Due Month","Status","Product Category","Qty pcs","Weight ton","WOs"]
    if not isinstance(master,pd.DataFrame) or master.empty:return pd.DataFrame(columns=cols)
    x=master.copy()
    wo_col="Work Order" if "Work Order" in x else ("WO" if "WO" in x else None)
    if not wo_col or "Due Date" not in x:return pd.DataFrame(columns=cols)
    x["Work Order"]=x[wo_col].astype(str).str.strip()
    x=x[x["Work Order"].ne("")].copy()
    if x.empty:return pd.DataFrame(columns=cols)
    x["Due Date"]=x["Due Date"].map(_local_date)
    if x["Due Date"].isna().all():return pd.DataFrame(columns=cols)
    asof=pd.Timestamp(as_of).normalize()
    current=pd.Period(asof,freq="M")
    first=current-(max(int(months),1)-1)
    x=x[x["Due Date"].notna() & x["Due Date"].dt.to_period("M").between(first,current)].copy()
    if x.empty:return pd.DataFrame(columns=cols)
    closed_cols=[c for c in ("Authoritative Closed","Strict Closed","Overall Closed","Packing Closed","Final Closed") if c in x]
    x["_closed"]=x[closed_cols].apply(lambda col:col.map(_truth)).any(axis=1) if closed_cols else False
    order=pd.to_numeric(x.get("Order Qty",x.get("QTY",0)),errors="coerce")
    if not isinstance(order,pd.Series):order=pd.Series(float(order or 0),index=x.index)
    packed=pd.to_numeric(x.get("Packing Actual Qty",x.get("Packing Actual",0)),errors="coerce")
    if not isinstance(packed,pd.Series):packed=pd.Series(float(packed or 0),index=x.index)
    if "pcs" in x:
        remain=pd.to_numeric(x["pcs"],errors="coerce").fillna(0).clip(lower=0)
    elif "Open Qty" in x:
        remain=pd.to_numeric(x["Open Qty"],errors="coerce").fillna(0).clip(lower=0)
    else:
        remain=(order.fillna(0)-packed.fillna(0)).clip(lower=0)
    x["_order_qty"]=order.fillna(packed).fillna(0).clip(lower=0)
    x["_remain"]=remain
    # Whole-WO closure or zero remaining makes the order closed for this view.
    x["_closed"]=x["_closed"] | x["_remain"].le(0)
    x["Status"]=x["_closed"].map({True:"CLOSED",False:"OPEN"})
    x["_measure_qty"]=np.where(x["_closed"],x["_order_qty"],x["_remain"])
    cat_col="Product Category" if "Product Category" in x else ("Category" if "Category" in x else None)
    x["Product Category"]=x[cat_col].fillna("").astype(str).str.strip().str.upper() if cat_col else "UNKNOWN"
    x["Product Category"]=x["Product Category"].replace({"F":"P","":"UNKNOWN","NAN":"UNKNOWN","NONE":"UNKNOWN","#N/A":"UNKNOWN"})
    if "Plan2026 kg/pc" in x:
        kgpc=pd.to_numeric(x["Plan2026 kg/pc"],errors="coerce").fillna(0)
        x["_weight_ton"]=x["_measure_qty"]*kgpc/1000.0
    elif "Net Weight g/pc" in x:
        gpc=pd.to_numeric(x["Net Weight g/pc"],errors="coerce").fillna(0)
        x["_weight_ton"]=x["_measure_qty"]*gpc/1_000_000.0
    elif "ton" in x and "pcs" in x:
        denominator=pd.to_numeric(x["pcs"],errors="coerce").replace(0,np.nan)
        tpc=pd.to_numeric(x["ton"],errors="coerce").fillna(0)/denominator
        x["_weight_ton"]=(x["_measure_qty"]*tpc).fillna(0)
    else:x["_weight_ton"]=0.0
    x["Due Month"]=x["Due Date"].dt.to_period("M").astype(str)
    x=x.sort_values("Due Date").drop_duplicates("Work Order",keep="first")
    out=x.groupby(["Due Month","Status","Product Category"],as_index=False).agg(
        **{"Qty pcs":("_measure_qty","sum"),"Weight ton":("_weight_ton","sum"),"WOs":("Work Order","nunique")})
    return out[cols].sort_values(["Due Month","Status","Product Category"]).reset_index(drop=True)


def future_open_month_category(master, as_of):
    """Open demand due today or later, kept separate from strict overdue WOs."""
    if not isinstance(master, pd.DataFrame) or master.empty:
        return pd.DataFrame(columns=["Due Month", "Product Category", "Status", "Qty pcs", "Weight ton", "WOs"])
    x = master.copy()
    wo_col = "Work Order" if "Work Order" in x else ("WO" if "WO" in x else None)
    if wo_col is None or "Due Date" not in x:
        return pd.DataFrame(columns=["Due Month", "Product Category", "Status", "Qty pcs", "Weight ton", "WOs"])
    if wo_col != "Work Order":
        x["Work Order"] = x[wo_col]
    x["Work Order"] = x["Work Order"].astype(str).str.strip()
    x["Due Date"] = x["Due Date"].map(_local_date)
    closed_cols = [c for c in ("Authoritative Closed", "Strict Closed", "Overall Closed", "Packing Closed", "Final Closed") if c in x]
    x["_closed"] = effective_closed(x,closed_cols) if closed_cols else False
    qty_col = next((c for c in ("pcs", "Open quantity (pcs)", "Open Qty", "Open Qty pcs") if c in x), None)
    if qty_col:
        x["_open_qty"] = pd.to_numeric(x[qty_col], errors="coerce").fillna(0).clip(lower=0)
    else:
        order = pd.to_numeric(x.get("Order Qty", 0), errors="coerce")
        if not isinstance(order, pd.Series): order = pd.Series(float(order or 0), index=x.index)
        packed = pd.to_numeric(x.get("Packing Actual Qty", x.get("Packing Actual", 0)), errors="coerce")
        if not isinstance(packed, pd.Series): packed = pd.Series(float(packed or 0), index=x.index)
        x["_open_qty"] = (order.fillna(0) - packed.fillna(0)).clip(lower=0)
    x = x[x["Work Order"].ne("")].copy()
    if x.empty: return pd.DataFrame(columns=["Due Month", "Product Category", "Status", "Qty pcs", "Weight ton", "WOs"])
    closed = x.groupby("Work Order")["_closed"].any()
    qty = x.groupby("Work Order")["_open_qty"].max()
    due = x.groupby("Work Order")["Due Date"].min()
    x = x.drop_duplicates("Work Order", keep="first").set_index("Work Order", drop=False)
    x["_closed"] = closed.reindex(x.index).fillna(False)
    x["_open_qty"] = qty.reindex(x.index).fillna(0)
    x["Due Date"] = due.reindex(x.index)
    x = x[(~x["_closed"]) & (x["_open_qty"] > 0) & x["Due Date"].notna()]
    x = x[x["Due Date"] >= pd.Timestamp(as_of).normalize()].copy()
    if x.empty: return pd.DataFrame(columns=["Due Month", "Product Category", "Status", "Qty pcs", "Weight ton", "WOs"])
    x["pcs"] = x["_open_qty"]
    cat = "Product Category" if "Product Category" in x else ("Category" if "Category" in x else None)
    x["Product Category"] = x[cat].astype(str).str.strip().str.upper() if cat else "UNKNOWN"
    x["Product Category"] = x["Product Category"].replace({"F": "P", "": "UNKNOWN", "NAN": "UNKNOWN", "NONE": "UNKNOWN"})
    if "ton" not in x:
        kgpc = pd.to_numeric(x.get("Plan2026 kg/pc", pd.Series(0, index=x.index)), errors="coerce").fillna(0)
        x["ton"] = x["pcs"] * kgpc / 1000.0
    else:
        x["ton"] = pd.to_numeric(x["ton"], errors="coerce").fillna(0)
    x["Due Month"] = x["Due Date"].dt.to_period("M").astype(str)
    return x.groupby(["Due Month", "Product Category"], as_index=False).agg(
        **{"Qty pcs": ("pcs", "sum"), "Weight ton": ("ton", "sum"), "WOs": ("Work Order", "nunique")}
    ).assign(Status="DUE TODAY / FUTURE OPEN")


def mps_order_buckets(plan, as_of, year, start_month):
    """Split firm WOs into overdue recovery and in-horizon future demand.

    This keeps MPS recovery aligned with the dashboard's overdue definition:
    overdue means due strictly before today's local date and positive open qty.
    Future demand is restricted to the selected calendar year and never overlaps
    with overdue recovery. Missing due dates are deliberately left unbucketed.
    """
    cols = list(plan.columns) if isinstance(plan, pd.DataFrame) else []
    empty = pd.DataFrame(columns=cols)
    if not isinstance(plan, pd.DataFrame) or plan.empty or "Due Date" not in plan or "Open Qty" not in plan:
        return empty.copy(), empty.copy()
    x = plan.copy()
    x["Due Date"] = x["Due Date"].map(_local_date)
    x["Open Qty"] = pd.to_numeric(x["Open Qty"], errors="coerce").fillna(0).clip(lower=0)
    if "WO" in x:
        x["WO"] = x["WO"].astype(str).str.strip()
        x = x[x["WO"].ne("")].copy()
        if x.empty:
            return empty.copy(), empty.copy()
        # The same WO may be repeated in a source export. Count its largest
        # remaining balance once and retain its earliest due date.
        agg = {c: "first" for c in x.columns if c not in {"WO", "Due Date", "Open Qty"}}
        agg.update({"Due Date": "min", "Open Qty": "max"})
        x = x.groupby("WO", as_index=False, dropna=False).agg(agg)
    asof = _local_date(as_of)
    if pd.isna(asof):
        return empty.copy(), empty.copy()
    overdue = x[x["Open Qty"].gt(0) & x["Due Date"].notna() & x["Due Date"].lt(asof)].copy()
    future = x[
        x["Open Qty"].gt(0)
        & x["Due Date"].notna()
        & x["Due Date"].ge(asof)
        & x["Due Date"].dt.year.eq(int(year))
        & x["Due Date"].dt.month.ge(int(start_month))
    ].copy()
    return overdue, future
