import datetime as dt
import pandas as pd
import pytest
from suite import closure_rules as C, planners as P
from suite.plan_reader import load_plan
from suite.common import REPO_ROOT

PLAN = REPO_ROOT / "Plan 2026-2-Update-01100926.xlsx"


def test_text_rules():
    assert C.is_closed_text("ปิด") and C.is_closed_text("ปิดใบสั่ง") and C.is_closed_text("Cancelled") and C.is_closed_text("ยกเลิก")
    assert not C.is_closed_text("ยังไม่ปิด") and not C.is_closed_text(None) and not C.is_closed_text("#N/A") and not C.is_closed_text("")


def _row(**kw):
    base = {"wo": "P001-010126", "due": dt.date(2026, 1, 1), "qty": 100.0, "prod_closed": "ยังไม่ปิด", "Packing.done": 0.0}
    for s in ("Preparation", "Mixing", "Forming", "Firing", "Grinding", "Packing"):
        base[f"{s}.closed"] = False
    base.update(kw)
    return base


def test_preparation_closure_never_closes_the_order():
    df = pd.DataFrame([_row(**{"Preparation.closed": True, "Mixing.closed": True, "Forming.closed": True, "Firing.closed": True, "Grinding.closed": True})])
    cl = C.classify(df, dt.date(2026, 10, 5))
    assert not cl.whole_closed.iloc[0] and cl.section_closed_but_order_open.iloc[0] and cl.backorder.iloc[0]


def test_packing_or_fc_closes_the_order():
    df = pd.DataFrame([_row(**{"Packing.closed": True}), _row(wo="B", prod_closed="ปิด"), _row(wo="C", prod_closed=None)])
    cl = C.classify(df, dt.date(2026, 10, 5))
    assert list(cl.whole_closed) == [True, True, False]
    assert cl.state.iloc[0] == C.STATE_CLOSED_PACKING and cl.state.iloc[1] == C.STATE_CLOSED_FC
    assert bool(cl.fc_blank.iloc[2]) and bool(cl.backorder.iloc[2])


def test_backorder_uses_the_passed_date_not_stored_dates():
    df = pd.DataFrame([_row(due=dt.date(2026, 10, 10))])
    assert not C.classify(df, dt.date(2026, 10, 5)).backorder.iloc[0]
    later = C.classify(df, dt.date(2026, 10, 20))
    assert later.backorder.iloc[0] and later.late_days.iloc[0] == 10


def test_fully_packed_open_order_is_not_backorder():
    df = pd.DataFrame([_row(**{"Packing.done": 100.0})])
    assert not C.classify(df, dt.date(2026, 10, 5)).backorder.iloc[0]


@pytest.mark.skipif(not PLAN.exists(), reason="Plan workbook not present")
def test_real_plan_counts_are_consistent(tmp_path):
    plan = load_plan(PLAN, cache_dir=tmp_path)
    cl = C.classify(plan, dt.date(2026, 10, 5))
    s = dict(C.summary(cl).values)
    assert s["WO rows in Plan workbook"] == len(plan)
    assert s["Whole-order CLOSED (EU or FC)"] + s["Whole-order OPEN"] == len(plan)
    assert (plan["open"] == ~cl.whole_closed).all()
    bo = P.backorder_plan(plan, dt.date(2026, 10, 5))
    assert set(bo.wo) <= set(plan.loc[plan.open, "wo"])


def test_section_daily_never_invents_capacity_or_days_off():
    plan = pd.DataFrame([{**_row(), "open": True, "current_section": "Forming", "Forming.plan_qty": 100.0, "Forming.done": 0.0, "mills": 0.0, "piece_g": 0.0,
                          "customer": "", "spec": "", "bond": "", "remark": ""}])
    out = P.section_daily(plan, "Forming", dt.date(2026, 10, 4), None)   # a Sunday
    assert out.plan_date.isna().all() and "UNSCHEDULED" in out.schedule_status.iloc[0]
    out = P.section_daily(plan, "Forming", dt.date(2026, 10, 4), 500)
    assert out.plan_date.iloc[0] == dt.date(2026, 10, 4) and "PROVISIONAL" in out.schedule_status.iloc[0]   # Sunday is NOT skipped unless asked
    out = P.section_daily(plan, "Forming", dt.date(2026, 10, 4), 500, non_working_weekdays=(6,))
    assert out.plan_date.iloc[0] == dt.date(2026, 10, 5)
