from suite import service_launcher as L


def test_ports_and_commands_match_the_start_bat():
    assert L.SERVICES["daily"]["port"] == 8511
    assert L.SERVICES["firing"]["port"] == 8512
    assert L.SERVICES["mobile"]["port"] == 8000
    d = L.command("daily")
    assert d[2:4] == ["streamlit", "run"] and "daily_planner_app.py" in d and "8511" in d
    assert "--server.address" in d and "0.0.0.0" in d
    f = L.command("firing")
    assert "firing_tomorrow_fast.py" in f and "8512" in f
    m = L.command("mobile")
    assert m[-1].endswith("start_mobile.py")


def test_phone_must_not_iframe_loopback():
    assert L.host_from_headers({"Host": "192.168.1.20:8510"}) == "192.168.1.20"
    assert L.host_from_headers({"host": "127.0.0.1:8510"}) == "127.0.0.1"
    assert L.host_from_headers({}) == "127.0.0.1"
    assert L.iframe_url("daily", "192.168.1.20", "focus=wip") == "http://192.168.1.20:8511?focus=wip"
    assert L.iframe_url("firing", "127.0.0.1") == "http://127.0.0.1:8512"
    assert L.is_phone_ua("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)")
    assert L.is_phone_ua("Mozilla/5.0 (Linux; Android 14) Mobile")
    assert not L.is_phone_ua("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    assert not L.is_phone_ua("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)")


def test_probe_unused_port_is_down(monkeypatch):
    monkeypatch.setitem(L.SERVICES["daily"], "port", 59999)
    monkeypatch.setitem(L.SERVICES["daily"], "health", "http://127.0.0.1:59999/_stcore/health")
    assert L.probe("daily") is False
    assert L.port_open(59999) is False


def test_child_env_points_at_central_data(monkeypatch, tmp_path):
    monkeypatch.delenv("SL_SHARED_ROOT", raising=False)
    monkeypatch.delenv("SL_DB_PATH", raising=False)
    env = L.child_env(tmp_path)
    assert env["SL_SHARED_ROOT"].endswith("CENTRAL_DATA")
    assert env["SL_DB_PATH"].endswith("sl_planning.db")


def test_start_is_noop_when_already_up(monkeypatch):
    monkeypatch.setattr(L, "probe", lambda _sid: True)
    monkeypatch.setattr(L, "is_foreign", lambda _sid: False)
    out = L.start("daily")
    assert out["already"] is True and out["started"] is False and out["ok"] is True


def test_start_replaces_foreign_daily(monkeypatch):
    state = {"probe": True}

    def _probe(_sid):
        return state["probe"]

    killed = []
    monkeypatch.setattr(L, "probe", _probe)
    monkeypatch.setattr(L, "is_foreign", lambda _sid: state["probe"])
    monkeypatch.setattr(L, "stop", lambda _sid: killed.append(_sid) or state.update(probe=False) or {"ok": True, "killed": [9]})
    monkeypatch.setattr(L, "_acquire_lock", lambda _sid: False)
    out = L.start("daily")
    assert killed == ["daily"]
    assert out["replaced"] is True


def test_origin_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "LOG_DIR", tmp_path)
    monkeypatch.setattr(L, "ROOT", tmp_path / "this")
    L.write_origin("daily", tmp_path / "this")
    assert L.recorded_origin("daily").resolve() == (tmp_path / "this").resolve()


def test_mobile_stays_up_when_pid_or_origin_is_unknown(monkeypatch):
    monkeypatch.setattr(L, "probe", lambda _sid: True)
    monkeypatch.setattr(L, "recorded_origin", lambda _sid: None)
    monkeypatch.setattr(L, "recorded_pid", lambda _sid: None)
    monkeypatch.setattr(L, "pid_on_port", lambda _port: 9999)
    assert L.is_foreign("mobile") is False
    assert L.is_foreign("daily") is True


def test_mobile_is_replaced_when_another_zip_owns_the_port(monkeypatch, tmp_path):
    monkeypatch.setattr(L, "ROOT", tmp_path / "this-zip")
    monkeypatch.setattr(L, "probe", lambda _sid: True)
    monkeypatch.setattr(L, "recorded_origin", lambda _sid: tmp_path / "older-zip")
    assert L.is_foreign("mobile") is True


def test_local_services_help_is_searchable():
    from suite import help_f1 as H
    from suite.common import REPO_ROOT
    hits = H.search("127.0.0.1 refused to connect daily firing phone", REPO_ROOT)
    assert any("8511" in b or "Daily" in t for _, k, t, b in hits)
    wo = H.search("work order does not exist phone QR Plan-2026", REPO_ROOT)
    assert any("sl_planning.db" in b or "phone database" in b for _, k, t, b in wo)
    mob = H.search("mobile not opening http 8000", REPO_ROOT)
    assert any("8000" in b and "certificate" in b.lower() for _, k, t, b in mob)
