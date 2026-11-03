"""Real QR decoding: labels made by the application's own generator, photographed-like variants, decoded by the real
OpenCV path through the real HTTP endpoints. Nothing is stubbed (see test_decoder_is_the_real_opencv_detector).
These are synthetic images; they do NOT prove a real phone camera reads a printed label in factory light."""
import io

import cv2
import numpy as np
import pytest
from PIL import Image

import qr_decode
from qr_images import photo_like, qr_array, raw_image

PAYLOAD = "SLWO:WO-TEST-0001"


def _post(client, raw, name="scan.jpg", ctype="image/jpeg"):
    return client.post("/api/decode-qr-photo", files={"photo": (name, raw, ctype)}).json()


def test_decoder_is_the_real_opencv_detector():
    det = cv2.QRCodeDetector()
    assert type(det).__module__.startswith("cv2") and cv2.__version__.startswith("4.")
    val, _, _ = det.detectAndDecode(cv2.cvtColor(qr_array("REAL-1"), cv2.COLOR_RGB2BGR))
    assert val == "REAL-1"


def test_label_generated_by_the_app_decodes_through_the_endpoint(core, operator):
    png = core.create_qr_png("WO-TEST-0001")                      # the production label generator
    r = _post(operator, png.read_bytes(), "label.png", "image/png")
    assert r["ok"] and r["value"] == PAYLOAD and r["wo_id"] == "WO-TEST-0001"


CASES = {
    "plain": {}, "small_12pct": {"scale": 0.12}, "rot15": {"angle": 15}, "rot45": {"angle": 45}, "rot90": {"angle": 90}, "rot180": {"angle": 180},
    "perspective": {"persp": 0.1}, "blur_1.5": {"blur": 1.5}, "blur_3": {"blur": 3}, "noise": {"noise": 10}, "jpeg_q30": {"jpeg": 30},
    "low_contrast": {"contrast": 0.4}, "12MP_small_label": {"W": 4000, "H": 3000, "scale": 0.1}, "rot30_persp_blur": {"angle": 30, "persp": 0.15, "blur": 1.5},
}


@pytest.mark.parametrize("name", list(CASES))
def test_photo_like_variants_decode_to_the_right_work_order(operator, name):
    raw = photo_like(qr_array(PAYLOAD), **CASES[name])
    r = _post(operator, raw)
    assert r["ok"], (name, r)
    assert r["value"] == PAYLOAD and r["wo_id"] == "WO-TEST-0001"


def test_heavy_blur_is_rescued_by_the_fallback_passes():
    res = qr_decode.decode_qr(photo_like(qr_array(PAYLOAD), blur=5))
    assert res.status == "OK" and res.value == PAYLOAD and res.strategy != "direct"


@pytest.mark.parametrize("kw", [{"blur": 8}, {"persp": 0.3}])
def test_documented_limits_fail_safely_with_no_wrong_work_order(operator, kw):
    r = _post(operator, photo_like(qr_array(PAYLOAD), **kw))
    assert r["ok"] is False and "wo_id" not in r and "QR not detected" in r["error"]


def test_photo_without_a_qr_is_not_detected(operator):
    img = np.full((600, 800, 3), 140, np.uint8)
    cv2.putText(img, "NO QR HERE", (80, 300), cv2.FONT_HERSHEY_SIMPLEX, 2, (30, 30, 30), 4)
    r = _post(operator, raw_image(img))
    assert r["ok"] is False and "not detected" in r["error"].lower()


def test_two_different_labels_in_one_photo_are_refused_not_guessed(operator):
    img = cv2.imdecode(np.frombuffer(photo_like(qr_array(PAYLOAD), scale=0.2, pos=(0.1, 0.5)), np.uint8), 1)
    img[100:340, 1100:1340] = cv2.resize(qr_array("SLWO:WO-TEST-0002"), (240, 240))
    r = _post(operator, raw_image(img))
    assert r["ok"] is False and "More than one" in r["error"] and set(r["values"]) == {PAYLOAD, "SLWO:WO-TEST-0002"}


def test_duplicate_production_code_qr_returns_candidates(operator):
    r = _post(operator, photo_like(qr_array("SYNTH-DUP")))
    assert r["ok"] and r.get("ambiguous") and len(r["candidates"]) >= 2


def test_unknown_work_order_is_reported(operator):
    r = _post(operator, photo_like(qr_array("SLWO:DOES-NOT-EXIST")))
    assert r["ok"] and r.get("wo_id") is None and r["value"] == "SLWO:DOES-NOT-EXIST"


def test_url_style_legacy_label_still_resolves(operator):
    r = _post(operator, photo_like(qr_array("http://192.168.1.50:8000/q/WO-TEST-0001")))
    assert r["ok"] and r["wo_id"] == "WO-TEST-0001"


def test_garbage_bytes_are_unreadable(operator):
    r = _post(operator, b"this is not an image at all", "x.jpg")
    assert r["ok"] is False and "could not be read" in r["error"]


def test_scan_is_logged_with_photo_hash(core, operator):
    _post(operator, photo_like(qr_array(PAYLOAD), seed=77))
    con = core.db()
    row = con.execute("SELECT result,scan_method,photo_sha256,photo_path FROM qr_scan_log ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert (row["result"], row["scan_method"]) == ("FOUND", "PHOTO") and len(row["photo_sha256"]) == 64


def test_heic_photo_with_decoder_installed(operator):
    pytest.importorskip("pillow_heif")
    assert qr_decode.HEIF_AVAILABLE
    jpg = photo_like(qr_array(PAYLOAD))
    buf = io.BytesIO()
    Image.open(io.BytesIO(jpg)).save(buf, "HEIF")
    r = _post(operator, buf.getvalue(), "IMG_0001.HEIC", "image/heic")
    assert r["ok"] and r["wo_id"] == "WO-TEST-0001"


def test_heic_photo_without_decoder_says_so_instead_of_pretending(operator, monkeypatch):
    pytest.importorskip("pillow_heif")
    jpg = photo_like(qr_array(PAYLOAD))
    buf = io.BytesIO()
    Image.open(io.BytesIO(jpg)).save(buf, "HEIF")
    monkeypatch.setattr(qr_decode, "HEIF_AVAILABLE", False)
    r = _post(operator, buf.getvalue(), "IMG_0001.HEIC", "image/heic")
    assert r["ok"] is False and "HEIC" in r["error"] and "pillow-heif" in r["error"]


def test_record_qr_photo_endpoint_stores_the_photo(operator):
    raw = photo_like(qr_array(PAYLOAD), seed=5)
    r = operator.post("/api/record-qr-photo", files={"photo": ("a.jpg", raw, "image/jpeg")}, data={"value": PAYLOAD}).json()
    assert r["ok"] and r["wo_id"] == "WO-TEST-0001" and r["photo_path"]


def test_login_required(core):
    from fastapi.testclient import TestClient
    r = TestClient(core.app).post("/api/decode-qr-photo", files={"photo": ("a.jpg", b"x", "image/jpeg")}).json()
    assert r["ok"] is False
