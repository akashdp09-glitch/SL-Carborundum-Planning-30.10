"""Fixtures for the mobile app tests. Every test run uses a throw-away data directory so no
real or shared database is ever touched; WOs created here are labelled SYNTHETIC."""
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="sl_mobile_test_"))
for k, sub in {"SL_SHARED_ROOT": "", "SL_COMPANY_DATA": "COMPANY_DATA", "SL_DB_PATH": "DATABASE/sl_planning.db", "SL_PHOTO_ROOT": "PHOTOS",
               "SL_SOURCE_COPY_ROOT": "SOURCE_COPIES", "SL_REPORT_ROOT": "REPORTS"}.items():
    os.environ[k] = str(_TMP / sub) if sub else str(_TMP)
os.environ["SL_APP_SECRET"] = "test-secret"
(_TMP / "DATABASE").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import io
import pytest
from PIL import Image


@pytest.fixture(scope="session")
def core():
    import app
    return app


@pytest.fixture(scope="session")
def audit(core):
    import audit_v2
    return audit_v2


@pytest.fixture(scope="session", autouse=True)
def synthetic_wos(core):
    con = core.db()
    try:
        for i, (wo, code, part) in enumerate([("WO-TEST-0001", "SYNTH-A", "SYNTH-PART-A"), ("WO-TEST-0002", "SYNTH-DUP", "SYNTH-PART-B"),
                                               ("WO-TEST-0003", "SYNTH-DUP", "SYNTH-PART-C")]):
            con.execute("INSERT OR IGNORE INTO work_orders(wo_id,production_code,product_code,customer_name,qty,status,imported_at) VALUES(?,?,?,?,?,?,?)",
                        (wo, code, part, "SYNTHETIC CUSTOMER", 100 + i, "RELEASED", "2026-10-04 08:00:00"))
        con.commit()
    finally:
        con.close()


def _login(core, username, password):
    from fastapi.testclient import TestClient
    c = TestClient(core.app, follow_redirects=False)
    r = c.post("/login", data={"username": username, "password": password})
    assert r.status_code == 303, r.text[:200]
    return c


@pytest.fixture()
def operator(core):
    return _login(core, "operator", "operator123")


@pytest.fixture()
def admin(core):
    return _login(core, "admin", "admin123")


@pytest.fixture()
def planning(core):
    return _login(core, "planning", "planning123")


@pytest.fixture()
def management(core):
    con = core.db()
    row = con.execute("SELECT username FROM users WHERE role='management' AND active=1").fetchone()
    con.close()
    pw = {"management": None}
    # demo management/viewer passwords are defined in app.py's seed list
    import re
    src = Path(core.__file__).read_text(encoding="utf-8")
    m = re.search(r'\("%s", "([^"]+)", "management"' % row["username"], src)
    return _login(core, row["username"], m.group(1))


def png_bytes(color=(200, 30, 30), size=(64, 48)):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "PNG")
    return b.getvalue()


@pytest.fixture()
def png():
    return png_bytes


@pytest.fixture()
def viewer(core):
    """A View Only user created through the application's own user table (the demo seed has none)."""
    import hashlib
    con = core.db()
    cols = {r[1] for r in con.execute("PRAGMA table_info(users)")}
    if not con.execute("SELECT 1 FROM users WHERE username='viewer_test'").fetchone():
        hasher = getattr(core, "hash_password", None) or getattr(core, "make_hash", None)
        assert hasher, "cannot find password hashing helper"
        con.execute("INSERT INTO users(username,password_hash,role,display_name,created_at) VALUES(?,?,?,?,?)",
                    ("viewer_test", hasher("viewer123"), "viewer", "Viewer (test)", "2026-01-01 00:00:00"))
        con.commit()
    con.close()
    return _login(core, "viewer_test", "viewer123")
