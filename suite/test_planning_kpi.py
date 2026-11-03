from suite.planning_kpi import METRICS, load_measurements, save_measurement, score


def test_kpi_score_requires_valid_counts():
    assert score(95, 100) == 95.0
    for numerator, denominator in [(-1, 4), (2, 0), (5, 4)]:
        try:
            score(numerator, denominator)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid percentage denominator/numerator must be refused")


def test_monthly_kpi_measurements_keep_revision_history_and_latest_score(tmp_path):
    db = tmp_path / "sl_planning.db"
    first = save_measurement(db, "2026-10", "KPI-PL-01", 8, 10, "Capacity review.xlsx / Oct / rows 4-13", "2 loads had documented recovery", "planner1")
    revised = save_measurement(db, "2026-10", "KPI-PL-01", 9, 10, "Capacity review.xlsx / Oct / rows 4-13", "One recovery record corrected", "planner2")
    assert revised["id"] > first["id"]
    latest = load_measurements(db, "2026-10")
    assert len(latest) == 1
    assert latest.iloc[0]["Actual %"] == 90.0
    assert latest.iloc[0]["recorded_by"] == "planner2"
    import sqlite3
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM planning_kpi_evidence").fetchone()[0] == 2


def test_controlled_kpi_list_has_all_monthly_output_measures_and_targets():
    by_code = {m["code"]:m for m in METRICS}
    assert len(by_code) == 9
    assert by_code["KPI-PL-01"]["target"] == 90.0
    assert by_code["KPI-PL-02"]["target"] == 98.0
    assert by_code["KPI-PL-03"]["target"] == 95.0
    assert by_code["KPI-PL-07"]["target"] == 95.0
    assert by_code["KPI-PL-08"]["target"] == 98.0
