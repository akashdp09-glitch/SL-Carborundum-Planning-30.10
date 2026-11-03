from pathlib import Path


def test_monthly_kpi_update_is_in_the_analysis_page_not_home():
    hub = Path('hub.py').read_text(encoding='utf-8')
    daily = Path('apps/daily/daily_planner_app.py').read_text(encoding='utf-8')
    assert "home_kpi_section" not in hub and "home_kpi_delivery" not in hub
    assert "Update monthly KPI workbooks" in daily
    assert "monthly_kpi_source_update_form" in daily
    assert "KPI_SECTION_PLAN_VS_ACTUAL" in daily
    assert "KPI_DELIVERY_WAREHOUSE" in daily


def test_kpi_analysis_uses_shared_published_paths_not_old_session_paths():
    daily = Path('apps/daily/daily_planner_app.py').read_text(encoding='utf-8')
    assert "_kp1=(_kpi_root/'Section-Performance-KPI-LATEST.xlsx').resolve()" in daily
    assert "_kp2=(_kpi_root/'Warehouse-Delivery-KPI-LATEST.xlsx').resolve()" in daily
    assert "Path(st.session_state.get('kpi_section_path'" not in daily
    assert "Path(st.session_state.get('kpi_delivery_path'" not in daily
    assert '_discover_monthly_kpi' not in daily
