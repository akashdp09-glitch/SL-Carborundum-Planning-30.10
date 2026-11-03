import threading
import datetime as dt
import openpyxl
import pytest
from suite.source_manager import SourceManager, SLOTS
from suite.plan_reader import load_plan
from suite import sheet_roles as SR


def _wb(path, sheets):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets:
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
    wb.save(path)
    return path


def plan_file(path, wo="P001-010126", qty=10, decoy_first=True):
    master = [["note"], [], ["ProductionCode", "วันที่ออกใบสั่งงาน", "กำหนดเข้าคลัง", "ORDER", "กำหนดส่งใหม่", "Customername", None, "Specification", None, "QTY"],
              [wo, None, dt.datetime(2026, 10, 1), "O1", None, "C", None, "S", None, qty]]
    decoy = [["a", "b"], [1, 2]]
    sheets = [("Summary", decoy), ("My master", master)] if decoy_first else [("My master", master), ("Summary", decoy)]
    return _wb(path, sheets)


@pytest.fixture()
def sm(tmp_path):
    return SourceManager(tmp_path / "shared", bundled_capacity=tmp_path / "none.xlsx")


def test_master_found_by_header_not_position(tmp_path):
    p = plan_file(tmp_path / "p.xlsx")
    assert SR.find_sheet(p, SR.MASTER_PLAN) == "My master"
    df = load_plan(p, cache_dir=tmp_path)
    assert list(df.wo) == ["P001-010126"] and df.qty.iloc[0] == 10


def test_import_once_and_duplicate_is_noop(sm, tmp_path):
    p = plan_file(tmp_path / "p.xlsx")
    a = sm.import_file("PLAN_2026", p, "tester")
    b = sm.import_file("PLAN_2026", p, "tester")
    assert a.status == "IMPORTED" and b.status == "DUPLICATE_UNCHANGED" and b.revision_no == a.revision_no == 1
    assert len(sm.history("PLAN_2026")) == 1
    assert any("Planning Suite" in m for m in a.affected_modules) and any("Mobile" in m for m in a.affected_modules)


def test_same_file_in_another_slot_is_refused(sm, tmp_path):
    p = plan_file(tmp_path / "p.xlsx")
    sm.import_file("PLAN_2026", p)
    r = sm.import_file("FIRING_PLAN", p)
    assert r.status == "DUPLICATE_OTHER_SLOT" and not sm.active("FIRING_PLAN")


def test_revisions_keep_originals_and_rollback(sm, tmp_path):
    p1, p2 = plan_file(tmp_path / "a.xlsx", qty=10), plan_file(tmp_path / "b.xlsx", qty=99)
    sm.import_file("PLAN_2026", p1)
    sm.import_file("PLAN_2026", p2)
    hist = sm.history("PLAN_2026")
    assert [h["revision_no"] for h in hist] == [2, 1] and hist[0]["active"] == 1 and hist[1]["active"] == 0
    assert all(__import__("pathlib").Path(h["stored_path"]).exists() for h in hist)
    rb = sm.rollback("PLAN_2026", 1)
    assert rb.status == "REACTIVATED" and sm.active("PLAN_2026")["sha256"] == hist[1]["sha256"]
    assert all(c["matches_active_revision"] for c in sm.consistency_report())
    assert load_plan(sm.data / "Plan-2026-LATEST.xlsx", cache_dir=tmp_path).qty.iloc[0] == 10


def test_wrong_file_for_plan_slot_is_rejected(sm, tmp_path):
    p = _wb(tmp_path / "x.xlsx", [("S", [["a"], [1]])])
    r = sm.import_file("PLAN_2026", p)
    assert r.status == "REJECTED" and "master" in r.message.lower() or "MASTER_PLAN" in r.message
    assert not sm.active("PLAN_2026")


def test_product_register_is_knowledge_only_and_not_listed_as_missing(sm, tmp_path):
    assert SLOTS["PRODUCT_REGISTER"].knowledge_only is True
    assert "PRODUCT_REGISTER" not in sm.missing()
    row = next(r for r in sm.status_table() if r["slot"] == "PRODUCT_REGISTER")
    assert row["state"] == "KNOWLEDGE"
    p = _wb(tmp_path / "reg.xlsx", [("codes", [["code"], ["1"]])])
    r = sm.import_file("PRODUCT_REGISTER", p, "tester")
    assert r.status == "REJECTED" and "Knowledge" in r.message
    assert not sm.active("PRODUCT_REGISTER")
    (sm.data / "Product-Register-LATEST.xlsx").write_bytes(p.read_bytes())
    assert sm.adopt_existing() == []
    assert not sm.active("PRODUCT_REGISTER")


def test_two_kpi_sources_and_six_daily_status_slots_are_separate(sm, tmp_path):
    assert {"KPI_SECTION_PLAN_VS_ACTUAL", "KPI_DELIVERY_WAREHOUSE"} <= set(SLOTS)
    assert len([s for s in SLOTS if s.startswith("DAILY_STATUS_")]) == 6
    k1 = sm.import_file("KPI_SECTION_PLAN_VS_ACTUAL", _wb(tmp_path / "k1.xlsx", [("ผลิตตามแผน", [["x", 1]])]))
    k2 = sm.import_file("KPI_DELIVERY_WAREHOUSE", _wb(tmp_path / "k2.xlsx", [("ส่งมอบ", [["y", 2]])]))
    assert k1.ok and k2.ok
    assert sm.active("KPI_SECTION_PLAN_VS_ACTUAL")["sha256"] != sm.active("KPI_DELIVERY_WAREHOUSE")["sha256"]
    assert (sm.root / "KPI" / "Section-Performance-KPI-LATEST.xlsx").exists() and (sm.root / "KPI" / "Warehouse-Delivery-KPI-LATEST.xlsx").exists()
    ds = sm.import_file("DAILY_STATUS_MIXING", _wb(tmp_path / "m.xlsx", [("01-10-2026", [["x"]]), ("02-10-2026", [["x"]])]), "u")
    assert ds.ok and any((sm.root / "DAILY_STATUS").glob("Mixing__2026-10__LATEST.xlsx"))
    other = sm.import_file("DAILY_STATUS_PACKING", _wb(tmp_path / "pk.xlsx", [("01-10-2026", [["z"]])]))
    assert other.ok and sm.active("DAILY_STATUS_MIXING")["sha256"] != sm.active("DAILY_STATUS_PACKING")["sha256"]
    assert "DAILY_STATUS_MIXING" not in sm.missing() and "DAILY_STATUS_FORMING" in sm.missing()
    assert "PROCESS_CLOSE" in SLOTS and "PROCESS_CLOSE_MIXING" in SLOTS
    pc = sm.import_file("PROCESS_CLOSE_MIXING", _wb(tmp_path / "pc.xlsx", [("Close", [["WO", 1]])]), "u")
    assert pc.ok and (sm.root / "PROCESS_CLOSE" / "Mixing__LATEST.xlsx").exists()


def test_concurrent_identical_imports_create_one_revision(sm, tmp_path):
    p = plan_file(tmp_path / "p.xlsx")
    data = p.read_bytes()
    results = []
    def go():
        results.append(sm.import_bytes("PLAN_2026", "p.xlsx", data, "t").status)
    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count("IMPORTED") == 1 and results.count("DUPLICATE_UNCHANGED") == 5
    assert len(sm.history("PLAN_2026")) == 1


def test_adopt_existing_daily_planner_files(sm, tmp_path):
    kpi = sm.root / "KPI"; kpi.mkdir(exist_ok=True)
    _wb(kpi / "Section-Performance-KPI-LATEST.xlsx", [("k", [["z"]])])
    adopted = sm.adopt_existing()
    assert [a.slot_id for a in adopted] == ["KPI_SECTION_PLAN_VS_ACTUAL"] and adopted[0].ok
    assert sm.adopt_existing() == []


def test_bundled_capacity_is_initial_revision(tmp_path):
    from suite.common import REPO_ROOT
    m = SourceManager(tmp_path / "s", bundled_capacity=REPO_ROOT / "apps/daily/CAPACITY_DATABASE.xlsx")
    a = m.active("CAPACITY_DATABASE")
    assert a and a["imported_by"] == "system" and a["revision_no"] == 1


def test_adopts_existing_company_data_files_once(tmp_path):
    shared = tmp_path / "s"
    (shared / "COMPANY_DATA").mkdir(parents=True)
    plan_file(shared / "COMPANY_DATA" / "Plan-2026-LATEST.xlsx")
    m = SourceManager(shared, bundled_capacity=tmp_path / "none.xlsx")
    res = m.adopt_existing()
    assert [r.slot_id for r in res] == ["PLAN_2026"] and res[0].ok
    assert m.adopt_existing() == []
    assert all(c["matches_active_revision"] for c in m.consistency_report())
