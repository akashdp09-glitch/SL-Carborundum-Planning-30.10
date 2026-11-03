import importlib.util
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from suite.common import REPO_ROOT
from suite.month_register import (
    infer_register_month,
    is_xls,
    parse_month_filename,
    parse_month_from_workbook,
    prepare_upload_bytes,
)
from suite.source_manager import SourceManager


def _job_control():
    spec = importlib.util.spec_from_file_location(
        "daily_job_control", REPO_ROOT / "apps" / "daily" / "daily_job_control.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_october_2026_xls_name():
    assert parse_month_filename("October-2026.xls") == (2026, 10)
    assert parse_month_filename("October-2026.xlsx") == (2026, 10)
    assert parse_month_filename("october-2026.XLS") == (2026, 10)
    assert parse_month_filename("Oct-2026.xls") == (2026, 10)
    assert parse_month_filename("ตุลาคม-2026.xls") == (2026, 10)


def test_other_months_and_unknown():
    assert parse_month_filename("September-2026.xlsx") == (2026, 9)
    assert parse_month_filename("November-2026.xls") == (2026, 11)
    assert parse_month_filename("January-2027.xlsx") == (2027, 1)
    assert parse_month_filename("Plan-2026-LATEST.xlsx") is None
    assert parse_month_filename("") is None


def test_xls_extension():
    assert is_xls("October-2026.xls")
    assert not is_xls("October-2026.xlsx")
    assert not is_xls("October-2026.xlsm")


def test_daily_job_control_uses_home_file_not_a_second_uploader():
    text = Path("apps/daily/daily_job_control.py").read_text(encoding="utf-8")
    assert "job_register_current" not in text
    assert "file_uploader" not in text
    assert "resolve_file" in text
    assert "parse_month_filename" in text or "infer_register_month" in text
    assert "bkk_now" in text
    assert "month=10" not in text


def test_hub_accepts_xls_for_job_register():
    text = Path("hub.py").read_text(encoding="utf-8")
    assert "home_jobs" in text
    assert "xls" in text
    assert "current month open/close register" in text.lower()
    assert "page=floor" in text
    assert "revised every day" in text
    assert "_ensure_all" not in text


def _october_xlsx(path: Path, month="October", days=31, marker=1.0):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, hdr in (("Open Job", f"Input {month} (JOB)"), ("Close Job", f"Close Job {month} (Item)")):
        ws = wb.create_sheet(title)
        ws.append(["Product", None, hdr] + [None] * (days - 1))
        ws.append(["Group", None, *list(range(1, days + 1))])
        cats = ["R", "P", "S", "T", "M"]
        for i, cat in enumerate(cats):
            ws.append(["MTO" if i == 0 else None, cat] + [float(marker)] * days)
        for i, cat in enumerate(cats):
            ws.append(["MTS" if i == 0 else None, cat] + [float(marker + 1)] * days)
    wb.save(path)
    return path


def test_parse_monthly_keeps_31_october_days(tmp_path):
    parse_monthly = _job_control().parse_monthly
    path = _october_xlsx(tmp_path / "October-2026.xlsx")
    assert infer_register_month("October-2026.xls", path) == (2026, 10)
    assert parse_month_from_workbook(path) == (2026, 10)
    df = parse_monthly(path, 2026, 10)
    assert not df.empty
    days = sorted({d.day for d in df["Date"]})
    assert days[0] == 1 and days[-1] == 31
    assert set(df["Metric"]) == {"Opened WOs", "Closed items"}


def test_september_reference_headers_are_september():
    src = Path("apps/daily/JOB_REGISTER_REFERENCE_SEP2026.xlsx")
    if not src.exists():
        pytest.skip("bundled September reference is not in this tree")
    parsed = parse_month_from_workbook(src)
    assert parsed is None or parsed[1] == 9


def test_prepare_upload_passthrough_xlsx():
    assert prepare_upload_bytes("October-2026.xlsx", b"abc") == b"abc"


def test_source_manager_daily_replace_of_register_is_a_new_revision(tmp_path):
    sm = SourceManager(tmp_path / "shared", bundled_capacity=tmp_path / "none.xlsx")
    a = tmp_path / "October-2026.xlsx"
    b = tmp_path / "October-2026-day2.xlsx"
    _october_xlsx(a, marker=1)
    _october_xlsx(b, marker=2)
    r1 = sm.import_bytes("SEPT_OPEN_CLOSED", "October-2026.xlsx", a.read_bytes(), "planner")
    assert r1.status == "IMPORTED" and sm.active("SEPT_OPEN_CLOSED")["original_name"] == "October-2026.xlsx"
    same = sm.import_bytes("SEPT_OPEN_CLOSED", "October-2026.xlsx", a.read_bytes(), "planner")
    assert same.status == "DUPLICATE_UNCHANGED"
    r2 = sm.import_bytes("SEPT_OPEN_CLOSED", "October-2026.xlsx", b.read_bytes(), "planner")
    assert r2.status == "IMPORTED" and r2.revision_no == 2
    published = sm.data / "Job-Register-LATEST.xlsx"
    assert published.exists()
    df = pd.read_excel(published, sheet_name="Open Job", header=None)
    assert any("October" in str(v) for v in df.iloc[0].tolist())


def test_xls_converts_and_keeps_original_name(tmp_path):
    xlwt = pytest.importorskip("xlwt")
    pytest.importorskip("xlrd")
    book = xlwt.Workbook()
    for title, hdr in (("Open Job", "Input October (JOB)"), ("Close Job", "Close Job October (Item)")):
        ws = book.add_sheet(title)
        ws.write(0, 0, "Product")
        ws.write(0, 2, hdr)
        ws.write(1, 0, "Group")
        for d in range(1, 32):
            ws.write(1, 1 + d, d)
        cats = ["R", "P", "S", "T", "M"]
        for i, cat in enumerate(cats):
            ws.write(2 + i, 0, "MTO" if i == 0 else "")
            ws.write(2 + i, 1, cat)
            ws.write(2 + i, 2, 3)
        for i, cat in enumerate(cats):
            ws.write(7 + i, 0, "MTS" if i == 0 else "")
            ws.write(7 + i, 1, cat)
            ws.write(7 + i, 2, 1)
    xls_path = tmp_path / "October-2026.xls"
    book.save(str(xls_path))
    converted = prepare_upload_bytes("October-2026.xls", xls_path.read_bytes())
    out = tmp_path / "out.xlsx"
    out.write_bytes(converted)
    names = pd.ExcelFile(out).sheet_names
    assert "Open Job" in names and "Close Job" in names
    sm = SourceManager(tmp_path / "shared", bundled_capacity=tmp_path / "none.xlsx")
    r = sm.import_bytes("SEPT_OPEN_CLOSED", "October-2026.xls", xls_path.read_bytes(), "planner")
    assert r.ok
    assert sm.active("SEPT_OPEN_CLOSED")["original_name"] == "October-2026.xls"
    assert (sm.data / "Job-Register-LATEST.xlsx").exists()
    parse_monthly = _job_control().parse_monthly
    df = parse_monthly(sm.data / "Job-Register-LATEST.xlsx", 2026, 10)
    assert not df.empty
    assert df["Date"].dt.day.max() >= 1
