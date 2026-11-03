import io

import pandas as pd
from openpyxl import load_workbook

from daily_plan_export import build_daily_plan_workbook


def test_download_plan_button_workbook_contains_schedule_and_reports():
    payload=build_daily_plan_workbook(
        pd.DataFrame([{"Work Order":"SYNTH-WO-1","Plan Date":"2026-10-06"}]),
        pd.DataFrame([{"Section":"SYNTH","Capacity":10}]),
        pd.DataFrame([{"Work Order":"SYNTH-WO-1","Remaining":3}]),
        pd.DataFrame([{"Work Order":"SYNTH-WO-1","Risk":"LOW"}]),
        pd.DataFrame(),
        {"plans":{"SYNTH Section":pd.DataFrame([{"Work Order":"SYNTH-WO-1"}])}},
    )
    wb=load_workbook(io.BytesIO(payload),read_only=True)
    assert {"Daily Plan","Capacity vs Plan","Planning WIP Snapshot","Delivery Risk","SYNTH Section"} <= set(wb.sheetnames)
