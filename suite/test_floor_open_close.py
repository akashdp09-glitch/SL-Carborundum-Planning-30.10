from suite.floor_open_close import COLS, confirmed_candidate, load_entries, save_entry


def test_save_entry_appends_and_does_not_invent_a_wo(tmp_path):
    row = save_entry(tmp_path, "P005-110826", "Mixing", "CLOSED", qty=4, remark="scan", user="operator", canonical_wo="P005-110826")
    assert row["Work Order"] == "P005-110826"
    assert row["Section"] == "Mixing"
    assert row["Status"] == "CLOSED"
    df = load_entries(tmp_path)
    assert list(df.columns) == COLS
    assert list(df["Work Order"]) == ["P005-110826"]
    save_entry(tmp_path, "P005-110826", "Forming", "OPEN", user="operator", canonical_wo="P005-110826")
    df = load_entries(tmp_path)
    assert len(df) == 2
    assert list(df["Section"]) == ["Mixing", "Forming"]


def test_save_entry_requires_work_order(tmp_path):
    try:
        save_entry(tmp_path, "  ", "Mixing", "OPEN", canonical_wo="P005-110826")
    except ValueError as exc:
        assert "Work Order" in str(exc)
    else:
        raise AssertionError("empty WO must be refused")
    assert load_entries(tmp_path).empty


def test_exact_wo_only_is_auto_confirmed():
    assert confirmed_candidate("P005-110826", ["P005-110826"]) == "P005-110826"
    assert confirmed_candidate("P005-1108", ["P005-110826"]) is None
    assert confirmed_candidate("P005110826", ["P005-110826", "P005110826"]) is None


def test_status_events_are_persisted_to_shared_sqlite(tmp_path):
    a = save_entry(tmp_path, "P005-110826", "Mixing", "CLOSED", qty=4, user="op1", canonical_wo="P005-110826", event_id="retry-1")
    retry = save_entry(tmp_path, "P005-110826", "Mixing", "CLOSED", qty=4, user="op1", canonical_wo="P005-110826", event_id="retry-1")
    b = save_entry(tmp_path, "P005-110826", "Forming", "OPEN", qty=0, user="op2", canonical_wo="P005-110826", event_id="retry-2")
    assert a["Event ID"] != b["Event ID"]
    assert retry["Event ID"] == a["Event ID"]
    assert (tmp_path / "daily_status_entries.sqlite3").is_file()
    assert list(load_entries(tmp_path)["Section"]) == ["Mixing", "Forming"]


def test_explicit_unknown_quantity_is_null_and_traceable(tmp_path):
    row = save_entry(tmp_path, "P005-110826", "Mixing", "OPEN", qty=None, user="operator",
                     canonical_wo="P005-110826", source_ref="Plan-2026-LATEST.xlsx",
                     source_row="37", qty_unknown=True)
    assert row["Actual Qty"] is None
    assert row["Quantity Unknown"] is True
    df = load_entries(tmp_path)
    assert bool(df.iloc[0]["Quantity Unknown"])
    import pandas as pd
    assert pd.isna(df.iloc[0]["Actual Qty"])
    assert df.iloc[0]["Source reference"] == "Plan-2026-LATEST.xlsx"
    assert df.iloc[0]["Plan row"] == "37"
