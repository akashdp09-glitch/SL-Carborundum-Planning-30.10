import datetime as dt
import pandas as pd
import pytest
from suite.capacity import load_capacity
from suite.common import REPO_ROOT
from suite.newpart_planner import (Item, Context, Calendar, SectionCap, plan_item, net_demand, ScenarioStore, existing_bookings,
                                   STATUS_BLOCKED, STATUS_PROVISIONAL, STATUS_LATE)


@pytest.fixture(scope="module")
def model():
    return load_capacity(REPO_ROOT / "apps/daily/CAPACITY_DATABASE.xlsx")


def item(**kw):
    base = dict(item_id="NP-1", description="synthetic test part", group="P", qty_pcs=2000, due=None)
    base.update(kw)
    return Item(**base)


def test_start_is_the_context_date_not_an_inherited_one(model):
    a = plan_item(model, item(), Context(today=dt.date(2026, 10, 5)))
    b = plan_item(model, item(), Context(today=dt.date(2026, 11, 2)))
    assert a.schedule.begin.min() == dt.date(2026, 10, 5) and b.schedule.begin.min() == dt.date(2026, 11, 2)
    assert (b.finish_conservative - a.finish_conservative).days == 28


def test_default_context_uses_bangkok_today(model):
    from suite.common import bkk_today
    assert plan_item(model, item()).schedule.begin.min() >= bkk_today()


def test_never_called_feasible_without_qualification(model):
    r = plan_item(model, item(due=dt.date(2027, 12, 31)), Context(today=dt.date(2026, 10, 5)))
    assert r.status == STATUS_PROVISIONAL and "not confirmed feasible" in r.status
    assert any("Sunday off per owner" in a for a in r.assumptions)


def test_missing_fired_weight_is_a_gap_not_an_invented_number(model):
    r = plan_item(model, item(kiln_program="P1"), Context(today=dt.date(2026, 10, 5)))
    assert any("FIRED stage" in g for g in r.gaps) and r.capacity_checks.empty


def test_firing_runs_use_documented_load_and_days(model):
    r = plan_item(model, item(kiln_program="P1", fired_piece_kg=2.0, qty_pcs=2000), Context(today=dt.date(2026, 10, 5)))
    row = r.capacity_checks[r.capacity_checks.step == "Firing"].iloc[0]
    assert "4.000 t" in row.item_demand and "4 run(s)" in row.note and row.days_needed_for_item == 7
    assert "CAPACITY_DATABASE.xlsx!G2" in row.source_cell and "PROVISIONAL" in row.note


def test_kiln_out_of_service_reduces_kilns(model):
    ctx = Context(today=dt.date(2026, 10, 5), kilns_out_of_service=tuple(f"T{i}" for i in range(1, 12)))
    r = plan_item(model, item(kiln_program="P1", fired_piece_kg=2.0, qty_pcs=5000), ctx)
    row = r.capacity_checks[r.capacity_checks.step == "Firing"].iloc[0]
    assert row.days_needed_for_item == 63      # 10 t / 1.2 t per run = 9 runs, one kiln left (T12), 7 days each


def test_resin_firing_row_is_pb_only_so_t_and_m_need_no_bond_type(model):
    """OD-5: the two Resin-row entries for T (C7) and M (G7) are ignored; T and M fire in the Vitrified row."""
    for g, cell in (("T", "C8"), ("M", "G8")):
        r = plan_item(model, item(group=g), Context(today=dt.date(2026, 10, 5)))
        assert r.status != STATUS_BLOCKED and not r.blockers
        f = r.schedule[(r.schedule.step == "Firing") & (r.schedule.scenario == "conservative")].iloc[0]
        assert f.lead_time_cell == f"Lead Time!{cell}"


def test_pb_resin_firing_shows_owner_two_days_and_workbook_three_days(model):
    r = plan_item(model, item(group="PB"), Context(today=dt.date(2026, 10, 5)))
    f = r.schedule[r.schedule.step == "Firing"].set_index("scenario")
    assert f.loc["optimistic", "lead_time_days"] == 2 and f.loc["conservative", "lead_time_days"] == 3
    assert f.loc["conservative", "lead_time_cell"] == "Lead Time!F7"


def test_sunday_is_not_a_working_day_and_holidays_can_be_selected(model):
    r = plan_item(model, item(), Context(today=dt.date(2026, 10, 5)))
    days = list(r.schedule.begin) + list(r.schedule.end)
    assert days and not any(d.weekday() == 6 for d in days)
    base = plan_item(model, item(), Context(today=dt.date(2026, 10, 5)))
    hol = plan_item(model, item(), Context(today=dt.date(2026, 10, 5), calendar=Calendar(holidays=(dt.date(2026, 10, 7),))))
    assert (hol.finish_conservative - base.finish_conservative).days >= 1
    assert any("2026-10-07" in a for a in hol.assumptions)


def test_capacity_in_matching_unit_extends_step_and_queue(model):
    plan = pd.DataFrame([{"open": True, "current_section": "Forming", "qty": 3000.0, "Forming.plan_qty": 3000.0, "Forming.done": 1000.0, "mills": 0.0,
                          "Forming.plan": dt.date(2026, 10, 6), "Preparation.plan_qty": 0, "Preparation.done": 0, "Preparation.plan": None,
                          "Mixing.plan_qty": 0, "Mixing.done": 0, "Mixing.plan": None, "Firing.plan_qty": 0, "Firing.done": 0, "Firing.plan": None,
                          "Grinding.plan_qty": 0, "Grinding.done": 0, "Grinding.plan": None}])
    ctx = Context(today=dt.date(2026, 10, 5), plan=plan, caps={"Forming": SectionCap("Forming", "USER|spec", 500.0, "pcs", "USER-ENTERED")})
    r = plan_item(model, item(qty_pcs=2000), ctx)
    row = r.capacity_checks[r.capacity_checks.step == "Forming"].iloc[0]
    assert row.days_needed_for_item == 4 and row["queue_days_ahead (estimate)"] == 4      # 2000/500 ; 2000 waiting/500
    f = r.schedule[(r.schedule.scenario == "conservative") & (r.schedule.step == "Forming")].iloc[0]
    assert f.queue_days == 4 and f.capacity_days == 4
    assert any("Forming" in b for b in r.bottlenecks)


def test_mill_capacity_not_applied_to_pieces(model):
    ctx = Context(today=dt.date(2026, 10, 5), caps={"Mixing": SectionCap("Mixing", "M8", 7, "mills", "CAP ผสม!F10")})
    r = plan_item(model, item(), ctx)          # no mills figure on the item
    assert any("Mixing" in g and "mills" in g for g in r.gaps)
    r2 = plan_item(model, item(mills=14), ctx)
    assert r2.capacity_checks[r2.capacity_checks.step == "Mixing"].iloc[0].days_needed_for_item == 2


def test_lateness_and_calendar(model):
    cal = Calendar(non_working_weekdays=(6,), supplied=True)
    r = plan_item(model, item(due=dt.date(2026, 10, 6)), Context(today=dt.date(2026, 10, 3), calendar=cal))   # 3 Oct 2026 is a Saturday
    assert r.status == STATUS_LATE and r.late_days > 0
    assert all(d.weekday() != 6 for d in r.schedule.end)
    assert not any("calendar" in g.lower() and "not supplied" in g for g in r.gaps)


def test_material_reservation_and_shortage_block(model):
    plan = pd.DataFrame([{"open": True, "Mixing.closed": False, "mat1": "AB1", "mat1_g": 60000.0, **{f"mat{n}": None for n in range(2, 6)}, **{f"mat{n}_g": 0.0 for n in range(2, 6)},
                          "current_section": "Mixing", "qty": 1.0, "mills": 0.0}])
    stock = pd.DataFrame([{"material": "AB1", "stock_g": 100000.0}])
    ctx = Context(today=dt.date(2026, 10, 5), plan=plan, stock=stock)
    r = plan_item(model, item(materials=[("AB1", 50.0)]), ctx)
    m = r.materials.iloc[0]
    assert m.shortage_kg == 10.0 and m.status == "SHORT" and r.status == STATUS_BLOCKED
    ok = plan_item(model, item(materials=[("AB1", 50.0)], material_ready_date=dt.date(2026, 10, 20)), ctx)
    assert ok.status != STATUS_BLOCKED and ok.schedule.begin.min() == dt.date(2026, 10, 20)


def test_forecast_is_netted_by_firm_orders():
    lines = pd.DataFrame([["A", "2026-11", 100, "FIRM", "SO1"], ["A", "2026-11", 150, "FORECAST", "F1"], ["B", "2026-11", 80, "FORECAST", "F2"], ["A", "2026-12", 40, "FIRM", "SO2"]],
                         columns=["product", "month", "qty", "type", "reference"])
    n = net_demand(lines).set_index(["product", "month"])
    assert n.loc[("A", "2026-11"), "counted_demand"] == 150      # 100 firm + (150-100) forecast, not 250
    assert n.loc[("B", "2026-11"), "counted_demand"] == 80 and n.loc[("A", "2026-12"), "counted_demand"] == 40
    assert "confirmed by the owner" in n.method.iloc[0] and "assumption" not in n.method.iloc[0]


def test_saved_scenarios_round_trip(model, tmp_path):
    store = ScenarioStore(tmp_path / "sc.sqlite")
    it = item(kiln_program="P1", fired_piece_kg=2.0, due=dt.date(2026, 12, 1))
    ctx = Context(today=dt.date(2026, 10, 5), source_revisions={"CAPACITY_DATABASE": {"revision": 1, "sha256": "abc", "file": "CAPACITY_DATABASE.xlsx"}})
    res = plan_item(model, it, ctx)
    sid = store.save("draft A", it, res, ctx, "tester")
    assert store.list().iloc[0]["name"] == "draft A" and store.list().iloc[0].state == "DRAFT"
    sheets = store.export_sheets(sid)
    assert {"Schedule", "Sources", "Assumptions", "Gaps", "Saved scenario"} <= set(sheets)
    assert sheets["Sources"].iloc[0].slot == "CAPACITY_DATABASE" and store.get(sid)["status"] == res.status
    from suite.exporters import to_workbook
    assert len(to_workbook(sheets)) > 2000


def test_existing_bookings_summary():
    assert existing_bookings(None, dt.date(2026, 10, 5)).empty
