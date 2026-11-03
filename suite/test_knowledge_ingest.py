from pathlib import Path

from suite.knowledge_ingest import classify, extract_bytes, ingest_bytes, merge_source, merged_register


def test_classify_training_vs_dated():
    assert classify("Defect Code.pptx", ".pptx") == "TECHNICAL_REFERENCE"
    assert classify("Stock on hand.xlsx", ".xlsx") == "DATED_STOCK"
    assert classify("MRP BOND2025-12-01.xlsx", ".xlsx") == "DATED_MATERIAL_PLAN"
    assert classify("Copy of รายการสินค้าส่งขึ้นทะเบียน Revice 2556.xlsx", ".xlsx") == "PRODUCT_REGISTER"


def test_csv_and_xlsx_extract_are_preview_only(tmp_path):
    csv_meta, csv_units = extract_bytes("note.csv", b"a,b\n1,2\n")
    assert csv_meta["rows"] == 2 and csv_units[0]["kind"] == "csv_preview"
    import openpyxl
    from io import BytesIO
    wb = openpyxl.Workbook()
    wb.active["A1"] = "ProductionCode"
    wb.active["B1"] = "QTY"
    buf = BytesIO(); wb.save(buf)
    meta, units = extract_bytes("plan.xlsx", buf.getvalue())
    assert units[0]["kind"] == "workbook_index" and units[0]["review_required"] is True
    assert "ProductionCode" in units[0]["text"]


def test_ingest_duplicate_is_unchanged(tmp_path):
    dest = tmp_path / "live.json"
    data = b"code,name\n126,partial\n"
    a = ingest_bytes("defects.csv", data, dest)
    b = ingest_bytes("defects.csv", data, dest)
    assert a["status"] == "INGESTED" and b["status"] == "DUPLICATE_UNCHANGED"


def test_merged_register_adds_overlay_without_replacing_shipped(tmp_path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    knowledge.joinpath("DOCUMENT_EXTRACTION.json").write_text(
        '{"sources":[{"source_id":1,"file":"a.pdf","sha256":"aaa","units":1}],"units":[{"source_id":1,"source":"a.pdf","text":"hello","kind":"t","locator":"p.1"}]}',
        encoding="utf8")
    shared = tmp_path / "CENTRAL"
    dest = shared / "KNOWLEDGE" / "DOCUMENT_EXTRACTION_LIVE.json"
    ingest_bytes("extra.csv", b"x,y\n1,2\n", dest)
    m = merged_register(tmp_path, shared)
    files = {s["file"] for s in m["sources"]}
    assert files == {"a.pdf", "extra.csv"}
    assert all(u.get("source") for u in m["units"])
