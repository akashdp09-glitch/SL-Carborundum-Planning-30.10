"""Build a downloadable workbook from the current, already calculated Daily Plan."""
from __future__ import annotations

import io
import pandas as pd


def build_daily_plan_workbook(allp, caps, wip, risk, issues, result) -> bytes:
    """Return a multi-sheet Excel evidence pack; never reads or changes source files."""
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        sheets = [
            (allp, "Daily Plan"), (caps, "Capacity vs Plan"),
            (wip, "Planning WIP Snapshot"), (risk, "Delivery Risk"),
            (issues, "Issues"),
        ]
        for frame, name in sheets:
            if isinstance(frame, pd.DataFrame):
                frame.to_excel(writer, index=False, sheet_name=name)
        extras = {
            "stock": "Stock Used", "bom": "BOM Used", "lead_time_master": "Lead Time Master",
            "lead_time_applied": "WO Lead Time", "ab_pair_audit": "AB Pair Audit",
            "ot_suggestion": "OT Suggestion", "capacity_evidence": "Capacity Evidence",
            "recovery_feasibility": "Recovery Feasibility",
            "recovery_capacity_evidence": "Recovery Capacity Evidence",
            "recovery_actions": "Recovery Actions",
        }
        for key, name in extras.items():
            frame = result.get(key)
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                frame.to_excel(writer, index=False, sheet_name=name)
        for section, frame in (result.get("plans") or {}).items():
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                safe = str(section).replace("/", "-")[:31]
                if safe not in writer.sheets:
                    frame.to_excel(writer, index=False, sheet_name=safe)
    return out.getvalue()
