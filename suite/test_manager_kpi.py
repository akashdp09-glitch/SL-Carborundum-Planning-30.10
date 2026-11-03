import sqlite3

import pytest

from suite.manager_kpi import METRICS, history, import_csv, save, submission_id_for, validate


def entry(db, submission="SYNTHETIC-1", **changes):
    row = dict(month="2026-10", code="KPI-PL-02", numerator=120, denominator=100,
               backlog=35, evidence="SYNTHETIC opening and closure register rows 1-120",
               reason="SYNTHETIC initial entry", author="SYNTHETIC planner", submission_id=submission)
    row.update(changes)
    return save(db, **row)


def test_owner_marks_ratio_and_backlog_are_separate(tmp_path):
    assert [m[1] for m in METRICS.values()] == [15, 10, 15]
    db = tmp_path / "SYNTHETIC.sqlite"
    assert entry(db) == 120
    row = history(db).iloc[0]
    assert row.backlog_closed == 35
    assert "awarded_marks" not in row.index
    assert validate("2026-10", "KPI-PL-03", 110, 100, 0, "SYNTHETIC", "SYNTHETIC") == pytest.approx(110)


def test_retries_do_not_duplicate_and_corrections_preserve_history(tmp_path):
    db = tmp_path / "SYNTHETIC.sqlite"
    entry(db)
    entry(db)
    assert len(history(db)) == 1
    with pytest.raises(ValueError, match="different evidence"):
        entry(db, numerator=121)
    entry(db, "SYNTHETIC-2", numerator=121, reason="SYNTHETIC corrected closure count")
    rows = history(db)
    assert list(rows.numerator) == [121, 120]


@pytest.mark.parametrize("changes", [dict(numerator=float("nan")), dict(denominator=0),
    dict(month="2026-13"), dict(backlog=121), dict(reason=""),
    dict(code="KPI-PL-01", numerator=101), dict(numerator=1.5)])
def test_invalid_evidence_does_not_write_rows(tmp_path, changes):
    db = tmp_path / "SYNTHETIC.sqlite"
    with pytest.raises(ValueError):
        entry(db, **changes)
    assert history(db).empty


def test_csv_is_atomic_idempotent_and_preserves_provenance(tmp_path):
    db = tmp_path / "SYNTHETIC.sqlite"
    header = "month,code,numerator,denominator,backlog,evidence,reason\n"
    first = "2026-10,KPI-PL-02,120,100,35,SYNTHETIC source,SYNTHETIC entry\n"
    invalid = "2026-10,KPI-PL-03,5,0,0,SYNTHETIC source,SYNTHETIC entry\n"
    with pytest.raises(ValueError):
        import_csv(db, (header + first + invalid).encode(), "SYNTHETIC planner")
    assert history(db).empty
    data = (header + first).encode()
    assert import_csv(db, data, "SYNTHETIC planner") == 1
    assert import_csv(db, data, "SYNTHETIC planner") == 0
    assert "SHA256" in history(db).iloc[0].evidence


def test_old_kpi_evidence_untouched(tmp_path):
    db = tmp_path / "SYNTHETIC.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE planning_kpi_evidence (evidence TEXT)")
        con.execute("INSERT INTO planning_kpi_evidence VALUES ('SYNTHETIC old evidence')")
    entry(db)
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT evidence FROM planning_kpi_evidence").fetchall() == [("SYNTHETIC old evidence",)]


def test_returning_to_a_previous_value_is_a_new_correction():
    state = {}
    first = submission_id_for(state, "SYNTHETIC original")
    assert submission_id_for(state, "SYNTHETIC original") == first
    second = submission_id_for(state, "SYNTHETIC correction")
    reverted = submission_id_for(state, "SYNTHETIC original")
    assert len({first, second, reverted}) == 3
