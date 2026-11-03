"""Compare Plan-2026 section columns so one WO cannot silently disagree with itself.

Uses only the master sheet columns already mapped in suite.plan_reader (no invented qty).
When two recorded figures disagree, both are listed. Nothing is chosen as the winner.
"""
from __future__ import annotations

from .plan_reader import ORDER, load_plan

# A later section with recorded work while an earlier section is still open is a contradiction
# only when the later section has a done qty or is marked closed.


def _num(v):
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def check_frame(df) -> list[dict]:
    issues = []
    if df is None or getattr(df, "empty", True):
        return issues
    for row in df.to_dict("records"):
        wo = row.get("wo", "")
        master_qty = _num(row.get("qty"))
        first_open = None
        for s in ORDER:
            closed = bool(row.get(f"{s}.closed", False))
            plan_qty = _num(row.get(f"{s}.plan_qty"))
            done = _num(row.get(f"{s}.done"))
            if first_open is None and not closed:
                first_open = s
            if master_qty is not None and plan_qty is not None and plan_qty > 0 and abs(plan_qty - master_qty) > 0.0001:
                issues.append({
                    "wo": wo, "kind": "qty_mismatch", "section": s,
                    "master_qty": master_qty, "section_plan_qty": plan_qty,
                    "detail": f"{s} plan qty {plan_qty} ≠ master qty {master_qty}",
                })
            if first_open and s != first_open and ORDER.index(s) > ORDER.index(first_open):
                later_active = closed or (done is not None and done > 0)
                if later_active:
                    issues.append({
                        "wo": wo, "kind": "section_order", "section": s,
                        "blocked_by": first_open,
                        "detail": f"{s} has done/closed while earlier section {first_open} is still open",
                    })
        cur = row.get("current_section")
        if cur and cur != "Done":
            for s in ORDER:
                if ORDER.index(s) < ORDER.index(cur) and not bool(row.get(f"{s}.closed", False)):
                    issues.append({
                        "wo": wo, "kind": "current_vs_closed", "section": s,
                        "detail": f"current section is {cur} but {s} is not marked closed",
                    })
                    break
    return issues


def check_plan(path, cache_dir=None, limit=None) -> dict:
    df = load_plan(path, cache_dir=cache_dir)
    if limit:
        df = df.head(limit)
    issues = check_frame(df)
    by_kind = {}
    for i in issues:
        by_kind[i["kind"]] = by_kind.get(i["kind"], 0) + 1
    return {
        "wos": int(df["wo"].nunique()) if "wo" in df.columns else len(df),
        "issues": issues,
        "issue_count": len(issues),
        "by_kind": by_kind,
        "sections": list(ORDER),
        "rule": "CONFLICT-1: list both sides; do not pick a winner.",
    }
