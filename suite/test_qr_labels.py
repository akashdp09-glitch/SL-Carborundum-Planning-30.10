from datetime import datetime
from pathlib import Path
import importlib.util
import unittest

import pandas as pd

from suite.qr_labels import collect_wo_rows, filter_open_plan_rows, norm_wo, photo_stem, rows_from_plan_frame, write_label_pack


def test_norm_wo_accepts_any_format():
    assert norm_wo("p005110826") == norm_wo("P005-110826") == "P005110826"
    assert norm_wo("SLWO:P005-110826") == "P005110826"
    assert norm_wo("http://pc/scan/P005-110826") == "P005110826"


def test_photo_stem_is_wo_location_datetime():
    stem = photo_stem("P005-110826", "Forming / D7", datetime(2026, 10, 5, 8, 15, 30))
    assert stem == "P005-110826_Forming-D7_20261005-081530"


def test_plan_frame_dedupes_and_skips_blank(tmp_path):
    df = pd.DataFrame([
        {"Work Order": "P005-110826", "Product Code": "WA60", "Customer": "A", "pcs": 10, "Due Date": "2026-11-01"},
        {"Work Order": "p005-110826", "Product Code": "dup", "Customer": "B", "pcs": 1, "Due Date": "2026-11-02"},
        {"Work Order": "", "Product Code": "X", "Customer": "C", "pcs": 2, "Due Date": "2026-11-03"},
    ])
    rows = rows_from_plan_frame(df)
    assert [r["wo_id"] for r in rows] == ["P005-110826"]


@unittest.skipUnless(importlib.util.find_spec("qrcode"), "qrcode runtime package is not installed in this test image")
def test_write_label_pack_embeds_slwo_payload(tmp_path: Path):
    out, n = write_label_pack(
        [{"wo_id": "P001-010126", "product_code": "X", "customer_name": "C", "qty": 4, "due_date": "2026-02-01"}],
        tmp_path / "qr.xlsx",
        tmp_path / "png",
        generated_at=datetime(2026, 10, 5, 9, 0, 0),
    )
    assert n == 1 and out.exists()
    pngs = list((tmp_path / "png").glob("*.png"))
    assert len(pngs) == 1 and pngs[0].stat().st_size > 20
    from openpyxl import load_workbook
    book = load_workbook(out)
    assert book["QR_LABELS"]["A2"].value == "P001-010126"
    assert book["QR_LABELS"]["K2"].value == "SLWO:P001-010126"
    assert book["Sticker Print"]["A3"].value == "P001-010126"
    assert len(book["Sticker Print"]._images) == 1


def test_section_due_date_filter_open_only():
    df = pd.DataFrame([
        {"Work Order":"P001-010126","pcs":10,"Due Date":"2026-10-10","Section":"Forming","Authoritative Closed":False},
        {"Work Order":"P002-010126","pcs":5,"Due Date":"2026-10-11","Section":"Firing","Authoritative Closed":False},
        {"Work Order":"P003-010126","pcs":5,"Due Date":"2026-10-10","Section":"Forming","Authoritative Closed":True},
        {"Work Order":"P004-010126","pcs":0,"Due Date":"2026-10-10","Section":"Forming","Authoritative Closed":False},
    ])
    selected=filter_open_plan_rows(rows_from_plan_frame(df),"Forming",pd.Timestamp("2026-10-10").date(),pd.Timestamp("2026-10-10").date())
    assert [r['wo_id'] for r in selected] == ['P001-010126']


def test_status_and_creation_date_filters_include_closed_and_all():
    df = pd.DataFrame([
        {"Work Order":"P001-010126","Order Qty":10,"pcs":4,"Due Date":"2026-10-20","Work Order Creation Date":"2026-09-01","Section":"Mixing","Authoritative Closed":False},
        {"Work Order":"P002-010126","Order Qty":7,"pcs":0,"Due Date":"2026-09-30","Work Order Creation Date":"2026-08-15","Section":"Mixing","Authoritative Closed":True},
        {"Work Order":"P003-010126","Order Qty":3,"pcs":0,"Due Date":"2026-10-20","Work Order Creation Date":"2026-10-01","Section":"Firing","Authoritative Closed":False},
    ])
    rows=rows_from_plan_frame(df)
    start=pd.Timestamp("2026-08-01").date();end=pd.Timestamp("2026-09-30").date()
    created=filter_open_plan_rows(rows,"All sections",start,end,"All orders","order_date")
    assert [r["wo_id"] for r in created]==["P001-010126","P002-010126"]
    closed=filter_open_plan_rows(rows,"All sections",None,None,"Closed orders","due_date")
    assert [r["wo_id"] for r in closed]==["P002-010126"]
    all_due=filter_open_plan_rows(rows,"All sections",None,None,"All orders","due_date")
    assert len(all_due)==3


def test_collect_falls_back_to_plan_when_db_missing(tmp_path):
    df = pd.DataFrame([{"Work Order": "PBS001-010126", "Product Code": "R1", "Customer": "Cust"}])
    rows, source = collect_wo_rows(tmp_path / "missing.db", df)
    assert source == "plan" and rows[0]["wo_id"] == "PBS001-010126"
