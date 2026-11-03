from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "fast_stage4_v15.py"


def test_exact_pack_has_pull_refill_step():
    s = SRC.read_text(encoding="utf-8")
    assert "PULL REFILL" in s
    assert "refill_pool" in s
    assert "_pull_rem" in s
    assert "EXACT PHYSICAL/FURNITURE PASS" in s


def test_planning_method_is_explicit_push_pull():
    s = SRC.read_text(encoding="utf-8")
    assert "DOWNSTREAM FIRING CAPACITY PULLS COMPATIBLE DEMAND" in s
    assert "UPSTREAM PREP→MIX→FORM PUSHES" in s
