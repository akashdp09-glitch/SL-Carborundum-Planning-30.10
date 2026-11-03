import datetime as dt

import pandas as pd

from suite import open_closed_view as OC
from suite.plan_reader import ORDER


def _plan_frame():
    row = {
        "wo": "P005-110826", "due": dt.date(2026, 11, 1), "qty": 10, "prod_closed": "ยังไม่ปิด",
        "Packing.done": 0, "open": True,
    }
    for s in ORDER:
        row[f"{s}.closed"] = s in {"Preparation", "Mixing"}
        row[f"{s}.done"] = 10 if s in {"Preparation", "Mixing"} else 0
    closed = {
        "wo": "P001-010126", "due": dt.date(2026, 9, 1), "qty": 4, "prod_closed": "ปิดใบสั่ง",
        "Packing.done": 4, "open": False,
    }
    for s in ORDER:
        closed[f"{s}.closed"] = True
        closed[f"{s}.done"] = 4
    return pd.DataFrame([row, closed])


def test_from_plan_uses_existing_workbook_not_a_second_upload(tmp_path, monkeypatch):
    frame = _plan_frame()
    monkeypatch.setattr(OC, "load_plan", lambda path, cache_dir=None: frame)
    out = OC.from_plan(tmp_path / "Plan-2026-LATEST.xlsx", cache_dir=tmp_path)
    assert out["wos"] == 2
    assert int(out["by_section"].iloc[-1]["Closed WOs"]) == 1
    assert list(out["open"]["wo"]) == ["P005-110826"]
    assert list(out["closed"]["wo"]) == ["P001-010126"]


def test_from_daily_status_marks_closed_when_actual_covers_required():
    df = pd.DataFrame([
        {"Date": "2026-10-01", "Work Order": "P005-110826", "Section": "Mixing",
         "Section Required Qty": 10, "Cumulative Actual Qty": 10, "Balance Qty": 0,
         "Production Plan Qty": 10, "Production Actual Qty": 10},
        {"Date": "2026-10-01", "Work Order": "P009-110826", "Section": "Mixing",
         "Section Required Qty": 8, "Cumulative Actual Qty": 2, "Balance Qty": 6,
         "Production Plan Qty": 8, "Production Actual Qty": 2},
    ])
    out = OC.from_daily_status(df)
    assert not out["rows"].empty
    status = out["rows"].set_index("Work Order")["Daily Status"]
    assert status["P005-110826"] == "CLOSED"
    assert status["P009-110826"] == "OPEN / IN PROGRESS"


def test_empty_daily_status_does_not_invent_rows():
    assert OC.from_daily_status(pd.DataFrame())["rows"].empty
    assert OC.from_daily_status(None)["rows"].empty
