"""The phone database must be filled from Home's CENTRAL_DATA Plan-2026, not company_data\\."""
import os
import sqlite3
import subprocess
import sys

import openpyxl

from suite.common import REPO_ROOT
from suite.central_paths import PLAN_FILE


def _tiny_plan(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "แผนการเผา"
    ws["A3"] = "ProductionCode"
    ws["B3"] = "QTY"
    ws["C3"] = "รหัสสินค้า"
    ws["A4"] = "P005-110826"
    ws["B4"] = 12
    ws["C4"] = "WA60"
    wb.save(path)
    wb.close()
    return path


def test_sync_mobile_plan_imports_home_central_file(tmp_path):
    shared = tmp_path / "CENTRAL_DATA"
    company = shared / "COMPANY_DATA"
    db = shared / "DATABASE" / "sl_planning.db"
    company.mkdir(parents=True)
    db.parent.mkdir(parents=True)
    _tiny_plan(company / PLAN_FILE)
    env = os.environ.copy()
    env["SL_SHARED_ROOT"] = str(shared)
    env["SL_COMPANY_DATA"] = str(company)
    env["SL_DB_PATH"] = str(db)
    env["SL_PHOTO_ROOT"] = str(shared / "PHOTOS")
    env["SL_SOURCE_COPY_ROOT"] = str(shared / "SOURCE_COPIES")
    env["SL_REPORT_ROOT"] = str(shared / "REPORTS")
    r = subprocess.run([sys.executable, str(REPO_ROOT / "sync_mobile_plan.py")], cwd=str(REPO_ROOT),
                       env=env, capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "new=1" in r.stdout or "updated=1" in r.stdout
    assert str(company / PLAN_FILE) in r.stdout.replace("\\", "/") or PLAN_FILE in r.stdout
    con = sqlite3.connect(db)
    try:
        row = con.execute("SELECT wo_id, qty, product_code FROM work_orders WHERE wo_id=?", ("P005-110826",)).fetchone()
    finally:
        con.close()
    assert row == ("P005-110826", 12.0, "WA60")


def test_daily_create_plan_does_not_raise_upload_first():
    text = (REPO_ROOT / "apps/daily/daily_planner_app.py").read_text(encoding="utf-8")
    assert "raise ValueError('Upload latest Plan 2026 first.')" not in text
    assert "missing_plan_message" in text
