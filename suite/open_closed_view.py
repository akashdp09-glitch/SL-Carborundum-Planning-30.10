"""Open / closed work-order view from files already on Home.

Daily Open / Closed used to live only inside the Daily Planner *after*
CREATE DAILY PLAN. Hub then asked for Daily Status uploads even when
Plan-2026 (and optional Daily Status / job register) were already stored.

This module reads those existing files. It does not invent closure flags.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from . import closure_rules as CR
from .central_paths import JOB_REGISTER_FILE, PLAN_FILE, resolve_file, shared_root
from .common import bkk_today
from .plan_reader import ORDER, load_plan


def from_plan(path, cache_dir=None, today=None) -> dict:
    plan = load_plan(path, cache_dir=cache_dir)
    cl = CR.classify(plan, today or bkk_today())
    by_section = []
    for section in ORDER:
        closed = cl[f"{section} closed"].astype(bool)
        by_section.append({
            "Section": section,
            "Closed WOs": int(closed.sum()),
            "Open WOs": int((~closed).sum()),
        })
    by_section.append({
        "Section": "WHOLE ORDER (Packing EU or production FC)",
        "Closed WOs": int(cl["whole_closed"].sum()),
        "Open WOs": int((~cl["whole_closed"]).sum()),
    })
    wo = cl.copy()
    wo["Status"] = wo["whole_closed"].map(lambda v: "CLOSED" if bool(v) else "OPEN")
    keep = [c for c in ("wo", "Status", "qty", "due", "state", "remaining_qty", "backorder") if c in wo.columns]
    return {
        "source": "Plan-2026",
        "path": str(Path(path).resolve()),
        "wos": int(len(plan)),
        "by_section": pd.DataFrame(by_section),
        "rule_summary": CR.summary(cl),
        "open": wo.loc[~wo["whole_closed"], keep].sort_values("wo") if keep else wo,
        "closed": wo.loc[wo["whole_closed"], keep].sort_values("wo") if keep else wo,
    }


def from_daily_status(df: pd.DataFrame) -> dict:
    """Date-tab Daily Status rows already parsed by the Daily Planner. Empty in → empty out."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return {"source": "Daily Status", "dates": [], "rows": pd.DataFrame()}
    x = df.copy()
    x["Date"] = pd.to_datetime(x.get("Date"), errors="coerce").dt.normalize()
    for col in ("Section Required Qty", "Cumulative Actual Qty", "Balance Qty", "Production Plan Qty", "Production Actual Qty"):
        if col not in x:
            x[col] = 0
        x[col] = pd.to_numeric(x[col], errors="coerce").fillna(0)
    keys = [c for c in ("Work Order", "Section", "Date") if c in x.columns]
    if not keys:
        return {"source": "Daily Status", "dates": [], "rows": pd.DataFrame()}
    agg = x.groupby(keys, dropna=False, as_index=False).agg(
        **{
            "Required Qty": ("Section Required Qty", "max"),
            "Cumulative Actual Qty": ("Cumulative Actual Qty", "max"),
            "Balance Qty": ("Balance Qty", "min"),
            "Daily Plan Qty": ("Production Plan Qty", "sum"),
            "Daily Actual Qty": ("Production Actual Qty", "sum"),
        }
    )
    agg["Daily Status"] = (
        (agg["Required Qty"] > 0)
        & ((agg["Cumulative Actual Qty"] >= agg["Required Qty"]) | (agg["Balance Qty"] <= 0))
    ).map(lambda v: "CLOSED" if v else "OPEN / IN PROGRESS")
    dates = sorted(d for d in agg["Date"].dropna().unique())
    return {"source": "Daily Status", "dates": dates, "rows": agg}


def list_daily_status_files(root=None) -> list[Path]:
    folder = Path(root or shared_root()) / "DAILY_STATUS"
    if not folder.exists():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in {".xlsx", ".xlsm"} and not p.name.startswith("~$")
    )


def render(st, plan_path: Optional[str] = None, daily_status=None, job_path: Optional[str] = None,
           cache_dir=None, key: str = "oc"):
    """Streamlit: show open/closed from whatever is already stored. Upload boxes stay elsewhere."""
    plan_path = plan_path or resolve_file(PLAN_FILE)
    job_path = job_path or resolve_file(JOB_REGISTER_FILE)
    shown = False

    if plan_path and Path(plan_path).exists():
        try:
            data = from_plan(plan_path, cache_dir=cache_dir)
        except Exception as exc:
            st.error(f"Plan-2026 is active but could not be read for open/closed: {exc}")
            data = None
        if data:
            shown = True
            st.success(f"Using active Plan-2026 — {data['wos']:,} work orders. `{data['path']}`")
            st.caption("Whole-order CLOSED = Packing (EU) closed OR production FC closed. Earlier section closures do not close the order.")
            c1, c2, c3 = st.columns(3)
            c1.metric("Work orders", f"{data['wos']:,}")
            c2.metric("Closed (whole order)", f"{int(data['by_section'].iloc[-1]['Closed WOs']):,}")
            c3.metric("Open (whole order)", f"{int(data['by_section'].iloc[-1]['Open WOs']):,}")
            st.dataframe(data["by_section"], use_container_width=True, hide_index=True)
            st.dataframe(data["rule_summary"], use_container_width=True, hide_index=True)
            open_tab, closed_tab = st.tabs(["🟠 Open work orders", "🟢 Closed work orders"])
            with open_tab:
                st.dataframe(data["open"], use_container_width=True, hide_index=True, height=360)
            with closed_tab:
                st.dataframe(data["closed"], use_container_width=True, hide_index=True, height=360)

    ds = from_daily_status(daily_status)
    if not ds["rows"].empty:
        shown = True
        rows = ds["rows"]
        st.success(f"Daily Status already loaded — {len(rows):,} WO×section×date rows. No second upload.")
        labels = {pd.Timestamp(d).strftime("%Y-%m-%d"): pd.Timestamp(d) for d in ds["dates"]}
        if labels:
            chosen = st.selectbox("Production date (worksheet tab)", list(labels)[::-1], key=f"{key}_ds_date")
            day = rows[rows["Date"].eq(labels[chosen])].copy()
        else:
            day = rows
            st.warning("Daily Status rows have no valid worksheet-tab dates.")
        if not day.empty:
            m1, m2, m3 = st.columns(3)
            m1.metric("WOs this date", f"{day['Work Order'].nunique():,}" if "Work Order" in day else "0")
            m2.metric("Closed", f"{day.loc[day['Daily Status'].eq('CLOSED'), 'Work Order'].nunique():,}" if "Work Order" in day else "0")
            m3.metric("Open / in progress", f"{day.loc[day['Daily Status'].ne('CLOSED'), 'Work Order'].nunique():,}" if "Work Order" in day else "0")
            show = [c for c in ("Work Order", "Section", "Daily Status", "Required Qty", "Cumulative Actual Qty", "Balance Qty", "Daily Plan Qty", "Daily Actual Qty") if c in day.columns]
            t_open, t_closed = st.tabs(["🟠 Open / In Progress", "🟢 Closed"])
            with t_open:
                st.dataframe(day[day["Daily Status"].ne("CLOSED")][show], use_container_width=True, hide_index=True, height=320)
            with t_closed:
                st.dataframe(day[day["Daily Status"].eq("CLOSED")][show], use_container_width=True, hide_index=True, height=320)
    else:
        ds_files = list_daily_status_files()
        if ds_files:
            st.info("Daily Status files already exist in shared data (" + ", ".join(p.name for p in ds_files[:8]) + "). The current section copies are reused; replace them from this page only when you have a newer workbook.")
        elif shown:
            st.caption("No Daily Status section workbook yet. Plan-2026 open/closed above is enough to start. Add section workbooks using Update sources for this page only if you need process-wise status.")

    if job_path and Path(job_path).exists():
        st.caption(
            f"Monthly Open/Close Job register already loaded: `{Path(job_path).resolve()}`. "
            "This is a separate JOB vs Item monthly measure. Replace the active workbook here when Planning revises it. "
            "It is not Plan-2026 and JOB is not netted against Item."
        )

    if not shown:
        st.warning("Plan-2026 is not on Home yet. Upload it once there. Other pages must not ask for the same file again.")
    return shown
