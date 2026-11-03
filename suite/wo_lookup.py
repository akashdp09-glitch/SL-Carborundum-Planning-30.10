"""Find a work order that already exists in Home Plan-2026 or sl_planning.db.

Desktop Find WO and the phone scanner used different sources (in-memory Plan
columns vs an empty work_orders table). This module searches the same files
both UIs already use. It never invents a work order.
"""
from __future__ import annotations

import re
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Optional

import pandas as pd

from .central_paths import db_path as _db_path
from .central_paths import resolve_plan

_PLAN_CACHE: dict = {"key": None, "df": None}

PLAN_COLS = (
    "ProductionCode",
    "Customername",
    "CustomernameID",
    "รหัสสินค้า",
    "Specification",
    "QTY",
    "กำหนดส่งใหม่",
    "กำหนดเข้าคลัง",
    "ORDER",
    "PO.NO.",
)


def norm_wo(value) -> str:
    s = urllib.parse.unquote(str(value or "")).strip()
    s = s.rstrip("/").split("/")[-1].strip()
    s = re.sub(r"^(?:SLWO|WO)\s*[:#=-]\s*", "", s, flags=re.I)
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def _cache_key(path: Path) -> tuple:
    st = path.stat()
    return (str(path.resolve()), st.st_mtime, st.st_size)


def load_plan_index(plan_path) -> pd.DataFrame:
    path = Path(plan_path)
    if not path.is_file():
        return pd.DataFrame()
    key = _cache_key(path)
    if _PLAN_CACHE["key"] == key and _PLAN_CACHE["df"] is not None:
        return _PLAN_CACHE["df"]
    raw = pd.read_excel(path, sheet_name="แผนการเผา", header=2, dtype=str)
    if "ProductionCode" not in raw.columns:
        raise ValueError("Plan-2026 sheet แผนการเผา has no ProductionCode column")
    keep = [c for c in PLAN_COLS if c in raw.columns]
    out = raw[keep].copy()
    out.insert(0, "Plan row", out.index.astype(int) + 4)
    out.insert(1, "Work Order", out["ProductionCode"].fillna("").astype(str).str.strip())
    _PLAN_CACHE["key"] = key
    _PLAN_CACHE["df"] = out
    return out


def suggestions_from_df(raw_df, query, limit: int = 12) -> pd.DataFrame:
    if not query or raw_df is None or not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
        return pd.DataFrame()
    q = norm_wo(query)
    qtext = str(query).strip().casefold()
    work = raw_df.copy()
    if "Work Order" not in work.columns:
        if "ProductionCode" not in work.columns:
            return pd.DataFrame()
        work.insert(0, "Work Order", work["ProductionCode"].fillna("").astype(str).str.strip())
    if "Plan row" not in work.columns:
        work.insert(0, "Plan row", work.index.astype(int) + 4)
    code_key = work["Work Order"].map(norm_wo)
    code_mask = (code_key.str.startswith(q) | code_key.str.contains(re.escape(q), regex=True)) if q else pd.Series(False, index=work.index)
    text_cols = [c for c in ("Customername", "CustomernameID", "รหัสสินค้า", "Specification", "ORDER", "PO.NO.") if c in work.columns]
    text_mask = pd.Series(False, index=work.index)
    if qtext:
        for c in text_cols:
            text_mask |= work[c].fillna("").astype(str).str.casefold().str.contains(re.escape(qtext), regex=True, na=False)
    mask = code_mask | text_mask
    if not mask.any():
        return pd.DataFrame()

    def _rank(row):
        k = norm_wo(row.get("Work Order", ""))
        if q and k == q:
            return (0, len(k))
        if q and k.startswith(q):
            return (1, len(k))
        if q and q in k:
            return (2, len(k))
        return (3, len(k))

    out = work.loc[mask].copy()
    out["_rank"] = out.apply(_rank, axis=1)
    return out.sort_values("_rank", kind="stable").drop(columns="_rank").head(limit)


def suggestions_from_plan(plan_path, query, limit: int = 12) -> pd.DataFrame:
    if not plan_path:
        return pd.DataFrame()
    return suggestions_from_df(load_plan_index(plan_path), query, limit=limit)


def suggestions_from_db(db_file, query, limit: int = 12) -> pd.DataFrame:
    if not query or not db_file or not Path(db_file).exists():
        return pd.DataFrame()
    q = norm_wo(query)
    qtext = str(query).strip()
    con = sqlite3.connect(str(db_file))
    con.row_factory = sqlite3.Row
    try:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='work_orders'").fetchone():
            return pd.DataFrame()
        rows = con.execute(
            """SELECT wo_id, production_code, customer_name, customer_id, product_code, specification, qty,
                      revised_due_date, initial_due_date, order_no, plan_source_row
               FROM work_orders"""
        ).fetchall()
    finally:
        con.close()
    hits = []
    for r in rows:
        wo = str(r["wo_id"] or "")
        key = norm_wo(wo) or norm_wo(r["production_code"])
        blob = " ".join(
            str(r[k] or "")
            for k in ("wo_id", "production_code", "customer_name", "customer_id", "product_code", "specification", "order_no")
        ).casefold()
        if (q and (key == q or key.startswith(q) or q in key)) or (qtext and qtext.casefold() in blob):
            hits.append(
                {
                    "Plan row": r["plan_source_row"] or "",
                    "Work Order": wo,
                    "ProductionCode": r["production_code"] or wo,
                    "Customername": r["customer_name"] or "",
                    "CustomernameID": r["customer_id"] or "",
                    "รหัสสินค้า": r["product_code"] or "",
                    "Specification": r["specification"] or "",
                    "QTY": r["qty"],
                    "กำหนดส่งใหม่": r["revised_due_date"] or "",
                    "กำหนดเข้าคลัง": r["initial_due_date"] or "",
                    "ORDER": r["order_no"] or "",
                    "_rank": 0 if key == q else 1 if q and key.startswith(q) else 2,
                }
            )
    if not hits:
        return pd.DataFrame()
    return pd.DataFrame(sorted(hits, key=lambda x: (x["_rank"], x["Work Order"]))).drop(columns="_rank").head(limit)


def find_canonical_wo(query, *, plan_path=None, db_file=None) -> Optional[str]:
    """Return the stored WO id, or None. Never invents a code."""
    q = norm_wo(query)
    if not q:
        return None
    db_file = db_file or _db_path()
    hits = suggestions_from_db(db_file, query, limit=1)
    if hits is not None and not hits.empty:
        return str(hits.iloc[0]["Work Order"])
    path = Path(plan_path) if plan_path else resolve_plan()
    if path:
        hits = suggestions_from_plan(path, query, limit=1)
        if hits is not None and not hits.empty:
            return str(hits.iloc[0]["Work Order"])
    return None


def lookup(query, *, plan_path=None, raw_df=None, db_file=None, limit: int = 12) -> tuple[pd.DataFrame, Optional[Path]]:
    """First source that already has the WO: in-memory Plan, Plan file, then phone DB."""
    if raw_df is not None:
        hits = suggestions_from_df(raw_df, query, limit=limit)
        if hits is not None and not hits.empty:
            return hits, Path(plan_path) if plan_path else resolve_plan()
    path = Path(plan_path) if plan_path else resolve_plan()
    if path:
        try:
            hits = suggestions_from_plan(path, query, limit=limit)
        except Exception:
            hits = pd.DataFrame()
        if hits is not None and not hits.empty:
            return hits, path
    db_file = db_file or _db_path()
    hits = suggestions_from_db(db_file, query, limit=limit)
    if hits is not None and not hits.empty:
        return hits, Path(db_file)
    return pd.DataFrame(), path


def candidate_rows(query, *, plan_path=None, raw_df=None, db_file=None, limit: int = 10) -> list[dict]:
    hits, _ = lookup(query, plan_path=plan_path, raw_df=raw_df, db_file=db_file, limit=limit)
    if hits is None or hits.empty:
        return []
    out = []
    for _, r in hits.iterrows():
        wo = str(r.get("Work Order") or "")
        qty = r.get("QTY")
        try:
            qty = float(qty) if qty not in (None, "") else None
        except (TypeError, ValueError):
            qty = None
        out.append({
            "kind": "WO",
            "tracking_id": wo,
            "wo_id": wo,
            "title": str(r.get("ProductionCode") or wo),
            "part": r.get("รหัสสินค้า") or None,
            "customer": r.get("Customername") or None,
            "qty": qty,
            "description": r.get("Specification") or None,
        })
    return out
