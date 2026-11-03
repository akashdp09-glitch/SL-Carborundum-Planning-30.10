"""Read-only inspection of an already uploaded firing schedule and its stored pattern."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


def _norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _find_col(columns, aliases):
    normalized = {_norm(c): c for c in columns}
    for alias in aliases:
        key = _norm(alias)
        if key in normalized:
            return normalized[key]
    for c in columns:
        key = _norm(c)
        if any(key.startswith(_norm(a)) for a in aliases if _norm(a)):
            return c
    return None


def _read_table(xls, sheet_names, preferred, required):
    ordered = sorted(sheet_names, key=lambda s: (0 if _norm(s) in {_norm(x) for x in preferred} else 1, sheet_names.index(s)))
    for sheet in ordered:
        for header_row in range(12):
            try:
                frame = pd.read_excel(xls, sheet_name=sheet, header=header_row)
            except Exception:
                continue
            if frame is None or frame.empty:
                continue
            mapping = {name: _find_col(frame.columns, aliases) for name, aliases in required.items()}
            if all(mapping.values()):
                return frame, sheet, mapping
    return pd.DataFrame(), "", {}


def load_existing_firing(path):
    """Return schedule rows and stored floor geometry without running a planner.

    Operator Print-only workbooks are supported. Physical pattern views are returned
    only when the uploaded workbook itself contains Floor Pattern Data.
    """
    path = Path(path)
    with pd.ExcelFile(path) as xls:
        names = list(xls.sheet_names)
        load_aliases = {
            "Load ID": ("Load ID", "Load Number", "Load No"),
            "Load Date": ("Load Date", "Loading Date", "Firing Date"),
            "Kiln": ("Kiln",),
            "Program": ("Program",),
            "WO": ("Work Order", "Production Code", "WO"),
            "Qty": ("Qty pcs", "Planned Firing Qty", "Planned Qty pcs", "Planned Qty", "Firing Qty", "Qty", "Quantity"),
            "Finish": ("Program Finish Date", "Firing Complete", "Unload Take-Out Date", "Firing Finish Date"),
        }
        # Prefer aggregate loads sheet; otherwise use the issued Operator Print rows.
        table, sheet, cols = _read_table(xls, names, ("Firing Loads", "Released Firing Plan", "Auto Firing Plan"),
                                         {k: load_aliases[k] for k in ("Load ID", "Load Date", "Kiln", "Program", "Qty")})
        if table.empty:
            table, sheet, cols = _read_table(xls, names,
                ("Released Operator Print", "Operator Print", "Firing Detail", "WO DETAIL", "Auto Firing Plan"),
                {k: load_aliases[k] for k in ("Load Date", "Kiln", "Program", "WO", "Qty")})
        if table.empty:
            raise ValueError("No supported firing schedule table found. Use Firing Loads or an Operator Print sheet with kiln, date, program, WO and quantity.")
        out = pd.DataFrame(index=table.index)
        for key, source in cols.items():
            out[key] = table[source]
        if "WO" not in out or not out["WO"].fillna("").astype(str).str.strip().any():
            wo_table, wo_sheet, wo_cols = _read_table(xls, names,
                ("Released Operator Print", "Operator Print", "Firing Detail", "WO DETAIL"),
                {k: load_aliases[k] for k in ("Load Date", "Kiln", "Program", "WO", "Qty")})
            if not wo_table.empty:
                wo_rows = pd.DataFrame({k: wo_table[v] for k, v in wo_cols.items()})
                _wo_load_id = wo_cols.get("Load ID") or _find_col(wo_table.columns, load_aliases["Load ID"])
                if _wo_load_id:
                    wo_rows["Load ID"] = wo_table[_wo_load_id].astype(str).str.strip()
                    out["Load ID"] = out["Load ID"].astype(str).str.strip()
                    wo_rows = wo_rows.groupby("Load ID", as_index=False).agg(WO=("WO", lambda x: ", ".join(dict.fromkeys(str(v).strip() for v in x if str(v).strip()))))
                    out = out.drop(columns=["WO"], errors="ignore").merge(wo_rows, on="Load ID", how="left")
        out["Load Date"] = pd.to_datetime(out["Load Date"], errors="coerce")
        if "Finish" in out:
            out["Finish"] = pd.to_datetime(out["Finish"], errors="coerce")
        out["Qty"] = pd.to_numeric(out["Qty"], errors="coerce").fillna(0)
        out["Kiln"] = out["Kiln"].fillna("").astype(str).str.strip()
        out["Program"] = out["Program"].fillna("").astype(str).str.strip()
        out["WO"] = out.get("WO", pd.Series("", index=out.index)).fillna("").astype(str).str.strip()
        out = out[(out["Qty"] > 0) & out["Load Date"].notna() & out["Kiln"].ne("")].copy()
        if "Load ID" not in out:
            out["Load ID"] = ""
        out["Load ID"] = out["Load ID"].fillna("").astype(str).str.strip()
        no_id = out["Load ID"].eq("")
        out.loc[no_id, "Load ID"] = out.loc[no_id].apply(lambda r: f"{r['Kiln']} | {r['Load Date']:%Y-%m-%d} | {r['Program']}", axis=1)
        # Per-WO print rows are summarized to one existing load; no new allocation is run.
        group_cols = ["Load ID", "Load Date", "Kiln", "Program"]
        agg = {"Qty": "sum", "WO": lambda x: ", ".join(dict.fromkeys(v for v in x if v))}
        if "Finish" in out:
            agg["Finish"] = "max"
        schedule = out.groupby(group_cols, as_index=False, dropna=False).agg(agg)
        schedule["WO Count"] = schedule["WO"].apply(lambda value: len({part.strip() for part in str(value or "").split(",") if part.strip()}))

        pattern_sheet = next((s for s in names if _norm(s) in {_norm("Floor Pattern Data"), _norm("Floor Stack Plan")}), None)
        floors = pd.read_excel(xls, sheet_name=pattern_sheet) if pattern_sheet else pd.DataFrame()
        kiln_sheet = next((s for s in names if _norm(s) == _norm("Kiln Master")), None)
        kiln_master = pd.read_excel(xls, sheet_name=kiln_sheet) if kiln_sheet else pd.DataFrame()
    return {"schedule": schedule.sort_values(["Load Date", "Kiln", "Load ID"], kind="stable"),
            "floor": floors, "kiln_master": kiln_master, "schedule_sheet": sheet,
            "pattern_sheet": pattern_sheet, "filename": path.name}
