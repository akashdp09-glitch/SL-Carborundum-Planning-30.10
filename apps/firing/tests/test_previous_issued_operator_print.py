from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook

from apps.firing.previous_issued import previous_kiln_blocks, validate_firing_source


class Upload:
    name = "Operator Print.xlsx"

    def __init__(self, data):
        self._data = data

    def getvalue(self):
        return self._data


def operator_workbook(include_finish=True):
    wb = Workbook()
    ws = wb.active
    ws.title = "Operator Print"
    headers = ["Load ID / รหัสโหลด", "Loading Date / วันที่เข้าเตา", "Kiln / เตา",
               "Program / โปรแกรม", "Work Order / ใบสั่งผลิต", "Qty pcs",
               "Firing Complete"]
    if not include_finish:
        headers.pop()
    ws.append(headers)
    ws.append(["LOAD-001", datetime(2026, 10, 9), "T0", "P1", "P001-091026", 12,
               datetime(2026, 10, 12)] if include_finish else
              ["LOAD-001", datetime(2026, 10, 9), "T0", "P1", "P001-091026", 12])
    ws.append(["LOAD-001", datetime(2026, 10, 9), "T0", "P1", "P002-091026", 8,
               datetime(2026, 10, 12)] if include_finish else
              ["LOAD-001", datetime(2026, 10, 9), "T0", "P1", "P002-091026", 8])
    out = BytesIO()
    wb.save(out)
    wb.close()
    return out.getvalue()


def test_operator_print_only_is_valid_and_protects_prior_load_once():
    data = operator_workbook()
    ok, message = validate_firing_source(data)
    assert ok, message
    blocks, audit = previous_kiln_blocks([Upload(data)], date(2026, 10, 10))
    assert blocks == {"T0": date(2026, 10, 13)}
    assert len(audit) == 1
    assert audit.iloc[0]["Load ID"] == "LOAD-001"
    assert audit.iloc[0]["Status"] == "PROTECTED BEFORE CUTOVER"


def test_operator_print_missing_finish_is_not_accepted_as_shared_firing_source():
    ok, message = validate_firing_source(operator_workbook(include_finish=False))
    assert not ok
    assert "Firing Complete" in message
