import pytest
from suite.user_settings import SettingsStore, KEY_OUT_OF_SERVICE, KEY_HOLIDAYS, effective_out_of_service, effective_holidays, default_out_of_service, owner_decisions


def test_every_change_keeps_user_time_and_reason(tmp_path):
    s = SettingsStore(tmp_path / "s.sqlite")
    s.set(KEY_HOLIDAYS, [{"date": "2026-12-31", "label": "Year end"}], "planner1", "Factory closed")
    s.set(KEY_HOLIDAYS, [], "planner2", "Reopened")
    h = s.history(KEY_HOLIDAYS)
    assert list(h.changed_by) == ["planner2", "planner1"] and all(h.reason) and all(h.changed_at)
    assert effective_holidays(s) == []                      # latest wins; the earlier value is still in the history


def test_user_and_reason_are_mandatory(tmp_path):
    s = SettingsStore(tmp_path / "s.sqlite")
    with pytest.raises(ValueError):
        s.set(KEY_HOLIDAYS, [], "", "why")
    with pytest.raises(ValueError):
        s.set(KEY_HOLIDAYS, [], "u", " ")
    assert s.history().empty


def test_out_of_service_defaults_to_the_owner_list_until_a_user_changes_it(tmp_path):
    s = SettingsStore(tmp_path / "s.sqlite")
    assert effective_out_of_service(s) == default_out_of_service() == ["D7", "D8", "D9", "D10", "D11", "D12", "D15", "D19", "D25", "D26", "D32"]
    s.set(KEY_OUT_OF_SERVICE, ["D7"], "planner1", "H5 repaired")
    assert effective_out_of_service(s) == ["D7"]
    assert effective_out_of_service(None) == default_out_of_service()


def test_owner_decisions_file_is_complete():
    ids = [d["id"] for d in owner_decisions()["decisions"]]
    assert ids == [f"OD-{i}" for i in range(1, 13)]
