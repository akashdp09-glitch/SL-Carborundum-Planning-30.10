"""Streamlit view of the shared Source Manager (thin: all logic lives in suite.source_manager)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .source_manager import SLOTS, SourceManager


def _operator_slot_ids():
    return [sid for sid, s in SLOTS.items() if not s.knowledge_only]


def render(sm: SourceManager, user: str = "", can_edit: bool = True, key: str = "smgr"):
    st.subheader("Shared Source Manager / ตัวจัดการแหล่งข้อมูลส่วนกลาง")
    st.caption("Start with **Plan-2026 on Home**. Other factory files are requested on the page that needs them and saved revisions are reused. "
               "Code-format references and training PDFs/PPTX stay in **Knowledge / F1**. Sales' dated registered-product master and Production's dated packaging standard are separate, replaceable sources.")
    if st.button("Go to Home for Plan-2026 / ไปหน้าหลักเพื่อโหลด Plan-2026", key=f"{key}_home"):
        st.query_params["page"] = "control"
        st.rerun()
    adopted = sm.adopt_existing(user or "adopt") if can_edit else []
    if adopted:
        st.info("Registered files already stored by the Daily Planner: " + ", ".join(a.slot_id for a in adopted))
    tbl = pd.DataFrame([r for r in sm.status_table() if not SLOTS[r["slot"]].knowledge_only])
    if not tbl.empty:
        st.dataframe(tbl[["slot", "label", "state", "revision", "file", "imported_at", "imported_by", "sha256", "affects"]], use_container_width=True, hide_index=True)
    miss = sm.missing()
    _core = [s for s in miss if s in {"PLAN_2026"}]
    _optional = [s for s in miss if s not in {"PLAN_2026", "COST_RESIN", "COST_VITIFILE", "COST_REPLACEMENT"}]
    if _core:
        st.error("Plan-2026 is missing. Open Home → Start here: Plan-2026. Other pages will use that same active copy.")
    if _optional:
        st.caption("Other inputs appear on the analysis page that needs them: " + ", ".join(_optional[:12]) + ("…" if len(_optional) > 12 else ""))
    if any(s in miss for s in ("COST_RESIN", "COST_VITIFILE", "COST_REPLACEMENT")):
        st.caption("Costing files: upload once from Reports → Cost & Planning KPI Analysis when cost results are needed.")
    bad = [c for c in sm.consistency_report() if not c["matches_active_revision"]]
    if bad:
        st.error("Published file differs from the active revision (modules would read different data): " + "; ".join(b["slot"] for b in bad))
    else:
        st.success("Consistency check: every module reads a published file that is byte-identical to the active revision.")
    with st.expander("Revision history, sheet roles and rollback", expanded=False):
        ops = _operator_slot_ids()
        slot_id = st.selectbox("Factory file", ops, format_func=lambda s: SLOTS[s].label, key=f"{key}_hslot")
        hist = sm.history(slot_id)
        if hist:
            st.dataframe(pd.DataFrame(hist)[["revision_no", "active", "original_name", "imported_at", "imported_by", "size_bytes", "sha256", "stored_path", "note"]], use_container_width=True, hide_index=True)
            act = sm.active(slot_id)
            import json
            roles = json.loads(act["sheet_roles"] or "[]") if act else []
            if roles:
                st.markdown("**Sheet roles (decided from headers, not position)**")
                st.dataframe(pd.DataFrame(roles)[["sheet", "role", "confidence", "evidence", "rows", "cols"]], use_container_width=True, hide_index=True)
            if can_edit and len(hist) > 1:
                rev = st.selectbox("Roll back to revision", [h["revision_no"] for h in hist if not h["active"]], key=f"{key}_rb")
                if st.button("Roll back (keeps all history)", key=f"{key}_rbgo"):
                    r = sm.rollback(slot_id, rev, user)
                    st.success(r.message)
        else:
            st.caption("No revisions yet. Open the analysis page that requires this source to add it there.")
    with st.expander("Import log"):
        ev = sm.events(100)
        if ev:
            st.dataframe(pd.DataFrame(ev), use_container_width=True, hide_index=True)
