"""Physical-audit report: category, date, status and location.

Uses only stored audits and Plan/work-order fields. Missing category stays
'NOT IN PLAN' instead of being guessed.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def _norm(s) -> str:
    return "".join(ch for ch in str(s or "").upper() if ch.isalnum())


def load_all_audits(db_path) -> pd.DataFrame:
    """Every physical-audit row (not only the latest per WO)."""
    path = Path(db_path) if db_path else None
    if not path or not path.exists():
        return pd.DataFrame()
    con = sqlite3.connect(str(path))
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "mobile_audits" not in tables:
            return pd.DataFrame()
        if "mobile_audit_photos" in tables:
            df = pd.read_sql_query("""SELECT a.*,
                (SELECT p.filename FROM mobile_audit_photos p WHERE p.audit_id=a.id ORDER BY p.id DESC LIMIT 1) AS photo_filename
                FROM mobile_audits a ORDER BY a.created_at DESC, a.id DESC""", con)
        else:
            df = pd.read_sql_query("SELECT * FROM mobile_audits ORDER BY created_at DESC", con)
        if df.empty or "work_orders" not in tables or "wo_id" not in df.columns:
            return df
        wcols = {r[1] for r in con.execute("PRAGMA table_info(work_orders)")}
        keep = [c for c in ("wo_id", "product_category", "product_code", "customer_name") if c in wcols]
        if "wo_id" not in keep:
            return df
        wo = pd.read_sql_query(f"SELECT {', '.join(keep)} FROM work_orders", con)
        return df.merge(wo, on="wo_id", how="left")
    except Exception:
        return pd.DataFrame()
    finally:
        con.close()


def load_latest_audits(db_path) -> pd.DataFrame:
    path = Path(db_path) if db_path else None
    if not path or not path.exists():
        return pd.DataFrame()
    con = sqlite3.connect(str(path))
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "mobile_audits" not in tables:
            return pd.DataFrame()
        acols={r[1] for r in con.execute("PRAGMA table_info(mobile_audits)")}
        observed="a.observed_process" if "observed_process" in acols else "''"
        qty_unit="a.qty_unit" if "qty_unit" in acols else "'pcs'"
        qty_unknown="a.qty_unknown" if "qty_unknown" in acols else "CASE WHEN a.verified_qty IS NULL THEN 1 ELSE 0 END"
        photo="(SELECT p.filename FROM mobile_audit_photos p WHERE p.audit_id=a.id ORDER BY p.id LIMIT 1)" if "mobile_audit_photos" in tables else "''"
        q = f"""
        SELECT a.id AS audit_id, a.wo_id, a.physical_status, a.physical_location, a.verified_qty,
               {observed} AS observed_process, {qty_unit} AS qty_unit, {qty_unknown} AS qty_unknown,
               {photo} AS photo_filename, a.user_name, a.created_at, a.notes,
               COALESCE(w.product_category,'') AS product_category,
               COALESCE(w.product_code,'') AS product_code,
               COALESCE(w.customer_name,'') AS customer_name,
               COALESCE(w.plan_location,'') AS plan_location, COALESCE(w.qty,0) AS plan_qty, COALESCE(w.due_date,'') AS due_date
        FROM mobile_audits a
        LEFT JOIN work_orders w ON w.wo_id=a.wo_id
        WHERE a.id IN (SELECT MAX(id) FROM mobile_audits GROUP BY wo_id)
        ORDER BY a.created_at DESC
        """
        if "work_orders" not in tables:
            observed_fallback = "observed_process" if "observed_process" in acols else "''"
            q = f"""
            SELECT a.id AS audit_id, a.wo_id, a.physical_status, a.physical_location, a.verified_qty,
                   {observed_fallback} AS observed_process, {qty_unit} AS qty_unit, {qty_unknown} AS qty_unknown,
                   {photo} AS photo_filename, a.user_name, a.created_at, a.notes,
                   '' AS product_category, '' AS product_code, '' AS customer_name, '' AS plan_location, 0 AS plan_qty, '' AS due_date
            FROM mobile_audits a
            WHERE id IN (SELECT MAX(id) FROM mobile_audits GROUP BY wo_id)
            ORDER BY created_at DESC
            """
        out=pd.read_sql_query(q, con)
        if not out.empty:
            out["Location comparison"]=["PLAN NOT RECORDED" if not str(p or "").strip() else ("MATCH" if _norm(p)==_norm(a) else "DIFFERENT — CHECK") for p,a in zip(out.get("plan_location",pd.Series("",index=out.index)),out.get("physical_location",pd.Series("",index=out.index)))]
            out["Plan qty"] = pd.to_numeric(out.get("plan_qty",0),errors="coerce")
            out["Audit qty variance vs full WO"] = pd.to_numeric(out.get("verified_qty"),errors="coerce") - out["Plan qty"]
        return out
    except Exception:
        return pd.DataFrame()
    finally:
        con.close()


def enrich_from_plan(audits: pd.DataFrame, plan_df) -> pd.DataFrame:
    out = audits.copy() if audits is not None else pd.DataFrame()
    if out.empty or plan_df is None:
        return out
    try:
        if plan_df.empty or "Work Order" not in plan_df.columns:
            return out
    except Exception:
        return out
    plan = plan_df.copy()
    plan["_k"] = plan["Work Order"].map(_norm)
    keep = [c for c in ["Work Order", "Product Category", "Product Code", "Customer", "Section", "pcs", "Due Date"] if c in plan.columns]
    plan = plan[keep + ["_k"]].drop_duplicates("_k", keep="last")
    out["_k"] = out["wo_id"].map(_norm)
    merged = out.merge(plan, on="_k", how="left")
    if "product_category" in merged.columns and "Product Category" in merged.columns:
        blank = merged["product_category"].fillna("").astype(str).str.strip().isin(("", "NAN", "#N/A"))
        merged.loc[blank, "product_category"] = merged.loc[blank, "Product Category"]
    return merged.drop(columns="_k", errors="ignore")


def analyze(audits: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if audits is None or audits.empty:
        return {
            "summary": pd.DataFrame([{"Audited WOs": 0, "Locations": 0, "Statuses": 0, "Categories": 0}]),
            "by_category": pd.DataFrame(columns=["Product category", "WOs", "Qty"]),
            "by_date": pd.DataFrame(columns=["Date", "WOs", "Qty"]),
            "by_status": pd.DataFrame(columns=["Status", "WOs", "Qty"]),
            "by_location": pd.DataFrame(columns=["Location", "WOs", "Qty"]),
            "by_process": pd.DataFrame(columns=["Observed process", "WOs", "Qty"]),
            "by_location_comparison": pd.DataFrame(columns=["Location comparison", "WOs", "Qty"]),
        }
    df = audits.copy()
    cat = df.get("product_category", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
    cat = cat.replace({"": "NOT IN PLAN", "NAN": "NOT IN PLAN", "#N/A": "NOT IN PLAN", "None": "NOT IN PLAN"})
    df["Product category"] = cat.str.upper()
    df["Status"] = df.get("physical_status", pd.Series("", index=df.index)).fillna("").astype(str).str.upper()
    df["Location"] = df.get("physical_location", pd.Series("", index=df.index)).fillna("").astype(str)
    df["Location"] = df["Location"].replace({"": "Not recorded"})
    df["Observed process"] = df.get("observed_process", pd.Series("", index=df.index)).fillna("").astype(str).str.strip().replace({"": "Not recorded"})
    df["Plan location"] = df.get("plan_location",pd.Series("",index=df.index)).fillna("").astype(str).str.strip().replace({"": "Not in plan"})
    df["Location comparison"] = ["PLAN NOT RECORDED" if p=="Not in plan" else ("MATCH" if _norm(p)==_norm(a) else "DIFFERENT — CHECK") for p,a in zip(df["Plan location"],df["Location"])]
    df["Qty"] = pd.to_numeric(df.get("verified_qty"), errors="coerce")
    when = pd.to_datetime(df.get("created_at"), errors="coerce")
    df["Date"] = when.dt.strftime("%Y-%m-%d")
    df.loc[when.isna(), "Date"] = "Unknown date"

    def grp(col):
        g = df.groupby(col, dropna=False).agg(WOs=("wo_id", "nunique"), Qty=("Qty", "sum")).reset_index()
        return g.sort_values("WOs", ascending=False)

    return {
        "summary": pd.DataFrame([{
            "Audit records": int(len(df)),
            "Audited WOs": int(df["wo_id"].nunique()),
            "Locations": int(df["Location"].nunique()),
            "Statuses": int(df["Status"].nunique()),
            "Categories": int(df["Product category"].nunique()),
            "Location differences": int(df["Location comparison"].eq("DIFFERENT — CHECK").sum()),
            "Audited qty pcs": float(pd.to_numeric(df.get("Qty"),errors="coerce").sum(min_count=1) or 0),
            "Quantity unknown": int(pd.to_numeric(df.get("Qty"),errors="coerce").isna().sum()),
            "Photos linked": int(df.get("photo_filename",pd.Series("",index=df.index)).fillna("").astype(str).str.strip().ne("").sum()),
        }]),
        "by_category": grp("Product category"),
        "by_date": grp("Date").sort_values("Date"),
        "by_status": grp("Status"),
        "by_location": grp("Location"),
        "by_process": grp("Observed process"),
        "by_location_comparison": grp("Location comparison"),
    }


def load_open_wip_by_process(db_path) -> pd.DataFrame:
    """Summarize remaining planned quantity by latest recorded process; this is not a physical count."""
    path = Path(db_path) if db_path else None
    cols = ["Process", "WOs", "Remaining order pcs"]
    if not path or not path.exists():
        return pd.DataFrame(columns=cols)
    con = sqlite3.connect(str(path))
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "work_orders" not in tables:
            return pd.DataFrame(columns=cols)
        w = pd.read_sql_query("SELECT wo_id,qty,status,plan_location FROM work_orders", con)
        e = pd.read_sql_query("SELECT wo_id,event_type,qty,process_name,event_time FROM events ORDER BY id", con) if "events" in tables else pd.DataFrame()
    finally:
        con.close()
    if w.empty:
        return pd.DataFrame(columns=cols)
    latest = e.drop_duplicates("wo_id", keep="last").set_index("wo_id") if not e.empty else pd.DataFrame()
    produced = {}
    accepted = {}
    if not e.empty:
        finished = e[e["event_type"].astype(str).str.upper().isin(["PARTIAL_COMPLETE", "COMPLETE"])].copy()
        finished["qty"] = pd.to_numeric(finished["qty"], errors="coerce")
        produced = finished.groupby("wo_id")["qty"].max().to_dict()
        qc = e[e["event_type"].astype(str).str.upper().eq("QC_ACCEPT")].copy()
        qc["qty"] = pd.to_numeric(qc["qty"], errors="coerce")
        accepted = qc.groupby("wo_id")["qty"].max().to_dict()
    rows = []
    for _, r in w.iterrows():
        wid = str(r["wo_id"])
        ev = latest.loc[wid] if not latest.empty and wid in latest.index else None
        state = str(ev.get("event_type", "") if ev is not None else r.get("status", "")).upper()
        if state in {"CANCELLED", "VOID"}:
            continue
        raw_qty = pd.to_numeric(pd.Series([r.get("qty")]), errors="coerce").iloc[0]
        qty = float(raw_qty) if pd.notna(raw_qty) else 0.0
        remain = max(qty - float(produced.get(wid, 0) or 0), 0)
        if state in {"FINAL_COMPLETE", "QC_ACCEPTED"} and float(accepted.get(wid, 0) or 0) >= qty > 0:
            continue
        process = str(ev.get("process_name", "") if ev is not None else "").strip() or str(r.get("plan_location", "")).strip() or "Planning / not scanned"
        rows.append({"Process": process, "WOs": wid, "Remaining order pcs": remain})
    d = pd.DataFrame(rows)
    return (d.groupby("Process", as_index=False).agg(WOs=("WOs", "nunique"), **{"Remaining order pcs": ("Remaining order pcs", "sum")}).sort_values("WOs", ascending=False)
            if not d.empty else pd.DataFrame(columns=cols))


def load_production_wip_snapshot(base_dir) -> tuple[pd.DataFrame, list[str]]:
    """Read active monthly Production WIP details with the shared traceable parser."""
    from apps.daily.production_wip_sources import candidates
    from suite.production_wip_data import read_production_wip

    ranked, metadata, errors = candidates(base_dir)
    rows = []
    for section, paths in ranked.items():
        last_error = None
        for path in paths:
            try:
                rows.append(read_production_wip(path, section, metadata.get(str(Path(path).resolve()), {})))
                if path != paths[0]:
                    errors.append(f"{section}: latest copy {paths[0].name} was unreadable; used previous readable copy {path.name}.")
                break
            except Exception as exc:
                last_error = exc
        else:
            if last_error is not None:
                errors.append(f"{section}: no readable WIP workbook. Latest file {paths[0].name}: {last_error}")
    return (pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()), errors
