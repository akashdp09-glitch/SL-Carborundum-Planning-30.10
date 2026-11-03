"""Import the REAL supplied workbooks once through the Source Manager and show that every consumer sees the same data.
(Synthetic-free: uses the files in the repo; nothing outside tmp_path is written.)"""
import json
import shutil

import pytest

from suite.capacity import load_capacity
from suite.closure_rules import classify
from suite.common import REPO_ROOT, sha256_file
from suite.plan_reader import load_plan
from suite.sept_analysis import read_sept
from suite.source_manager import SLOTS, SourceManager

PLAN = REPO_ROOT / "Plan 2026-2-Update-01100926.xlsx"
JOB = REPO_ROOT / "apps/daily/JOB_REGISTER_REFERENCE_SEP2026.xlsx"
CAP = REPO_ROOT / "apps/daily/CAPACITY_DATABASE.xlsx"


pytestmark = pytest.mark.skipif(not PLAN.exists(), reason="live Plan workbook is not shipped in the release ZIP; import it through the Source Manager and re-run")


@pytest.fixture(scope="module")
def sm(tmp_path_factory):
    root = tmp_path_factory.mktemp("shared")
    m = SourceManager(root, bundled_capacity=CAP)
    assert m.import_file("PLAN_2026", PLAN, "tester").status == "IMPORTED"
    assert m.import_file("SEPT_OPEN_CLOSED", JOB, "tester").status == "IMPORTED"
    return m


def test_one_import_is_visible_to_every_declared_module_path(sm):
    rep = {r["slot"]: r for r in sm.consistency_report()}
    assert rep["PLAN_2026"]["matches_active_revision"] and rep["SEPT_OPEN_CLOSED"]["matches_active_revision"]
    assert all(r["matches_active_revision"] for r in rep.values())
    published = sm.data / SLOTS["PLAN_2026"].legacy_target
    assert sha256_file(published) == sha256_file(PLAN) == sm.active("PLAN_2026")["sha256"]


def test_all_readers_of_the_plan_agree_on_the_same_orders(sm, tmp_path):
    published = sm.data / "Plan-2026-LATEST.xlsx"
    a = load_plan(str(published), cache_dir=str(tmp_path / "c1"))
    b = load_plan(str(sm.active_path("PLAN_2026")), cache_dir=str(tmp_path / "c2"))
    assert list(a.wo) == list(b.wo) and len(a) > 3000
    cl = classify(a, __import__("datetime").date(2026, 10, 5))
    assert int(cl.whole_closed.sum()) == int((~a["open"]).sum())       # planners' "open" flag == closure rule used by backorder


def test_second_import_of_same_bytes_creates_no_second_revision_or_copy(sm):
    again = sm.import_file("PLAN_2026", PLAN, "someone else")
    assert again.status == "DUPLICATE_UNCHANGED" and len(sm.history("PLAN_2026")) == 1


def test_changed_source_updates_every_consumer_and_rollback_restores(sm, tmp_path):
    cap2 = tmp_path / "cap2.xlsx"
    shutil.copyfile(CAP, cap2)
    import openpyxl
    wb = openpyxl.load_workbook(cap2)
    wb[wb.sheetnames[0]]["Z99"] = "revision marker"
    wb.save(cap2)
    sha0 = sm.active("CAPACITY_DATABASE")["sha256"]
    r = sm.import_file("CAPACITY_DATABASE", cap2, "tester")
    assert r.status == "IMPORTED" and r.revision_no == 2
    assert sm.active("CAPACITY_DATABASE")["sha256"] != sha0
    published = sm.data / "CAPACITY_DATABASE.xlsx"
    assert sha256_file(published) == sm.active("CAPACITY_DATABASE")["sha256"]
    assert load_capacity(published).records                              # consumers can still read it
    rb = sm.rollback("CAPACITY_DATABASE", 1, "tester")
    assert rb.ok and sha256_file(published) == sha0
    assert [h["revision_no"] for h in sm.history("CAPACITY_DATABASE")] == [3, 2, 1]      # history is append-only; rollback is a new revision
    assert sm.active("CAPACITY_DATABASE")["sha256"] == sha0


def test_original_files_are_preserved_for_each_revision(sm):
    for h in sm.history("CAPACITY_DATABASE"):
        assert sha256_file(h["stored_path"]) == h["sha256"]


def test_sept_reader_uses_the_manager_copy_and_matches_the_original(sm):
    via_sm = read_sept(sm.active_path("SEPT_OPEN_CLOSED")).measures.set_index("measure").total_by_day_cells.to_dict()
    direct = read_sept(JOB).measures.set_index("measure").total_by_day_cells.to_dict()
    assert via_sm == direct


def test_two_kpi_sources_and_daily_status_per_section_remain_distinct_slots():
    kpi = [s for s in SLOTS if s.startswith("KPI_")]
    daily = [s for s in SLOTS if s.startswith("DAILY_STATUS_")]
    assert len(kpi) == 2 and len(daily) == 6
    assert len({SLOTS[s].legacy_target for s in kpi}) == 2
