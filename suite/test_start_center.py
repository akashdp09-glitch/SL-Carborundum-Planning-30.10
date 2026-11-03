import importlib.util

from suite.common import REPO_ROOT
import control_center as cc

_spec = importlib.util.spec_from_file_location("sl_open_when_ready", REPO_ROOT / "scripts" / "windows" / "open_when_ready.py")
ready = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ready)


def test_hub_listens_on_lan_browser_stays_localhost():
    src = (REPO_ROOT / "control_center.py").read_text(encoding="utf-8")
    assert "wait_services(" not in src
    cmd = cc.hub_command("py")
    assert cmd[1:5] == ["-m", "streamlit", "run", str(REPO_ROOT / "hub.py")]
    assert cmd.count("8510") == 1
    assert "--server.address" in cmd and "0.0.0.0" in cmd
    assert "--browser.serverAddress" in cmd and "127.0.0.1" in cmd
    assert "--server.headless" in cmd and "false" in cmd


def test_start_bat_is_one_click_streamlit():
    bat = (REPO_ROOT / "START_SL_CARBORUNDUM_PLANNING_CENTER.bat").read_text(encoding="utf-8")
    assert "streamlit run" in bat
    assert "--server.headless false" in bat
    assert "--server.address 0.0.0.0" in bat
    assert "--browser.serverAddress 127.0.0.1" in bat
    assert "runtime_env.py\" install" in bat or "runtime_env.py install" in bat
    assert "timeout /t 5" not in bat
    assert 'start "SL Daily Planner"' not in bat
    assert "The .sha256 file is only a download check" in bat
    assert "Already installed — starting Planning Center" in bat
    assert r"%SL_RUNTIME_ROOT%\venv" in bat
    assert "goto INSTALL" in bat
    assert "First run in this folder" in bat
    install_echo = bat.split(":INSTALL", 1)[1].split(":LAUNCH", 1)[0]
    assert "First run in this folder" in install_echo
    before_install = bat.split("goto INSTALL", 1)[0]
    assert "Already installed" in before_install
    assert "CREATE_DESKTOP_SHORTCUT.bat" in bat
    assert "First run in this folder" not in before_install


def test_open_when_ready_does_not_open_a_dead_port(monkeypatch):
    monkeypatch.setattr(ready, "hub_up", lambda url=ready.HUB, timeout=0.8: False)
    opened = []
    monkeypatch.setattr(ready.webbrowser, "open", lambda *a, **k: opened.append(a))
    assert ready.wait_for_hub(0.2) is False
    assert ready.open_hub() is False
    assert opened == []


def test_hub_sources_page_lists_home_files_not_undefined_uploads():
    src = (REPO_ROOT / "hub.py").read_text(encoding="utf-8")
    assert "HOME_SOURCE_FILES" in src
    assert "for _,target,_ in uploads:" not in src
    assert "for _,target,_ in HOME_SOURCE_FILES:" in src
    assert "[class*='css']" not in src
    assert "stIconMaterial" in src
    assert 'font-size:0!important' in src.replace(" ", "") or "font-size: 0 !important" in src
    assert "stExpanderToggleIcon" not in src
    assert "src_product_reg" not in src
    assert "Start here: Plan-2026" in src
    assert "_render_context_source_updates(_page)" in src
    assert "HOME_SOURCE_FILES=(" in src
    assert "Product register and training files stay in Knowledge" in src


def test_home_has_compact_all_source_upload_and_no_optional_path_prompts():
    src = (REPO_ROOT / "hub.py").read_text(encoding="utf-8")
    assert "All software inputs" in src
    assert "Original source folder (optional)" not in src
    assert "Source revision / revised date (optional)" not in src
    assert "page in ('daily','daily_closed','daily_status')" in src


def test_daily_open_closed_falls_back_to_plan_when_daily_actuals_are_missing():
    src = (REPO_ROOT / "apps" / "daily" / "daily_planner_app.py").read_text(encoding="utf-8")
    assert "No readable Daily Status actual rows are available" in src
    assert "_render_plan_open_closed(st,plan_path=str(_plan_for_status)" in src
    assert "Upload or replace Daily Status on Files" in src


def test_source_manager_page_has_no_slot_import_uploader():
    src = (REPO_ROOT / "suite" / "source_manager_page.py").read_text(encoding="utf-8")
    assert "Import into a slot" not in src
    assert "file_uploader" not in src
    assert "knowledge_only" in src
    assert "Go to Home for Plan-2026" in src
    assert "already in **Knowledge / F1**" in src
