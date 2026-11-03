"""Owner's three-manager-KPI register, isolated from retired KPI definitions.

Additive, append-only evidence. Achievement percentages are not awarded HR marks.
Uploaded standard CSV batches are validated completely before any row is saved.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from .common import bkk_now

VERSION = "2026-11-03-owner-manager-15-10-15"
METRICS = {
    "KPI-PL-01": ("Planning accuracy / ความถูกต้องของแผน", 15,
                  "Correct plan records ÷ inspected records; use Planning Analyst evidence / ใช้หลักฐานนักวิเคราะห์"),
    "KPI-PL-02": ("Closed vs opened WOs / ใบงานปิดเทียบเปิด", 10,
                  "Closed WOs ÷ opened WOs × 100, same period; show backlog closures separately / แสดงใบงานค้างที่ปิดแยกต่างหาก"),
    "KPI-PL-03": ("Packed vs planned WOs / ใบงานแพ็คจริงเทียบแผน", 15,
                  "Actually packed WOs ÷ planned WOs × 100; same period and plan revision / ใช้ช่วงเวลาและรุ่นแผนเดียวกัน"),
}


def validate(month, code, numerator, denominator, backlog, evidence, reason):
    if code not in METRICS:
        raise ValueError("Choose one of the three manager KPIs / เลือก KPI ผู้จัดการ")
    if not re.fullmatch(r"\d{4}-\d{2}", str(month)):
        raise ValueError("Month must be YYYY-MM / เดือนต้องเป็น YYYY-MM")
    date.fromisoformat(str(month) + "-01")
    n, d, b = float(numerator), float(denominator), float(backlog)
    if not all(math.isfinite(x) for x in (n, d, b)) or n < 0 or d <= 0 or b < 0:
        raise ValueError("Use finite nonnegative counts and a positive denominator / ตัวหารต้องมากกว่า 0")
    if code == "KPI-PL-01" and n > d:
        raise ValueError("Correct records cannot exceed inspected records / จำนวนถูกต้องเกินจำนวนตรวจไม่ได้")
    if code != "KPI-PL-01" and any(x != int(x) for x in (n, d, b)):
        raise ValueError("WO counts must be whole numbers / จำนวนใบงานต้องเป็นจำนวนเต็ม")
    if b > n or (code != "KPI-PL-02" and b != 0):
        raise ValueError("Backlog closures apply to KPI 2 and cannot exceed closed WOs / ตรวจจำนวนใบงานค้างที่ปิด")
    if not str(evidence).strip() or not str(reason).strip():
        raise ValueError("Evidence and reason are required / ต้องระบุหลักฐานและเหตุผล")
    return n / d * 100


def connection(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=20)
    con.execute("PRAGMA busy_timeout=20000")
    con.execute("""CREATE TABLE IF NOT EXISTS manager_kpi_events (
        id INTEGER PRIMARY KEY, definition_version TEXT NOT NULL, month TEXT NOT NULL,
        code TEXT NOT NULL, numerator REAL NOT NULL, denominator REAL NOT NULL,
        backlog_closed REAL NOT NULL, evidence TEXT NOT NULL, reason TEXT NOT NULL,
        author TEXT NOT NULL, recorded_at TEXT NOT NULL, submission_id TEXT NOT NULL UNIQUE
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS manager_kpi_latest ON manager_kpi_events(definition_version,month,code,id)")
    con.commit()
    return con


def save(path, *, month, code, numerator, denominator, backlog=0, evidence, reason,
         author, submission_id, con=None):
    pct = validate(month, code, numerator, denominator, backlog, evidence, reason)
    if not str(submission_id).strip() or not str(author).strip():
        raise ValueError("An identified author and submission ID are required")
    owned = con is None
    db = connection(path) if owned else con
    try:
        payload = (VERSION, month, code, float(numerator), float(denominator), float(backlog),
                   str(evidence).strip(), str(reason).strip(), str(author).strip())
        old = db.execute("SELECT definition_version,month,code,numerator,denominator,backlog_closed,evidence,reason,author FROM manager_kpi_events WHERE submission_id=?", (submission_id,)).fetchone()
        if old and old != payload:
            raise ValueError("Submission ID already belongs to different evidence / รหัสส่งข้อมูลซ้ำกับข้อมูลอื่น")
        if not old:
            db.execute("INSERT INTO manager_kpi_events(definition_version,month,code,numerator,denominator,backlog_closed,evidence,reason,author,recorded_at,submission_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       payload + (bkk_now().isoformat(timespec="seconds"), submission_id))
        if owned:
            db.commit()
        return pct
    finally:
        if owned:
            db.close()


def import_csv(path, data, author):
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    if not rows or len(rows) > 10000:
        raise ValueError("CSV requires 1–10000 rows")
    required = {"month", "code", "numerator", "denominator", "backlog", "evidence", "reason"}
    for row in rows:
        if not required.issubset(row):
            raise ValueError("Use the downloadable CSV template / ใช้แม่แบบ CSV")
        validate(*(row[k] for k in ("month", "code", "numerator", "denominator", "backlog", "evidence", "reason")))
    digest = hashlib.sha256(data).hexdigest()
    db = connection(path)
    try:
        before = db.total_changes
        with db:
            for i, row in enumerate(rows):
                save(path, month=row["month"], code=row["code"], numerator=row["numerator"],
                     denominator=row["denominator"], backlog=row["backlog"], evidence=f"CSV SHA256 {digest} row {i+2}; {row['evidence']}",
                     reason=row["reason"], author=author, submission_id=f"csv:{digest}:{i}", con=db)
        return db.total_changes - before
    finally:
        db.close()


def history(path):
    db = connection(path)
    try:
        return pd.read_sql_query("SELECT * FROM manager_kpi_events WHERE definition_version=? ORDER BY id DESC", db, params=(VERSION,))
    finally:
        db.close()


def submission_id_for(state, fingerprint):
    import uuid
    previous = state.get("manager_kpi_last_submission", {})
    if previous.get("fingerprint") != fingerprint:
        previous = {"fingerprint": fingerprint, "id": uuid.uuid4().hex}
        state["manager_kpi_last_submission"] = previous
    return previous["id"]


def render(st, db_path, *, can_edit=False, user="Unknown", **_):
    st.header("🎯 Planning Manager KPI / KPI ผู้จัดการวางแผน")
    st.caption("Maximum marks / คะแนนเต็ม: 15 + 10 + 15 = 40 · HR awarded marks require the approved scoring bands / ยังไม่คำนวณคะแนน HR หากไม่มีเกณฑ์")
    period = st.text_input("Month / เดือน (YYYY-MM)", bkk_now().strftime("%Y-%m"), key="manager_kpi_month")
    hist = history(db_path)
    current = hist[hist.month.eq(period)].drop_duplicates("code") if not hist.empty else hist
    for col, (code, (title, marks, formula)) in zip(st.columns(3), METRICS.items()):
        entry = current[current.code.eq(code)] if not current.empty else current
        value = "—" if entry.empty else f"{entry.iloc[0].numerator / entry.iloc[0].denominator * 100:.2f}%"
        col.metric(title, value)
        col.caption(f"{marks} marks / คะแนน · {formula}")
    st.caption("Missing periods stay unrecorded. A closure ratio above 100% can reflect backlog reduction. / เดือนที่ไม่มีข้อมูลไม่ใช่ศูนย์ อัตราปิดเกิน 100% อาจเกิดจากการลดงานค้าง")
    if can_edit:
        code = st.selectbox("Measure / ตัวชี้วัด", list(METRICS), format_func=lambda k: METRICS[k][0], key="manager_kpi_code")
        with st.form("manager_kpi_entry", clear_on_submit=False):
            left, right = st.columns(2)
            n = left.number_input("Actual / correct / closed WOs / ตัวตั้ง", min_value=0.0, key="manager_kpi_n")
            d = right.number_input("Inspected / opened / planned WOs / ตัวหาร", min_value=0.0, key="manager_kpi_d")
            b = st.number_input("KPI 2 backlog closures / ใบงานค้างที่ปิด (KPI 2)", min_value=0.0, step=1.0, key="manager_kpi_b")
            evidence = st.text_input("Source, sheet, rows and period / หลักฐาน ชีต แถว ช่วงเวลา", key="manager_kpi_evidence")
            reason = st.text_input("Entry / correction reason / เหตุผลบันทึกหรือแก้ไข", key="manager_kpi_reason")
            submitted = st.form_submit_button("💾 Save / บันทึก", type="primary")
        if submitted:
            payload = [period, code, n, d, b, evidence, reason, user]
            fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()
            sid = submission_id_for(st.session_state, fingerprint)
            try:
                save(db_path, month=period, code=code, numerator=n, denominator=d, backlog=b,
                     evidence=evidence, reason=reason, author=user, submission_id=sid)
                st.success("Saved after database commit / บันทึกฐานข้อมูลแล้ว")
                st.rerun()
            except (ValueError, sqlite3.Error) as exc:
                st.error(str(exc))
        with st.expander("📤 Import CSV / นำเข้า CSV"):
            template = "month,code,numerator,denominator,backlog,evidence,reason\n"
            st.download_button("⬇ Blank template / แม่แบบ", template, "manager_kpi_template.csv", "text/csv")
            uploaded = st.file_uploader("Completed template / แม่แบบที่กรอกแล้ว", type=["csv"], key="manager_kpi_csv")
            if uploaded and st.button("Import / นำเข้า", key="manager_kpi_import"):
                try:
                    count = import_csv(db_path, uploaded.getvalue(), user)
                    st.success(f"Saved {count} new evidence rows / บันทึก {count} รายการใหม่")
                    st.rerun()
                except (ValueError, UnicodeError, sqlite3.Error) as exc:
                    st.error(str(exc))
    if not hist.empty:
        display = hist.copy()
        display["Achievement %"] = display.numerator / display.denominator * 100
        display["Maximum marks"] = display.code.map(lambda c: METRICS[c][1])
        with st.expander("📈 History and trend / ประวัติและแนวโน้ม"):
            latest = display.drop_duplicates(["month", "code"])
            st.line_chart(latest.pivot(index="month", columns="code", values="Achievement %"))
            st.dataframe(display, hide_index=True, use_container_width=True)
            # Escape spreadsheet formula prefixes in user-entered text before CSV export.
            export = display.map(lambda v: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v)
            st.download_button("⬇ Evidence CSV / ดาวน์โหลดหลักฐาน", export.to_csv(index=False).encode("utf-8-sig"), "manager_kpi_history.csv", "text/csv")
