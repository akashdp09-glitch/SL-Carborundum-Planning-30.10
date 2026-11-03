"""HTTP /mobile must open the FastAPI app, not bounce to HTTPS."""
from fastapi.testclient import TestClient

from suite.common import REPO_ROOT


def test_mobile_home_redirects_to_login_not_https():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "apps" / "mobile"))
    import app as core
    c = TestClient(core.app, follow_redirects=False)
    r = c.get("/mobile")
    assert r.status_code in (302, 303)
    loc = r.headers.get("location", "")
    assert loc.startswith("/login"), loc
    assert "8443" not in loc and not loc.startswith("https://")


def test_health_is_the_real_app():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "apps" / "mobile"))
    import app as core
    c = TestClient(core.app)
    d = c.get("/health").json()
    assert d["ok"] is True
    assert "work_orders" in d
    assert d.get("http") is True


def test_plan_file_fallback_finds_wo_when_db_empty(tmp_path, monkeypatch):
    import openpyxl
    from suite import wo_lookup as W
    from suite.central_paths import PLAN_FILE
    company = tmp_path / "COMPANY_DATA"
    company.mkdir()
    plan = company / PLAN_FILE
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "แผนการเผา"
    ws["A3"] = "ProductionCode"
    ws["B3"] = "QTY"
    ws["C3"] = "รหัสสินค้า"
    ws["A4"] = "P005-110826"
    ws["B4"] = 12
    ws["C4"] = "WA60"
    wb.save(plan)
    wb.close()
    W._PLAN_CACHE["key"] = None
    rows = W.candidate_rows("p005110826", plan_path=plan, db_file=tmp_path / "missing.db")
    assert [r["wo_id"] for r in rows] == ["P005-110826"]
