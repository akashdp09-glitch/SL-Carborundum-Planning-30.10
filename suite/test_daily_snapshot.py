import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "daily"))
from daily_snapshot import content_digest, dataframe_fingerprint, describe_changes, file_record


def test_dataframe_fingerprint_is_stable_for_the_same_rows():
    a = pd.DataFrame([{"Work Order": "P001-010126", "Qty": 12, "Note": None}])
    b = pd.DataFrame([{"Work Order": "P001-010126", "Qty": 12, "Note": None}])
    assert dataframe_fingerprint(a) == dataframe_fingerprint(b)
    assert dataframe_fingerprint(a) == dataframe_fingerprint(a)


def test_file_content_digest_ignores_mtime_only_change(tmp_path):
    p = tmp_path / "plan.xlsx"
    p.write_bytes(b"PK\x03\x04synthetic-workbook")
    first = file_record(p, force_hash=True)
    os.utime(p, (p.stat().st_atime, p.stat().st_mtime + 5))
    second = file_record(p, force_hash=True)
    assert first["sha256"] == second["sha256"]
    assert first["modified_ns"] != second["modified_ns"]
    params = {"horizon": 60}
    assert content_digest({"Plan 2026": first}, params) == content_digest({"Plan 2026": second}, params)
    assert describe_changes({"Plan 2026": first}, params, {"Plan 2026": second}, params) == []


def test_content_change_is_reported(tmp_path):
    p = tmp_path / "plan.xlsx"
    p.write_bytes(b"AAAA")
    before = file_record(p, force_hash=True)
    p.write_bytes(b"BBBB")
    after = file_record(p, force_hash=True)
    params = {"horizon": 60}
    assert content_digest({"Plan 2026": before}, params) != content_digest({"Plan 2026": after}, params)
    assert "Plan 2026: sha256 changed" in describe_changes({"Plan 2026": before}, params, {"Plan 2026": after}, params)


def test_same_file_token_reuses_hash_without_reread(tmp_path):
    p = tmp_path / "plan.xlsx"
    p.write_bytes(b"AAAA")
    cache = {}
    first = file_record(p, cache, force_hash=True)
    cache[first["path"]]["sha256"] = "from-cache"
    second = file_record(p, cache, force_hash=True)
    assert second["sha256"] == "from-cache"


def test_control_change_is_reported():
    rec = {"path": "x", "bytes": 1, "sha256": "ab", "modified_ns": 9}
    assert "control horizon changed" in describe_changes({"Plan": rec}, {"horizon": 60}, {"Plan": rec}, {"horizon": 90})
