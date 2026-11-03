"""SYNTHETIC fixtures only; execute with basetemp in .cloud-test-data/."""
import json
from datetime import time

import pytest
from openpyxl import Workbook

from stage_workbooks import PLAN_SHEETS, connect, stage


def recovery_fixture(path, correct_second_sheet=True):
    workbook = Workbook()
    workbook.active.title = "SYNTHETIC excluded cover"
    workbook.active["A1"] = "SYNTHETIC MUST NOT BE IMPORTED"
    sheet = workbook.create_sheet("แผน Recovery" if correct_second_sheet else "Wrong sheet")
    sheet["A1"] = "SYNTHETIC"
    sheet["B4"] = "SYNTHETIC-WO-001"
    sheet["G4"] = 10
    sheet["FO4"] = 4
    sheet["B5"] = "SYNTHETIC-WO-001"
    sheet["G5"] = 10
    sheet["FO5"] = 4
    workbook.save(path)


def test_duplicate_import_and_revised_file(tmp_path):
    source = tmp_path / "แผนผลิต Recovery SYNTHETIC.xlsx"
    recovery_fixture(source)
    with connect(tmp_path / "SYNTHETIC.sqlite") as con:
        first = stage(con, source)
        count = con.execute("SELECT COUNT(*) FROM evidence_rows").fetchone()[0]
        assert stage(con, source)["status"] == "unchanged"
        assert con.execute("SELECT COUNT(*) FROM evidence_rows").fetchone()[0] == count
        assert con.execute("SELECT sheet_name FROM sheets").fetchall() == [("แผน Recovery",)]
        # Repeated WO rows remain separate evidence, not silently summed or removed.
        assert con.execute("SELECT COUNT(*) FROM evidence_rows WHERE excel_row>=4").fetchone()[0] == 2
        book = Workbook()
        book.active.title = "SYNTHETIC cover"
        sheet = book.create_sheet("แผน Recovery")
        sheet["A1"] = "SYNTHETIC revised"
        book.save(source)
        second = stage(con, source)
        assert second["sha256"] != first["sha256"]
        assert con.execute("SELECT COUNT(*) FROM imports").fetchone()[0] == 2
        assert con.execute("SELECT COUNT(*) FROM evidence_rows WHERE source_sha256=?", (first["sha256"],)).fetchone()[0] == count


def test_wrong_recovery_sheet_rejected_without_partial_import(tmp_path):
    source = tmp_path / "แผนผลิต Recovery SYNTHETIC.xlsx"
    recovery_fixture(source, correct_second_sheet=False)
    with connect(tmp_path / "SYNTHETIC.sqlite") as con:
        with pytest.raises(ValueError, match="second worksheet"):
            stage(con, source)
        assert con.execute("SELECT COUNT(*) FROM imports").fetchone()[0] == 0


def test_production_column_bounds_and_error_evidence(tmp_path):
    source = tmp_path / "Plan SYNTHETIC.xlsx"
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title in PLAN_SHEETS:
        sheet = workbook.create_sheet(title)
        sheet["A1"] = "SYNTHETIC"
        sheet["B2"] = "#N/A"
    workbook["แผนการเผา"].cell(1, 16329, "SYNTHETIC outside supported projection")
    workbook.save(source)
    with connect(tmp_path / "SYNTHETIC.sqlite") as con:
        stage(con, source)
        dimensions = con.execute("SELECT reported_columns,retained_columns FROM sheets WHERE sheet_name='แผนการเผา'").fetchone()
        assert dimensions == (16329, 220)
        cells = json.loads(con.execute("SELECT cells_json FROM evidence_rows WHERE sheet_name='แผนการเผา' AND excel_row=2").fetchone()[0])
        assert cells == {"B": "#N/A"}


def test_kpi_time_and_formula_are_retained_without_execution(tmp_path):
    source = tmp_path / "KPI_Sirinun_monthly.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = "SYNTHETIC"
    sheet["B1"] = time(8, 30)
    sheet["C1"] = "=1/0"
    workbook.save(source)
    with connect(tmp_path / "SYNTHETIC.sqlite") as con:
        stage(con, source)
        cells = json.loads(con.execute("SELECT cells_json FROM evidence_rows").fetchone()[0])
        assert cells["B"] == {"type": "time", "value": "08:30:00"}
        assert con.execute("SELECT cell,formula FROM formula_cells").fetchall() == [("C1", "=1/0")]
