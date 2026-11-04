from pathlib import Path
from suite.common import REPO_ROOT


def test_wip_has_one_central_reporting_page_and_clear_source_names():
    hub = (REPO_ROOT / "hub.py").read_text(encoding="utf-8")
    daily = (REPO_ROOT / "apps" / "daily" / "daily_planner_app.py").read_text(encoding="utf-8")
    assert "('🏭 WIP — Planning vs Production','wip')" in hub
    assert "if _page == 'wip':" in hub
    assert "PLAN-2026 PLANNING WIP" in hub
    assert "PRODUCTION WIP · section snapshot reports" in hub
    assert "One WIP destination" in hub
    assert "st.metric('Production WIP — loaded sections'" not in daily
    assert "Production WIP by section × product category (source evidence)" not in daily


def test_report_and_section_status_entry_are_separate_and_events_are_visible():
    hub = (REPO_ROOT / "hub.py").read_text(encoding="utf-8")
    floor = (REPO_ROOT / "suite" / "floor_open_close.py").read_text(encoding="utf-8")
    assert "This page reports loaded workbooks and saved section events." in hub
    assert "Open WO Section Status Entry" in hub
    assert "All saved section-status event history" in hub
    assert "event_id" in floor and "source_ref" in floor and "source_row" in floor
    assert "quantity_unknown" in floor
    assert "This records a section event only; it does not close the whole work order." in floor


def test_department_kpi_and_production_evidence_routes_are_distinct():
    hub = (REPO_ROOT / "hub.py").read_text(encoding="utf-8")
    assert "('🎯 Department KPI / KPI แผนก','kpi')" in hub
    assert "('🏭 Production Evidence Analysis','production_analysis')" in hub
    assert "if _page == 'daily_kpi': _page = 'kpi'" in hub
    kpi = (REPO_ROOT / "suite" / "planning_kpi.py").read_text(encoding="utf-8")
    assert "Source evidence / หลักฐานแหล่งข้อมูล" in kpi
    assert "MAX(id) id FROM planning_kpi_evidence" in kpi
