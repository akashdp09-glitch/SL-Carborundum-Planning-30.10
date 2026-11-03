import json
import os
from pathlib import Path

from suite import central_paths as C


def _touch(path: Path, text: str = "xlsx") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def test_resolve_plan_uses_company_data_env(tmp_path, monkeypatch):
    plan = _touch(tmp_path / "COMPANY_DATA" / C.PLAN_FILE, "PLAN")
    monkeypatch.setenv("SL_SHARED_ROOT", str(tmp_path))
    monkeypatch.setenv("SL_COMPANY_DATA", str(tmp_path / "COMPANY_DATA"))
    monkeypatch.delenv("SL_DB_PATH", raising=False)
    assert C.resolve_plan() == plan.resolve()
    assert C.resolve_file("missing.xlsx") is None


def test_pointer_lets_daily_find_hub_plan_when_env_points_elsewhere(tmp_path, monkeypatch):
    hub = tmp_path / "hub"
    daily = tmp_path / "daily"
    plan = _touch(hub / "CENTRAL_DATA" / "COMPANY_DATA" / C.PLAN_FILE, "HUBPLAN")
    monkeypatch.setenv("SL_SHARED_ROOT", str(hub / "CENTRAL_DATA"))
    monkeypatch.setenv("SL_COMPANY_DATA", str(hub / "CENTRAL_DATA" / "COMPANY_DATA"))
    C.write_pointer(hub)
    pointer = json.loads((hub / "CENTRAL_DATA" / C.POINTER_NAME).read_text(encoding="utf-8"))
    assert pointer["files"][C.PLAN_FILE] == str(plan.resolve())
    # Daily from another unzip: env points at its empty COMPANY_DATA, but it can still
    # be told the hub path via the pointer when SL_SHARED_ROOT is the hub folder.
    monkeypatch.setenv("SL_COMPANY_DATA", str(daily / "CENTRAL_DATA" / "COMPANY_DATA"))
    found = C.resolve_plan()
    assert found == plan.resolve()


def test_legacy_company_data_folder_is_last_resort(tmp_path, monkeypatch):
    monkeypatch.delenv("SL_SHARED_ROOT", raising=False)
    monkeypatch.delenv("SL_COMPANY_DATA", raising=False)
    legacy = _touch(tmp_path / "company_data" / C.PLAN_FILE, "OLD")
    assert C.resolve_plan(start=tmp_path) == legacy.resolve()


def test_missing_plan_message_names_home_and_old_zip():
    msg = C.missing_plan_message()
    assert "Home" in msg and "Plan-2026-LATEST.xlsx" in msg
    assert "older ZIP" in msg
    th = C.missing_plan_message(thai=True)
    assert "หน้าหลัก" in th and "Plan-2026" in th


def test_child_environ_matches_hub_folders(tmp_path, monkeypatch):
    monkeypatch.delenv("SL_SHARED_ROOT", raising=False)
    monkeypatch.delenv("SL_COMPANY_DATA", raising=False)
    monkeypatch.delenv("SL_DB_PATH", raising=False)
    env = C.child_environ(tmp_path, env={})
    assert env["SL_SHARED_ROOT"].endswith("CENTRAL_DATA")
    assert env["SL_COMPANY_DATA"].endswith("COMPANY_DATA")
    assert env["SL_DB_PATH"].endswith(os.path.join("DATABASE", "sl_planning.db")) or env["SL_DB_PATH"].endswith("DATABASE/sl_planning.db")
