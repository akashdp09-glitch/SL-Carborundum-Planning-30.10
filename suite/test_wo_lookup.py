import sqlite3

import openpyxl
import pandas as pd

from suite import wo_lookup as W


def _tiny_plan(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "แผนการเผา"
    ws["A3"] = "ProductionCode"
    ws["B3"] = "QTY"
    ws["C3"] = "รหัสสินค้า"
    ws["D3"] = "Customername"
    ws["A4"] = "P005-110826"
    ws["B4"] = 12
    ws["C4"] = "WA60"
    ws["D4"] = "SYNTHETIC CUSTOMER"
    wb.save(path)
    wb.close()
    return path


def test_plan_file_finds_wo_in_any_typed_format(tmp_path):
    plan = _tiny_plan(tmp_path / "Plan-2026-LATEST.xlsx")
    W._PLAN_CACHE["key"] = None
    for q in ("P005-110826", "p005110826", "SLWO:P005-110826", "P005 110826"):
        hits = W.suggestions_from_plan(plan, q)
        assert not hits.empty, q
        assert hits.iloc[0]["Work Order"] == "P005-110826"
    assert W.find_canonical_wo("slwo:p005-110826", plan_path=plan, db_file=tmp_path / "missing.db") == "P005-110826"


def test_unknown_wo_is_not_invented(tmp_path):
    plan = _tiny_plan(tmp_path / "Plan-2026-LATEST.xlsx")
    W._PLAN_CACHE["key"] = None
    hits = W.suggestions_from_plan(plan, "NOTHING-LIKE-THIS")
    assert hits.empty
    assert W.find_canonical_wo("NOTHING-LIKE-THIS", plan_path=plan, db_file=tmp_path / "missing.db") is None


def test_work_orders_table_is_fallback(tmp_path):
    db = tmp_path / "sl_planning.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE work_orders (wo_id TEXT, production_code TEXT, customer_name TEXT, customer_id TEXT, product_code TEXT, specification TEXT, qty REAL, revised_due_date TEXT, initial_due_date TEXT, order_no TEXT, plan_source_row INTEGER)")
    con.execute("INSERT INTO work_orders VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("P009-010126", "P009-010126", "DB CUSTOMER", "", "WA10", "", 3, "", "", "", 9))
    con.commit()
    con.close()
    hits = W.suggestions_from_db(db, "p009010126")
    assert list(hits["Work Order"]) == ["P009-010126"]
    df, src = W.lookup("p009010126", plan_path=tmp_path / "no-plan.xlsx", db_file=db)
    assert list(df["Work Order"]) == ["P009-010126"]
    assert src == db


def test_empty_inputs_return_empty():
    assert W.suggestions_from_df(pd.DataFrame(), "P005").empty
    assert W.suggestions_from_plan(None, "P005").empty
    assert W.find_canonical_wo("", plan_path=None, db_file=None) is None
