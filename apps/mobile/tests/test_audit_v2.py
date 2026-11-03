import re
import sqlite3
import uuid

import pytest

PNG_NAME = ("part.png", None, "image/png")


def csid():
    return "t-" + uuid.uuid4().hex[:16]


def wo_form(**kw):
    d = {"mode": "WO", "wo_id": "WO-TEST-0001", "client_submission_id": csid(), "status": "OK", "verified_qty": "12", "qty_unit": "pcs",
         "location_text": "Test bay 1"}
    d.update(kw)
    return {k: v for k, v in d.items() if v is not None}


def post(client, data, png=None):
    files = [("photos", ("part.png", png, "image/png"))] if png else None
    return client.post("/api/v2/audit", data=data, files=files)


def one(core, sql, *a):
    con = core.db()
    try:
        return con.execute(sql, a).fetchone()
    finally:
        con.close()


def test_wo_audit_saved_with_bangkok_times(operator, core, png):
    r = post(operator, wo_form(client_time="2026-10-04T08:00:00+07:00"), png())
    d = r.json()
    assert r.status_code == 200 and d["ok"] and not d["duplicate"] and d["photos"] == 1
    row = one(core, "SELECT * FROM mobile_audits WHERE id=?", d["audit_id"])
    assert row["verified_qty"] == 12 and row["qty_unit"] == "pcs" and row["qty_unknown"] == 0
    assert row["client_time"] == "2026-10-04T08:00:00+07:00"
    assert row["server_received_at"] == row["created_at"]
    expected_date = core.bkk_now().strftime("%Y-%m-%d")
    assert row["server_received_at"].startswith(expected_date)
    photo = one(core, "SELECT * FROM mobile_audit_photos WHERE audit_id=?", d["audit_id"])
    assert photo["sha256"] and photo["thumb_filename"]
    assert re.match(r"WO-TEST-0001_Test-bay-1_\d{8}-\d{6}", photo["filename"])


def test_retry_with_same_id_is_idempotent(operator, core, png):
    data = wo_form()
    first = post(operator, data, png()).json()
    again = post(operator, data, png()).json()
    assert first["ok"] and again["ok"] and again["duplicate"] is True
    assert again["audit_id"] == first["audit_id"]
    n = one(core, "SELECT COUNT(*) c FROM mobile_audits WHERE client_submission_id=?", data["client_submission_id"])["c"]
    assert n == 1
    nphotos = one(core, "SELECT COUNT(*) c FROM mobile_audit_photos WHERE audit_id=?", first["audit_id"])["c"]
    assert nphotos == 1


def test_unknown_quantity_is_null_not_zero(operator, core):
    d = post(operator, wo_form(verified_qty=None, qty_unknown="1", qty_unit=None)).json()
    assert d["ok"]
    row = one(core, "SELECT verified_qty,qty_unknown FROM mobile_audits WHERE id=?", d["audit_id"])
    assert row["verified_qty"] is None and row["qty_unknown"] == 1


@pytest.mark.parametrize("patch,fragment", [
    ({"verified_qty": None, "qty_unit": None}, "quantity"),
    ({"verified_qty": "-3"}, "negative"),
    ({"verified_qty": "5", "qty_unknown": "1"}, "both"),
    ({"qty_unit": None}, "unit"),
    ({"location_text": None}, "location"),
    ({"status": "BOGUS"}, "status"),
    ({"client_submission_id": "x"}, "client_submission_id"),
])
def test_validation_rejects_bad_input_and_saves_nothing(operator, core, patch, fragment):
    data = wo_form(**patch)
    before = one(core, "SELECT COUNT(*) c FROM mobile_audits")["c"]
    r = post(operator, data)
    assert r.status_code == 400 and fragment.lower() in r.json()["error"].lower()
    assert one(core, "SELECT COUNT(*) c FROM mobile_audits")["c"] == before


def test_unknown_work_order_rejected(operator):
    r = post(operator, wo_form(wo_id="NOPE-123"))
    assert r.status_code == 404 and r.json()["code"] == "WO_NOT_FOUND"


def test_several_observations_for_same_wo(operator, core):
    for loc in ("Bay A", "Bay B"):
        assert post(operator, wo_form(location_text=loc)).json()["ok"]
    n = one(core, "SELECT COUNT(*) c FROM mobile_audits WHERE wo_id='WO-TEST-0001' AND physical_location IN ('Bay A','Bay B')")["c"]
    assert n == 2


def test_audit_does_not_touch_production_events(operator, core):
    before = one(core, "SELECT COUNT(*) c FROM events")["c"]
    assert post(operator, wo_form()).json()["ok"]
    assert one(core, "SELECT COUNT(*) c FROM events")["c"] == before


def test_bad_photo_rejected_and_nothing_saved(operator, core):
    data = wo_form()
    r = operator.post("/api/v2/audit", data=data, files=[("photos", ("evil.png", b"not an image", "image/png"))])
    assert r.status_code == 400
    assert one(core, "SELECT COUNT(*) c FROM mobile_audits WHERE client_submission_id=?", data["client_submission_id"])["c"] == 0


def test_unidentified_requires_photo_and_description(operator, png):
    base = {"mode": "UNIDENTIFIED", "client_submission_id": csid(), "verified_qty": "3", "qty_unit": "pcs", "location_unknown": "1", "description": "grey ring"}
    assert post(operator, base).status_code == 400
    assert post(operator, {**base, "client_submission_id": csid(), "description": "", "markings": ""}, png()).status_code == 400


def test_unidentified_part_created_with_temp_id_and_history(operator, core, png):
    d = post(operator, {"mode": "UNIDENTIFIED", "client_submission_id": csid(), "qty_unknown": "1", "location_unknown": "1",
                        "markings": "SYNTHETIC marking 123"}, png()).json()
    assert d["ok"] and re.fullmatch(r"UNID-\d{8}-[A-Z0-9]{5}", d["temp_id"])
    row = one(core, "SELECT * FROM unidentified_parts WHERE temp_id=?", d["temp_id"])
    assert row["qty"] is None and row["qty_unknown"] == 1 and row["identification_state"] == "UNIDENTIFIED"
    assert row["location_source"] == "UNKNOWN" and row["process_name"] == "UNKNOWN"
    assert one(core, "SELECT COUNT(*) c FROM reconciliation_history WHERE temp_id=? AND action='CREATED'", d["temp_id"])["c"] == 1
    assert one(core, "SELECT COUNT(*) c FROM unidentified_photos WHERE temp_id=?", d["temp_id"])["c"] == 1
    assert operator.get(f"/qr/tracking/{d['temp_id']}").content[:4] == b"\x89PNG"


def _make_unid(client, png, **extra):
    d = post(client, {"mode": "UNIDENTIFIED", "client_submission_id": csid(), "verified_qty": "7", "qty_unit": "pcs", "location_text": "Yard",
                      "description": "SYNTHETIC unlabeled part", **extra}, png()).json()
    assert d["ok"], d
    return d["temp_id"]


def test_link_unlink_and_no_double_count(operator, planning, core, png):
    tid = _make_unid(operator, png)
    r = operator.post(f"/api/v2/unidentified/{tid}/link", json={"wo_id": "WO-TEST-0001", "reason": "Matches drawing", "counts_toward_wo": False})
    assert r.json()["ok"]
    row = one(core, "SELECT * FROM unidentified_parts WHERE temp_id=?", tid)
    assert row["identification_state"] == "LINKED" and row["resolved_wo_id"] == "WO-TEST-0001" and row["counts_toward_wo"] == 0
    # linking again to a different WO is refused; the same link is a harmless duplicate
    assert planning.post(f"/api/v2/unidentified/{tid}/link", json={"wo_id": "WO-TEST-0002", "reason": "oops"}).status_code == 409
    assert planning.post(f"/api/v2/unidentified/{tid}/link", json={"wo_id": "WO-TEST-0001", "reason": "again"}).json()["duplicate"] is True
    assert planning.post(f"/api/v2/unidentified/{tid}/unlink", json={"reason": "Wrong match"}).json()["ok"]
    assert one(core, "SELECT identification_state s FROM unidentified_parts WHERE temp_id=?", tid)["s"] == "UNIDENTIFIED"
    con = core.db()
    actions = [r["action"] for r in con.execute("SELECT action FROM reconciliation_history WHERE temp_id=? ORDER BY id", (tid,))]
    con.close()
    assert actions == ["CREATED", "LINKED", "UNLINKED"]


def test_link_requires_reason(planning, operator, png):
    tid = _make_unid(operator, png)
    assert planning.post(f"/api/v2/unidentified/{tid}/link", json={"wo_id": "WO-TEST-0001", "reason": ""}).status_code == 400


def test_every_role_can_record_but_submitted_audit_is_immutable(core, viewer, management, operator, png):
    """Every signed-in role can track; submitted observations require a new correction record."""
    cap = {r for r in core.ROLES if core.can({"role": r}, "mobile_capture")}
    assert cap == set(core.ROLES)
    r = post(viewer, wo_form(), png())
    assert r.status_code == 200 and r.json()["ok"]
    assert post(management, wo_form(), png()).status_code == 200
    edit = operator.post("/api/v2/edit", json={"kind": "WO_AUDIT", "audit_id": r.json()["audit_id"], "reason": "typo", "fields": {"verified_qty": 20}})
    assert edit.status_code == 409 and edit.json()["code"] == "IMMUTABLE"
    row = one(core, "SELECT verified_qty FROM mobile_audits WHERE id=?", r.json()["audit_id"])
    assert row["verified_qty"] == 12


def test_photo_file_name_carries_work_order_location_and_date(operator, core, png):
    d = post(operator, wo_form(location_text="Rack B / Bin 3"), png()).json()
    ph = one(core, "SELECT filename FROM mobile_audit_photos WHERE audit_id=?", d["audit_id"])
    assert re.match(r"WO-TEST-0001_Rack-B-Bin-3_\d{8}-\d{6}\.(png|jpg)", ph["filename"])


def test_login_required(core):
    from fastapi.testclient import TestClient
    c = TestClient(core.app, follow_redirects=False)
    assert c.post("/api/v2/audit", data=wo_form()).status_code == 401
    assert c.get("/mobile/scan").status_code in (302, 303)


def test_ambiguous_code_returns_all_candidates(operator):
    d = operator.get("/api/v2/resolve", params={"value": "SYNTH-DUP"}).json()
    assert d["ambiguous"] is True and {c["wo_id"] for c in d["candidates"]} == {"WO-TEST-0002", "WO-TEST-0003"}


def test_search_accepts_any_wo_format(operator, core):
    con = core.db()
    con.execute("INSERT OR IGNORE INTO work_orders(wo_id,production_code,product_code,customer_name,qty,status,imported_at) VALUES(?,?,?,?,?,?,?)",
                ("P005-110826", "P005-110826", "SYNTH-PART-P", "SYNTHETIC CUSTOMER", 12, "RELEASED", "2026-10-04 08:00:00"))
    con.commit(); con.close()
    for q in ("p005110826", "P005-110826", "P005 110826", "slwo:p005-110826"):
        rows = operator.get("/api/v2/search", params={"q": q}).json()["rows"]
        assert any(r["wo_id"] == "P005-110826" for r in rows), q
    hit = operator.get("/api/v2/resolve", params={"value": "p005110826"}).json()
    assert hit["ok"] and hit["candidates"][0]["wo_id"] == "P005-110826"


def test_resolve_identity_payloads(operator, png):
    assert [c["wo_id"] for c in operator.get("/api/v2/resolve", params={"value": "SLWO:WO-TEST-0001"}).json()["candidates"]] == ["WO-TEST-0001"]
    tid = _make_unid(operator, png)
    c = operator.get("/api/v2/resolve", params={"value": f"SLTMP:{tid}"}).json()["candidates"]
    assert len(c) == 1 and c[0]["kind"] == "TEMP"
    miss = operator.get("/api/v2/resolve", params={"value": "NOTHING-LIKE-THIS"}).json()
    assert miss["ok"] is False and miss["candidates"] == []


def test_production_scan_payload_does_not_expose_customer_name(operator):
    rows=operator.get("/api/v2/resolve",params={"value":"SLWO:WO-TEST-0001"}).json()["candidates"]
    assert rows and all("customer" not in row for row in rows)


def test_register_filters_pagination_and_exports(operator, admin):
    for i in range(3):
        assert post(operator, wo_form(wo_id="WO-TEST-0003", status="HOLD", location_text=f"Register bay {i}")).json()["ok"]
    d = admin.get("/api/register", params={"wo_id": "WO-TEST-0003", "limit": 2}).json()
    assert d["total"] >= 1 and len(d["rows"]) <= 2 and d["limit"] == 2
    d2 = admin.get("/api/register", params={"q": "SYNTHETIC", "limit": 200}).json()
    assert d2["total"] >= 1
    csv = admin.get("/register/export.csv")
    assert csv.status_code == 200 and csv.content.startswith(b"\xef\xbb\xbftracking_id")
    xl = admin.get("/register/export.xlsx")
    assert xl.status_code == 200 and xl.content[:2] == b"PK"


def test_register_pages_render(operator, admin):
    for p in ["/mobile", "/mobile/scan", "/mobile/find?q=SYNTH", "/mobile/confirm/WO-TEST-0001", "/mobile/audit/WO-TEST-0001",
              "/mobile/unidentified", "/mobile/submissions", "/mobile/part/WO-TEST-0001", "/mobile/wo/WO-TEST-0001", "/mobile/report"]:
        r = operator.get(p)
        assert r.status_code == 200, p
    for p in ["/register", "/register/WO-TEST-0001", "/admin/locations", "/labels/print?id=WO-TEST-0001", "/qr-generator"]:
        assert admin.get(p).status_code == 200, p
    ca = operator.get("/tls/ca.crt")
    assert ca.status_code == 200 and b"BEGIN CERTIFICATE" in ca.content


def test_mobile_confirm_does_not_auto_pick_among_several(operator):
    r = operator.get("/mobile/find?q=SYNTH-DUP")
    assert r.status_code == 200 and "WO-TEST-0002" in r.text and "WO-TEST-0003" in r.text and "Nothing is selected for you" in r.text


def test_migration_is_idempotent(audit):
    assert audit.migrate()["applied"] is False


def test_migration_on_a_database_created_by_the_original_code(tmp_path):
    """Create a database with the ORIGINAL (pre-change) app from git, add legacy rows, then start the new code on it."""
    import os, subprocess, sys, textwrap
    from pathlib import Path
    repo = Path(__file__).resolve().parents[3]
    old = tmp_path / "old"
    old.mkdir()
    rev = subprocess.run(["git", "log", "--format=%H", "-1", "--", "apps/mobile/app.py"], cwd=repo, capture_output=True, text=True).stdout.strip()
    # last commit that touched app.py before the audit_v2 work started: the first one that does not mention audit_v2
    for h in subprocess.run(["git", "log", "--format=%H", "--", "apps/mobile/app.py"], cwd=repo, capture_output=True, text=True).stdout.split():
        src = subprocess.run(["git", "show", f"{h}:apps/mobile/app.py"], cwd=repo, capture_output=True, text=True).stdout
        if "audit_v2" not in src:
            rev = h
            break
    else:
        pytest.skip("original app.py not found in git history")
    tar = subprocess.run(["git", "archive", rev, "apps/mobile"], cwd=repo, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(old)], input=tar, check=True)
    root = tmp_path / "shared"
    (root / "DATABASE").mkdir(parents=True)
    env = {**os.environ}
    for k, sub in {"SL_SHARED_ROOT": "", "SL_COMPANY_DATA": "COMPANY_DATA", "SL_DB_PATH": "DATABASE/sl_planning.db", "SL_PHOTO_ROOT": "PHOTOS",
                   "SL_SOURCE_COPY_ROOT": "SOURCE_COPIES", "SL_REPORT_ROOT": "REPORTS"}.items():
        env[k] = str(root / sub) if sub else str(root)
    legacy = textwrap.dedent("""
        import app
        con = app.db()
        con.execute("INSERT INTO work_orders(wo_id,qty,imported_at,status) VALUES('LEGACY-1',10,'2026-01-01 08:00:00','RELEASED')")
        con.execute("INSERT INTO mobile_audits(wo_id,user_name,verified_qty,physical_status,physical_location,created_at) VALUES('LEGACY-1','legacy',5,'OK','Old rack','2026-01-01 09:00:00')")
        con.execute("INSERT INTO unidentified_parts(temp_id,qty,process_name,location,issue_type,notes,reporter,created_at) VALUES('UNID-LEGACY',NULL,'','Yard','OTHER','n','legacy','2026-01-01 09:00:00')")
        con.commit(); print('LEGACY-OK')
    """)
    p = subprocess.run([sys.executable, "-c", legacy], env=env, capture_output=True, text=True, cwd=old / "apps/mobile")
    assert "LEGACY-OK" in p.stdout, p.stdout + p.stderr
    new_code = textwrap.dedent("""
        import os, sqlite3, app
        con = app.db()
        row = con.execute("SELECT verified_qty,qty_unknown,physical_location FROM mobile_audits WHERE wo_id='LEGACY-1'").fetchone()
        u = con.execute("SELECT qty,identification_state FROM unidentified_parts WHERE temp_id='UNID-LEGACY'").fetchone()
        backups = os.listdir(os.environ['SL_SHARED_ROOT'] + '/BACKUPS')
        b = sqlite3.connect(os.environ['SL_SHARED_ROOT'] + '/BACKUPS/' + backups[0])
        had_old_cols = 'client_submission_id' in [r[1] for r in b.execute('PRAGMA table_info(mobile_audits)')]
        print('NEW-OK', row['verified_qty'], row['qty_unknown'], row['physical_location'], u['qty'], u['identification_state'], len(backups), had_old_cols,
              b.execute("SELECT COUNT(*) FROM mobile_audits").fetchone()[0])
    """)
    p = subprocess.run([sys.executable, "-c", new_code], env=env, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])
    assert "NEW-OK 5.0 0 Old rack None UNIDENTIFIED 1 False 1" in p.stdout, p.stdout + p.stderr


def test_location_admin_requires_admin_and_validates(operator, admin):
    assert operator.get("/admin/locations").status_code in (302, 303, 403)
    r = admin.post("/admin/locations", data={"building": "TEST-B1", "section": "Grinding", "position": "Rack 1"})
    assert r.status_code == 303
    locs = admin.get("/api/v2/locations").json()
    assert any(l["building"] == "TEST-B1" for l in locs["locations"])


def test_gps_honesty(operator, core):
    d = post(operator, wo_form(gps_status="CAPTURED", gps_lat="999", gps_lon="100")).json()
    row = one(core, "SELECT gps_status,gps_lat FROM mobile_audits WHERE id=?", d["audit_id"])
    assert row["gps_status"] == "UNAVAILABLE" and row["gps_lat"] is None
    d = post(operator, wo_form(gps_status="DENIED")).json()
    assert one(core, "SELECT gps_status FROM mobile_audits WHERE id=?", d["audit_id"])["gps_status"] == "DENIED"
