"""Concurrent operators, racing duplicate retries, quantity edge cases and photo upload limits.
Synthetic data only; run against a throw-away database. Threads share one SQLite file exactly as the real server does."""
import io
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import qr_decode  # noqa: F401  (registers the HEIC reader when pillow-heif is installed)
from fastapi.testclient import TestClient
from PIL import Image

from conftest import _login, png_bytes
from test_audit_v2 import csid, one, post, wo_form


def _jpeg(size=(320, 240), color=(10, 120, 200), exif=False, quality=85):
    b = io.BytesIO()
    im = Image.new("RGB", size, color)
    if exif:
        ex = Image.Exif()
        ex[0x0112] = 6        # orientation tag
        im.save(b, "JPEG", quality=quality, exif=ex)
    else:
        im.save(b, "JPEG", quality=quality)
    return b.getvalue()


def test_many_operators_submit_at_once_without_loss_or_duplication(core):
    n_ops, per_op = 8, 6
    clients = [_login(core, "operator", "operator123") for _ in range(n_ops)]
    ids = [[csid() for _ in range(per_op)] for _ in range(n_ops)]
    start = threading.Barrier(n_ops)
    errors = []

    def work(i):
        start.wait()
        for k, sid in enumerate(ids[i]):
            r = post(clients[i], wo_form(client_submission_id=sid, verified_qty=str(i * 100 + k), location_text=f"Bay {i}-{k}"), png_bytes())
            if r.status_code != 200 or not r.json().get("ok"):
                errors.append((i, k, r.status_code, r.text[:200]))

    with ThreadPoolExecutor(n_ops) as ex:
        list(ex.map(work, range(n_ops)))
    assert not errors, errors[:3]
    for i in range(n_ops):
        for k, sid in enumerate(ids[i]):
            row = one(core, "SELECT verified_qty,physical_location FROM mobile_audits WHERE client_submission_id=?", sid)
            assert row and row["verified_qty"] == i * 100 + k and row["physical_location"] == f"Bay {i}-{k}"
    total = one(core, "SELECT COUNT(*) c FROM mobile_audits WHERE client_submission_id IN (%s)" % ",".join("?" * (n_ops * per_op)),
                *[s for row in ids for s in row])["c"]
    assert total == n_ops * per_op


def test_same_submission_sent_by_many_threads_is_stored_once(core):
    sid = csid()
    n = 10
    clients = [_login(core, "operator", "operator123") for _ in range(n)]
    start = threading.Barrier(n)
    out = []

    def go(c):
        start.wait()
        out.append(post(c, wo_form(client_submission_id=sid), png_bytes()))

    ts = [threading.Thread(target=go, args=(c,)) for c in clients]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert all(r.status_code == 200 and r.json()["ok"] for r in out), [r.text[:150] for r in out if r.status_code != 200]
    assert sum(1 for r in out if not r.json()["duplicate"]) == 1
    assert len({r.json()["audit_id"] for r in out}) == 1
    assert one(core, "SELECT COUNT(*) c FROM mobile_audits WHERE client_submission_id=?", sid)["c"] == 1
    aid = out[0].json()["audit_id"]
    assert one(core, "SELECT COUNT(*) c FROM mobile_audit_photos WHERE audit_id=?", aid)["c"] == 1


def test_same_unidentified_submission_racing_creates_one_temp_id(core):
    sid = csid()
    n = 8
    clients = [_login(core, "operator", "operator123") for _ in range(n)]
    start = threading.Barrier(n)
    out = []
    data = {"mode": "UNIDENTIFIED", "client_submission_id": sid, "verified_qty": "2", "qty_unit": "pcs", "location_text": "Yard", "description": "SYNTHETIC race part"}

    def go(c):
        start.wait()
        out.append(post(c, data, png_bytes()))

    ts = [threading.Thread(target=go, args=(c,)) for c in clients]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert all(r.status_code == 200 and r.json()["ok"] for r in out), [r.text[:150] for r in out]
    assert len({r.json()["temp_id"] for r in out}) == 1
    assert one(core, "SELECT COUNT(*) c FROM unidentified_parts WHERE client_submission_id=?", sid)["c"] == 1


def test_many_new_unidentified_parts_get_unique_temp_ids(core):
    n = 12
    clients = [_login(core, "operator", "operator123") for _ in range(n)]
    start = threading.Barrier(n)
    ids = []

    def go(c):
        start.wait()
        r = post(c, {"mode": "UNIDENTIFIED", "client_submission_id": csid(), "verified_qty": "1", "qty_unit": "pcs", "location_text": "Yard", "description": "SYNTHETIC unique"}, png_bytes())
        ids.append(r.json())

    ts = [threading.Thread(target=go, args=(c,)) for c in clients]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert all(d["ok"] for d in ids), ids
    assert len({d["temp_id"] for d in ids}) == n
    assert all(re.fullmatch(r"UNID-\d{8}-[A-Z0-9]{5}", d["temp_id"]) for d in ids)


def test_two_people_link_the_same_temp_id_only_one_wins(core, operator):
    d = post(operator, {"mode": "UNIDENTIFIED", "client_submission_id": csid(), "verified_qty": "9", "qty_unit": "pcs", "location_text": "Yard", "description": "SYNTHETIC link race"}, png_bytes()).json()
    tid = d["temp_id"]
    planners = [_login(core, "planning", "planning123") for _ in range(4)]
    start = threading.Barrier(4)
    res = []

    def go(c, wo):
        start.wait()
        res.append(c.post(f"/api/v2/unidentified/{tid}/link", json={"wo_id": wo, "reason": "SYNTHETIC race"}))

    wos = ["WO-TEST-0001", "WO-TEST-0001", "WO-TEST-0002", "WO-TEST-0002"]
    ts = [threading.Thread(target=go, args=(c, w)) for c, w in zip(planners, wos)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    linked = one(core, "SELECT resolved_wo_id AS linked_wo_id, identification_state FROM unidentified_parts WHERE temp_id=?", tid)
    assert linked["identification_state"] == "LINKED" and linked["linked_wo_id"] in ("WO-TEST-0001", "WO-TEST-0002")
    n_link = one(core, "SELECT COUNT(*) c FROM reconciliation_history WHERE temp_id=? AND action='LINKED'", tid)["c"]
    assert n_link == 1, [(r.status_code, r.text[:120]) for r in res]


@pytest.mark.parametrize("qty,ok", [("0", True), ("1", True), ("12.5", True), ("1e3", True), ("abc", False), ("", False), ("-0.0001", False),
                                    ("NaN", False), ("inf", False), ("99999999999", True), (" 7 ", True)])
def test_quantity_validation_edges(operator, core, qty, ok):
    r = post(operator, wo_form(verified_qty=qty))
    assert (r.status_code == 200) == ok, (qty, r.status_code, r.text[:200])
    if ok:
        row = one(core, "SELECT verified_qty FROM mobile_audits WHERE id=?", r.json()["audit_id"])
        assert row["verified_qty"] == float(qty.strip())
    else:
        assert "finite" in r.json()["error"] or "quantity" in r.json()["error"].lower()


def test_zero_is_a_real_count_not_unknown(operator, core):
    d = post(operator, wo_form(verified_qty="0")).json()
    row = one(core, "SELECT verified_qty,qty_unknown FROM mobile_audits WHERE id=?", d["audit_id"])
    assert row["verified_qty"] == 0 and row["qty_unknown"] == 0


def test_jpeg_with_exif_is_stored_with_thumbnail_and_hash(operator, core):
    d = post(operator, wo_form(), _jpeg(exif=True)).json()
    assert d["ok"] and d["photos"] == 1
    ph = one(core, "SELECT * FROM mobile_audit_photos WHERE audit_id=?", d["audit_id"])
    assert len(ph["sha256"]) == 64 and ph["thumb_filename"]


def test_several_photos_in_one_submission(operator, core):
    files = [("photos", (f"p{i}.jpg", _jpeg(color=(i * 40, 50, 90)), "image/jpeg")) for i in range(4)]
    r = operator.post("/api/v2/audit", data=wo_form(), files=files).json()
    assert r["ok"] and r["photos"] == 4


def test_photo_content_is_sniffed_not_trusted_from_the_extension(operator, core):
    data = wo_form()
    r = operator.post("/api/v2/audit", data=data, files=[("photos", ("renamed.jpg", b"%PDF-1.4 not a photo", "image/jpeg"))])
    assert r.status_code == 400
    assert one(core, "SELECT COUNT(*) c FROM mobile_audits WHERE client_submission_id=?", data["client_submission_id"])["c"] == 0


def test_oversize_photo_is_rejected_and_nothing_saved(operator, core, audit):
    big = _jpeg() + b"\0" * (audit.MAX_PHOTO_BYTES + 10) if hasattr(audit, "MAX_PHOTO_BYTES") else _jpeg() + b"\0" * (core.MOBILE_AUDIT_MAX_PHOTO_BYTES + 10)
    data = wo_form()
    r = operator.post("/api/v2/audit", data=data, files=[("photos", ("big.jpg", big, "image/jpeg"))])
    assert r.status_code in (400, 413)
    assert one(core, "SELECT COUNT(*) c FROM mobile_audits WHERE client_submission_id=?", data["client_submission_id"])["c"] == 0


def test_heic_photo_is_accepted_and_kept_as_original(operator, core):
    pytest.importorskip("pillow_heif")
    b = io.BytesIO()
    Image.new("RGB", (200, 150), (30, 160, 60)).save(b, "HEIF")
    d = operator.post("/api/v2/audit", data=wo_form(), files=[("photos", ("IMG_1.HEIC", b.getvalue(), "image/heic"))]).json()
    assert d["ok"] and d["photos"] == 1
    ph = one(core, "SELECT filename,thumb_filename FROM mobile_audit_photos WHERE audit_id=?", d["audit_id"])
    assert ph["filename"].lower().endswith(".heic") and ph["thumb_filename"]    # thumbnail so desktop browsers can show it


def test_submission_without_login_is_refused_and_stores_nothing(core):
    data = wo_form()
    r = TestClient(core.app).post("/api/v2/audit", data=data)
    assert r.status_code in (401, 403)
    assert one(core, "SELECT COUNT(*) c FROM mobile_audits WHERE client_submission_id=?", data["client_submission_id"])["c"] == 0
