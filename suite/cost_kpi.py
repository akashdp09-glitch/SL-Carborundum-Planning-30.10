"""Traceable costing diagnostics and planning KPI views for RC29.

The calculations intentionally separate source-reported results from diagnostic
alternatives when source formulas or units conflict. No result here is an
approved standard cost unless the underlying rates and method are approved.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import re

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string


def _num(value):
    return float(value) if isinstance(value, (int, float)) and value == value else 0.0


def _wo_key(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _sheet(wb, exact, contains=None):
    if exact in wb.sheetnames:
        return wb[exact]
    if contains:
        for name in wb.sheetnames:
            if contains.casefold() in name.casefold():
                return wb[name]
    raise ValueError(f"Required sheet not found: {exact}")


def material_exposure(stock_path: str | Path, price_paths: list[tuple[str, str | Path]]):
    """Return material lines and source-coded audit metadata from current files."""
    stock_path = Path(stock_path)
    swb = load_workbook(stock_path, data_only=True, read_only=True)
    ws = _sheet(swb, "Abrasive")
    first = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    headers = {str(v).strip(): i for i, v in enumerate(first) if v is not None}
    needed = {"รหัสสินค้า", "ใบงานเปิดผลิต", "วัตถุดิบคงคลัง", "รอวัถุดิบเข้า", "รอผลLAB", "BalanceStock"}
    missing = needed - set(headers)
    if missing:
        swb.close()
        raise ValueError("Abrasive sheet is missing required headers: " + ", ".join(sorted(missing)))
    prices: dict[str, list[dict]] = {}
    for label, p in price_paths:
        if not p or not Path(p).is_file():
            continue
        pwb = load_workbook(p, data_only=True, read_only=True)
        try:
            pws = _sheet(pwb, "ราคาวัตถุดิบ NEW")
            for r, row in enumerate(pws.iter_rows(min_row=3, values_only=True), start=3):
                code = str(row[1] or "").strip() if len(row) > 1 else ""
                rate = row[8] if len(row) > 8 else None
                if code:
                    prices.setdefault(code, []).append({"source": label, "row": r, "rate": rate, "description": row[2] if len(row) > 2 else None})
        finally:
            pwb.close()
    rows = []
    for r, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        code = str(row[headers["รหัสสินค้า"]] or "").strip()
        if not code:
            continue
        demand = _num(row[headers["ใบงานเปิดผลิต"]])
        onhand = _num(row[headers["วัตถุดิบคงคลัง"]])
        incoming = _num(row[headers["รอวัถุดิบเข้า"]])
        labhold = _num(row[headers["รอผลLAB"]])
        balance = _num(row[headers["BalanceStock"]])
        gap_onhand = max(0.0, demand - onhand)
        gap_book = max(0.0, -balance)
        if gap_onhand <= 0 and gap_book <= 0:
            continue
        matches = prices.get(code, [])
        positive = [m for m in matches if isinstance(m["rate"], (int, float)) and m["rate"] > 0]
        distinct = sorted({round(float(m["rate"]), 12) for m in positive})
        conflict = len(distinct) > 1
        rate = distinct[0] if len(distinct) == 1 else None
        psource = next((m for m in positive if rate is not None and round(float(m["rate"]), 12) == rate), None)
        rows.append({
            "Stock row": r, "Material code": code,
            "Description": row[headers.get("รายละเอียดสินค้า", 4)] if len(row) > headers.get("รายละเอียดสินค้า", 4) else None,
            "Open-WO demand (g)": demand, "On hand (g)": onhand,
            "Inbound waiting (g)": incoming, "Lab hold (g)": labhold,
            "Workbook balance (g)": balance, "Gap vs on hand (g)": gap_onhand,
            "Workbook shortage (g)": gap_book, "Rate (THB/g)": rate,
            "Costed workbook gap (THB)": gap_book * rate if rate is not None else None,
            "Rate conflict": conflict,
            "Rate source": f"{psource['source']} | ราคาวัตถุดิบ NEW!I{psource['row']}" if psource else ("Conflicting rates" if conflict else "No positive exact-code rate"),
            "Stock source": f"{stock_path.name} | Abrasive row {r}"
        })
    swb.close()
    return rows


def replacement_diagnostics(replacement_path: str | Path, plan_path: str | Path | None = None):
    """Compare cached source costs and reject counts with formula diagnostics."""
    rp = Path(replacement_path)
    wbv = load_workbook(rp, data_only=True, read_only=True)
    wbf = load_workbook(rp, data_only=False, read_only=True)
    plan_map = {}
    if plan_path and Path(plan_path).is_file():
        pwb = load_workbook(plan_path, data_only=True, read_only=True)
        pws = _sheet(pwb, "แผนการเผา", "แผนการเผา")
        wo_col = column_index_from_string("A")
        rej_col = column_index_from_string("FH")
        for r, row in enumerate(pws.iter_rows(min_row=4, min_col=1, max_col=rej_col, values_only=True), start=4):
            wo = row[wo_col - 1]
            if wo:
                plan_map[_wo_key(wo)] = (r, row[rej_col - 1])
        pwb.close()
    details = []
    divide_formula_rows = 0
    material_formula_issue_rows = 0
    for sheet_name in ("SAINT-GOBAIN", "PT Rutan"):
        if sheet_name not in wbv.sheetnames:
            continue
        s, sf = wbv[sheet_name], wbf[sheet_name]
        rates = [_num(v) for v in next(s.iter_rows(min_row=2, max_row=2, min_col=12, max_col=17, values_only=True))]
        for r, (row, formula_row) in enumerate(zip(s.iter_rows(min_row=3, values_only=True), sf.iter_rows(min_row=3, values_only=True)), start=3):
            wo = row[0] if row else None
            if not wo:
                continue
            gw = _num(row[2] if len(row) > 2 else None)
            rejects = _num(row[3] if len(row) > 3 else None)
            raw_rate, bond_rate = _num(row[4] if len(row) > 4 else None), _num(row[5] if len(row) > 5 else None)
            plan = plan_map.get(_wo_key(wo))
            formula_k = str(formula_row[10] or "") if len(formula_row) > 10 else ""
            expected_k = f"=+I{r}+J{r}"
            bad_k = sheet_name == "SAINT-GOBAIN" and formula_k.strip().upper().replace("=+", "=") != expected_k.strip().upper().replace("=+", "=")
            if bad_k:
                material_formula_issue_rows += 1
            proc_formulas = [str(v or "") for v in formula_row[11:17]]
            divides = any("/" in f for f in proc_formulas)
            divide_formula_rows += int(divides)
            reported_unit = _num(row[17] if len(row) > 17 else None)
            reported_total = _num(row[18] if len(row) > 18 else None)
            plan_rej = _num(plan[1]) if plan and isinstance(plan[1], (int, float)) else None
            alt_mat = gw * (0.8 * raw_rate + 0.2 * bond_rate)
            alt_unit = alt_mat + gw * sum(rates)
            details.append({
                "Customer": sheet_name, "Cost file row": r, "Work order": str(wo),
                "Plan row": plan[0] if plan else None, "Spec": row[1] if len(row) > 1 else None,
                "Gross weight (kg/pc)": gw, "Rejects in cost file": rejects,
                "Rejects in Plan FH": plan_rej, "Raw rate (THB/kg)": raw_rate,
                "Bond rate (THB/kg)": bond_rate, "Source material cost/pc (THB)": _num(row[10] if len(row) > 10 else None),
                "Material formula issue": bad_k, "Process formula divides": divides,
                "Source unit cost/pc (THB)": reported_unit, "Source extended cost (THB)": reported_total,
                "Diagnostic material/pc (THB)": alt_mat,
                "Diagnostic unit cost/pc (THB)": alt_unit,
                "Diagnostic extended cost (THB)": alt_unit * rejects,
                "Reject quantity match": plan_rej == rejects if plan_rej is not None else None,
                "Cost source": f"{rp.name} | {sheet_name} row {r}",
                "Plan source": f"{Path(plan_path).name} | แผนการเผ row {plan[0]} FH" if plan and plan_path else "Plan match unavailable"
            })
    total_sheet = wbv["สรุปต้นทุนการผลิต"] if "สรุปต้นทุนการผลิต" in wbv.sheetnames else None
    reported_rejects = _num(total_sheet.cell(6, 3).value) if total_sheet else sum(x["Rejects in cost file"] for x in details)
    reported_cost = _num(total_sheet.cell(6, 4).value) if total_sheet else sum(x["Source extended cost (THB)"] for x in details)
    result = {
        "details": details,
        "reported_rejects": reported_rejects,
        "reported_cost": reported_cost,
        "diagnostic_cost": sum(x["Diagnostic extended cost (THB)"] for x in details),
        "plan_rejects_matched": sum(x["Rejects in Plan FH"] or 0 for x in details if x["Rejects in Plan FH"] is not None),
        "wo_plan_matches": sum(x["Plan row"] is not None for x in details),
        "quantity_mismatches": sum(x["Reject quantity match"] is False for x in details),
        "material_formula_issue_rows": material_formula_issue_rows,
        "process_divide_formula_rows": divide_formula_rows,
        "source_file": rp.name,
    }
    wbv.close(); wbf.close()
    return result


KPI_ROWS = [
    {"KPI": "Material shortage exposure", "Formula": "Σ max(0, demand g − on-hand g); separately show workbook balance, inbound and lab hold", "Unit": "g / kg / t; THB only for priced codes", "Cadence": "Daily snapshot / weekly / monthly", "Can calculate": "Snapshot: yes", "Gap": "Date-phased receipts and lab release; current effective price list", "Source": "Plan BOM + Stock Abrasive J:N + exact-code price list"},
    {"KPI": "Overdue open backlog", "Formula": "Count open WOs with remaining qty and due date < Bangkok as-of date; also sum remaining qty", "Unit": "WOs + source quantity units", "Cadence": "Daily snapshot; trend needs history", "Can calculate": "Snapshot: yes", "Gap": "Immutable dated snapshots for trend; confirmed due-date/closure policy", "Source": "Plan 2026 due, QTY, pack actual, closure"},
    {"KPI": "Section plan attainment", "Formula": "Actual completed ÷ planned qty for matching section and period", "Unit": "% plus each section's native unit", "Cadence": "Daily / weekly / monthly / quarterly", "Can calculate": "Current source comparison: partial", "Gap": "Frozen plan versions, event dates, section units", "Source": "Plan 2026 section planned/actual blocks"},
    {"KPI": "Post-release change complaint rate", "Formula": "Released WOs with validated post-release change complaint ÷ WOs released", "Unit": "% of WOs", "Cadence": "Weekly / monthly / quarterly", "Can calculate": "No", "Gap": "Append-only change/NCR event ledger with WO, reason, old/new, timestamp", "Source": "Not present in supplied files"},
    {"KPI": "Reject / replacement cost", "Formula": "Σ reject qty × approved SKU manufacturing cost; show uncosted coverage separately", "Unit": "THB + pcs", "Cadence": "Weekly / monthly / quarterly", "Can calculate": "Provisional only", "Gap": "Resolve count conflicts and validate process rates and cost method", "Source": "Replacement cost workbook + Plan FH + current approved cost master"},
    {"KPI": "On-time customer delivery", "Formula": "WOs shipped on/before confirmed customer date ÷ WOs shipped", "Unit": "% of shipped WOs", "Cadence": "Monthly / quarterly", "Can calculate": "No", "Gap": "Actual shipment event date and confirmed customer PO date", "Source": "Plan due dates alone are not delivery actuals"},
    {"KPI": "Plan stability", "Formula": "Released line-day qty or WOs changed after freeze ÷ released line-day qty or WOs", "Unit": "% / count", "Cadence": "Weekly / monthly", "Can calculate": "Going forward only", "Gap": "Frozen daily plans and append-only reschedule/change reasons", "Source": "Latest Plan alone cannot reconstruct prior versions"},
]


def render(st, source_manager, user="Unknown", can_edit=True):
    """Streamlit page; all uploads are revisioned in the shared source manager."""
    st.markdown("### Cost & Planning KPI / ต้นทุนและ KPI วางแผน")
    st.caption("Source-linked results. Snapshot files are dated evidence. Formula conflicts are shown as diagnostics, not silently accepted as approved costs.")
    slots = {
        "COST_RESIN": ("Resin costing workbook", ["xlsx", "xlsm"]),
        "COST_VITIFILE": ("Vitifile costing workbook", ["xlsx", "xlsm"]),
        "COST_REPLACEMENT": ("Replacement/reject cost workbook", ["xlsx", "xlsm"]),
    }
    with st.expander("Cost data sources / แหล่งข้อมูลต้นทุน", expanded=False):
        for sid, (label, types) in slots.items():
            active = source_manager.active(sid)
            path = source_manager.active_path(sid)
            st.write(f"**{label}:** {active['original_name'] if active else 'Not loaded'}" + (f" · revision {active['revision_no']} · SHA-256 {active['sha256'][:12]} · {path}" if active and path else ""))
            if can_edit:
                up = st.file_uploader(f"Upload / replace {label}", type=types, key=f"cost_upload_{sid}")
                if up is not None:
                    payload = up.getvalue()
                    digest = hashlib.sha256(payload).hexdigest()
                    seen_key = f"cost_upload_sha_{sid}"
                    if st.session_state.get(seen_key) != digest:
                        result = source_manager.import_bytes(sid, up.name, payload, user, note="Cost & KPI page")
                        (st.success if result.ok else st.error)(result.message)
                        if result.ok:
                            st.session_state[seen_key] = digest
    plan_path = source_manager.active_path("PLAN_2026")
    stock_path = source_manager.active_path("STOCK_ON_HAND")
    resin_path = source_manager.active_path("COST_RESIN")
    vit_path = source_manager.active_path("COST_VITIFILE")
    repl_path = source_manager.active_path("COST_REPLACEMENT")
    if not plan_path or not stock_path:
        st.warning("Load Plan 2026 and Stock on Hand once using the shared source manager. This page will reuse those active revisions.")
    if stock_path:
        try:
            materials = material_exposure(stock_path, [("Resin price list", resin_path), ("Vitifile price list", vit_path)])
            n = len(materials)
            negative = sum(r["Workbook shortage (g)"] for r in materials)
            gap = sum(r["Gap vs on hand (g)"] for r in materials)
            valued = sum(r["Costed workbook gap (THB)"] or 0 for r in materials)
            missing_rates = sum(r["Workbook shortage (g)"] > 0 and r["Rate (THB/g)"] is None for r in materials)
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Workbook negative balance",f"{negative:,.0f} g")
            c2.metric("Demand above on-hand",f"{gap:,.0f} g")
            c3.metric("Priced subset only",f"฿{valued:,.2f}")
            c4.metric("Negative lines without positive price",missing_rates)
            st.caption(f"Stock source: {stock_path.name} · SHA-256 {hashlib.sha256(stock_path.read_bytes()).hexdigest()} · Balance formula must be verified against the source workbook. Incoming and lab-hold are displayed separately.")
            st.dataframe(pd.DataFrame(materials), use_container_width=True, hide_index=True)
            st.download_button("Download material exposure CSV",pd.DataFrame(materials).to_csv(index=False).encode("utf-8-sig"),"Material_Shortage_Exposure.csv","text/csv",key="cost_material_csv")
        except Exception as exc:
            st.error(f"Material exposure could not be calculated: {exc}")
    if repl_path:
        try:
            diag = replacement_diagnostics(repl_path, plan_path)
            st.markdown("#### Replacement cost — source result and diagnostic method")
            a,b,c,d=st.columns(4)
            a.metric("Workbook reported cost",f"฿{diag['reported_cost']:,.2f}")
            b.metric("Workbook reject qty",f"{diag['reported_rejects']:,.0f}")
            c.metric("Plan FH rejects for matched WOs",f"{diag['plan_rejects_matched']:,.0f}")
            d.metric("WO reject mismatches",f"{diag['quantity_mismatches']} / {len(diag['details'])}")
            st.warning(f"Diagnostic alternative is ฿{diag['diagnostic_cost']:,.2f}, not approved. {diag['material_formula_issue_rows']} material formula rows use an inconsistent formula; process rate division appears in {diag['process_divide_formula_rows']} WO rows. Confirm the rate unit/method before using any alternative as official cost.")
            st.caption(f"Replacement source: {repl_path.name} · rows matched to Plan: {diag['wo_plan_matches']} / {len(diag['details'])}")
            det = pd.DataFrame(diag["details"])
            if not det.empty:
                st.dataframe(det, use_container_width=True, hide_index=True, height=430)
                st.download_button("Download replacement detail CSV",det.to_csv(index=False).encode("utf-8-sig"),"Replacement_Cost_Trace.csv","text/csv",key="cost_replacement_csv")
        except Exception as exc:
            st.error(f"Replacement-cost analysis could not be calculated: {exc}")
    st.markdown("#### Result-oriented planning KPI / KPI ผลลัพธ์ที่วัดได้")
    st.dataframe(pd.DataFrame(KPI_ROWS),use_container_width=True,hide_index=True,height=420)
    st.caption("Weekly/monthly/quarterly KPI trends require dated source snapshots or append-only actual/change events. A single current workbook cannot prove historical performance.")
