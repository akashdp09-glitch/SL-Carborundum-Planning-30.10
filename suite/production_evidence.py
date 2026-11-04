"""Revisioned owner evidence; originals and parsed rows persist in SQLite.

No workbook is executed or modified. Production handovers, operator reports,
kiln loads and WIP snapshots remain separate quantities, never added together.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import sqlite3
from collections import Counter
from statistics import median
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter as letter

from .common import bkk_now, bkk_today

PARSER_VERSION = "production-evidence-2026-11-04-v3"
OWNER_SHORT_YEAR_MAP = {69: 2026}  # Explicit owner confirmation; not a moving current-year guess.
MONTHS = [
    ("january","มกราคม"),("february","กุมภาพันธ์"),("march","มีนาคม"),
    ("april","เมษายน"),("may","พฤษภาคม"),("june","มิถุนายน"),
    ("july","กรกฎาคม"),("august","สิงหาคม"),("september","กันยายน"),
    ("october","ตุลาคม"),("november","พฤศจิกายน"),("december","ธันวาคม")]
# Sheet, section, evidence basis, first data row, WO, qty, weight, category,
# customer, specification, machine. Positions are 1-based, explicitly bounded.
PROFILES = {
    "เตรียมจ่าย": ("Preparation", "Output", 3, 4, 10, 11, 6, 8, 9, None),
    "Report ผสม": ("Mixing", "Activity report", 2, 8, 12, 13, 7, None, 9, 4),
    "คนชั่ง": ("Weighing", "Activity report", 3, 8, 12, 14, 7, None, 9, 4),
    "ผสมจ่าย": ("Mixing", "Output", 3, 4, 7, 8, 5, None, 6, None),
    "Report ขึ้นรูป": ("Forming", "Activity report", 3, 9, 21, 23, 8, None, 10, 4),
    "ขึ้นรูปจ่าย": ("Forming", "Output", 3, 4, 10, 11, 6, 8, 9, None),
    "Report เตา": ("Firing", "Activity report", 4, 14, 25, 26, 13, None, 15, 4),
    "เตาจ่าย": ("Firing", "Output", 3, 4, 9, 10, 5, None, 8, 13),
    "รายงานเข้าเตา": ("Firing", "Kiln loaded", 2, 11, 13, None, 14, 16, 12, 4),
    "Report  คัดกรอง": ("Screening", "Activity report", 3, 8, 12, 14, 7, None, 9, 4),
    "Report เจียร": ("Grinding", "Activity report", 3, 9, 14, 16, 8, None, 10, 4),
    "คัดกรองจ่าย": ("Screening", "Output", 3, 4, 9, 10, 5, None, 8, 13),
    "เจียรจ่าย": ("Grinding", "Output", 3, 4, 9, 10, 5, None, 8, 13),
    "Report Pack": ("Packing", "Activity report", 3, 9, 14, 16, 8, None, 10, 4),
    "Pack จ่าย": ("Packing", "Output", 3, 4, 10, 12, 7, 8, 9, None),
}
PER_PIECE_COLUMN={"เตรียมจ่าย":12,"Report ผสม":14,"คนชั่ง":15,"ผสมจ่าย":9,
                  "Report ขึ้นรูป":24,"ขึ้นรูปจ่าย":12,"Report เตา":28,"เตาจ่าย":11,
                  "Report  คัดกรอง":15,"Report เจียร":17,"คัดกรองจ่าย":11,
                  "เจียรจ่าย":11,"Report Pack":17,"Pack จ่าย":11}


def number(v):
    try:
        if isinstance(v, bool) or v is None or str(v).startswith("#"):
            return None
        n = float(str(v).replace(",", ""))
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def clean(v):
    return "" if v is None or str(v).strip() in ("", "0", "None", "nan") or str(v).startswith("#") else str(v).strip()


def key(v):
    return re.sub(r"[^A-Z0-9]", "", clean(v).upper())


def serialise(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    raise TypeError(type(value).__name__)


def dump(value):
    return json.dumps(value, ensure_ascii=False, default=serialise, allow_nan=False)


def split_date(row):
    try:
        values=[float(row[i]) for i in (2,1,0)]
        if not all(math.isfinite(v) and v==int(v) for v in values):return None
        y,m,d=map(int,values)
        if y==0:return None
        y = OWNER_SHORT_YEAR_MAP.get(y,y - 543 if y > 2400 else y + 2000 if y < 100 else y)
        return date(y, m, d)
    except (TypeError, ValueError, OverflowError):
        return None


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS evidence_documents(
          id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, filename TEXT NOT NULL,
          role TEXT NOT NULL, revision INTEGER NOT NULL, imported_at TEXT NOT NULL,
          imported_by TEXT NOT NULL, original BLOB NOT NULL, config TEXT NOT NULL,
          inventory TEXT NOT NULL, parser_version TEXT NOT NULL,
          UNIQUE(role,sha256,config,parser_version));
        CREATE TABLE IF NOT EXISTS production_evidence_rows(
          source_id INTEGER NOT NULL REFERENCES evidence_documents(id),
          sheet TEXT NOT NULL, excel_row INTEGER NOT NULL, data TEXT NOT NULL,
          PRIMARY KEY(source_id,sheet,excel_row));
        CREATE TABLE IF NOT EXISTS automatic_kpi_values(
          source_id INTEGER NOT NULL REFERENCES evidence_documents(id),
          period TEXT NOT NULL, measure TEXT NOT NULL, grouping TEXT NOT NULL,
          data TEXT NOT NULL, PRIMARY KEY(source_id,period,measure,grouping));
        CREATE INDEX IF NOT EXISTS ix_evidence_role_revision ON evidence_documents(role,revision);
        CREATE TABLE IF NOT EXISTS evidence_settings(
          name TEXT PRIMARY KEY, value TEXT NOT NULL, reason TEXT NOT NULL,
          author TEXT NOT NULL, recorded_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence_setting_history(
          id INTEGER PRIMARY KEY, name TEXT, value TEXT, reason TEXT, author TEXT, recorded_at TEXT);
        CREATE TABLE IF NOT EXISTS department_kpi_snapshots(
          id INTEGER PRIMARY KEY, period TEXT NOT NULL, source_signature TEXT NOT NULL,
          calculated_at TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(period,source_signature));
    """)
    return con


def set_setting(path, name, value, reason, author):
    if name not in {"kpi_order", "report_basis", "forming_unit", "final_packing_sheet"}:
        raise ValueError("Unknown evidence setting")
    if not reason.strip() or not author.strip():
        raise ValueError("A reason and identified author are required")
    allowed = {"kpi_order": {"original", "swap"}, "report_basis": {"Activity report", "Production plan"},
               "forming_unit": {"g", "unconfirmed"}, "final_packing_sheet": {"Pack จ่าย", "Report Pack"}}
    if value not in allowed[name]:
        raise ValueError("Unsupported setting value")
    with connect(path) as con:
        args = (name, value, reason, author, bkk_now().isoformat())
        con.execute("INSERT OR REPLACE INTO evidence_settings VALUES(?,?,?,?,?)", args)
        con.execute("INSERT INTO evidence_setting_history(name,value,reason,author,recorded_at) VALUES(?,?,?,?,?)", args)


def settings(path):
    with connect(path) as con:
        return dict(con.execute("SELECT name,value FROM evidence_settings"))


def parse_production(wb, config):
    if "สถานะผลิต" not in wb.sheetnames or "Pack จ่าย" not in wb.sheetnames:
        raise ValueError("Production status format needs สถานะผลิต and Pack จ่าย")
    masters = {}
    for n, r in enumerate(wb["สถานะผลิต"].iter_rows(min_row=6, max_col=135, values_only=True), 6):
        if not clean(r[0]):
            continue
        m = dict(customer=clean(r[5]), category=clean(r[57]), product=clean(r[10]),
                 specification=clean(r[7]), D=number(r[59]), T=number(r[60]), H=number(r[61]), master_row=n)
        if not all(m[x] is not None and m[x] > 0 for x in ("D", "T", "H")):
            m.update(D=number(r[12]), T=number(r[13]), H=number(r[14]))
            m["dimension_basis"] = "Forming dimensions M:O"
        else:
            m["dimension_basis"] = "Finished dimensions BH:BJ"
        masters.setdefault(key(r[0]), []).append(m)
    result = []
    inventory = []
    # Stronger evidence than magnitude alone: same-section handover mass/pc.
    # A tight 1000x agreement supports the owner's mixed gram/kg correction.
    anchors = {}
    for title, profile in PROFILES.items():
        section,basis,start,wi,qi,weight_i,*_ = profile
        if basis != "Output" or title not in wb.sheetnames or not weight_i:
            continue
        for rn,row in enumerate(wb[title].iter_rows(min_row=start,max_col=max(wi,qi,weight_i),values_only=True),start):
            q,w=number(row[qi-1]),number(row[weight_i-1])
            if q and q>0 and w is not None and 0<w/q<=500 and clean(row[wi-1]):
                anchors.setdefault((section,key(row[wi-1])),[]).append((w/q,f"{title}!{letter(weight_i)}{rn}"))
    for ws in wb:
        inventory.append(dict(sheet=ws.title, reported_rows=ws.max_row, reported_columns=ws.max_column,
                              scope="Bounded transaction reader" if ws.title in PROFILES else "Reference / summary / QC; separate from output"))
        if ws.title not in PROFILES:
            # Keep every nonempty bounded row for inspection, never mix it with output.
            limit = 145 if ws.title in ("สถานะผลิต", "Sheet1") else 55
            for n, row in enumerate(ws.iter_rows(max_col=limit, values_only=True), 1):
                cells = {letter(i): v for i, v in enumerate(row, 1) if v is not None}
                if cells:
                    result.append(dict(sheet=ws.title, excel_row=n, basis="Reference / QC / WIP", section="Reference", raw=cells))
            continue
        section, basis, first, wi, qi, kg_i, ci, cust_i, spec_i, machine_i = PROFILES[ws.title]
        header=next(ws.iter_rows(min_row=first-1,max_row=first-1,max_col=31,values_only=True),())
        wo_header=clean(header[wi-1]).casefold() if len(header)>=wi else ""
        qty_header=clean(header[qi-1]).casefold() if len(header)>=qi else ""
        if not ("รหัส" in wo_header or wo_header in {"p/pb","productioncode","wo","work order"}):
            raise ValueError(f"{ws.title}!{letter(wi)}{first-1}: work-order header changed; mapping review required")
        canonical_qty=re.sub(r"[\s.'’\-]","",qty_header)
        if canonical_qty not in {"qty","จำนวน","จำนวนก้อน","จำนวนเข้าเตา","จำนวนของดี","รวม","รวมชิ้น","quantity"}:
            raise ValueError(f"{ws.title}!{letter(qi)}{first-1}: quantity header changed; mapping review required")
        if basis == "Activity report" and ws.title.startswith("Report"):
            basis = config.get("report_basis", "Production plan")
        seen = Counter()
        for n, row in enumerate(ws.iter_rows(min_row=first, max_col=31, values_only=True), first):
            if not any(v is not None for v in row):
                continue
            get = lambda i: row[i-1] if i else None
            wo, qty, raw_weight = clean(get(wi)), number(get(qi)), number(get(kg_i))
            day = split_date(row)
            flags = []
            if not wo: flags.append("No work-order identity: not output")
            if day is None: flags.append("Invalid or missing transaction date")
            elif day > bkk_today(): flags.append("Future transaction date: excluded from actuals")
            if number(row[2]) in OWNER_SHORT_YEAR_MAP:
                flags.append("Owner-confirmed date correction: short year 69 = Buddhist 2569 = 2026")
            if qty is None: flags.append("Unknown quantity; not zero")
            elif qty < 0: flags.append("Negative quantity / reversal needs review")
            matches = masters.get(key(wo), [])
            master = matches[0] if len(matches) == 1 else {}
            if len(matches) > 1: flags.append("Ambiguous master WO: enrichment withheld")
            category = clean(get(ci)) or master.get("category", "")
            if ws.title == "ขึ้นรูปจ่าย": category = category or clean(get(13))
            customer = clean(get(cust_i)) or master.get("customer", "")
            if not category: flags.append("Category missing")
            unit = "g" if ws.title == "Report ขึ้นรูป" and config.get("forming_unit", "g") == "g" else "kg"
            if ws.title == "Report ขึ้นรูป" and config.get("forming_unit", "g") != "g": unit = "unconfirmed"
            unit_reason="Owner-confirmed forming grams /1,000,000 to tonnes" if unit=="g" else "Source kilogram scale /1000 to tonnes"
            anchor=anchors.get((section,key(wo)),[])
            if unit=="kg" and basis=="Production plan" and qty and qty>0 and raw_weight and anchor:
                mass=median(v for v,_ in anchor)
                if mass>0 and abs((raw_weight/qty/1000)/mass-1)<=0.02:
                    unit="g"
                    reference=min(anchor,key=lambda pair:abs(pair[0]-mass))[1]
                    unit_reason="Owner mixed-unit guidance; 1000x match to same-section output median mass/pc (2% tolerance); "+reference
            normalised = raw_weight / 1000 if raw_weight is not None and unit == "g" else raw_weight if unit == "kg" else None
            # Never let a guessed magnitude conversion contaminate verified totals.
            if raw_weight is not None and unit == "kg" and qty and raw_weight / qty > 500:
                flags.append("Suspected gram/kg mismatch: weight excluded pending review")
                normalised = None
            if normalised is not None and normalised < 0:
                flags.append("Negative weight / reversal needs review")
                normalised = None
            if raw_weight is not None and unit == "unconfirmed": flags.append("Weight unit not confirmed")
            signature = dump(list(row))
            seen[signature] += 1
            if seen[signature] > 1: flags.append("Exact repeated source row: possible repeated transaction, not silently removed")
            valid = bool(wo and day and day <= bkk_today() and qty is not None and qty >= 0)
            record = dict(sheet=ws.title, excel_row=n, section=section, basis=basis,
                          date=day.isoformat() if day else None, wo=wo, wo_key=key(wo),
                          date_rule="Owner: 69 = Buddhist 2569 = 2026" if number(row[2])==69 else "Explicit Gregorian/Buddhist year; 25/26 mean 2025/2026",
                          category=category or "Unknown", customer=customer or "Unknown",
                          specification=clean(get(spec_i)) or master.get("specification", ""),
                          product=master.get("product", ""), quantity=qty,
                          weight_raw=raw_weight, weight_unit=unit, weight_kg=normalised,
                          weight_tonnes=normalised/1000 if normalised is not None else None,
                          weight_rule=unit_reason,
                          D=master.get("D"), T=master.get("T"), H=master.get("H"),
                          dimension_basis=master.get("dimension_basis", "Unknown; not inferred from SPEC"),
                          machine=clean(get(machine_i)), valid=valid, issues=flags,
                          raw={letter(i): v for i, v in enumerate(row, 1) if v is not None})
            if ws.title == "Report เจียร":
                for k, col in (("D", 19), ("T", 20), ("H", 21)):
                    v = number(get(col))
                    if v is not None: record[k] = v
                record["dimension_basis"] = "Grinding source S:U where present, otherwise master"
            result.append(record)
    return result, inventory


def parse_kpi(wb, filename, role, config):
    year = int(config.get("year", bkk_today().year))
    values = []
    def grid(ws,nr,nc):
        rows=list(ws.iter_rows(max_row=nr,max_col=nc,values_only=True))
        return rows+[(None,)*nc]*(nr-len(rows))
    def add(period, measure, group, value, ref, **extra):
        if value is not None:
            values.append(dict(period=period, measure=measure, grouping=group,
                               value=float(value), ref=ref, **extra))
    def reporting_month(ws):
        title=" ".join(str(v or "") for row in ws.iter_rows(max_row=2,max_col=4,values_only=True) for v in row)+" "+filename
        hits=[(title.casefold().find(name),i) for i,names in enumerate(MONTHS,1) for name in names if name in title.casefold()]
        if hits: return f"{year}-{min(hits)[1]:02d}"
        value=config.get("month")
        if value and re.fullmatch(r"\d{4}-\d{2}",value):
            date.fromisoformat(value+"-01");return value
        raise ValueError("Reporting month is missing; select it explicitly")
    if "DATA KPI__daily" in wb.sheetnames:
        ws = wb["DATA KPI__daily"]
        anchor = ws.cell(6, 12).value
        if not isinstance(anchor, (date, datetime)):
            raise ValueError("Staff daily evidence requires a real month anchor at L6")
        for r, measure in ((8, "accuracy"), (9, "staff_plan_preparation"), (10, "staff_wip_reporting"), (11, "staff_risk_reporting")):
            vals = [number(ws.cell(r, c).value) for c in range(12, 43)]
            available = [v for v in vals if v is not None]
            if available:
                if any(v<0 or v>1 for v in available):
                    raise ValueError(f"DATA KPI__daily row {r}: expected source ratios 0..1, not unlabelled percentage points")
                add(anchor.strftime("%Y-%m"), measure, "Planning Analyst", sum(available)/len(available)*100,
                    f"DATA KPI__daily!L{r}:AP{r}", unit="percent", method="Arithmetic mean of recorded daily ratios; blanks excluded, actual zero retained", observations=len(available))
        # Revised monthly sheets can also correct older months. Keep those
        # source percentages without manufacturing inspected-item counts.
        for monthly in wb:
            if "chosita" not in monthly.title.casefold() or "monthly" not in monthly.title.casefold():continue
            cells=grid(monthly,11,31)
            for r,measure in ((8,"accuracy"),(9,"staff_plan_preparation"),(10,"staff_wip_reporting"),(11,"staff_risk_reporting")):
                for m in range(1,13):
                    period=f"{anchor.year}-{m:02d}";v=number(cells[r-1][18+m])
                    if v is None:continue
                    if not 0<=v<=1:raise ValueError(f"{monthly.title}: staff percentage ratio outside 0..1; review source scale")
                    existing=next((e for e in values if e["period"]==period and e["measure"]==measure),None)
                    if existing:
                        existing["source_monthly_cached_percent"]=v*100
                        if abs(existing["value"]-v*100)>0.000001:
                            existing["conflict"]="Source monthly percentage differs from the daily calculation; reconcile before accepting department KPI"
                        continue
                    add(period,measure,"Planning Analyst",v*100,f"{monthly.title}!{letter(19+m)}{r}",
                        unit="percent",method="Source monthly percentage; underlying inspected counts not supplied")
    elif role=="staff_reference":
        for ws in wb:
            if "KPI-PL-" not in ws.title:continue
            cells=grid(ws,9,31)
            for r,measure in ((8,"staff_material_readiness"),(9,"staff_wo_issuance")):
                for m in range(1,13):
                    v=number(cells[r-1][18+m])
                    if v is not None and not 0<=v<=1:raise ValueError(f"{ws.title}: staff percentage ratio outside 0..1; review source scale")
                    if v is not None:add(f"{year}-{m:02d}",measure,"Planning Coordinator",v*100,
                        f"{ws.title}!{letter(19+m)}{r}",unit="percent",method="Source monthly percentage; reporting year supplied at import")
    if "Open Job" in wb.sheetnames:
        ws = wb["Open Job"]
        period=reporting_month(ws)
        cells=grid(ws,13,66)
        for block, measure in ((3, "opening_input"), (35, "opened")):
            rows = [(r, c, number(cells[r-1][c-1])) for r in range(3,13) for c in range(block,block+31)]
            nums = [v for _,_,v in rows if v is not None]
            if nums:
                add(period, measure, "Planning", sum(nums), f"Open Job!{letter(block)}3:{letter(block+30)}12", unit="source item count", method="Category row totals; does not prove distinct WO identity")
    for title,measure in (("สรุปKPIความพร้อมวัตถุดิบ","staff_material_readiness"),("สรุปKPIออกใบผลิต","staff_wo_issuance")):
        if title in wb.sheetnames:
            ws=wb[title];cells=grid(ws,5,33)
            target=sum(number(v) or 0 for v in cells[2][2:33])
            actual=sum(number(v) or 0 for v in cells[3][2:33])
            if target>0:
                add(reporting_month(ws),measure,"Planning Coordinator",actual/target*100,
                    f"{title}!C3:AG4",unit="percent",numerator=actual,denominator=target,
                    method="Ratio of source sums; zero-target days N/A")
    if "Close Job" in wb.sheetnames:
        ws = wb["Close Job"]
        period=reporting_month(ws);cells=grid(ws,13,33)
        nums = [number(cells[r-1][c-1]) for r in range(3,13) for c in range(3,34)]
        if any(v is not None for v in nums):
            add(period, "closed", "Planning", sum(v for v in nums if v is not None),
                "Close Job!C3:AG12", unit="source item count", method="Separate closure workbook; backlog identities unavailable in category totals")
    # Revised count-based production KPI matrices: explicit Plan/Actual rows,
    # B=section/category, C=measure, dates/day numbers in row 3, values D:AH.
    if role in ("production_kpi_section", "production_kpi_category"):
        for ws in wb:
            rows = list(ws.iter_rows(max_col=40, values_only=True))
            if len(rows) < 2: continue
            tidy=None
            aliases={"date":{"date","วันที่","month","เดือน"},
                     "group":{"section","แผนก","ฝ่าย","category","product category","ประเภทสินค้า","group","กลุ่ม"},
                     "plan":{"planned wos","plan wos","plan","แผน","จำนวนใบงานแผน"},
                     "actual":{"actual wos","packed wos","actual","ผลิตจริง","จำนวนใบงานจริง"}}
            for rn,row in enumerate(rows[:10]):
                mapping={name:next((i for i,v in enumerate(row) if clean(v).casefold() in names),None) for name,names in aliases.items()}
                if all(v is not None for v in mapping.values()):tidy=(rn,mapping);break
            if tidy:
                hr,cols=tidy
                for rn,row in enumerate(rows[hr+1:],hr+2):
                    source_date=row[cols["date"]]
                    if not isinstance(source_date,(date,datetime,str)):continue
                    dt=pd.to_datetime(source_date,errors="coerce",dayfirst=True)
                    if pd.isna(dt):continue
                    group=clean(row[cols["group"]])
                    if not group:continue
                    for measure in ("plan","actual"):
                        v=number(row[cols[measure]])
                        if v is None:continue
                        if v<0 or (config.get("unit","work orders")=="work orders" and v!=int(v)):
                            raise ValueError("WO counts must be nonnegative whole numbers")
                        add(dt.strftime("%Y-%m"),measure,group,v,f"{ws.title}!{letter(cols[measure]+1)}{rn}",
                            date=None if isinstance(source_date,str) and re.fullmatch(r"\d{4}-\d{2}",source_date) else dt.date().isoformat(),
                            unit=config.get("unit","work orders"),method="Revised column-format Production KPI; source counts")
                continue
            if len(rows) < 4: continue
            dates = rows[2]
            group = ""
            month = config.get("month")
            if not month or not re.fullmatch(r"\d{4}-\d{2}", str(month)):
                # Accept actual date headers; never infer a month from today's date.
                anchors = [v for v in dates if isinstance(v,(date,datetime))]
                if anchors: month = anchors[0].strftime("%Y-%m")
                else: raise ValueError("Choose the reporting month for a day-number KPI matrix")
            date.fromisoformat(month+"-01")
            daily = []
            for rn,row in enumerate(rows[3:],4):
                group = clean(row[1]) or group
                typ = clean(row[2]).lower()
                if typ not in ("แผน", "ผลิตจริง", "plan", "actual"): continue
                measure = "plan" if typ in ("แผน","plan") else "actual"
                for c in range(3,min(34,len(row))):
                    day = dates[c]; v = number(row[c])
                    if v is None: continue
                    if isinstance(day,(date,datetime)): dt = day.date() if isinstance(day,datetime) else day
                    elif number(day) is not None and 1 <= number(day) <= 31 and number(day)==int(number(day)):
                        try: dt = date(int(month[:4]),int(month[5:]),int(number(day)))
                        except ValueError: continue
                    else: continue
                    if v < 0 or (config.get("unit","work orders")=="work orders" and v!=int(v)):
                        raise ValueError("WO counts must be nonnegative whole numbers")
                    daily.append((dt,group,measure,v,f"{ws.title}!{letter(c+1)}{rn}"))
            for dt,g,m,v,ref in daily:
                add(dt.strftime("%Y-%m"),m,g,v,ref,date=dt.isoformat(),unit=config.get("unit","work orders"),method="Production KPI matrix; source-declared count")
    if not values and role != "staff_reference":
        raise ValueError("No validated KPI evidence recognised. Original retained only after a supported mapping is supplied.")
    return values


def identify(wb, requested="auto"):
    if {"Open Job","Close Job"} <= set(wb.sheetnames):
        raise ValueError("Retired combined opening/closure format: import the revised opening file and separate closure file")
    if requested != "auto": return requested
    names = set(wb.sheetnames)
    if {"สถานะผลิต", "Pack จ่าย"} <= names: return "production_status"
    if "DATA KPI__daily" in names: return "analyst_kpi"
    if "Open Job" in names: return "planning_open"
    if "Close Job" in names: return "planning_close"
    if any("KPI-PL-" in n for n in names): return "staff_reference"
    # Auto-detect the two revised production KPI families by real header/group
    # evidence. Unknown structures still require an explicit mapping choice.
    sections=("packing","mixing","forming","preparation","firing","grinding","screening","บรรจุ","แพ็ค","แพค","ผสม","ขึ้นรูป","เตรียม","เตา","เจียร","คัดกรอง")
    categories={"p","pb","m","r","s","t","o"}
    for ws in wb:
        groups=[]
        for row in ws.iter_rows(max_row=30,max_col=15,values_only=True):
            texts=[clean(v).casefold() for v in row]
            if any(v in {"planned wos","plan wos","plan","แผน"} for v in texts):
                if any(v in {"category","product category","ประเภทสินค้า"} for v in texts):return "production_kpi_category"
                if any(v in {"section","แผนก","ฝ่าย"} for v in texts):return "production_kpi_section"
            if len(texts)>2 and texts[2] in {"แผน","ผลิตจริง","plan","actual"} and texts[1]:groups.append(texts[1])
        if groups and any(any(s in g for s in sections) for g in groups):return "production_kpi_section"
        if groups and set(groups)<=categories:return "production_kpi_category"
    raise ValueError("Choose Production KPI – section or category for the revised production matrices")


def canonical_config(role,cfg):
    if role == "production_status":
        return {"forming_unit":cfg.get("forming_unit","g"),"report_basis":cfg.get("report_basis","Production plan"),"short_year_69":2026}
    if role == "analyst_kpi":
        return {}
    if role == "staff_reference":
        return {"year":int(cfg.get("year",bkk_today().year))}
    if role in ("planning_open","planning_close"):
        return {"year":int(cfg.get("year",bkk_today().year))}
    if role in ("production_kpi_section","production_kpi_category"):
        result={"unit":cfg.get("unit","work orders")}
        if cfg.get("month"):result["month"]=cfg["month"]
        return result
    return dict(cfg)


def import_workbook(path, data, filename, author, requested="auto", config=None):
    if not author.strip(): raise ValueError("Identified uploader required")
    cfg = dict(config or {})
    digest = hashlib.sha256(data).hexdigest()
    # Skip ZIP/XML/style parsing entirely for an unchanged retained original.
    # Compare the actual parsing configuration, not unrelated UI fields.
    with connect(path) as lookup:
        candidates=lookup.execute("SELECT id,revision,role,config FROM evidence_documents WHERE sha256=? AND parser_version=? ORDER BY id DESC",(digest,PARSER_VERSION)).fetchall()
    for sid,rev,known_role,encoded in candidates:
        if requested not in ("auto",known_role):continue
        if canonical_config(known_role,cfg)==json.loads(encoded):
            return dict(id=sid,revision=rev,role=known_role,status="UNCHANGED",sha256=digest)
    wb = load_workbook(io.BytesIO(data),read_only=True,data_only=True,keep_links=False)
    try:
        role = identify(wb,requested)
        cfg=canonical_config(role,cfg)
        encoded = dump(cfg)
        con = connect(path)
        try:
            prior = con.execute("SELECT id,revision FROM evidence_documents WHERE role=? AND sha256=? AND config=? AND parser_version=?",
                                (role,digest,encoded,PARSER_VERSION)).fetchone()
            if prior: return dict(id=prior[0],revision=prior[1],role=role,status="UNCHANGED",sha256=digest)
            rows, inventory, kpis = [], [], []
            if role == "production_status": rows, inventory = parse_production(wb,cfg)
            else:
                kpis = parse_kpi(wb,filename,role,cfg)
                inventory = [dict(sheet=s.title,reported_rows=s.max_row,reported_columns=s.max_column) for s in wb]
            # Matrix daily observations aggregate by month/measure/group while retaining every cell.
            grouped = {}
            for v in kpis:
                k=(v["period"],v["measure"],v["grouping"])
                if k not in grouped: grouped[k]=dict(v,cells=[dict(v)])
                else:
                    grouped[k]["value"] += v["value"]
                    grouped[k]["cells"].append(v)
            with con:
                rev=con.execute("SELECT COALESCE(MAX(revision),0)+1 FROM evidence_documents WHERE role=?",(role,)).fetchone()[0]
                cur=con.execute("INSERT INTO evidence_documents(sha256,filename,role,revision,imported_at,imported_by,original,config,inventory,parser_version) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                (digest,filename,role,rev,bkk_now().isoformat(),author,data,encoded,dump(inventory),PARSER_VERSION))
                sid=cur.lastrowid
                con.executemany("INSERT INTO production_evidence_rows VALUES(?,?,?,?)",((sid,r["sheet"],r["excel_row"],dump(r)) for r in rows))
                con.executemany("INSERT INTO automatic_kpi_values VALUES(?,?,?,?,?)",((sid,*k,dump(v)) for k,v in grouped.items()))
            return dict(id=sid,revision=rev,role=role,status="IMPORTED",sha256=digest,rows=len(rows),values=len(grouped))
        finally: con.close()
    finally: wb.close()


def source_list(path):
    with connect(path) as con:
        return pd.read_sql_query("SELECT id,sha256,filename,role,revision,imported_at,imported_by,parser_version,config,inventory FROM evidence_documents ORDER BY id DESC",con)


def production_frame(path):
    with connect(path) as con:
        row=con.execute("SELECT id FROM evidence_documents WHERE role='production_status' ORDER BY revision DESC LIMIT 1").fetchone()
        if not row: return pd.DataFrame()
        data=[]
        for raw, in con.execute("SELECT data FROM production_evidence_rows WHERE source_id=?",row):
            record=json.loads(raw)
            if str(record.get("weight_rule","")).startswith("Owner mixed-unit guidance;"):
                record.setdefault("issues",[]).append("Cross-referenced gram/kg correction: review retained rule and handover reference")
            if record.get("basis")!="Reference / QC / WIP":
                q=record.get("quantity")
                if q and q>0 and record.get("weight_raw")==0:
                    record["weight_kg"]=record["weight_tonnes"]=None
                    record.setdefault("issues",[]).append("Zero source weight with positive pieces: mass unknown, not zero")
                per_col=PER_PIECE_COLUMN.get(record.get("sheet"))
                per=number(record.get("raw",{}).get(letter(per_col))) if per_col else None
                unit=record.get("weight_unit")
                record["piece_weight_raw"]=per
                record["piece_weight_tonnes"]=(per/1_000_000 if unit=="g" else per/1000 if unit=="kg" else None) if per is not None and per>0 else None
                if q and q>0 and per and per>0 and record.get("weight_raw") is not None:
                    if abs(record["weight_raw"]/q/per-1)>0.02:
                        record.setdefault("issues",[]).append("Total / quantity differs from source per-piece mass by over 2%: review")
                if record.get("weight_kg") is None and record.get("weight_raw") not in (None,0):
                    record["piece_weight_tonnes"]=None
            # Transaction originals stay in SQL and the source BLOB. Avoid
            # duplicating 100k raw-cell dictionaries on every chart rerender.
            if record.get("basis")!="Reference / QC / WIP": record.pop("raw",None)
            data.append(record)
    df=pd.DataFrame(data)
    for name in ("date","quantity","weight_kg","weight_tonnes","valid","wo","wo_key","section"):
        if name not in df:df[name]=False if name=="valid" else None
    if "date" in df: df["date"]=pd.to_datetime(df["date"],errors="coerce")
    return df


def automatic_values(path):
    with connect(path) as con:
        rows=con.execute("""SELECT d.role,d.filename,d.revision,d.imported_at,d.sha256,v.period,v.measure,v.grouping,v.data
            FROM automatic_kpi_values v JOIN evidence_documents d ON d.id=v.source_id
            ORDER BY d.role,v.period,d.revision DESC""").fetchall()
    output=[];seen=set()
    for role,filename,rev,at,sha,period,measure,group,data in rows:
        k=(role,period,measure,group)
        if k in seen: continue
        seen.add(k)
        output.append(dict(json.loads(data),role=role,filename=filename,revision=rev,imported_at=at,sha256=sha))
    return pd.DataFrame(output)


def department_results(path, period, frame=None):
    """Owner-confirmed department order: accuracy, packing plan/actual, closure.

    Source counts are reported as evidence, never converted into invented WO IDs
    or awarded HR marks. Production snapshot ratios use Pack จ่าย only.
    """
    values = automatic_values(path)
    selected = values[values.period.eq(period)] if not values.empty else values
    rows = []
    def result(code, title, marks, percent=None, numerator=None, denominator=None, evidence="", note=""):
        rows.append(dict(Code=code, KPI=title, Maximum_marks=marks, Achievement_percent=percent,
                         Numerator=numerator, Denominator=denominator, Evidence=evidence, Note=note,
                         Awarded_HR_marks=None))
    accuracy = selected[selected.measure.eq("accuracy")] if not selected.empty else selected
    a = accuracy.iloc[0] if not accuracy.empty else None
    conflict=str(a.get("conflict", "")) if a is not None else ""
    if conflict=="nan":conflict=""
    result("KPI-PL-01", "Planning accuracy from analyst", 15,
           float(a.value) if a is not None and not conflict else None,
           evidence=f"{a.filename}; {a.ref}; SHA {a.sha256}" if a is not None else "Not recorded",
           note=conflict or (str(a.method) if a is not None else "Upload revised analyst evidence; no fabricated inspected-record counts"))
    df = frame if frame is not None else production_frame(path)
    if not df.empty and "date" in df:
        valid = df[df["valid"].eq(True)].copy()
        valid = valid[valid.date.dt.strftime("%Y-%m").eq(period)]
        plan = valid[(valid.section == "Packing") & (valid.basis == "Production plan") & (valid.sheet == "Report Pack")]
        actual = valid[(valid.section == "Packing") & (valid.sheet == "Pack จ่าย") & (valid.quantity > 0)]
        p, akeys = set(plan.loc[plan.quantity > 0,"wo_key"]), set(actual.wo_key)
        counts = (len(akeys) if not actual.empty else None,len(p) if not plan.empty else None)
        evidence = "Production status: Report Pack approved plans; Pack จ่าย final handover; distinct WOs within month"
        note = f"Matched planned/packed WOs {len(p & akeys)}; packed outside month-plan {len(akeys-p)}; planned not packed {len(p-akeys)}. Month-to-date if source coverage is incomplete. Plan row quantities can repeat across operators; WO counts deduplicated."
    else:
        counts=(None,None);evidence="Not recorded";note="Production status or revised production KPI evidence required"
    # If the two revised production KPI workbooks supply packing WO counts,
    # prefer the explicit section count; category data is supporting evidence.
    section = selected[selected.role.eq("production_kpi_section")] if not selected.empty else selected
    packing_names = {"packing","pack","บรรจุ","แพ็ค","แพค"}
    if not section.empty:
        section = section[section.grouping.map(lambda g:str(g).strip().casefold() in packing_names)]
        plans=section[section.measure.eq("plan")];actuals=section[section.measure.eq("actual")]
        if not plans.empty and not actuals.empty and set(section.unit)=={"work orders"}:
            # This role is one snapshot per group/month; do not sum it with a
            # category file or the transaction workbook (the same outputs).
            if section.grouping.nunique()==1:
                transaction_counts=counts
                counts=(float(actuals.value.sum()),float(plans.value.sum()))
                evidence="; ".join(section.filename.unique())+"; Packing rows only; retained source cell references"
                note="Reported Production KPI counts; daily WO counts may overlap periods. Transaction-based distinct WO counts shown separately; do not add sources."
                if all(v is not None for v in transaction_counts):
                    note+=f" Transaction cross-check: {transaction_counts[0]} distinct packed / {transaction_counts[1]} distinct planned WOs."
                    if counts!=transaction_counts:note+=" REVIEW: reported counts and transaction distinct counts differ; verify period and repeated WOs before acceptance."
    n,d=counts
    result("KPI-PL-02", "Actually packed WOs / planned WOs", 10,
           n/d*100 if d and n is not None else None,n,d,evidence,note)
    opened = selected[selected.measure.eq("opened")] if not selected.empty else selected
    closed = selected[selected.measure.eq("closed")] if not selected.empty else selected
    if not opened.empty and not closed.empty:
        o,c=opened.iloc[0],closed.iloc[0]
        result("KPI-PL-03", "Closed WOs / opened WOs",15,c.value/o.value*100 if o.value>0 else None,
               c.value,o.value,f"{c.filename}: {c.ref}; {o.filename}: {o.ref}",
               "Separate opening and closure files. Source category totals are labelled items; distinct WO IDs and backlog split cannot be verified from these totals. Ratio is reported-count evidence, not verified distinct-WO achievement.")
    else:
        result("KPI-PL-03", "Closed WOs / opened WOs",15,evidence="Not recorded",
               note="Upload opening and closure as two separate revised workbooks")
    with connect(path) as con:
        sources=con.execute("SELECT role,MAX(revision) FROM evidence_documents GROUP BY role ORDER BY role").fetchall()
        signature=hashlib.sha256(dump(["department-2026-11-04-packing-kpi2",sources]).encode()).hexdigest()
        con.execute("INSERT OR IGNORE INTO department_kpi_snapshots(period,source_signature,calculated_at,data) VALUES(?,?,?,?)",
                    (period,signature,bkk_now().isoformat(),dump(rows)))
    return pd.DataFrame(rows)


def department_history(path):
    with connect(path) as con:
        records=con.execute("SELECT id,period,calculated_at,data FROM department_kpi_snapshots ORDER BY id DESC").fetchall()
    rows=[]
    for sid,period,at,data in records:
        for r in json.loads(data):rows.append(dict(r,Period=period,Snapshot_id=sid,Calculated_at=at))
    return pd.DataFrame(rows)


def aggregate(frame, dimensions):
    """Counts are distinct within each bucket, never sums of daily distinct counts."""
    x=frame.copy()
    if x.empty: return pd.DataFrame()
    x["month"]=x["date"].dt.strftime("%Y-%m")
    iso=x["date"].dt.isocalendar()
    x["week"]=iso.year.astype(str)+"-W"+iso.week.astype(str).str.zfill(2)
    for c in dimensions:
        if c not in x: x[c]="Unknown"
        x[c]=x[c].fillna("Unknown")
    x["_positive_quantity_wo"]=x["wo_key"].where(x.quantity.gt(0))
    return x.groupby(dimensions,dropna=False).agg(
        source_rows=("wo","size"),distinct_WOs=("_positive_quantity_wo","nunique"),
        pieces=("quantity",lambda s:s.sum(min_count=1)),
        weight_tonnes=("weight_tonnes",lambda s:s.sum(min_count=1)),
        weight_known_rows=("weight_kg","count")).reset_index()


def reference_views(frame):
    """Translate the validated WIP/QC fields without inferring stock corrections."""
    wip=[];qc=[]
    blocks={"Mixing":("CR","CS","CT","CU","CV","CW","CX","CY"),
            "Forming":("CZ","DA","DB","DC","DD","DE","DF","DG"),
            "Firing":("DH","DI","DJ","DK","DL","DM","DN","DO"),
            "Grinding":("DP","DQ","DR","DS","DT","DU","DV","DW"),
            "Packing":("DX","DY","DZ","EA","EB","EC","ED","EE")}
    refs=frame[frame.basis.eq("Reference / QC / WIP")]
    for _,row in refs.iterrows():
        raw=row.raw
        if not isinstance(raw,dict):continue
        if row.sheet=="สถานะผลิต" and row.excel_row>=6 and clean(raw.get("A")):
            for section,cols in blocks.items():
                vals=[number(raw.get(c)) for c in cols[:7]]
                if all(v is None for v in vals):continue
                wip.append(dict(section=section,wo=clean(raw.get("A")),category=clean(raw.get("BF")) or "Unknown",
                    customer=clean(raw.get("F")) or "Unknown",incoming_pieces=vals[0],reported_or_loaded_pieces=vals[1],
                    output_pieces=vals[2],rejected_pieces=vals[3],NCR_pieces=vals[4],source_balance_pieces=vals[5],
                    source_balance_tonnes=vals[6],section_status=clean(raw.get(cols[7])),
                    needs_review=any(v is not None and v<0 for v in vals),
                    source=f"สถานะผลิต!{cols[0]}{row.excel_row}:{cols[-1]}{row.excel_row}"))
        elif row.sheet=="QC Reject" and row.excel_row>=3 and clean(raw.get("F")):
            parsed=split_date([raw.get("C"),raw.get("D"),raw.get("E")])
            dt=parsed.isoformat() if parsed else None
            qc.append(dict(date=dt,wo=clean(raw.get("F")),customer=clean(raw.get("Z")) or "Unknown",
                category=clean(raw.get("I")) or "Unknown",cause_section=clean(raw.get("N")) or "Unknown",
                detected_section=clean(raw.get("O")) or "Unknown",NCR_reference=clean(raw.get("B")),
                NCR_pieces=number(raw.get("J")),rework_pieces=number(raw.get("K")),
                accepted_pieces=number(raw.get("L")),rejected_pieces=number(raw.get("M")),
                NCR_tonnes=number(raw.get("T")),rework_tonnes=number(raw.get("U")),
                accepted_tonnes=number(raw.get("V")),rejected_tonnes=number(raw.get("W")),
                description=clean(raw.get("P")),source=f"QC Reject!A{row.excel_row}:AY{row.excel_row}"))
    return pd.DataFrame(wip),pd.DataFrame(qc)
