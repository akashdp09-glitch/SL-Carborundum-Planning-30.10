"""Capacity registry view: source file / sheet / cell / unit / time basis for every figure, conflicts, gaps, per-resource utilisation."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .capacity import load_capacity, Demand, utilisation, kiln_throughput, TONNE_CONVERSION_NOTE


@st.cache_data(show_spinner=False)
def _load(path: str, sha: str, oos=()):
    return load_capacity(path, out_of_service_cells=list(oos))


def render(path, sha: str = "", key: str = "capreg", shared_root=None, user: str = ""):
    from .user_settings import SettingsStore, effective_out_of_service, KEY_OUT_OF_SERVICE
    from pathlib import Path as _P
    if not _P(path).is_file():
        st.error(f"Capacity file is missing: {path}. Use the Update sources panel to upload CAPACITY_DATABASE.xlsx.")
        return
    sstore = SettingsStore(_P(shared_root) / "DATA" / "user_settings.sqlite") if shared_root else None
    model = _load(str(path), sha, tuple(effective_out_of_service(sstore)))
    st.subheader("Capacity registry - units and time basis preserved / ทะเบียนกำลังการผลิต")
    st.caption(f"Source: **{model.source_file}** (revision sha256 {sha[:12] or 'n/a'}). Tonnes, pieces, mill counts, persons and days are NEVER added together; "
               "utilisation is shown per resource in its own unit. " + TONNE_CONVERSION_NOTE)
    df = model.frame()
    c1, c2, c3 = st.columns(3)
    sec = c1.selectbox("Section", ["All"] + sorted(df.section.unique()), key=f"{key}_sec")
    kind = c2.selectbox("Unit kind", ["All"] + sorted(df.unit_kind.unique()), key=f"{key}_kind")
    only_sched = c3.checkbox("Only values that can be scheduled (have a time basis)", False, key=f"{key}_sched")
    v = df
    if sec != "All": v = v[v.section == sec]
    if kind != "All": v = v[v.unit_kind == kind]
    if only_sched: v = v[v.schedulable]
    st.dataframe(v[["section", "resource", "measure", "value", "value_max", "unit", "unit_kind", "time_basis", "schedulable", "source_file", "sheet", "cell", "flags", "assumptions", "attributes"]],
                 use_container_width=True, hide_index=True, height=360)
    st.caption(f"{len(v)} of {len(df)} figures shown. Schedulable = has an explicit time basis and is in use.")
    tabs = st.tabs(["Conflicts in the approved source", "Information still missing", "Kiln programs / lead times", "Utilisation of one resource", "Owner decisions", "Machines not working"])
    with tabs[0]:
        if not [c for c in model.conflicts if c.get("severity") != "rounding"]:
            st.success("No open conflicts. Conflicts closed by an owner decision are listed under 'Owner decisions'.")
        for c in model.conflicts:
            if c.get("severity") == "rounding":
                continue
            with st.expander(f"{c['id']} - {c['issue'][:110]}"):
                st.write(c["issue"])
                st.code("\n".join(c["entries"]))
                if c.get("decision_needed"):
                    st.warning("Decision needed: " + c["decision_needed"])
        n_round = sum(1 for c in model.conflicts if c.get("severity") == "rounding")
        if n_round:
            st.caption(f"{n_round} further Forming rows differ from Cap./Hr. x hours only by rounding (<= 6%); listed in the export, no decision asked.")
        st.download_button("Download conflicts (CSV)", pd.DataFrame(model.conflicts).to_csv(index=False).encode("utf-8-sig"), "capacity_conflicts.csv", key=f"{key}_dlc")
    with tabs[1]:
        for g in model.gaps:
            st.markdown(f"- {g}")
        st.info("Until these are supplied, any schedule built on this registry is PROVISIONAL and is never labelled confirmed feasible.")
    with tabs[2]:
        st.markdown("**Kiln programs (Cap เตา F:H)**")
        kp = model.kiln_programs.copy()
        if not kp.empty:
            kp["provisional t/day per kiln (low-high)"] = [f"{kiln_throughput(model, str(p).split()[0])['t_per_day_low']:.2f}-{kiln_throughput(model, str(p).split()[0])['t_per_day_high']:.2f}" for p in kp["program"]]
        st.dataframe(kp, use_container_width=True, hide_index=True)
        st.markdown("**Kilns / ovens and the programs they may run**")
        st.dataframe(model.kiln_machines, use_container_width=True, hide_index=True)
        st.markdown("**Lead time (days) by process and product group**")
        st.dataframe(model.lead_times, use_container_width=True, hide_index=True, height=300)
    with tabs[3]:
        cand = df[df.schedulable]
        res = st.selectbox("Resource", sorted(cand.section + " :: " + cand.resource + " :: " + cand.measure + " [" + cand.sheet + "!" + cand.cell + "]"), key=f"{key}_res")
        rec = cand[(cand.section + " :: " + cand.resource + " :: " + cand.measure + " [" + cand.sheet + "!" + cand.cell + "]") == res].iloc[0]
        amt = st.number_input(f"Demand in the SAME unit ({rec.unit}) per {'month' if rec.time_basis == 'per month' else 'day'}", 0.0, 1e9, 0.0, key=f"{key}_dem")
        wd = None
        if rec.time_basis == "per month":
            wd = st.number_input("Working days per month (explicit - not assumed)", 0.0, 31.0, 0.0, key=f"{key}_wd") or None
        hc = st.number_input("Headcount (only for per-person figures)", 0.0, 500.0, 0.0, key=f"{key}_hc") or None if "person" in rec.time_basis else None
        out = utilisation(model, [Demand(rec.section, amt, rec.unit_kind, rec.unit, "month" if rec.time_basis == "per month" else "day", resource=rec.resource,
                                          measure_contains=rec.measure.split(" (")[0], headcount=hc)], wd)
        st.dataframe(out, use_container_width=True, hide_index=True)
    with tabs[4]:
        from .user_settings import owner_decisions
        od = owner_decisions()
        st.caption(f"Recorded {od['recorded']} from the factory owner's answers. Source: knowledge/owner_decisions.json")
        st.dataframe(pd.DataFrame(od["decisions"])[["id", "topic", "owner_answer", "applied_in"]], use_container_width=True, hide_index=True)
        st.markdown("**Source conflicts closed by those decisions (exact entries kept)**")
        for c in model.resolved:
            with st.expander(f"{c['id']} - {c['decision'][:90]}"):
                st.code("\n".join(c["entries"]))
                st.write(c["decision"])
    with tabs[5]:
        st.caption("Forming machine cells (sheet CAP ขึ้นรูป, column D 'M/C.') that are not working now. Their capacity is excluded from planning. The first list is the owner's of 2026-10-04; "
                   "any user can change it and every change is stored with user, time and reason.")
        st.dataframe(pd.DataFrame(model.out_of_service), use_container_width=True, hide_index=True)
        if sstore is None:
            st.info("Open this page from the hub to edit the list (it needs the shared data folder).")
        else:
            allcells = [f"D{r}" for r in range(5, 44)]
            cur = effective_out_of_service(sstore)
            pick = st.multiselect("Cells whose machines are NOT working", allcells, default=[c for c in cur if c in allcells], key=f"{key}_oos")
            why = st.text_input("Reason for the change (required)", key=f"{key}_oos_why")
            if st.button("Save list", key=f"{key}_oos_save", disabled=not (why.strip() and user and pick != cur)):
                sstore.set(KEY_OUT_OF_SERVICE, pick, user, why)
                st.success("Saved. Planning pages use the new list immediately.")
                st.rerun()
            if not user:
                st.caption("Sign in to change the list.")
            h = sstore.history(KEY_OUT_OF_SERVICE)
            if not h.empty:
                st.markdown("**History**")
                st.dataframe(h[["changed_at", "changed_by", "reason", "value_json"]], use_container_width=True, hide_index=True)
        st.warning("The same machine codes also appear on forming rows that were not listed; those rows stay in service until the owner says otherwise.")
