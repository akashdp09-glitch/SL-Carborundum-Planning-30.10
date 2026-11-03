import json
from suite import help_f1 as H
from suite.common import REPO_ROOT

ROOT = REPO_ROOT


def _titles(q, **kw):
    return [(k, t, b) for _, k, t, b in H.search(q, ROOT, limit=10, **kw)]


def test_thai_question_answers_thai_first_with_citation():
    hits = _titles("ใบสั่งปิด ค้างส่ง")
    k, t, b = hits[0]
    assert k == "Factory knowledge" and b.startswith("TH:") and "EN:" in b and "Source:" in b and "CLOSE-1" in b


def test_english_question_answers_english_first():
    k, t, b = _titles("backorder closure EU FC")[0]
    assert b.startswith("EN:") and "TH:" in b


def test_specification_question_returns_one_focused_answer():
    hits = H.search("how to read product specification", ROOT, limit=8)
    assert len(hits) == 1
    assert hits[0][1] == "Factory knowledge"
    assert "Reading a SPEC string" in hits[0][2]
    assert "slide 6" in hits[0][3]


def test_every_curated_entry_has_both_languages_and_a_citation():
    for e in H.ENTRIES:
        assert e["en"].strip() and e["th"].strip() and e["cites"], e["id"]
        assert H.is_thai(e["th"]), e["id"]
        assert len(H._THAI.findall(e["en"])) < 0.15 * len(e["en"]), e["id"]   # English text may quote a Thai column label, not be Thai prose


def test_every_cited_rule_exists_and_every_approved_rule_is_searchable():
    rules = {r["id"] for r in H.approved_rules(ROOT)}
    for e in H.ENTRIES:
        assert set(e["rules"]) <= rules, e["id"]
    for rid in rules:
        assert any(k == "Approved rule" and t == rid for k, t, _ in _titles(rid)), rid


def test_help_text_matches_the_implemented_closure_rule():
    b = " ".join(e["en"] for e in H.ENTRIES if e["id"] == "closure")
    assert "EU" in b and "FC" in b and "never close the order" in b
    assert "FC not closed" not in b          # the pre-approval help wrongly said FC alone decided


def test_document_hits_cite_page_or_slide_and_label_ocr_as_unverified():
    hits = H.search("Arithmetical average roughness", ROOT)
    docs = [h for h in hits if h[1] == "Training document"]
    assert docs and "p." in docs[0][2] and "Grinding" in docs[0][2]
    assert "UNVERIFIED" in docs[0][3]        # page 34 is an OCR page


def test_pptx_definition_found_with_slide_reference():
    docs = [h for h in H.search("Test RPM speed test", ROOT, limit=20) if h[1] == "Training document"]
    assert docs and any("slide" in h[2] for h in docs)


def test_missing_knowledge_db_is_reported_not_hidden(tmp_path):
    (tmp_path / "knowledge").mkdir()
    out = H.search("capacity", tmp_path)
    assert out[-1][1] == "Notice" and "not installed" in out[-1][2]
    assert H.knowledge_status(tmp_path)["records_db_installed"] is False


def test_extraction_register_claims_nothing_is_fully_understood():
    reg = json.loads((ROOT / "knowledge/DOCUMENT_EXTRACTION.json").read_text(encoding="utf8"))
    assert all(s["understanding"] == "TEXT_EXTRACTED_NOT_VERIFIED" for s in reg["sources"])
    assert reg["missing_sources"] and "NOT SUPPLIED" in reg["missing_sources"][0]["status"]
    ocr = [u for u in reg["units"] if u["kind"] == "ocr"]
    assert ocr and all(u["source"] and u["locator"].startswith("p.") for u in ocr)
    assert all(u["review_required"] for u in ocr if (u["confidence"] or 0) < 70)


def test_all_known_image_only_pages_were_ocred():
    reg = json.loads((ROOT / "knowledge/DOCUMENT_EXTRACTION.json").read_text(encoding="utf8"))
    grind = next(s for s in reg["sources"] if s["file"].startswith("The Basic"))
    for p in [22, 23, 25, 26, 27, 28, 29, 30, 31, 34, 35, 37, 40, 48, 60, 66, 68, 70, 72]:
        u = next(x for x in reg["units"] if x["source_id"] == grind["source_id"] and x["locator"] == f"p.{p}")
        assert u["kind"] == "ocr" and u["method"].startswith("tesseract")


def test_new_owner_decks_are_searchable_from_f1():
    k, t, b = _titles("SP227 dry room 18-20")[0]
    assert "Resin" in t or "เรซิ่น" in t
    assert "SD-PL-001" in b or "18-20" in b
    k2, t2, b2 = _titles("defect 128 radial crack")[0]
    assert "128" in t2 + b2
    k3, t3, b3 = _titles("11 digit 18 digit product code")[0]
    assert "11" in b3 and "18" in b3


def test_extraction_register_matches_the_source_files_in_the_repo():
    from suite.common import sha256_file
    reg = json.loads((ROOT / "knowledge/DOCUMENT_EXTRACTION.json").read_text(encoding="utf8"))
    present = [s for s in reg["sources"] if (ROOT / s["file"]).exists()]
    if not present:
        import pytest
        pytest.skip("source documents are not present next to the register")
    for s in present:
        assert sha256_file(ROOT / s["file"]) == s["sha256"], s["file"]
