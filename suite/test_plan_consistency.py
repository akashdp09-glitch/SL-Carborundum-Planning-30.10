import pandas as pd

from suite.plan_consistency import check_frame
from suite.plan_reader import ORDER


def _row(**kw):
    base = {"wo": "P001-010126", "qty": 10, "current_section": "Preparation"}
    for s in ORDER:
        base[f"{s}.closed"] = False
        base[f"{s}.plan_qty"] = 0.0
        base[f"{s}.done"] = 0.0
    base.update(kw)
    return base


def test_later_section_closed_while_earlier_open_is_listed():
    r = _row(**{"Mixing.closed": True, "Mixing.done": 10, "current_section": "Preparation"})
    issues = check_frame(pd.DataFrame([r]))
    kinds = {i["kind"] for i in issues}
    assert "section_order" in kinds
    assert any(i["blocked_by"] == "Preparation" for i in issues)


def test_matching_qty_and_order_is_clean():
    r = _row(**{
        "Preparation.closed": True, "Preparation.plan_qty": 10, "Preparation.done": 10,
        "current_section": "Mixing",
    })
    issues = check_frame(pd.DataFrame([r]))
    assert issues == []


def test_section_qty_mismatch_lists_both_figures():
    r = _row(**{"Preparation.plan_qty": 8, "qty": 10, "current_section": "Preparation"})
    issues = check_frame(pd.DataFrame([r]))
    assert any(i["kind"] == "qty_mismatch" and i["master_qty"] == 10 and i["section_plan_qty"] == 8 for i in issues)
