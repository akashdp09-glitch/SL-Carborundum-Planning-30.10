"""Capacity registry tests (real CAPACITY_DATABASE.xlsx; no Streamlit)."""
import pytest
from suite.capacity import (load_capacity, Demand, utilisation, pieces_to_kg, tonnes_to_kg, MissingConversion, kiln_throughput,
                            KIND_MASS_T, KIND_MASS_KG, KIND_PIECES, KIND_MILLS, TONNE_TO_KG, TONNE_CONVERSION_NOTE)
from suite.common import REPO_ROOT

WB = REPO_ROOT / "apps" / "daily" / "CAPACITY_DATABASE.xlsx"


@pytest.fixture(scope="module")
def model():
    return load_capacity(WB)


def test_every_record_has_provenance_and_unit(model):
    assert len(model.records) > 400
    for r in model.records:
        assert r.source_file == "CAPACITY_DATABASE.xlsx" and r.sheet and r.cell and r.unit and r.unit_kind and r.time_basis


def test_unstated_time_basis_is_never_schedulable(model):
    bad = [r for r in model.records if r.time_basis == "UNSTATED" and r.schedulable]
    assert not bad


def test_mixing_units_are_kept_separate(model):
    kinds = {r.unit_kind for r in model.by_section("Mixing")}
    assert {KIND_MASS_T, KIND_MILLS} <= kinds
    mills = [r for r in model.by_section("Mixing", KIND_MILLS)]
    assert all("not converted to batches" in " ".join(r.assumptions) for r in mills)


def test_tonne_is_the_owner_confirmed_metric_tonne(model):
    t = model.by_section("Mixing", KIND_MASS_T)[0]
    assert "UNIT_CONFIRMED_METRIC_TONNE" in t.flags and "UNIT_ASSUMED_METRIC_TONNE" not in t.flags
    assert "confirmed" in TONNE_CONVERSION_NOTE and tonnes_to_kg(1) == 1000.0


def test_utilisation_does_not_mix_unit_kinds(model):
    out = utilisation(model, [Demand("Forming", 100, KIND_MASS_T, "t", "day")])
    assert out.iloc[0]["status"] == "NOT_CALCULABLE"


def test_alternative_rows_are_not_summed(model):
    out = utilisation(model, [Demand("Packing", 100, KIND_PIECES, "pcs", "day")]).iloc[0]
    assert out["status"] == "NOT_CALCULABLE" and "alternatives" in out["reason"]


def test_named_resource_utilisation(model):
    rec = next(r for r in model.by_section("Packing", KIND_PIECES) if r.time_basis == "per day")
    out = utilisation(model, [Demand("Packing", rec.value / 2, KIND_PIECES, "pcs", "day", resource=rec.resource)]).iloc[0]
    assert out["status"] == "CALCULATED" and 49 < out["utilisation_pct"] <= 100
    assert rec.cell in out["sources"]


def test_per_person_needs_headcount(model):
    rec = next(r for r in model.by_section("Packing", KIND_PIECES) if "per person" in r.time_basis)
    no = utilisation(model, [Demand("Packing", 10, KIND_PIECES, "pcs", "day", resource=rec.resource)]).iloc[0]
    assert no["status"] == "NOT_CALCULABLE"
    ok = utilisation(model, [Demand("Packing", 10, KIND_PIECES, "pcs", "day", resource=rec.resource, headcount=2)]).iloc[0]
    assert ok["status"] == "CALCULATED"


def test_mixing_is_scheduled_in_mills_per_day_only(model):
    """OD-2: tonnes/month and kg/day of the mixing sheet are reference values and are never used to schedule."""
    for kind in (KIND_MASS_T, KIND_MASS_KG):
        recs = model.by_section("Mixing", kind)
        assert recs and not any(r.schedulable for r in recs) and all(("REFERENCE_ONLY" in r.flags or "MILL_LOAD_WINDOW" in r.flags) for r in recs)
    d = [Demand("Mixing", 10, KIND_MASS_T, "t", "day", measure_contains="capacity per month")]
    assert utilisation(model, d, working_days_per_month=25).iloc[0]["status"] == "NOT_CALCULABLE"
    mills = [r for r in model.by_section("Mixing", KIND_MILLS) if r.schedulable]
    assert mills and all(r.time_basis == "per day" and r.unit == "mills" for r in mills)
    assert {c["id"] for c in model.resolved} >= {"MIX-MONTH-vs-DAY"} and "MIX-MONTH-vs-DAY" not in {c["id"] for c in model.conflicts}


def test_mill_count_cannot_be_used_as_batches(model):
    out = utilisation(model, [Demand("Mixing", 5, KIND_MILLS, "mills", "day", resource="M8")]).iloc[0]
    assert out["status"] == "CALCULATED"  # compared as mills with mills only
    assert out["unit_kind"] == KIND_MILLS


def test_conversions():
    assert tonnes_to_kg(1.5) == 1.5 * TONNE_TO_KG
    with pytest.raises(MissingConversion):
        pieces_to_kg(10, None, "fired", "fired")
    with pytest.raises(MissingConversion):
        pieces_to_kg(10, 2.0, "green", "fired")
    assert pieces_to_kg(10, 2.0, "Fired", "fired") == 20.0


def test_conflicts_list_exact_cells(model):
    mix = next(c for c in model.resolved if c["id"] == "MIX-MONTH-vs-DAY")      # closed by the owner (OD-2) but the exact cells stay on record
    assert any("E4=" in e and "F4=" in e and "G4=" in e for e in mix["entries"])
    assert "OD-2" in mix["decision"]
    open_ids = {c["id"] for c in model.conflicts if c.get("severity") != "rounding"}
    assert open_ids == {"RESIN-RUN-DAYS-PB"}, open_ids
    resin = next(c for c in model.conflicts if c["id"] == "RESIN-RUN-DAYS-PB")
    assert any("F7" in e for e in resin["entries"]) and resin["decision_needed"]


def test_kiln_throughput_provisional(model):
    t = kiln_throughput(model, "P1")
    assert t["status"] == "PROVISIONAL" and t["run_days"] == 7
    with pytest.raises(MissingConversion):
        kiln_throughput(model, "P99")


def test_gaps_declared(model):
    text = " ".join(model.gaps)
    assert "mills per day only" in text and "Sunday" in text and "calendar" in text.lower()


def test_forming_hourly_rate_is_authoritative_on_owner_rows(model):
    """OD-3: sheet rows 28, 33, 38, 40-43 - the hourly rate (E) is correct; the 3-hour totals (G) are reference only."""
    ids = {c["id"] for c in model.resolved}
    assert {f"FORM-G{r}" for r in (28, 33, 38, 40, 41, 42, 43)} <= ids
    assert not [c for c in model.conflicts if c.get("severity") == "conflict"]
    g28 = next(r for r in model.records if r.sheet == "CAP ขึ้นรูป" and r.cell == "G28")
    e28 = next(r for r in model.records if r.sheet == "CAP ขึ้นรูป" and r.cell == "E28")
    assert not g28.schedulable and "REFERENCE_ONLY_RATE_AUTHORITATIVE" in g28.flags and e28.schedulable


def test_machines_marked_not_working_are_excluded_and_editable(model):
    """OD-4: the owner's cells are out of service by default; a different list (saved by a user) changes the result."""
    cells = ["D7", "D8", "D9", "D10", "D11", "D12", "D15", "D19", "D25", "D26", "D32"]
    assert [o["cell"] for o in model.out_of_service] == cells
    off = [r for r in model.records if r.section == "Forming" and r.cell[1:] in {c[1:] for c in cells} and r.cell[0] in "EFG"]
    assert off and not any(r.schedulable for r in off) and all("OUT_OF_SERVICE" in r.flags for r in off)
    again = load_capacity(REPO_ROOT / "apps/daily/CAPACITY_DATABASE.xlsx", out_of_service_cells=[])
    assert again.out_of_service == [] and any(r.schedulable for r in again.records if r.cell == "E7")
    only = load_capacity(REPO_ROOT / "apps/daily/CAPACITY_DATABASE.xlsx", out_of_service_cells=["D5"])
    assert [o["cell"] for o in only.out_of_service] == ["D5"]


def test_resin_firing_lead_time_is_pb_only_with_owner_run_time(model):
    lt = model.lead_times
    resin = lt[lt.process.str.contains("เตาเผา Resin")].set_index("group")
    assert not resin.loc["T", "routed"] and not resin.loc["M", "routed"]
    assert resin.loc["T", "ignored_raw"] == "2 Day" and resin.loc["M", "ignored_raw"] == "5-7 Day"
    assert resin.loc["PB", "routed"] and resin.loc["PB", "days_low"] == 2 and resin.loc["PB", "days_high"] == 3
    assert kiln_throughput(model, "KM-185")["run_days_low"] == 2 and kiln_throughput(model, "P1")["run_days_low"] == 7
