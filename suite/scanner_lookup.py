"""Indexed, exact identity lookup. Partial text belongs in the search/confirm UI."""
from __future__ import annotations

NORMALIZED_SQL = "REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER({}),'-',''),' ',''),'/',''),'.',''),'_','')"


def exact_work_orders(con, value, limit=3):
    from .wo_lookup import norm_wo
    key = norm_wo(value)
    if not key:
        return []
    # Both indexes are installed by the shared app migration. Bounded output,
    # including a second match, prevents silent selection of ambiguous labels.
    expr_wo = NORMALIZED_SQL.format('wo_id')
    expr_code = NORMALIZED_SQL.format('production_code')
    return con.execute(
        f"SELECT * FROM work_orders WHERE {expr_wo}=? OR {expr_code}=? LIMIT ?",
        (key, key, max(2, int(limit))),
    ).fetchall()
