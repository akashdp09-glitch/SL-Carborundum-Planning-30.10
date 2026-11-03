"""Drive the New part / MPS-MRP page like a user (Streamlit AppTest, no browser): enter an item, plan it, save a draft, see it listed."""
import sqlite3
from pathlib import Path

from streamlit.testing.v1 import AppTest

from suite.common import REPO_ROOT


def _app():
    import os
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path.cwd()))
    from suite.source_manager import SourceManager
    from suite.newpart_page import render
    root = Path(os.environ["NP_TEST_ROOT"])
    sm = SourceManager(root, bundled_capacity=Path(os.environ["NP_TEST_CAP"]))
    render(sm, None, None, "ui-tester", "np")


def test_plan_save_and_list_a_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("NP_TEST_ROOT", str(tmp_path))
    monkeypatch.setenv("NP_TEST_CAP", str(REPO_ROOT / "apps/daily/CAPACITY_DATABASE.xlsx"))
    monkeypatch.chdir(REPO_ROOT)
    at = AppTest.from_function(_app, default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    at.text_input(key="np_id").set_value("SYNTH-NEW-1")
    at.number_input(key="np_qty").set_value(1500.0)
    at.run()
    [b for b in at.button if b.key == "np_go"][0].click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    shown = " ".join([w.value for w in at.warning] + [w.value for w in at.error])
    assert "PROVISIONAL" in shown or "BLOCKED" in shown or "LATE" in shown
    assert "feasible" not in shown.lower().replace("not confirmed feasible", "").replace("not feasible", "")
    [b for b in at.button if b.key == "np_save"][0].click()
    at.run()
    assert any("DRAFT" in s.value for s in at.success)
    con = sqlite3.connect(tmp_path / "DATA" / "newpart_scenarios.sqlite")
    n = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    assert n >= 1
    rows = sum(con.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall())
    assert rows >= 1


def test_sunday_default_and_holiday_is_saved_with_user_and_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("NP_TEST_ROOT", str(tmp_path))
    monkeypatch.setenv("NP_TEST_CAP", str(REPO_ROOT / "apps/daily/CAPACITY_DATABASE.xlsx"))
    monkeypatch.chdir(REPO_ROOT)
    at = AppTest.from_function(_app, default_timeout=120).run()
    assert at.multiselect(key="np_cal_off").value == ["Sun"]
    at.text_input(key="np_cal_hl").set_value("Test holiday")
    at.text_input(key="np_cal_hr").set_value("synthetic UI test")
    at.run()
    [b for b in at.button if b.key == "np_cal_hadd"][0].click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    from suite.user_settings import SettingsStore, KEY_HOLIDAYS
    h = SettingsStore(tmp_path / "DATA" / "user_settings.sqlite").history(KEY_HOLIDAYS)
    assert list(h.changed_by) == ["ui-tester"] and list(h.reason) == ["synthetic UI test"]
    assert len(at.multiselect(key="np_cal_hol").options) == 1


def _cap_app():
    import os
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path.cwd()))
    from suite.capacity_page import render
    render(Path(os.environ["NP_TEST_CAP"]), "synthetic-sha", "capreg", shared_root=Path(os.environ["NP_TEST_ROOT"]), user="ui-tester")


def test_capacity_page_edits_machines_not_working_with_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("NP_TEST_ROOT", str(tmp_path))
    monkeypatch.setenv("NP_TEST_CAP", str(REPO_ROOT / "apps/daily/CAPACITY_DATABASE.xlsx"))
    monkeypatch.chdir(REPO_ROOT)
    at = AppTest.from_function(_cap_app, default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.multiselect(key="capreg_oos").value == ["D7", "D8", "D9", "D10", "D11", "D12", "D15", "D19", "D25", "D26", "D32"]
    at.multiselect(key="capreg_oos").set_value(["D7"])
    at.text_input(key="capreg_oos_why").set_value("H5 repaired (synthetic test)")
    at.run()
    [b for b in at.button if b.key == "capreg_oos_save"][0].click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    from suite.user_settings import SettingsStore, effective_out_of_service
    s = SettingsStore(tmp_path / "DATA" / "user_settings.sqlite")
    assert effective_out_of_service(s) == ["D7"] and list(s.history().changed_by) == ["ui-tester"]
