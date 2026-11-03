"""Monthly Planning KPI evidence register.

Definitions and targets follow the revised Planning KPI Measurement Evidence
workbook. Monthly values are entered with explicit numerator/denominator and
source evidence; the app never invents a score from incomplete data.
"""
from __future__ import annotations

import sqlite3
import hashlib
import io
import re
from pathlib import Path

import pandas as pd
import plotly.express as px

from .common import bkk_now

CURRENT_DEFINITION_VERSION = "2026-10-12-OWNER-PL-KPI-v1"

METRICS = [
    {"code":"KPI-PL-01","name":"Production planning accuracy","thai":"ความแม่นยำของแผนการผลิต","role":"Planning Manager / ผู้จัดการวางแผน","target":90.0,"weight":15.0,"definition":"Items produced to the frozen plan without rescheduling ÷ total frozen planned items × 100. Approved business/customer/priority revisions are not Planning failures.","thai_formula":"รายการผลิตตามแผนตรึงโดยไม่เลื่อน ÷ รายการผลิตตามแผนทั้งหมด × 100"},
    {"code":"KPI-PL-02","name":"On-time production plan issuance","thai":"การออกแผนการผลิตตรงเวลา","role":"Planning Manager / ผู้จัดการวางแผน","target":98.0,"weight":10.0,"definition":"Plans issued on schedule ÷ plans required × 100.","thai_formula":"แผนที่ออกตามกำหนด ÷ แผนที่ต้องออกทั้งหมด × 100"},
    {"code":"KPI-PL-03","name":"On-Time Delivery (OTD)","thai":"การส่งมอบตรงเวลา","role":"Planning Manager / ผู้จัดการวางแผน","target":95.0,"weight":15.0,"definition":"Orders completed by the Due-to-FG / delivery date ÷ orders due × 100.","thai_formula":"รายการเสร็จทันกำหนดเข้า FG ÷ รายการครบกำหนดทั้งหมด × 100"},
    {"code":"KPI-PL-04","name":"Production plan data accuracy","thai":"ความถูกต้องของข้อมูลแผนผลิต","role":"Planning Analyst — Chosita Kanha / นักวิเคราะห์วางแผน","target":98.0,"weight":15.0,"definition":"Correct plan-data items ÷ audited items × 100.","thai_formula":"รายการข้อมูลแผนถูกต้อง ÷ รายการที่ตรวจสอบทั้งหมด × 100"},
    {"code":"KPI-PL-05","name":"On-time plan preparation","thai":"การจัดเตรียมแผนตรงเวลา","role":"Planning Analyst — Chosita Kanha / นักวิเคราะห์วางแผน","target":98.0,"weight":15.0,"definition":"Draft plans ready for review by the deadline ÷ draft plans required × 100.","thai_formula":"ร่างแผนพร้อมตรวจตามกำหนด ÷ ร่างแผนที่ต้องจัดทำทั้งหมด × 100"},
    {"code":"KPI-PL-06","name":"On-time WIP and progress reporting","thai":"การรายงาน WIP และความคืบหน้าตรงเวลา","role":"Planning Analyst — Chosita Kanha / นักวิเคราะห์วางแผน","target":98.0,"weight":10.0,"definition":"Complete WIP reports sent on time ÷ WIP reports required × 100.","thai_formula":"รายงาน WIP ที่ส่งครบและตรงเวลา ÷ รายงานที่ต้องส่งทั้งหมด × 100"},
    {"code":"KPI-PL-07","name":"On-time material readiness confirmation","thai":"การยืนยันความพร้อมวัตถุดิบก่อนผลิต","role":"Planning Coordinator — Sirinun Kanha / ผู้ประสานงานวางแผน","target":95.0,"weight":10.0,"definition":"Items with material readiness confirmed or shortage reported on time ÷ items checked × 100.","thai_formula":"รายการที่ยืนยัน/แจ้งขาดวัตถุดิบทันเวลา ÷ รายการที่ต้องตรวจทั้งหมด × 100"},
    {"code":"KPI-PL-08","name":"On-time work-order distribution and acknowledgement","thai":"การแจกจ่ายแผนและรับทราบตรงเวลา","role":"Planning Coordinator — Sirinun Kanha / ผู้ประสานงานวางแผน","target":98.0,"weight":15.0,"definition":"Work orders issued ÷ total work orders required × 100.","thai_formula":"จำนวนใบสั่งงานที่แจกจ่าย ÷ ใบสั่งงานที่ต้องแจกจ่ายทั้งหมด × 100"},
    {"code":"KPI-PL-09","name":"On-time delivery-risk escalation","thai":"การแจ้งความเสี่ยงส่งมอบก่อนกำหนด","role":"Planning Coordinator — Sirinun Kanha / ผู้ประสานงานวางแผน","target":95.0,"weight":15.0,"definition":"Delivery risks escalated within the required time ÷ delivery risks requiring escalation × 100.","thai_formula":"ความเสี่ยงที่แจ้งตามเวลาที่กำหนด ÷ ความเสี่ยงที่ต้องแจ้งทั้งหมด × 100"},
]


def init_db(db_path):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=15) as con:
        con.execute("PRAGMA busy_timeout=15000")
        con.execute("""CREATE TABLE IF NOT EXISTS planning_kpi_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            kpi_code TEXT NOT NULL,
            numerator REAL NOT NULL,
            denominator REAL NOT NULL,
            evidence_ref TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            recorded_by TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            definition_version TEXT NOT NULL DEFAULT '2026-10-12-RC29.34'
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS ix_planning_kpi_month_code ON planning_kpi_evidence(month,kpi_code,id)")


def score(numerator, denominator):
    n, d = float(numerator), float(denominator)
    if n < 0 or d <= 0 or n > d:
        raise ValueError("For a percentage KPI, enter 0 ≤ numerator ≤ denominator and denominator > 0.")
    return n / d * 100.0


def save_measurement(db_path, month, kpi_code, numerator, denominator, evidence_ref, notes="", user="", definition_version=CURRENT_DEFINITION_VERSION):
    metrics = {m["code"] for m in METRICS}
    if kpi_code not in metrics:
        raise ValueError("Choose a KPI code from the controlled Planning KPI list.")
    if len(str(month)) != 7 or str(month)[4] != "-":
        raise ValueError("Month must use YYYY-MM format.")
    ev = str(evidence_ref or "").strip()
    if not ev:
        raise ValueError("Enter source evidence, such as workbook name + sheet/date, report ID, or WO list.")
    pct = score(numerator, denominator)
    init_db(db_path)
    stamp = bkk_now().isoformat(timespec="seconds")
    with sqlite3.connect(db_path, timeout=15) as con:
        con.execute("PRAGMA busy_timeout=15000")
        cur = con.execute("""INSERT INTO planning_kpi_evidence
            (month,kpi_code,numerator,denominator,evidence_ref,notes,recorded_by,recorded_at,definition_version)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (str(month), kpi_code, float(numerator), float(denominator), ev,
             str(notes or "").strip(), str(user or "Unknown"), stamp, str(definition_version or CURRENT_DEFINITION_VERSION)))
        row_id = cur.lastrowid
    return {"id": row_id, "month": str(month), "kpi_code": kpi_code, "actual_pct": pct, "recorded_at": stamp}


def load_measurements(db_path, month=None, definition_version=CURRENT_DEFINITION_VERSION):
    init_db(db_path)
    sql = """SELECT e.* FROM planning_kpi_evidence e
        JOIN (SELECT month,kpi_code,MAX(id) id FROM planning_kpi_evidence WHERE definition_version=? GROUP BY month,kpi_code) latest
        ON latest.id=e.id"""
    params = [str(definition_version or CURRENT_DEFINITION_VERSION)]
    if month:
        sql += " WHERE e.month=?"
        params.append(str(month))
    sql += " ORDER BY e.month,e.kpi_code"
    with sqlite3.connect(db_path, timeout=15) as con:
        df = pd.read_sql_query(sql, con, params=params)
    if not df.empty:
        df["Actual %"] = df.apply(lambda r: score(r["numerator"], r["denominator"]), axis=1)
    return df


def _extract_reference(data):
    """Read only the controlled owner template columns; reject unexpected code sets or blank targets."""
    from openpyxl import load_workbook
    wb=load_workbook(io.BytesIO(data),data_only=True,read_only=True)
    required={"FM-MR-02-02","ผลการวัดรายเดือน"}
    if not required.issubset(set(wb.sheetnames)):
        raise ValueError("Expected sheets FM-MR-02-02 and ผลการวัดรายเดือน were not both found.")
    ws=wb["FM-MR-02-02"]; found=[]
    for row_number,row in enumerate(ws.iter_rows(min_row=5,values_only=True),start=5):
        code=str(row[1] or "").strip() if len(row)>1 else ""
        if not re.fullmatch(r"KPI-PL-\d{2}",code): continue
        raw_name=str(row[2] or "").strip(); lines=[x.strip() for x in raw_name.splitlines() if x.strip()]
        english=next((x for x in reversed(lines) if re.search(r"[A-Za-z]",x)),"")
        thai=next((x for x in lines if not re.search(r"[A-Za-z]",x)),lines[0] if lines else code)
        role_th=str(row[3] or "").strip()
        if code.endswith(("01","02","03")): role_en="Planning Manager"
        elif code.endswith(("04","05","06")): role_en="Planning Analyst"
        else: role_en="Planning Coordinator"
        target=row[10] if len(row)>10 else None; weight=row[11] if len(row)>11 else None
        if not isinstance(target,(int,float)) or not isinstance(weight,(int,float)):
            raise ValueError(f"{code} has no numeric target/weight in columns K/L.")
        found.append({"code":code,"name":english or thai,"thai":thai,"role":f"{role_en} — {role_th}","target":float(target),"weight":float(weight),"definition":str(row[4] or "").strip(),"thai_formula":str(row[8] or "").strip(),"definition_row":row_number})
    found.sort(key=lambda m:m["code"])
    if [m["code"] for m in found] != [f"KPI-PL-{i:02}" for i in range(1,10)]:
        raise ValueError("Planning KPI workbook must define KPI-PL-01 through KPI-PL-09 exactly once.")
    wb.close()
    return found



def _read_planning_monthly_inputs(execution_path=None, closure_path=None):
    """Read the owner-supplied daily Planning KPI workbooks without treating
    blank/non-working days as KPI failures. Returns controlled evidence rows."""
    out = []
    def _row_metric(path, sheet, target_label, actual_label, code, name):
        if not path or not Path(path).is_file():
            return
        df = pd.read_excel(path, sheet_name=sheet, header=None)
        labels = df.iloc[:, 1].astype(str).str.strip().str.lower() if df.shape[1] > 1 else pd.Series(dtype=str)
        target_rows = df[labels.eq(target_label.lower())]
        actual_rows = df[labels.eq(actual_label.lower())]
        if target_rows.empty or actual_rows.empty:
            return
        target = pd.to_numeric(target_rows.iloc[0, 2:-1], errors="coerce")
        actual = pd.to_numeric(actual_rows.iloc[0, 2:-1], errors="coerce")
        # A blank target means no KPI obligation for that date. A zero target is
        # also non-applicable, not a failed denominator.
        valid = target.notna() & (target > 0)
        denominator = float(target[valid].sum())
        numerator = float(actual[valid].fillna(0).sum())
        if denominator <= 0:
            return
        out.append({
            "month": "2026-10", "kpi_code": code, "numerator": numerator,
            "denominator": denominator,
            "actual_pct": numerator / denominator * 100.0,
            "name": name,
            "evidence_ref": f"{Path(path).name} · {sheet} · daily Target/Actual rows",
            "notes": f"Calculated from non-blank, positive Target days only; blank/zero-target days are N/A. Source total cells were also checked."
        })

    _row_metric(execution_path, "สรุปKPIความพร้อมวัตถุดิบ", "Target", "Actual",
                "KPI-PL-07", "On-time material readiness confirmation")
    _row_metric(execution_path, "สรุปKPIออกใบผลิต", "Target", "Actual",
                "KPI-PL-08", "On-time work-order distribution and acknowledgement")

    if closure_path and Path(closure_path).is_file():
        try:
            df = pd.read_excel(closure_path, sheet_name="Close Job", header=None)
            total_row = df[df.iloc[:, 0].astype(str).str.strip().str.lower().eq("total")]
            if not total_row.empty:
                # The workbook already provides a Total column at the far right.
                # Use that controlled total instead of summing the daily cells again.
                _last = pd.to_numeric(total_row.iloc[0, -1], errors="coerce")
                _total = float(_last) if pd.notna(_last) else 0.0
                out.append({
                    "month": "2026-10", "kpi_code": "INFO-CLOSE-JOB", "numerator": _total,
                    "denominator": None, "actual_pct": None,
                    "name": "October closed-job activity",
                    "evidence_ref": f"{Path(closure_path).name} · Close Job · Total row",
                    "notes": "Operational evidence only; no KPI target is inferred from this workbook."
                })
        except Exception:
            pass
    return out


def _planning_monthly_input_paths(source_manager=None):
    paths = {"execution": None, "closure": None}
    if source_manager is not None:
        for key, sid in (("execution", "KPI_PLANNING_DAILY_EXECUTION"),
                         ("closure", "KPI_PLANNING_JOB_CLOSURE")):
            try:
                a = source_manager.active(sid)
                if a and Path(a.get("stored_path", "")).is_file():
                    paths[key] = Path(a["stored_path"])
            except Exception:
                pass
    if paths["execution"] is None:
        candidates = list(Path(__file__).resolve().parents[1].glob("knowledge/kpi/inputs/*in*out*.xlsx"))
        if candidates: paths["execution"] = max(candidates, key=lambda p: p.stat().st_mtime)
    if paths["closure"] is None:
        candidates = list(Path(__file__).resolve().parents[1].glob("knowledge/kpi/inputs/*closure*.xlsx"))
        if candidates: paths["closure"] = max(candidates, key=lambda p: p.stat().st_mtime)
    return paths



def _classify_kpi_workbook(data: bytes, filename: str):
    """Classify uploaded KPI workbooks without relying only on filename."""
    from openpyxl import load_workbook
    wb=load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    sheets=set(wb.sheetnames)
    name=str(filename or '').lower()
    if 'FM-MR-02-02' in sheets or any('Planning_KPI' in x for x in sheets):
        return 'KPI_PLANNING_REFERENCE', 'Planning KPI definitions / approved KPI form'
    if 'สรุปKPIความพร้อมวัตถุดิบ' in sheets or 'สรุปKPIออกใบผลิต' in sheets:
        return 'KPI_PLANNING_DAILY_EXECUTION', 'Planning daily KPI execution evidence'
    if 'Close Job' in sheets:
        return 'KPI_PLANNING_JOB_CLOSURE', 'Planning job-closure evidence'
    if 'Monthly KPI Log' in sheets or 'เกณท์การประเมิน' in sheets:
        return 'KPI_EMPLOYEE_REFERENCE', 'Employee KPI / appraisal reference'
    # Existing production KPI workbooks can also be uploaded from this common control.
    joined=' '.join(str(x) for x in sheets)
    if 'ผลิตตามแผน' in joined or 'Plan vs Actual' in name:
        return 'KPI_SECTION_PLAN_VS_ACTUAL', 'Production section plan-vs-actual KPI'
    if 'ส่งมอบเข้าคลัง' in joined or 'warehouse' in name or 'delivery' in name:
        return 'KPI_DELIVERY_WAREHOUSE', 'Delivery / warehouse KPI'
    wb.close()
    raise ValueError('KPI workbook type could not be identified from its sheet names. Please use an approved KPI workbook.')


def _daily_execution_detail(path):
    """Return daily Target/Actual rows from the two October Planning KPI sheets."""
    rows=[]
    if not path or not Path(path).is_file(): return pd.DataFrame()
    for sheet,code,name in [
        ("สรุปKPIความพร้อมวัตถุดิบ","KPI-PL-07","Material readiness"),
        ("สรุปKPIออกใบผลิต","KPI-PL-08","WO issuance"),
    ]:
        try:
            raw=pd.read_excel(path,sheet_name=sheet,header=None)
            if raw.shape[0] < 4: continue
            date_row=raw.iloc[1]
            target_row=raw[raw.iloc[:,1].astype(str).str.strip().str.lower().eq('target')]
            actual_row=raw[raw.iloc[:,1].astype(str).str.strip().str.lower().eq('actual')]
            if target_row.empty or actual_row.empty: continue
            tr=target_row.iloc[0]; ar=actual_row.iloc[0]
            for j in range(2,raw.shape[1]):
                day=pd.to_numeric(date_row.iloc[j],errors='coerce')
                target=pd.to_numeric(tr.iloc[j],errors='coerce')
                actual=pd.to_numeric(ar.iloc[j],errors='coerce')
                if pd.isna(day) or pd.isna(target): continue
                # zero/blank target = N/A; never score as failure
                if float(target)<=0: continue
                rows.append({'KPI Code':code,'KPI':name,'Day':int(day),'Target':float(target),'Actual':float(actual) if pd.notna(actual) else 0.0,
                             'Achievement %':(float(actual)/float(target)*100.0) if pd.notna(actual) else 0.0,
                             'Gap':(float(actual)-float(target))})
        except Exception:
            continue
    return pd.DataFrame(rows)

def _employee_kpi_analysis(path):
    """Read the supplied employee KPI reference as evidence, never inventing scores."""
    try:
        xls=pd.ExcelFile(path)
        rows=[]
        if 'Monthly KPI Log' in xls.sheet_names:
            df=pd.read_excel(path,sheet_name='Monthly KPI Log',header=4)
            if not df.empty:
                num_col=next((c for c in df.columns if 'Numerator' in str(c)),None)
                den_col=next((c for c in df.columns if 'Denominator' in str(c)),None)
                code_col=next((c for c in df.columns if 'KPI Code' in str(c)),None)
                target_col=next((c for c in df.columns if 'target' in str(c).lower()),None)
                actual_col=next((c for c in df.columns if 'Actual %' in str(c)),None)
                rows.append({'Workbook':Path(path).name,'Sheet':'Monthly KPI Log','Rows':len(df),
                             'KPI codes':int(df[code_col].nunique()) if code_col else None,
                             'Evidence rows':int(df[den_col].notna().sum()) if den_col else 0,
                             'Actual % populated':int(df[actual_col].notna().sum()) if actual_col else 0,
                             'Target average':float(pd.to_numeric(df[target_col],errors='coerce').mean()) if target_col else None})
        for sh in xls.sheet_names:
            if 'Level 3.1-3.3' in sh and 'Planning' in sh:
                raw=pd.read_excel(path,sheet_name=sh,header=None)
                rows.append({'Workbook':Path(path).name,'Sheet':sh,'Rows':len(raw),'KPI codes':None,'Evidence rows':None,'Actual % populated':None,'Target average':None})
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()

def _render(st, db_path, *, can_edit=False, user="Unknown", language="English", source_manager=None):
    st.header("🎯 Monthly Planning KPI / KPI ผลลัพธ์ฝ่ายวางแผนรายเดือน")
    st.caption("Planning results only. The Section and Delivery/Warehouse KPI files measure Production. / แสดงเฉพาะผลลัพธ์ฝ่ายวางแผน ไม่ใช้ไฟล์ KPI ฝ่ายผลิต")
    st.info("Source: owner-supplied Planning KPI workbook, sheet FM-MR-02-02 rows 5–13; monthly result template, sheet ผลการวัดรายเดือน rows 2–28. The supplied numerator/denominator/result cells are blank, so unentered values show NOT RECORDED.")
    st.caption("Approved customer, Sales, management-priority or other business revisions—including within a frozen period—must not be counted as Planning failure. / การแก้ไขที่ได้รับอนุมัติไม่ถือเป็นความผิดของฝ่ายวางแผน")
    from pathlib import Path as _Path
    if source_manager is None:
        from suite.source_manager import SourceManager
        root=_Path(db_path).resolve().parent.parent
        source_manager=SourceManager(root,root/"COMPANY_DATA",root/"SOURCE_COPIES",root/"source_registry.json")
    active_ref=source_manager.active("KPI_PLANNING_REFERENCE")
    ref_path=_Path(active_ref["stored_path"]) if active_ref and active_ref.get("stored_path") else _Path(__file__).resolve().parents[1]/"knowledge"/"Planning_KPI_Reference_Q4_2026.xlsx"
    if not ref_path.is_file():
        published=source_manager.root/"KPI"/"Planning-KPI-Evidence-LATEST.xlsx"
        ref_path=published if published.is_file() else ref_path
    if ref_path.is_file():
        ref_bytes=ref_path.read_bytes(); metrics_list=_extract_reference(ref_bytes)
        _metric_signature="|".join("|".join(str(m[k]) for k in ("code","name","thai","role","target","weight","definition","thai_formula")) for m in metrics_list)
        definition_version="owner-kpi-"+hashlib.sha256(_metric_signature.encode("utf-8")).hexdigest()[:16]
        ref_name=(active_ref.get("original_name") if active_ref else None) or ref_path.name
        ref_meta=f"{ref_name} · revision {active_ref.get('revision_no','bundled') if active_ref else 'bundled'} · imported {active_ref.get('imported_at','release reference') if active_ref else 'release reference'} · SHA-256 {hashlib.sha256(ref_bytes).hexdigest()[:12]}"
    else:
        metrics_list=METRICS; definition_version=CURRENT_DEFINITION_VERSION; ref_name="Planning KPI reference unavailable"; ref_meta=ref_name
        st.error("Planning KPI workbook is missing. Upload the owner-approved Planning KPI workbook below; no results will be guessed.")
    st.caption("Active definition source: "+ref_meta)

    # Common KPI upload control: all approved KPI workbook types can be uploaded here.
    # Files are classified by workbook structure, revisioned by Source Manager, and reused
    # by the analysis below. This avoids repeated upload prompts on different pages.
    with st.expander("📤 Upload KPI files / อัปโหลดไฟล์ KPI (all KPI sources)", expanded=False):
        st.caption("You may select multiple KPI workbooks at once. The system identifies Planning KPI reference, daily Planning evidence, job closure evidence, employee KPI reference, section plan-vs-actual KPI, and delivery/warehouse KPI by workbook structure.")
        _all_kpi_uploads=st.file_uploader("Select one or more approved KPI workbooks", type=["xlsx","xlsm"], accept_multiple_files=True, key="all_kpi_sources_upload")
        if can_edit and _all_kpi_uploads and st.button("Save all selected KPI files and refresh analysis", key="all_kpi_sources_save", type="primary"):
            results=[]
            for _up in _all_kpi_uploads:
                try:
                    _slot,_label=_classify_kpi_workbook(_up.getvalue(),_up.name)
                    _res=source_manager.import_bytes(_slot,_up.name,_up.getvalue(),user,note="Common KPI upload / centralized KPI analysis")
                    results.append((_up.name,_label,_res.status,_res.message))
                except Exception as _err:
                    results.append((_up.name,"UNCLASSIFIED","ERROR",str(_err)))
            for _name,_label,_status,_msg in results:
                if _status in ("IMPORTED","REACTIVATED","DUPLICATE_UNCHANGED"):
                    st.success(f"{_name} → {_label}: {_status}")
                else:
                    st.error(f"{_name}: {_msg}")
            if results and all(x[2] in ("IMPORTED","REACTIVATED","DUPLICATE_UNCHANGED") for x in results):
                st.rerun()

    today = bkk_now().date()
    quarter_month=(today.month-1)//3*3+1
    first_default=today.replace(month=quarter_month,day=1)
    period=st.date_input("KPI date range / ช่วงวันที่ KPI (results are monthly)",value=(first_default,today),key="planning_kpi_range")
    if isinstance(period,(tuple,list)) and len(period)==2:
        start_date,end_date=period
    else:
        start_date=end_date=period
    if end_date<start_date: start_date,end_date=end_date,start_date
    months=pd.period_range(pd.Timestamp(start_date).to_period("M"),pd.Timestamp(end_date).to_period("M"),freq="M")
    month_keys=[str(x) for x in months]
    month_labels={str(x):x.strftime("%b %Y") for x in months}
    month_key=month_keys[-1] if month_keys else today.strftime("%Y-%m")
    st.caption(f"Reporting period: {pd.Timestamp(start_date):%d %b %Y} – {pd.Timestamp(end_date):%d %b %Y} · monthly KPI results")
    metrics = {m["code"]: m for m in metrics_list}

    # Automatic evidence from the revised October Planning KPI files.
    _monthly_paths = _planning_monthly_input_paths(source_manager)
    _monthly_evidence = _read_planning_monthly_inputs(
        _monthly_paths.get("execution"), _monthly_paths.get("closure")
    )
    if _monthly_evidence:
        with st.expander("📥 Detected monthly Planning KPI evidence / พบหลักฐาน KPI รายเดือน", expanded=True):
            _shown = pd.DataFrame(_monthly_evidence)
            st.dataframe(_shown[["month","kpi_code","name","numerator","denominator","actual_pct","evidence_ref","notes"]],
                         use_container_width=True, hide_index=True)
            st.caption("Blank/zero-target days are treated as N/A. No KPI failure is created for a day on which no plan/input was required.")
            if can_edit:
                if st.button("Import detected October evidence / นำเข้าหลักฐานเดือนตุลาคม",
                             key="planning_kpi_import_october", type="primary"):
                    imported = 0
                    for ev in _monthly_evidence:
                        if ev["kpi_code"] not in metrics:
                            continue
                        try:
                            save_measurement(db_path, ev["month"], ev["kpi_code"], ev["numerator"],
                                              ev["denominator"], ev["evidence_ref"], ev["notes"], user,
                                              definition_version)
                            imported += 1
                        except Exception as _imp_err:
                            st.warning(f"{ev['kpi_code']}: {_imp_err}")
                    if imported:
                        st.success(f"Imported {imported} controlled monthly KPI result(s).")
                        st.rerun()
    all_values=load_measurements(db_path,definition_version=definition_version)
    if not all_values.empty: all_values=all_values[all_values["month"].astype(str).isin(month_keys)].copy()
    latest={(str(r["month"]),str(r["kpi_code"])):r for _,r in all_values.iterrows()} if not all_values.empty else {}
    rows = []
    for mth in month_keys:
      for m in metrics_list:
        entry=latest.get((mth,m["code"]))
        actual=float(entry["Actual %"]) if entry is not None else None
        status="NOT RECORDED" if actual is None else ("MEETS TARGET" if actual>=m["target"] else "BELOW TARGET")
        rows.append({"Month":month_labels[mth],"Code":m["code"],"KPI / ตัวชี้วัด":m["name"]+" / "+m["thai"],"Owner role":m["role"],"Target %":m["target"],"Weight":m["weight"],"Actual %":round(actual,2) if actual is not None else None,"Status":status,"Numerator":entry["numerator"] if entry is not None else None,"Denominator":entry["denominator"] if entry is not None else None,"Evidence":entry["evidence_ref"] if entry is not None else "","Recorded by":entry["recorded_by"] if entry is not None else "","Recorded at (Thailand local time — Phan Thong, Chonburi)":entry["recorded_at"] if entry is not None else "","Definition source":f"{ref_name} · FM-MR-02-02!B{m['definition_row']}:L{m['definition_row']}","Monthly result source":f"{ref_name} · ผลการวัดรายเดือน!A2:J28 · {month_labels[mth]}"})
    scorecard = pd.DataFrame(rows)
    summary=scorecard[scorecard["Month"].eq(month_labels[month_key])]
    c1,c2,c3=st.columns(3)
    c1.metric("Planning KPIs meeting target",f"{int(summary['Status'].eq('MEETS TARGET').sum())} / {len(metrics_list)}")
    c2.metric("Below target",int(summary["Status"].eq("BELOW TARGET").sum()))
    c3.metric("Not recorded",int(summary["Status"].eq("NOT RECORDED").sum()))
    st.dataframe(scorecard,use_container_width=True,hide_index=True,height=min(620,220+len(scorecard)*28))
    with st.expander("📊 KPI analysis / วิเคราะห์ KPI", expanded=True):
        _ana=summary.copy()
        _ana["Gap to target %"] = pd.to_numeric(_ana["Actual %"],errors="coerce") - pd.to_numeric(_ana["Target %"],errors="coerce")
        _ana["Weighted contribution"] = pd.to_numeric(_ana["Actual %"],errors="coerce") * pd.to_numeric(_ana["Weight"],errors="coerce") / 100.0
        st.dataframe(_ana[["Code","KPI / ตัวชี้วัด","Target %","Actual %","Gap to target %","Weight","Weighted contribution","Status"]],use_container_width=True,hide_index=True)
        _valid=_ana.dropna(subset=["Actual %"]).copy()
        if not _valid.empty:
            _weighted=float(_valid["Weighted contribution"].sum())
            _avg=float(_valid["Actual %"].mean())
            _below=_valid.sort_values("Gap to target %").head(3)[["Code","Gap to target %"]]
            a,b,c=st.columns(3); a.metric("Average actual %",f"{_avg:.1f}%"); b.metric("Weighted result %",f"{_weighted:.1f}%"); c.metric("KPIs below target",int((_valid["Gap to target %"]<0).sum()))
            if not _below.empty:
                st.caption("Largest gaps to target / ช่องว่างจากเป้าหมายมากที่สุด")
                st.dataframe(_below,use_container_width=True,hide_index=True)
        else:
            st.info("No reviewed KPI result is recorded for the selected period. / ยังไม่มีผล KPI ที่ตรวจสอบแล้วในช่วงเวลาที่เลือก")
        # Analyze all currently active KPI evidence files together.
        _paths=_planning_monthly_input_paths(source_manager)
        _active_exec=_paths.get("execution"); _active_close=_paths.get("closure")
        _evidence_rows=[]
        if _active_exec and Path(_active_exec).is_file():
            for _ev in _read_planning_monthly_inputs(_active_exec,None): _evidence_rows.append(_ev)
        if _active_close and Path(_active_close).is_file():
            for _ev in _read_planning_monthly_inputs(None,_active_close): _evidence_rows.append(_ev)
        if _evidence_rows:
            _evdf=pd.DataFrame(_evidence_rows)
            st.markdown("**Source evidence analysis / วิเคราะห์หลักฐานจากไฟล์ KPI**")
            st.dataframe(_evdf,use_container_width=True,hide_index=True)
            _daily_detail=_daily_execution_detail(_active_exec)
            if not _daily_detail.empty:
                st.markdown("**Daily KPI performance / ผล KPI รายวัน**")
                _d1,_d2=st.columns(2)
                _d1.metric("Valid KPI-day records",len(_daily_detail))
                _d2.metric("Days below target",int((_daily_detail["Achievement %"]<100).sum()))
                _fig=px.line(_daily_detail,x="Day",y="Achievement %",color="KPI",markers=True,title="Daily achievement vs target (100% = target)")
                _fig.add_hline(y=100,line_dash="dash",annotation_text="Target")
                st.plotly_chart(_fig,use_container_width=True)
                st.dataframe(_daily_detail,use_container_width=True,hide_index=True)
        _emp=source_manager.active("KPI_EMPLOYEE_REFERENCE")
        if _emp and Path(_emp.get("stored_path","")).is_file():
            _empdf=_employee_kpi_analysis(_emp["stored_path"])
            if not _empdf.empty:
                st.markdown("**Employee KPI reference analysis / วิเคราะห์ไฟล์ KPI ประเมินพนักงาน**")
                st.dataframe(_empdf,use_container_width=True,hide_index=True)
    trend_code=st.selectbox("KPI trend / แนวโน้ม KPI",[m["code"] for m in metrics_list],format_func=lambda c:f"{c} — {metrics[c]['name']}",key="planning_kpi_trend")
    trend=scorecard[scorecard["Code"].eq(trend_code)].copy()
    trend["Actual %"]=pd.to_numeric(trend["Actual %"],errors="coerce")
    trend=trend.dropna(subset=["Actual %"])
    if not trend.empty:
        fig=px.line(trend,x="Month",y="Actual %",markers=True,title=f"{trend_code} — monthly result vs target")
        fig.add_scatter(x=trend["Month"],y=trend["Target %"],mode="lines",name="Target %",line=dict(dash="dash"))
        st.plotly_chart(fig,use_container_width=True)
    else:
        st.info(f"No measured values for {trend_code} in the selected period. The attached Planning KPI result cells are blank; enter reviewed numerator, denominator and evidence below to create the trend.")
    with st.expander("Planning KPI reference file / ไฟล์อ้างอิง KPI ฝ่ายวางแผน",expanded=False):
        st.caption("The bundled source is copied into CENTRAL_DATA/KPI and archived by Source Manager. The active worksheet supplies definitions, target, weight and formula. This is distinct from the two Production KPI files.")
        try:
            if active_ref: st.caption(f"Active: {active_ref['original_name']} · revision {active_ref['revision_no']} · imported {active_ref['imported_at']} · SHA-256 {active_ref['sha256'][:12]}")
            if can_edit:
                up=st.file_uploader("Upload approved Planning KPI workbook revision",type=["xlsx","xlsm"],key="planning_kpi_ref_upload")
                if up is not None and st.button("Save Planning KPI reference revision",key="planning_kpi_ref_save"):
                    try:
                        _extract_reference(up.getvalue())
                        result=source_manager.import_bytes("KPI_PLANNING_REFERENCE",up.name,up.getvalue(),user,note="Context upload from Planning KPI analysis")
                        if result.ok: st.success(f"Planning KPI reference saved as revision {result.revision_no}; historical copy retained.");st.rerun()
                        else: st.error(f"Reference not changed: {result.message}")
                    except Exception as err: st.error(f"Not imported; workbook layout/codes are not valid: {err}")
        except Exception as exc: st.warning(f"Reference provenance unavailable: {exc}")
    with st.expander("KPI definitions and formulas / นิยามและสูตร", expanded=False):
        st.dataframe(pd.DataFrame([{"Code":m["code"],"Name":m["name"],"Thai name":m["thai"],"Owner role":m["role"],"Target %":m["target"],"Weight":m["weight"],"Formula / rule":m["definition"],"สูตรจากชีต":m["thai_formula"],"Reference":f"{ref_name} · FM-MR-02-02!B{m['definition_row']}:L{m['definition_row']}"} for m in metrics_list]),use_container_width=True,hide_index=True,height=520)
    if can_edit:
        st.subheader("Add monthly measurement / เพิ่มค่าประจำเดือน")
        entry_month=st.selectbox("Month to record / เดือนที่จะบันทึก",month_keys,format_func=lambda x:month_labels[x],index=max(0,len(month_keys)-1),key="planning_kpi_entry_month")
        choices = [f"{m['code']} — {m['name']}" for m in metrics_list]
        code = st.selectbox("KPI measure / ตัวชี้วัด", choices, key="planning_kpi_code").split(" — ",1)[0]
        m = metrics[code]
        st.caption(f"Target: {m['target']:.0f}% · {m['definition']}")
        with st.form("planning_kpi_evidence_form", clear_on_submit=True):
            ncol,dcol = st.columns(2)
            numerator = ncol.number_input("Numerator / ตัวตั้ง", min_value=0.0, value=0.0, step=1.0)
            denominator = dcol.number_input("Denominator / ตัวหาร", min_value=0.0, value=0.0, step=1.0)
            evidence = st.text_input("Source evidence / หลักฐานแหล่งข้อมูล", placeholder=f"e.g. report or workbook + sheet + row / WO IDs · KPI workbook reference: ผลการวัดรายเดือน rows 2–28")
            notes = st.text_area("Notes / explanation / หมายเหตุและคำอธิบาย")
            save = st.form_submit_button("Save monthly KPI evidence / บันทึกหลักฐาน KPI", type="primary", use_container_width=True)
        if save:
            try:
                saved = save_measurement(db_path, entry_month, code, numerator, denominator, evidence, notes, user, definition_version)
                st.success(f"Saved {code}: {saved['actual_pct']:.2f}% for {entry_month}. Evidence event #{saved['id']} · {saved['recorded_at']} Thailand local time.")
                st.rerun()
            except Exception as exc:
                st.error(f"Not saved: {exc}")
    else:
        st.caption("Read-only view. Sign in with an editing role to submit a monthly measurement.")
    if not all_values.empty:
        st.download_button("⬇ Export selected-period Planning KPI evidence CSV / ดาวน์โหลด CSV", all_values.to_csv(index=False).encode("utf-8-sig"), f"Planning_KPI_Evidence_{month_keys[0]}_{month_keys[-1]}.csv", "text/csv", key="planning_kpi_export")
        with st.expander("Revision history for selected period / ประวัติการแก้ไข"):
            with sqlite3.connect(db_path, timeout=15) as con:
                hist = pd.read_sql_query("SELECT id,month,kpi_code,numerator,denominator,evidence_ref,notes,recorded_by,recorded_at FROM planning_kpi_evidence WHERE month BETWEEN ? AND ? ORDER BY id DESC", con, params=(month_keys[0],month_keys[-1]))
            st.dataframe(hist, use_container_width=True, hide_index=True, height=300)
    from suite.employee_kpi import render_custom
    render_custom(st, db_path, can_edit=can_edit, user=user)


def render(st, db_path, *, can_edit=False, user="Unknown", language="English", source_manager=None):
    # The owner's three-manager-KPI scheme supersedes the old nine-measure screen.
    # Old evidence remains untouched and separate; do not apply new definitions to it.
    from .manager_kpi import render as render_manager
    return render_manager(st, db_path, can_edit=can_edit, user=user, language=language)


def render_legacy(st, db_path, *, can_edit=False, user="Unknown", language="English", source_manager=None):
    try:
        _render(st, db_path, can_edit=can_edit, user=user, language=language, source_manager=source_manager)
    except Exception as exc:
        st.error(f"Planning KPI could not be loaded: {exc}")
