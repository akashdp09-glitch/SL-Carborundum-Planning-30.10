from __future__ import annotations

import streamlit as st

from . import exporters as X
from .sept_analysis import read_sept, by_product, MEASURES
from .source_manager import SourceManager
from .common import REPO_ROOT


def render(sm: SourceManager, key: str = "sept"):
    st.subheader("Monthly Open / Close Job analysis — four separate measures")
    a = sm.active("SEPT_OPEN_CLOSED")
    if a:
        path, label = a["stored_path"], f"active source revision {a['revision_no']} ({a['original_name']}, imported {a['imported_at']})"
    else:
        path = str(REPO_ROOT / "apps" / "daily" / "JOB_REGISTER_REFERENCE_SEP2026.xlsx")
        label = "bundled September REFERENCE sample (import the current month's register in the Home Open/Close slot)"
    st.caption(f"Source: {label}. Sales requests, issued production orders, unissued items and production item closures are never added or netted against each other; "
               "closing a section or an item is not issuing or closing the order.")
    res = read_sept(path)
    st.dataframe(res.measures.drop(columns=["total_cells"]), use_container_width=True, hide_index=True)
    st.markdown("**By order type and product (columns stay separate)**")
    st.dataframe(by_product(res), use_container_width=True, hide_index=True)
    if res.issues:
        st.error("Cells that disagree with the sheet's own totals:\n- " + "\n- ".join(res.issues))
    else:
        st.success("Day cells re-added equal the sheet's Total cells for every row.")
    if res.notes:
        with st.expander("Notes written in the workbook"):
            for n in res.notes:
                st.markdown(f"- {n}")
    st.download_button("Download (xlsx)", X.to_workbook({"Measures": res.measures, "By product": by_product(res), "Row totals": res.totals, "Day cells": res.long}), "OpenClose_job_analysis.xlsx", key=f"{key}_dl",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
