"""A prior SQLite expression index must not prevent the active Plan import."""
from openpyxl import Workbook

import app as mobile_app


def test_plan_import_repairs_legacy_python_function_index(tmp_path, monkeypatch):
    monkeypatch.setattr(mobile_app, "DB_PATH", tmp_path / "sl_planning.db")
    mobile_app.init_db()

    # Recreate the index format found in older shared databases. Without the
    # registered function/migration, importing a new work order fails with
    # "unknown function: norm_wo()".
    con = mobile_app.db()
    con.execute("DROP INDEX IF EXISTS idx_work_orders_norm_wo")
    con.execute("CREATE INDEX idx_work_orders_norm_wo ON work_orders(norm_wo(wo_id))")
    con.commit()
    con.close()

    book = Workbook()
    sheet = book.active
    sheet.title = "แผนการเผา"
    sheet.cell(3, 1, "ProductionCode")
    sheet.cell(3, 2, "QTY")
    sheet.cell(3, 3, "รหัสสินค้า")
    sheet.cell(4, 1, "P-TEST-2026")
    sheet.cell(4, 2, 12)
    sheet.cell(4, 3, "TEST-PART")
    plan = tmp_path / "Plan-2026-test.xlsx"
    book.save(plan)

    added, updated, rejected, errors = mobile_app.import_plan2026(plan, plan.name, "test")
    assert (added, updated, rejected) == (1, 0, 0)
    assert errors == []
    con = mobile_app.db()
    assert con.execute("SELECT wo_id FROM work_orders WHERE wo_id='P-TEST-2026'").fetchone()[0] == "P-TEST-2026"
    idx_sql = con.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_work_orders_norm_wo'").fetchone()[0]
    assert "norm_wo(" not in idx_sql.lower()
    con.close()
