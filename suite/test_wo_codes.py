import datetime as dt
from suite.wo_codes import parse_wo, decode_spec


def test_deck_example_slide4():
    w = parse_wo("P005-150118")
    assert (w.prefix, w.seq, w.family, w.kind) == ("P", 5, "VITRIFY", "MADE_TO_ORDER")
    assert w.opened_date == dt.date(2018, 1, 15) and w.normalized == "P005-150118" and w.documented


def test_all_six_documented_prefixes():
    got = {p: (parse_wo(f"{p}001-010126").family, parse_wo(f"{p}001-010126").kind) for p in ("P", "PM", "PS", "PB", "PBM", "PBS")}
    assert got["PBS"] == ("RESIN", "MONTHLY_MADE_TO_ORDER") and got["PM"] == ("VITRIFY", "MONTHLY_CONTINUOUS")


def test_input_variants_normalise():
    assert parse_wo("p005110826").normalized == "P005-110826" and parse_wo("P005 110826").normalized == "P005-110826"


def test_undocumented_prefix_is_not_guessed():
    w = parse_wo("PF001-010126")
    assert w.family is None and not w.documented and "UNDOCUMENTED" in w.source


def test_opened_date_is_not_a_due_date():
    assert parse_wo("P005-150118").opened_date.year == 2018   # still the opening date; callers must use bkk_today() for scheduling


def test_spec_example_slide6():
    d = decode_spec("WA60L8VB21351A152.4X3.17X31.75")
    assert (d["abrasive"], d["grain"], d["structures"], d["structures_no"], d["product_type"], d["bond_type"]) == ("WA", 60, "L", 8, "V", "B21")
    assert (d["m_per_sec"], d["shape"], d["diameter"], d["thickness"], d["hold"]) == (35, "1A", 152.4, 3.17, 31.75)


def test_unmatched_spec_returns_none():
    assert decode_spec("not a spec") is None and decode_spec(None) is None
