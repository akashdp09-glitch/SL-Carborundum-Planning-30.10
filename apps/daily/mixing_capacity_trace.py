"""Traceable Mixing daily plan, actual mill use and capacity comparison.

Inputs follow the supplied templates: date is the worksheet tab; Mixing rows use
B=WO, E=order qty, L=machine, M=planned mill batches, N=plan pcs,
O=actual pcs, Q=product group, R=actual kg. Capacity is read from CAP ผสม.
"""
from __future__ import annotations
import re
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook


def _text(v):
    return str(v).strip() if v is not None else ""


def _num(v):
    if v is None: return None
    if isinstance(v,(int,float)): return float(v)
    s=re.sub(r"[^0-9.\-]", "", str(v))
    try: return float(s) if s else None
    except ValueError: return None


def _tab_date(value):
    m=re.fullmatch(r"\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\s*",str(value))
    if not m:return None
    d,mo,y=map(int,m.groups())
    if y<100:y+=2000 if y<70 else 1900
    if y>2400:y-=543
    try:return pd.Timestamp(year=y,month=mo,day=d).date()
    except ValueError:return None


def _machine_key(value, capacity_row=False):
    s=_text(value).upper().replace(" ","")
    # CAP M3/1 is a distinct post-mix grinding resource; daily M3.1 maps to mill family M3.
    if capacity_row and re.fullmatch(r"M\d+/\d+",s):return s
    m=re.match(r"^(M\d+)",s)
    return m.group(1) if m else s


def read_mixing_capacity(path):
    """Return source-backed active mixer capacity keyed by machine family."""
    wb=load_workbook(path,read_only=True,data_only=True)
    try:
        if "CAP ผสม" not in wb.sheetnames: raise ValueError("Capacity workbook has no CAP ผสม sheet")
        ws=wb["CAP ผสม"]
        out={}
        # Template rows: machine A, status B, job D, mill batches/day F, kg/day G.
        for row in ws.iter_rows(min_row=3,values_only=True):
            machine=_text(row[0] if len(row)>0 else "")
            status=_text(row[1] if len(row)>1 else "")
            if not machine or "ใช้" not in status or "ไม่ใช้" in status: continue
            entry={"Machine":machine,"Job":_text(row[3] if len(row)>3 else ""),
                   "Capacity batches/day":_num(row[5] if len(row)>5 else None),
                   "Capacity kg/day":_num(row[6] if len(row)>6 else None),
                   "Abrasive eligibility":_text(row[8] if len(row)>8 else "")}
            out[_machine_key(machine,capacity_row=True)]=entry
        return out
    finally: wb.close()


def build_mixing_daily(files, capacity_path):
    """Return (daily_summary, WO_detail, diagnostics) from separate Mix workbooks."""
    cap=read_mixing_capacity(capacity_path)
    detail=[]; diagnostics=[]
    for file in files or []:
        path=Path(getattr(file,"_p",file))
        if not path.is_file():
            diagnostics.append({"Source file":str(path),"Issue":"file not found"});continue
        wb=load_workbook(path,read_only=True,data_only=True)
        try:
            for ws in wb.worksheets:
                day=_tab_date(ws.title)
                if not day:continue
                # Stable template addresses; skip blank/template rows and retain exact row provenance.
                for rno,row in enumerate(ws.iter_rows(min_row=5,values_only=True),start=5):
                    if len(row)<18:continue
                    wo=_text(row[1])
                    if not re.match(r"^(?:P|PB|PBS|PM|PS)[A-Z0-9-]*\d[A-Z0-9-]*$",wo,re.I):continue
                    qty=_num(row[4]); mill_batches=_num(row[12]); planpcs=_num(row[13]); actualpcs=_num(row[14]); actualkg=_num(row[17])
                    machine=_text(row[11]); group=_text(row[16]); total_kg=_num(row[8])
                    plan_kg=(total_kg/qty*planpcs) if total_kg is not None and qty and qty>0 and planpcs is not None else None
                    key=_machine_key(machine); c=cap.get(key,{})
                    detail.append({"Date":day,"Work Order":wo,"Product group":group,"Machine":machine,
                      "Planned mill batches":mill_batches,"Plan pcs":planpcs,"Actual pcs":actualpcs,
                      "Source unit kg/pc":(total_kg/qty if total_kg is not None and qty and qty>0 else None),
                      "Plan kg (calculated)":plan_kg,"Actual kg (source)":actualkg,
                      "Capacity batches/day":c.get("Capacity batches/day"),"Capacity kg/day":c.get("Capacity kg/day"),
                      "Machine capacity source":str(Path(capacity_path).resolve())+" :: CAP ผสม :: "+c.get("Machine", "UNMAPPED"),
                      "Source file":path.name,"Source path":str(path.resolve()),"Source sheet":ws.title,"Source row":rno,
                      "Capacity machine eligibility":c.get("Abrasive eligibility","")})
        finally:wb.close()
    if not detail:return pd.DataFrame(),pd.DataFrame(),diagnostics
    d=pd.DataFrame(detail)
    daily=[]
    for day,g in d.groupby("Date",sort=True):
        assigned=g[g["Machine"].astype(str).str.strip().ne("")]
        mapped=assigned[assigned["Capacity batches/day"].notna()]
        # Capacity is counted once per assigned mill family per day, not once per WO.
        machine_caps=mapped.drop_duplicates("Machine")
        active=g[pd.to_numeric(g["Actual pcs"],errors="coerce").fillna(0)>0]
        active_mills=sorted(set(active["Machine"].astype(str).str.strip())-{""})
        planned_mills=sorted(set(g.loc[pd.to_numeric(g["Plan pcs"],errors="coerce").fillna(0)>0,"Machine"].astype(str).str.strip())-{""})
        plan_batches=pd.to_numeric(g["Planned mill batches"],errors="coerce").sum(min_count=1)
        batch_cap=pd.to_numeric(machine_caps["Capacity batches/day"],errors="coerce").sum(min_count=1)
        kg_cap=pd.to_numeric(machine_caps["Capacity kg/day"],errors="coerce").sum(min_count=1)
        plan_kg=pd.to_numeric(g["Plan kg (calculated)"],errors="coerce").sum(min_count=1)
        actual_kg=pd.to_numeric(g["Actual kg (source)"],errors="coerce").sum(min_count=1)
        plan_pcs=pd.to_numeric(g["Plan pcs"],errors="coerce").sum(min_count=1)
        actual_pcs=pd.to_numeric(g["Actual pcs"],errors="coerce").sum(min_count=1)
        available_mills=sum(1 for _machine,entry in cap.items() if entry.get("Capacity batches/day") is not None)
        daily.append({"Date":day,"Work Orders":g["Work Order"].nunique(),"Planned mill batches":plan_batches,
          "Available batch capacity on assigned mills":batch_cap,"Batch capacity utilization %":(plan_batches/batch_cap*100 if pd.notna(plan_batches) and pd.notna(batch_cap) and batch_cap else None),
          "Planned mills assigned":len(planned_mills),"Actual mills active":len(active_mills),"Available mills/day":available_mills,
          "Planned pcs":plan_pcs,"Actual pcs":actual_pcs,"Plan kg (calculated from source kg/pc)":plan_kg,
          "Actual kg (source)":actual_kg,"Available kg capacity on assigned mills":kg_cap,
          "Actual kg capacity utilization %":(actual_kg/kg_cap*100 if pd.notna(actual_kg) and pd.notna(kg_cap) and kg_cap else None),
          "Mill names planned":"; ".join(planned_mills),"Mill names actually used":"; ".join(active_mills),
          "Unmapped machine rows":int((assigned["Capacity batches/day"].isna()).sum()),
          "Source files":"; ".join(sorted(g["Source file"].unique())),"Source sheets":"; ".join(sorted(g["Source sheet"].unique()))})
    return pd.DataFrame(daily),d,diagnostics
