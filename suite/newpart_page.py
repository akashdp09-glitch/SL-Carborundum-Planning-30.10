"""New part / project planning + MPS netting UI (thin wrapper over suite.newpart_planner)."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from . import exporters as X
from .capacity import load_capacity
from .common import bkk_today
from .newpart_planner import (Item, Context, Calendar, SectionCap, plan_item, net_demand, ScenarioStore, STATUS_BLOCKED, existing_bookings)
from .source_manager import SourceManager

GROUPS = ["S", "T", "P", "R", "PB", "M"]
PROGRAMS = ["", "P1", "P2", "P3", "P3 (T14)", "P6", "KM-185", "KM-170"]


@st.cache_data(show_spinner=False)
def _cap(path, sha, oos_cells=()):
    return load_capacity(path, out_of_service_cells=list(oos_cells))


def render(sm: SourceManager, plan, stock, user: str, key: str = "np"):
    st.subheader("New part / project plan and MPS netting")
    st.caption("Starts from today's Thailand local date (Phan Thong, Chonburi), uses the active Capacity, Plan and Stock revisions, and is always PROVISIONAL: it is never labelled feasible until every gap below is closed and the factory confirms.")
    cap_rev = sm.active("CAPACITY_DATABASE")
    if not cap_rev:
        st.error("No capacity source is active. Import CAPACITY_DATABASE in the Source Manager.")
        return
    from .calendar_ui import store_for
    from .user_settings import effective_out_of_service
    sstore = store_for(sm.root)
    oos_cells = tuple(effective_out_of_service(sstore))
    model = _cap(cap_rev["stored_path"], cap_rev["sha256"], oos_cells)
    today = st.date_input("Planning date (defaults to today, Phan Thong, Chonburi)", bkk_today(), key=f"{key}_today")
    t1, t2, t3 = st.tabs(["New part plan", "MPS: firm vs forecast", "Saved scenarios"])
    (sm.root / "DATA").mkdir(parents=True, exist_ok=True)
    store = ScenarioStore(sm.root / "DATA" / "newpart_scenarios.sqlite")
    with t1:
        c = st.columns(4)
        iid = c[0].text_input("Item / project ID", key=f"{key}_id")
        desc = c[1].text_input("Description", key=f"{key}_desc")
        grp = c[2].selectbox("Product group", GROUPS, index=2, key=f"{key}_grp")
        dtype = c[3].selectbox("Demand type", ["FIRM", "FORECAST"], key=f"{key}_type")
        c = st.columns(4)
        qty = c[0].number_input("Quantity (pcs)", 0.0, 1e9, 0.0, key=f"{key}_qty")
        due = c[1].date_input("Requested date (optional)", None, key=f"{key}_due")
        bond = c[2].selectbox("Bond type", ["", "Vitrified", "Resin"], key=f"{key}_bond")
        prog = c[3].selectbox("Kiln program", PROGRAMS, key=f"{key}_prog")
        c = st.columns(3)
        wkg = c[0].number_input("Weight per piece at FIRED stage (kg), if known", 0.0, 1e6, 0.0, key=f"{key}_wkg", format="%.4f")
        mills = c[1].number_input("Mill count (จำนวนโม่), if known", 0.0, 1e6, 0.0, key=f"{key}_mills")
        ready = c[2].date_input("Material ready date (only if confirmed)", None, key=f"{key}_ready")
        mat_txt = st.text_area("Materials: one per line as CODE,total_kg", "", key=f"{key}_mat", height=70)
        st.markdown("**Calendar (Sunday off; select holidays)**")
        from .calendar_ui import calendar_inputs
        offi, hols = calendar_inputs(sstore, user, f"{key}_cal")
        out_k = st.text_input("Kilns out of service (e.g. T1,T4)", "", key=f"{key}_oos")
        cal = Calendar(offi, tuple(hols), supplied=True)
        st.markdown("**Capacity to apply (unit and time basis must match the demand)**")
        caps = {}
        cols = st.columns(3)
        for i, (step, sec, unit) in enumerate([("Mixing", "Mixing", "mills"), ("Forming", "Forming", "pcs"), ("Grinding", "Grinding", "pcs"), ("Packaging prep", "Packing", "pcs")]):
            opts = [r for r in model.records if r.section == sec and r.unit == unit and r.time_basis == "per day" and r.schedulable]
            labels = ["(none - lead time only)", "(type my own)"] + [f"{r.resource} = {r.value:g} {r.unit}/day [{r.sheet}!{r.cell}]" for r in opts]
            ch = cols[i % 3].selectbox(f"{step} ({unit}/day)", labels, key=f"{key}_cap_{step}")
            if ch == "(type my own)":
                v = cols[i % 3].number_input(f"{step} {unit}/day (user-entered)", 0.0, 1e9, 0.0, key=f"{key}_capv_{step}")
                if v > 0:
                    caps[step] = SectionCap(step, "USER-ENTERED", v, unit, "USER-ENTERED")
            elif not ch.startswith("(none"):
                r = opts[labels.index(ch) - 2]
                caps[step] = SectionCap(step, r.resource, r.value, r.unit, f"{r.sheet}!{r.cell}")
        revs = {}
        for slot in ("CAPACITY_DATABASE", "PLAN_2026", "STOCK_ON_HAND"):
            a = sm.active(slot)
            if a:
                revs[slot] = {"revision": a["revision_no"], "file": a["original_name"], "sha256": a["sha256"][:16], "imported_at": a["imported_at"]}
        mats = []
        for line in mat_txt.splitlines():
            if "," in line:
                code, kg = line.rsplit(",", 1)
                try:
                    mats.append((code.strip(), float(kg)))
                except ValueError:
                    st.warning(f"Ignored line: {line}")
        if st.button("Plan this item", key=f"{key}_go", disabled=not (iid and qty > 0)):
            it = Item(iid, desc, grp, qty, dtype, due, bond or None, prog or None, wkg or None, mills or None, mats, None, ready)
            ctx = Context(today, cal, caps, tuple(x.strip() for x in out_k.split(",") if x.strip()), plan, stock, revs)
            st.session_state[f"{key}_res"] = (plan_item(model, it, ctx), it, ctx)
        got = st.session_state.get(f"{key}_res")
        if got:
            res, it, ctx = got
            (st.error if res.status == STATUS_BLOCKED else st.warning)(f"{res.status} (as of {res.as_of})")
            m = st.columns(3)
            m[0].metric("Finish - optimistic", str(res.finish_optimistic))
            m[1].metric("Finish - conservative", str(res.finish_conservative))
            m[2].metric("Days late vs requested", "n/a" if res.late_days is None else res.late_days)
            for title, items in (("Blockers", res.blockers), ("Bottlenecks", res.bottlenecks), ("Assumptions", res.assumptions), ("Missing information", res.gaps)):
                if items:
                    with st.expander(f"{title} ({len(items)})", expanded=title in ("Blockers", "Bottlenecks")):
                        for x in items:
                            st.markdown(f"- {x}")
            st.markdown("**Schedule (each row cites its Lead Time cell)**")
            st.dataframe(res.schedule, use_container_width=True, hide_index=True)
            if not res.capacity_checks.empty:
                st.markdown("**Capacity checks (own unit, own time basis)**")
                st.dataframe(res.capacity_checks, use_container_width=True, hide_index=True)
            if not res.materials.empty:
                st.markdown("**Materials (stock is dated evidence; reservations = open firm orders)**")
                st.dataframe(res.materials, use_container_width=True, hide_index=True)
            if not res.bookings.empty:
                st.markdown("**Existing bookings from the Plan workbook**")
                st.dataframe(res.bookings, use_container_width=True, hide_index=True)
            c = st.columns(2)
            nm = c[0].text_input("Save draft as", f"{it.item_id} {res.as_of}", key=f"{key}_nm")
            if c[1].button("Save draft scenario", key=f"{key}_save"):
                sid = store.save(nm, it, res, ctx, user)
                st.success(f"Saved scenario #{sid} (DRAFT).")
            st.download_button("Download traceable export (xlsx)", X.to_workbook(res.sheets()), f"NewPart_{it.item_id}_{res.as_of}.xlsx", key=f"{key}_dl",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with t2:
        st.caption("Paste demand lines: product, month (YYYY-MM), qty, type FIRM|FORECAST, reference. Forecast is reduced by firm orders of the same product and month so it is never counted twice.")
        txt = st.text_area("CSV lines", "product,month,qty,type,reference\n", height=140, key=f"{key}_mps")
        try:
            df = pd.read_csv(pd.io.common.StringIO(txt))
            if not df.empty:
                st.dataframe(net_demand(df), use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"Cannot read lines: {e}")
        if plan is not None:
            st.markdown("**Existing open orders already booked in each section (from the active Plan workbook)**")
            st.dataframe(existing_bookings(plan, today), use_container_width=True, hide_index=True)
    with t3:
        lst = store.list()
        if lst.empty:
            st.caption("No saved scenarios yet.")
        else:
            st.dataframe(lst, use_container_width=True, hide_index=True)
            sid = st.selectbox("Scenario", list(lst.id), key=f"{key}_sid")
            st.download_button("Download scenario export", X.to_workbook(store.export_sheets(int(sid))), f"Scenario_{sid}.xlsx", key=f"{key}_sdl",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
