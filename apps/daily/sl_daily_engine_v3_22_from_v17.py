from pathlib import Path
# -*- coding: utf-8 -*-
"""
SL Carborundum Daily Production Planner V3.22 SELF-DEPENDENT MAPPED ENGINE
Validation-first production planning.

Core philosophy:
- Verified Firing Planner is the pull anchor.
- Plan 2026 is the order/process-status authority.
- Department capacity workbook is the controlled capacity evidence.
- A plan row must show WHY it is feasible.
"""

import math, re
from io import BytesIO
from datetime import date, datetime, timedelta
import pandas as pd

class _DummyST:
    @staticmethod
    def cache_data(*args, **kwargs):
        def deco(fn): return fn
        return deco
st = _DummyST()

# page config is controlled by the parent PPC Control Center

SECTIONS = ["Preparation","Mixing","Forming","Firing","Grinding / Cutting","Packing"]
SHIFT_START="08:00"
SHIFT_END="17:00"
LUNCH="12:00-13:00"
BREAK_1="10:00-10:10"
BREAK_2="15:00-15:10"
NORMAL_NET_HOURS=8.0-(20.0/60.0)  # 9h attendance - 1h lunch - 20m breaks = 7h40m
PROCESS_COLS = {
    "Preparation": ("CW","CX","CY"),
    "Mixing": ("DF","DG","DH"),
    "Forming": ("DP","DQ","DR"),
    "Firing": ("DZ","EA","EC"),
    "Grinding / Cutting": ("EJ","EK","EL"),
    "Packing": ("ES","ET","EU"),
}

MIN_PLAN_DATE = date(2026,1,1)
MAX_PLAN_DATE = date(2035,12,31)

# Furniture dimensions supplied in the controlled firing files.
PLATE_MASTER = [
    {"Plate":"360x410x10","L":360.0,"W":410.0,"T":10.0,"Qty":376},
    {"Plate":"400x400x20","L":400.0,"W":400.0,"T":20.0,"Qty":97},
    {"Plate":"420x370x15","L":420.0,"W":370.0,"T":15.0,"Qty":252},
    {"Plate":"400x500x20","L":400.0,"W":500.0,"T":20.0,"Qty":1070},
    {"Plate":"510x510x20","L":510.0,"W":510.0,"T":20.0,"Qty":41},
    {"Plate":"650x530x20","L":650.0,"W":530.0,"T":20.0,"Qty":164},
]


I_BLOCK_MASTER = [
    {"Leg in":2.0,"Height mm":50.8,"Qty":412},
    {"Leg in":2.5,"Height mm":63.5,"Qty":575},
    {"Leg in":3.0,"Height mm":76.2,"Qty":597},
    {"Leg in":3.5,"Height mm":88.9,"Qty":33},
    {"Leg in":4.0,"Height mm":101.6,"Qty":480},
    {"Leg in":4.5,"Height mm":114.3,"Qty":1242},
    {"Leg in":5.0,"Height mm":127.0,"Qty":292},
    {"Leg in":5.5,"Height mm":139.7,"Qty":1100},
    {"Leg in":6.0,"Height mm":152.4,"Qty":800},
    {"Leg in":7.0,"Height mm":177.8,"Qty":208},
    {"Leg in":8.0,"Height mm":203.2,"Qty":191},
]

# Conservative operational clearances for visual feasibility verification.
PRODUCT_GAP_MM = 10.0
PLATE_GAP_MM = 20.0
CLEARANCE_ABOVE_PART_MM = 15.0

# Kiln dimensions based on the controlled planning dimensions supplied earlier.
def kiln_dimensions(kiln):
    k=txt(kiln).upper().replace(" ","")
    if k in {"T0","KILN0","0"}:
        return 1000.0,900.0,700.0
    if k in {"T14","KILN14","14"}:
        return 2900.0,1500.0,1500.0
    if k.startswith("R"):
        return 2200.0,1200.0,1200.0
    # T1-T12 / Kiln 1-12
    return 2150.0,1650.0,1600.0

def txt(v):
    if v is None or pd.isna(v): return ""
    return str(v).strip()

def num(v, default=0.0):
    try:
        x=float(v)
        if math.isnan(x) or math.isinf(x): return default
        return x
    except Exception:
        m=re.findall(r"-?\d+(?:\.\d+)?",txt(v))
        return float(m[0]) if m else default

def pdate(v):
    if v is None or (isinstance(v,float) and math.isnan(v)) or v=="":
        return None
    if isinstance(v,pd.Timestamp): d=v.date()
    elif isinstance(v,datetime): d=v.date()
    elif isinstance(v,date): d=v
    elif isinstance(v,(int,float)):
        x=float(v)
        if x<20000: return None
        try: d=(datetime(1899,12,30)+timedelta(days=x)).date()
        except Exception: return None
    else:
        z=pd.to_datetime(v,errors="coerce")
        if pd.isna(z): return None
        d=z.date()
    return d if 2020 <= d.year <= 2100 else None

def workday(d):
    return d is not None and d.weekday()!=6

def add_workdays(d,n):
    if d is None: return None
    cur=d
    if n==0: return cur
    step=1 if n>0 else -1
    left=abs(int(n))
    while left:
        cur+=timedelta(days=step)
        if workday(cur): left-=1
    return cur

def excel_col_num(col):
    n=0
    for c in col.upper():
        n=n*26+(ord(c)-64)
    return n

def priority_default(due,fire,today):
    anchor=due or fire
    if not anchor: return "MEDIUM"
    delta=(anchor-today).days
    if delta<0: return "OVERDUE"
    if delta<=3: return "HIGH"
    if delta<=10: return "MEDIUM"
    return "LOW"

def priority_rank(x):
    return {"OVERDUE":0,"HIGH":1,"MEDIUM":2,"LOW":3}.get(txt(x).upper(),2)

# ---------------------------------------------------------------------
# FIRING PLANNER
# ---------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def read_firing(upload):
    """Read legacy and F12R+ Firing Planner output by normalized bilingual headers."""
    import re
    def _n(v): return re.sub(r'[^0-9A-Za-zก-๙]+','',txt(v)).lower()
    xls=pd.ExcelFile(upload)
    preferred=['Released Operator Print','Operator Print','Firing Detail','WO DETAIL','Auto Firing Plan','Released Firing Plan']
    sheets=[s for s in preferred if s in xls.sheet_names] + [s for s in xls.sheet_names if s not in preferred]
    aliases={
      'wo':['Work Order','Work Order / ใบสั่งผลิต','WO','WorkOrder','เลขที่ใบสั่งผลิต'],
      'qty':['Planned Firing Qty','Planned Qty (pcs) / จำนวนแผน (ชิ้น)','Firing Qty','Qty pcs','Plan Qty','Planned Qty'],
      'date':['Load Date','Loading Date / วันที่เข้าเตา','Firing Date','Firing Start Date','วันที่เข้าเผา','วันที่เผา'],
      'finish':['Program Finish Date','Firing Finish Date / วันที่เผาเสร็จ','Firing Complete','Unload / Take-Out Date','Firing Finish Date','Finish Date','วันที่ออกเตา'],
      'kgpc':['kg/pc','kg/pc / กก./ชิ้น','Weight kg/pc','Gross kg/pc','น้ำหนัก/ก้อน']}
    an={k:{_n(x) for x in v} for k,v in aliases.items()}
    def pick(cols,k): return next((c for c in cols if _n(c) in an[k]),None)
    diagnostics=[]
    for sheet in sheets:
      for hdr in (0,1):
        try: df=pd.read_excel(upload,sheet_name=sheet,header=hdr)
        except Exception as e: diagnostics.append(f'{sheet}[{hdr}]: {e}'); continue
        if df is None or df.empty: continue
        df.columns=[txt(c).strip() for c in df.columns]
        wc,qc,dc,fc=pick(df.columns,'wo'),pick(df.columns,'qty'),pick(df.columns,'date'),pick(df.columns,'finish')
        if not all([wc,qc,dc,fc]): diagnostics.append(f'{sheet}[{hdr}]: missing WO/Qty/Load/Finish'); continue
        out=df.copy(); out['Work Order']=df[wc].fillna('').astype(str).str.strip(); out['Firing Qty']=pd.to_numeric(df[qc],errors='coerce').fillna(0)
        out['Firing Date']=df[dc].apply(pdate); out['Firing Complete']=df[fc].apply(pdate)
        kc=pick(df.columns,'kgpc'); out['kg/pc']=pd.to_numeric(df[kc],errors='coerce').fillna(0) if kc else 0.0
        out=out[(out['Work Order']!='') & (out['Firing Qty']>0) & out['Firing Date'].notna() & out['Firing Complete'].notna()].copy()
        if out.empty: continue
        out['Firing Source']=f'{sheet} - bilingual header mapped'
        agg={'Firing Qty':'sum','Firing Date':'min','Firing Complete':'max','kg/pc':'first','Firing Source':'first'}
        optional={'Kiln':['Kiln','Kiln / เตา'],'Program':['Program','Program / โปรแกรม'],'Due Date':['Due Date','Due Date / วันกำหนดส่ง'],'Test Work':['Test Work','Test Work / งานทดสอบ'],'Product Code':['Product Code','Product Code / รหัสสินค้า'],'Customer':['Customer','Customer / ลูกค้า'],'Category':['Category','Product Category / ประเภทผลิตภัณฑ์']}
        for target,names in optional.items():
          c=next((cc for cc in df.columns if _n(cc) in {_n(n) for n in names}),None)
          if c is not None:
            out[target]=df.loc[out.index,c]; agg[target]='first'
        return out.groupby('Work Order',as_index=False).agg(agg)
    raise ValueError('Firing file could not be mapped. F12R bilingual Operator Print is supported. ' + ' | '.join(diagnostics[:8]))


@st.cache_data(show_spinner=False)
def read_fixed_optimization_inputs(upload):
    xls=pd.ExcelFile(upload)
    if "Fixed Optimization Inputs" not in xls.sheet_names:
        return pd.DataFrame()
    x=pd.read_excel(upload,sheet_name="Fixed Optimization Inputs")
    if "Load Date" in x.columns:x["Load Date"]=x["Load Date"].apply(pdate)
    return x


# ---------------------------------------------------------------------
# PLAN 2026
# ---------------------------------------------------------------------
def status_closed(v):
    t=txt(v).strip().lower()
    return t in {"ปิดใบสั่ง","closed","close","done","finished","complete","completed"}

@st.cache_data(show_spinner=False)
def read_plan2026(upload, source_map=None):
    """
    V3.22 SELF-DEPENDENT ENGINE:
    Read the authoritative Plan 2026 planning sheet using a configurable
    source mapping. This keeps the Daily Planner usable if a sheet name or
    column location changes in future.

    source_map keys may include:
      sheet, data_start_row,
      WO, Due Date, Customer, Specification, Order Qty, Product Code,
      Product Type, D, T, H, Category, Shape, Weight g/pc, WO Closure,
      Plan2026 Firing Date,
      and "<Section> Plan/Actual/Status" for each process.
    """
    import openpyxl
    from openpyxl.utils import column_index_from_string

    if hasattr(upload,"seek"): upload.seek(0)
    wb=openpyxl.load_workbook(upload,data_only=True,read_only=True,keep_links=False)

    defaults = {
        "sheet":"แผนการเผา", "data_start_row":4,
        'WO':'A',
        'WO Date':'B',
        'Warehouse Target':'C',
        'ORDER':'D',
        'Due Date':'E',
        'Customer':'F',
        'Specification':'H',
        'Order Qty':'J',
        'Product Code':'K',
        'Product Type':'L',
        'D':'M',
        'T':'N',
        'H':'O',
        'Program':'BB',
        'Category':'BF',
        'Shape':'BW',
        'Cut Factor':'CP',
        'Preparation Plan':'CW',
        'Preparation Actual':'CX',
        'Preparation Status':'CY',
        'Mixing Plan':'DF',
        'Mixing Actual':'DG',
        'Mixing Status':'DH',
        'Forming Plan':'DP',
        'Forming Actual':'DQ',
        'Forming Status':'DR',
        'Firing Plan':'DZ',
        'Firing Actual':'EA',
        'Plan2026 Firing Date':'EB',
        'Firing Status':'EC',
        'Firing Exit Date':'DX',
        'Firing Issue':'DY',
        'Grinding / Cutting Plan':'EJ',
        'Grinding / Cutting Actual':'EK',
        'Grinding / Cutting Status':'EL',
        'Packing Plan':'ES',
        'Packing Actual':'ET',
        'Packing Status':'EU',
        'Actual Warehouse Date':'EV',
        'WO Closure':'FC',
        'NCR':'FF',
        'APPROVE':'FG',
        'REJECT':'FH',
        'Sales Delivery Date':'IB',
        'Weight g/pc':'AH',
    }
    mp = defaults.copy()
    if source_map:
        for k,v in source_map.items():
            if v not in (None,""):
                mp[k]=v

    sheet = mp.get("sheet","แผนการเผา")
    if sheet not in wb.sheetnames:
        wb.close()
        raise ValueError(f"Plan 2026 sheet `{sheet}` not found.")

    ws=wb[sheet]
    keys=[k for k,v in mp.items() if k not in {"sheet","data_start_row"} and isinstance(v,str) and v.strip()]
    idx={k:column_index_from_string(mp[k].strip().upper())-1 for k in keys}
    max_needed=max(idx.values())+1

    def getv(vals,key):
        if key not in idx:
            return None
        i=idx[key]
        return vals[i] if i<len(vals) else None

    rows=[]
    start_row=int(mp.get("data_start_row",4) or 4)
    for excel_row,vals in enumerate(ws.iter_rows(min_row=start_row,max_col=max_needed,values_only=True),start=start_row):
        wo=txt(getv(vals,"WO"))
        if not wo:
            continue

        row={
            "Excel Sequence":excel_row,
            "Work Order":wo,
            "Delivery Date":pdate(getv(vals,"Due Date")),
            "Customer":txt(getv(vals,"Customer")),
            "Specification":txt(getv(vals,"Specification")),
            "Order Qty":num(getv(vals,"Order Qty"),0),
            "Product Code":txt(getv(vals,"Product Code")),
            "Real Spec":txt(getv(vals,"Product Type")),
            "D":num(getv(vals,"D"),0),
            "T":num(getv(vals,"T"),0),
            "H":num(getv(vals,"H"),0),
            "Type":txt(getv(vals,"Category")),
            "Shape":txt(getv(vals,"Shape")),"Cut Factor":num(getv(vals,"Cut Factor"),1),
            "Plan2026 kg/pc":num(getv(vals,"Weight g/pc"),0)/1000.0,
            "Overall WO Status": ("CLOSED" if (status_closed(getv(vals,"WO Closure")) or status_closed(getv(vals,"Packing Status"))) else txt(getv(vals,"WO Closure"))),
            "Overall Closed": (status_closed(getv(vals,"WO Closure")) or status_closed(getv(vals,"Packing Status"))),
            "Plan2026 Firing Date":pdate(getv(vals,"Plan2026 Firing Date")),
            "Planning Remark":"",
        }

        for sec in PROCESS_COLS:
            planq=num(getv(vals,f"{sec} Plan"),0)
            actualq=num(getv(vals,f"{sec} Actual"),0)
            status=txt(getv(vals,f"{sec} Status"))
            closed=status_closed(status)
            diff=max(planq-actualq,0)
            row[f"{sec} Plan Qty"]=planq
            row[f"{sec} Actual Qty"]=actualq
            row[f"{sec} Status"]=status
            row[f"{sec} Remaining Qty"]=0 if closed else diff
            row[f"{sec} Accepted Short Qty"]=diff if closed else 0

        if row.get("Overall Closed", False):
            for _sec in PROCESS_COLS:
                row[f"{_sec} Remaining Qty"] = 0
        rows.append(row)

    wb.close()
    df=pd.DataFrame(rows)
    if df.empty:
        return df,pd.DataFrame(),pd.DataFrame()

    actual_rows=[]
    for _,r in df.iterrows():
        for sec in PROCESS_COLS:
            q=num(r.get(f"{sec} Actual Qty",0),0)
            if q>0:
                actual_rows.append({
                    "Section / กระบวนการ":sec,
                    "Work Order":r["Work Order"],
                    "Actual Qty":q,
                    "Actual Source":"Mapped Plan 2026 process Actual column"
                })
    actual=pd.DataFrame(actual_rows)

    order_events=pd.DataFrame({
        "Work Order":df["Work Order"],
        "Current Status":[
            "CLOSED" if bool(x) else "OPEN"
            for x in df["Overall Closed"]
        ]
    })

    return df.sort_values("Excel Sequence").reset_index(drop=True),actual,order_events

# ---------------------------------------------------------------------
# CAPACITY MASTER
# ---------------------------------------------------------------------
def parse_range(v):
    z=[float(x) for x in re.findall(r"\d+(?:\.\d+)?",txt(v))]
    return (z[0],z[1]) if len(z)>=2 else ((z[0],z[0]) if z else (0,0))

@st.cache_data(show_spinner=False)
def read_capacity(upload):
    """
    Read the controlled capacity workbook in detail. Core scheduling tables come
    from CAP ผสม, CAP ขึ้นรูป, Cap เตา, Cap เจีย and Cap บรรจุ. The parser also
    uses Set Up Time/Grinding manpower and the production manpower summary, while
    Lead Time is controlled by lead_time_control_v1.py from the same workbook.
    """
    if upload is None:
        return (pd.DataFrame(),)*6

    import openpyxl
    if hasattr(upload,"seek"): upload.seek(0)
    wb=openpyxl.load_workbook(upload,data_only=True,read_only=False)

    # ---------------- MIXING ----------------
    mix=[]
    if "CAP ผสม" in wb.sheetnames:
        ws=wb["CAP ผสม"]
        current=None; attrs={}
        for rr in range(3,ws.max_row+1):
            machine=txt(ws.cell(rr,1).value)
            status=txt(ws.cell(rr,2).value)
            man=num(ws.cell(rr,3).value,0)
            job=txt(ws.cell(rr,4).value)
            cap_mo=num(ws.cell(rr,6).value,0)
            machinekg=num(ws.cell(rr,7).value,0)
            rtxt=txt(ws.cell(rr,8).value)
            abrasive=txt(ws.cell(rr,9).value)

            if machine.upper().startswith("M"):
                current=machine
                attrs={"Status":status,"Man":man,"CAP-โม่":cap_mo,
                       "Machine kg":machinekg,"Range":rtxt,"Abrasive":abrasive}
            elif not machine and job and current:
                machine=current

            if not machine or not job:
                continue

            a=attrs.copy()
            if status:a["Status"]=status
            if ws.cell(rr,3).value is not None:a["Man"]=man
            if ws.cell(rr,6).value is not None:a["CAP-โม่"]=cap_mo
            if ws.cell(rr,7).value is not None:a["Machine kg"]=machinekg
            if rtxt:a["Range"]=rtxt
            if abrasive:a["Abrasive"]=abrasive
            mn,mx=parse_range(a.get("Range",""))
            if mx<=0:mx=a.get("Machine kg",0)

            mix.append({"Machine":machine,"Status":a.get("Status",""),"Man":a.get("Man",0),
                        "Job":job,"CAP-โม่":a.get("CAP-โม่",0),
                        "Machine kg":a.get("Machine kg",0),"Min batch kg":mn,
                        "Max batch kg":mx,"Abrasive":a.get("Abrasive","")})

    # ---------------- FORMING ----------------
    form=[]
    if "CAP ขึ้นรูป" in wb.sheetnames:
        ws=wb["CAP ขึ้นรูป"]
        headers={txt(ws.cell(4,c).value):c for c in range(1,ws.max_column+1)}
        for rr in range(5,ws.max_row+1):
            spec=txt(ws.cell(rr,headers.get("Spec & Size",2)).value)
            if not spec:continue
            phr=num(ws.cell(rr,headers.get("Cap./ Hr.",5)).value,0)
            normal=num(ws.cell(rr,headers.get("8 Hr. (08.00-17.00)",6)).value,0)
            ot3=num(ws.cell(rr,headers.get("3 Hr. (17.30-20.30)",7)).value,0)
            if normal<=0 and phr>0:normal=phr*NORMAL_NET_HOURS
            form.append({"Spec Pattern":spec,
                         "Type":txt(ws.cell(rr,headers.get("Group",3)).value),
                         "Machine":txt(ws.cell(rr,headers.get("M/C.",4)).value),
                         "pcs/hour":phr,"Normal pcs/8h":normal,"OT pcs/3h":ot3})

    # ---------------- FIRING / KILN CAPABILITY + PROGRAM CAPACITY ----------------
    # IMPORTANT workbook structure:
    # A:D = kiln capability table (Kiln, number, compatible programs, note)
    # F:H = program capacity / running-day table.
    kiln=[]
    kiln_capability=[]
    if "Cap เตา" in wb.sheetnames:
        ws=wb["Cap เตา"]
        for rr in range(2,ws.max_row+1):
            kind=txt(ws.cell(rr,1).value); kn=txt(ws.cell(rr,2).value)
            programs=txt(ws.cell(rr,3).value); note=txt(ws.cell(rr,4).value)
            if kn:
                kiln_capability.append({'Kiln Type':kind,'Kiln':kn,'Compatible Programs':programs,'Kiln Note':note})
        capmap={x['Kiln']:x for x in kiln_capability}
        for rr in range(2,ws.max_row+1):
            prog=txt(ws.cell(rr,6).value)
            cap=txt(ws.cell(rr,7).value)
            days=num(ws.cell(rr,8).value,0)
            if not prog: continue
            nums=[float(x) for x in re.findall(r"\d+(?:\.\d+)?",cap)]
            if len(nums)>=2: minkg,maxkg=nums[0]*1000,nums[1]*1000
            elif len(nums)==1: minkg=maxkg=nums[0]*1000
            else: minkg=maxkg=0
            pn=prog.upper().replace(' ','')
            if 'P3(T14)' in pn:
                eligible='T14'
            elif pn.startswith('KM-') or pn.startswith('BK-'):
                eligible='R4, R5, R6'
            else:
                eligible=', '.join(x['Kiln'] for x in kiln_capability if x['Kiln'].upper().startswith('T') and x['Kiln'].upper()!='T14' and prog.split()[0].replace('(T14)','') in x['Compatible Programs'])
            kiln.append({'Program':prog,'Min kg/load':minkg,'Max kg/load':maxkg,'Running Days':days,'Eligible Kilns':eligible,'Capacity Source':'Cap เตา F:H'})

    # ---------------- GRINDING / CUTTING ----------------
    # Each operation column contains the actual machine/resource name, followed
    # by its CAP/day column. A WO may require several machines sequentially.
    grind=[]
    grind_setup={}
    current_people={}
    # Machine setup + operator requirement. Rows marked ชำรุด are unavailable.
    if "Set Up Time, จำนวน พนักงาน เจีย" in wb.sheetnames:
        sws=wb["Set Up Time, จำนวน พนักงาน เจีย"]
        for rr in range(2,sws.max_row+1):
            mc=txt(sws.cell(rr,2).value)
            if not mc: continue
            setup=num(sws.cell(rr,3).value,0)
            pv=txt(sws.cell(rr,4).value)
            broken=('ชำรุด' in pv)
            workers=0 if broken else int(num(pv,0))
            grind_setup[mc.upper()]={'Setup Time hr':setup,'Required Workers':workers,'Machine Status':'BROKEN' if broken else 'AVAILABLE'}
    if "กำลังคนแผนกผลิต" in wb.sheetnames:
        mws=wb["กำลังคนแผนกผลิต"]
        for rr in range(4,mws.max_row+1):
            sec=txt(mws.cell(rr,1).value)
            if not sec or sec=='รวม': continue
            current_people[sec]={'Plan People':int(num(mws.cell(rr,2).value,0)),'Current People':int(num(mws.cell(rr,3).value,0)),'People Gap':int(num(mws.cell(rr,4).value,0)),'Note':txt(mws.cell(rr,5).value)}

    if "Cap เจีย" in wb.sheetnames:
        ws=wb["Cap เจีย"]
        op_pairs=[
            ("DE","DF","บดหน้า"),
            ("DG","DH","หยอดรู"),
            ("DI","DJ","แต่งขอบ"),
            ("DK","DL","รูปทรงเล็ก"),
            ("DM","DN","รูปใหญ่-1"),
            ("DO","DP","รูปใหญ่-2"),
        ]
        for rr in range(3,ws.max_row+1):
            prodcode=txt(ws[f"A{rr}"].value)
            spec=txt(ws[f"H{rr}"].value)
            if not prodcode and not spec:continue

            rec={
                "ProductionCode":prodcode,
                "Specification":spec,
                "Type":txt(ws[f"BF{rr}"].value),
                "Shape":txt(ws[f"BW{rr}"].value),
            }
            caps=[]; resources=[]
            op_no=0
            for oc,cc,op_name in op_pairs:
                machine=txt(ws[f"{oc}{rr}"].value)
                rawcap=num(ws[f"{cc}{rr}"].value,0)
                if not machine and rawcap<=0:
                    continue
                op_no+=1
                sm=grind_setup.get(machine.upper(),{}) if machine else {}
                status=sm.get('Machine Status','AVAILABLE')
                cap=0 if status=='BROKEN' else rawcap
                rec[f"Op{op_no}"]=op_name
                rec[f"Op{op_no} Machine"]=machine
                rec[f"Op{op_no} CAP/day"]=cap
                rec[f"Op{op_no} Raw CAP/day"]=rawcap
                rec[f"Op{op_no} Setup hr"]=sm.get('Setup Time hr',0)
                rec[f"Op{op_no} Workers"]=sm.get('Required Workers',0)
                rec[f"Op{op_no} Machine Status"]=status
                if machine and status=='BROKEN':
                    rec['Broken Machine In Route']=machine
                if machine and cap>0:
                    caps.append(cap)
                    resources.append(f"{op_name}:{machine}@{cap:g}/day; setup {sm.get('Setup Time hr',0):g}h; workers {sm.get('Required Workers',0)}")
            rec["Operation Count"]=op_no
            rec["Operations"]=" | ".join(resources)
            if rec.get('Broken Machine In Route'):
                rec["Bottleneck CAP/day"]=0
                rec["Max CAP/day"]=max(caps) if caps else 0
                rec["Route Status"]='HOLD - BROKEN MACHINE IN REQUIRED ROUTE'
                rec["Bottleneck Machine"]=rec.get('Broken Machine In Route')
                rec["Bottleneck Setup hr"]=grind_setup.get(rec["Bottleneck Machine"].upper(),{}).get('Setup Time hr',0)
                rec["Bottleneck Workers"]=0
            elif caps:
                rec["Bottleneck CAP/day"]=min(caps)
                rec["Max CAP/day"]=max(caps)
                rec["Route Status"]='AVAILABLE'
                # first machine whose effective CAP/day equals route bottleneck
                bm=''
                for i in range(1,op_no+1):
                    if num(rec.get(f'Op{i} CAP/day'),0)==rec["Bottleneck CAP/day"] and txt(rec.get(f'Op{i} Machine')):
                        bm=txt(rec.get(f'Op{i} Machine'));break
                rec["Bottleneck Machine"]=bm
                rec["Bottleneck Setup hr"]=grind_setup.get(bm.upper(),{}).get('Setup Time hr',0) if bm else 0
                rec["Bottleneck Workers"]=grind_setup.get(bm.upper(),{}).get('Required Workers',0) if bm else 0
            else:
                continue
            rec["Grinding Dept Current People"]=current_people.get('เจียร',{}).get('Current People',0)
            grind.append(rec)

    # ---------------- PACKING ----------------
    # Capture BOTH blocks in Cap บรรจุ.
    pack=[]
    if "Cap บรรจุ" in wb.sheetnames:
        ws=wb["Cap บรรจุ"]
        header_rows=[]
        for rr in range(1,ws.max_row+1):
            first=txt(ws.cell(rr,1).value)
            if first=="ขนาด":
                header_rows.append(rr)

        for hi,hr in enumerate(header_rows):
            endr=(header_rows[hi+1]-1) if hi+1<len(header_rows) else ws.max_row
            headers=[txt(ws.cell(hr,c).value) for c in range(1,ws.max_column+1)]
            for rr in range(hr+1,endr+1):
                size=txt(ws.cell(rr,1).value)
                if not size or size.startswith("Cap "):continue
                typ=txt(ws.cell(rr,2).value)
                vals=[]
                detail=[]
                for c in range(3,ws.max_column+1):
                    h=headers[c-1]
                    v=num(ws.cell(rr,c).value,0)
                    if h and v>0:
                        vals.append(v);detail.append(f"{h}:{v:g}")
                if vals:
                    pack.append({"Spec Pattern":size,"Type":typ,
                                 "Bottleneck pcs/day/person":min(vals),
                                 "Max process pcs/day/person":max(vals),
                                 "Processes":" | ".join(detail),
                                 "Source Block":hr,
                                 "Department Current People":current_people.get('บรรจุ',{}).get('Current People',0),
                                 "Department Planned People":current_people.get('บรรจุ',{}).get('Plan People',0)})

    mp=current_people
    evidence=pd.DataFrame([
        {"Section / กระบวนการ":"Preparation / เตรียม","Source":"No dedicated capacity sheet in supplied workbook","Validation":"Preparation LT = 1 day from Lead Time sheet. Daily kg capacity remains an explicit Planning input because a rated Preparation kg/day master is not supplied."},
        {"Section / กระบวนการ":"Mixing / ผสม","Source":"CAP ผสม","Validation":f"Machine + active status + Job/family + CAP-โม่ + batch kg range + abrasive. Current department people={mp.get('ผสม',{}).get('Current People',0)} / plan={mp.get('ผสม',{}).get('Plan People',0)}."},
        {"Section / กระบวนการ":"Forming / ขึ้นรูป","Source":"CAP ขึ้นรูป","Validation":f"Spec/size + eligible M/C + pcs/hr + 8h normal + 3h OT. Current people={mp.get('ขึ้นรูป',{}).get('Current People',0)} / plan={mp.get('ขึ้นรูป',{}).get('Plan People',0)}."},
        {"Section / กระบวนการ":"Firing / เผา","Source":"Cap เตา A:D + F:H + Firing Planner","Validation":f"A:D controls kiln/program compatibility; F:H controls program ton/load and running days. Current kiln people={mp.get('เตา',{}).get('Current People',0)}."},
        {"Section / กระบวนการ":"Grinding/Cutting / เจียร-ตัด","Source":"Cap เจีย + Set Up Time, จำนวน พนักงาน เจีย","Validation":f"Product-specific operation sequence + machine CAP/day + 0.5h setup + machine worker requirement; broken machines are unavailable. Current grinding people={mp.get('เจียร',{}).get('Current People',0)} / plan={mp.get('เจียร',{}).get('Plan People',0)}."},
        {"Section / กระบวนการ":"Packing / บรรจุ","Source":"Cap บรรจุ + กำลังคนแผนกผลิต","Validation":f"Size/category process bottleneck pcs/day/person × available people. Current packing people={mp.get('บรรจุ',{}).get('Current People',0)} / plan={mp.get('บรรจุ',{}).get('Plan People',0)}."},
        {"Section / กระบวนการ":"Manpower / กำลังคน","Source":"กำลังคนแผนกผลิต","Validation":"Current total 90 vs planned 95; gaps: Forming +2, Grinding +2, Packing +1."},
        {"Section / กระบวนการ":"Lead Time","Source":"Lead Time","Validation":"Category-specific S/T/P/R/PB/M values are exported and applied to upstream working-day readiness gates; firing plan remains the exact kiln-date authority."},
    ])

    return pd.DataFrame(mix),pd.DataFrame(form),pd.DataFrame(kiln),pd.DataFrame(grind),pd.DataFrame(pack),evidence


# ---------------------------------------------------------------------
# MERGE
# ---------------------------------------------------------------------
def merge_master(plan,firing,today):
    base=plan.copy()
    f=firing.set_index("Work Order") if firing is not None and not firing.empty else pd.DataFrame()

    final=[]
    for _,r in base.iterrows():
        x=r.to_dict()
        wo=r["Work Order"]
        if isinstance(f,pd.DataFrame) and not f.empty and wo in f.index:
            fr=f.loc[wo]
            x["Firing Date"]=pdate(fr["Firing Date"])
            x["Firing Complete"]=pdate(fr["Firing Complete"])
            x["Firing Qty"]=num(fr["Firing Qty"],0)
            x["Firing Date Source"]=txt(fr.get("Firing Source","Firing Planner released schedule"))
            x["Kiln"]=txt(fr.get("Kiln",""))
            x["Program"]=txt(fr.get("Program",""))
            fk=num(fr.get("kg/pc",0),0)
        else:
            x["Firing Date"]=pdate(r["Plan2026 Firing Date"])
            x["Firing Complete"]=None
            x["Firing Qty"]=num(r.get("Firing Remaining Qty",0),0)
            x["Firing Date Source"]="Plan 2026 fallback ID"
            x["Kiln"]=""; x["Program"]=""
            fk=0

        pk=num(r.get("Plan2026 kg/pc",0),0)
        x["Unit kg/pc"]=fk if fk>0 else pk
        x["Weight Source"]="Firing Planner" if fk>0 else ("Plan 2026 WIP" if pk>0 else "MISSING")
        x["Priority"]=priority_default(r["Delivery Date"],x["Firing Date"],today)
        _p=txt(x["Priority"]).upper()
        x["Priority Rank"]={"OVERDUE":0,"HIGH":1,"MEDIUM":2,"LOW":3}.get(_p,2)
        final.append(x)

    out=pd.DataFrame(final)
    if "Priority Rank" not in out.columns:
        out["Priority Rank"]=2
    # Physical downstream WIP implied by cumulative process actuals.
    # These are the quantities that can be worked immediately, independent of
    # whether the whole WO has finished the previous process.
    # Stage-aware WIP evidence. Downstream actual is also proof that at least
    # that quantity completed upstream; this prevents inconsistent/blank upstream
    # actual cells from hiding real WIP.
    fa=pd.to_numeric(out["Firing Actual Qty"],errors="coerce").fillna(0)
    ga=pd.to_numeric(out["Grinding / Cutting Actual Qty"],errors="coerce").fillna(0)
    pa=pd.to_numeric(out["Packing Actual Qty"],errors="coerce").fillna(0)
    fp=pd.to_numeric(out["Firing Plan Qty"],errors="coerce").fillna(0)
    gp=pd.to_numeric(out["Grinding / Cutting Plan Qty"],errors="coerce").fillna(0)

    fire_closed=out["Firing Status"].fillna("").astype(str).str.upper().isin(["ปิดใบสั่ง","CLOSED","DONE","FINISHED"])
    grind_closed=out["Grinding / Cutting Status"].fillna("").astype(str).str.upper().isin(["ปิดใบสั่ง","CLOSED","DONE","FINISHED"])

    # Never reduce a known actual. A CLOSED process with blank actual may use its
    # latest-plan quantity as controlled evidence; if actual exists, actual wins
    # so accepted-short/NCR closure is not inflated.
    effective_fired=pd.concat([fa,ga,pa],axis=1).max(axis=1)
    effective_fired=effective_fired.where(~(fire_closed & (fa<=0)),pd.concat([effective_fired,fp],axis=1).max(axis=1))
    effective_ground=pd.concat([ga,pa],axis=1).max(axis=1)
    effective_ground=effective_ground.where(~(grind_closed & (ga<=0)),pd.concat([effective_ground,gp],axis=1).max(axis=1))

    out["Effective Fired Qty"]=effective_fired
    out["Effective Ground Qty"]=effective_ground
    out["Ready for Grinding Qty"]=(effective_fired-ga).clip(lower=0)
    out["Ready for Packing Qty"]=(effective_ground-pa).clip(lower=0)
    return out.sort_values("Excel Sequence").reset_index(drop=True)

# ---------------------------------------------------------------------
# MATCHING
# ---------------------------------------------------------------------
def abrasive_codes(spec):
    s=txt(spec).upper()
    known=["38A","WA","PA","SA","BA","GC","AZC","C","A"]
    return [k for k in known if re.search(r"(^|[/+ -])"+re.escape(k)+r"(?=\d|[/+ -]|$)",s)]

def family(typ):
    u=txt(typ).upper()
    if u.startswith("PB"): return "PB"
    if u.startswith("R"): return "R"
    if u.startswith("S"): return "S"
    if u.startswith("T"): return "T"
    return "P"

def mix_job_ok(job,fam):
    j=txt(job)
    c=j.upper().replace(" ","")
    if "บด" in j: return False
    if fam=="PB": return "PB" in c
    return ("ผสม"+fam) in c

def abrasive_ok(master,spec):
    m=txt(master).upper()
    codes=abrasive_codes(spec)
    return bool(m and codes and any(c in m for c in codes))

def forming_match(row,rates):
    if rates.empty: return None,0
    spec=txt(row["Specification"]).upper()
    typ=txt(row["Type"]).upper()
    D=num(row.get("D"),0)

    best=None; bs=0
    for _,r in rates.iterrows():
        pat=txt(r["Spec Pattern"]).upper()
        if not pat: continue
        textscore=0
        if pat==spec: textscore=1000
        elif pat in spec or spec in pat: textscore=500
        else:
            toks=[x for x in re.split(r"[^A-Z0-9]+",pat) if len(x)>=2]
            textscore=sum(1 for x in toks if x in spec)*10

        # Controlled generic P-size rows.
        if typ=="P":
            if D and D<=203 and ('2"' in pat and '8"' in pat): textscore=max(textscore,300)
            elif D and 230<=D<=280 and '10"' in pat: textscore=max(textscore,300)
            elif D and 300<=D<=390 and '12"' in pat and '15"' in pat: textscore=max(textscore,300)

        if textscore<=0: continue
        score=textscore+(20 if txt(r["Type"]).upper()==typ else 0)
        if score>bs: best=r; bs=score
    return best,bs

def packing_match(row,rates):
    if rates.empty:return None,0
    s=(txt(row.get("Specification",""))+" "+txt(row.get("Real Spec",""))).upper()
    typ=txt(row["Type"]).upper()
    D=num(row.get("D"),0);T=num(row.get("T"),0);H=num(row.get("H"),0)
    inch=D/25.4 if D>0 else 0
    nominal=None
    for n in [2,4,6,8,10,12,14,16,18,20,24,26,30,32,34,36,42]:
        if inch and abs(inch-n)<=0.8:
            nominal=n;break
    best=None;bs=-999
    for _,r in rates.iterrows():
        pat=txt(r["Spec Pattern"]).upper()
        rtyp=txt(r["Type"]).upper().replace(" ","")
        score=0
        if pat and pat in s:score+=500
        toks=[x for x in re.split(r"[^A-Z0-9]+",pat) if len(x)>=2]
        score+=sum(1 for x in toks if x in s)*15
        compatible=(typ in rtyp.split(",")) or (typ=="PB" and "PB" in rtyp) or (typ=="P" and "P" in rtyp)
        score += 200 if compatible else (-300 if rtyp else 0)
        if typ in {"P","PB"} and nominal:
            if nominal==2 and "2''" in pat and "ไม่เกิน" in pat:score+=350
            elif f"{nominal}''" in pat or f'{nominal}"' in pat:score+=350
        if score>bs:best=r;bs=score
    return best,bs


def grinding_match(row,rates):
    if rates.empty:return None,0
    product_code=txt(row.get("Product Code",""))
    spec=(txt(row.get("Specification",""))+" "+txt(row.get("Real Spec",""))).upper()

    # Cap เจีย column A is PRODUCT/PRODUCTION CODE, not Work Order.
    if product_code:
        exact=rates[rates["ProductionCode"].astype(str).str.strip().str.upper()==product_code.upper()]
        if not exact.empty:return exact.iloc[0],1200

    best=None;bs=0
    for _,r in rates.iterrows():
        pat=txt(r["Specification"]).upper()
        if not pat:continue
        if pat==spec:score=900
        elif pat in spec or spec in pat:score=500
        else:
            toks=[x for x in re.split(r"[^A-Z0-9]+",pat) if len(x)>=3]
            score=sum(1 for x in toks if x in spec)*10
        if txt(r.get("Type","")).upper()==txt(row.get("Type","")).upper():score+=25
        if txt(r.get("Shape","")).upper()==txt(row.get("Shape","")).upper():score+=15
        if score>bs:best=r;bs=score
    return best,bs


def firing_program_rule(program,kiln,rates):
    if rates.empty:return None
    p=txt(program).upper().replace(" ","")
    k=txt(kiln).upper().replace(" ","")
    # T14 has its own P3 rule.
    target="P3(T14)" if ("P3" in p and "14" in k) else p
    for _,r in rates.iterrows():
        rp=txt(r["Program"]).upper().replace(" ","")
        if rp==target or rp==p:
            return r
    return None

def machines(s):
    return [x.strip() for x in re.split(r"[/,]",txt(s)) if x.strip()] or ["UNSPECIFIED"]

# ---------------------------------------------------------------------
# SCHEDULING
# ---------------------------------------------------------------------
def working_days(start,end,reverse=False):
    ds=[]; d=start
    while d<=end:
        if workday(d):ds.append(d)
        d+=timedelta(days=1)
    return list(reversed(ds)) if reverse else ds

def latest_date(df,wo):
    if df is None or df.empty:return None
    x=df[df["Work Order"].astype(str)==str(wo)]
    if x.empty:return None
    vals=[pdate(v) for v in x["Plan Date"]]
    vals=[v for v in vals if v]
    return max(vals) if vals else None


def operational_job_sort(jobs, section):
    """Common pull-priority sequence with defensive rank creation."""
    x=jobs.copy()
    if x.empty:return x
    if "Priority Rank" not in x.columns:
        p=x["Priority"] if "Priority" in x.columns else pd.Series("MEDIUM",index=x.index)
        x["Priority Rank"]=p.fillna("MEDIUM").astype(str).str.upper().map(
            {"OVERDUE":0,"HIGH":1,"MEDIUM":2,"LOW":3}
        ).fillna(2).astype(int)
    x["_fire"]=x["Firing Date"].apply(lambda z:z or date(2099,12,31))
    x["_delivery"]=x["Delivery Date"].apply(lambda z:z or date(2099,12,31))
    # Earliest required firing first; due date next; priority then Excel sequence.
    keys=["_fire","_delivery","Priority Rank"]
    if "Excel Sequence" in x.columns:keys.append("Excel Sequence")
    return x.sort_values(keys,na_position="last")


def process_status_text(row, section):
    c=f"{section} Status"
    v=str(row.get(c,"")).strip()
    return v


def schedule_preparation(master,start,end,capacity_kg):
    rows=[]; issues=[]; used={}
    days=working_days(start,end,True)
    jobs=master[master["Preparation Remaining Qty"]>0].copy()
    jobs=operational_job_sort(jobs,"Preparation")
    for _,j in jobs.iterrows():
        rem=num(j["Preparation Remaining Qty"],0)
        target=add_workdays(j["Firing Date"],-3) if j["Firing Date"] else None
        kgpc=num(j["Unit kg/pc"],0)
        if kgpc<=0:
            issues.append({"Section / กระบวนการ":"Preparation","Work Order":j["Work Order"],"Qty":rem,"Reason":"Missing kg/pc"})
            continue
        # Balance workload: among dates that can still protect the firing target,
        # use the least-loaded day first instead of front-loading all work.
        eligible_days=[d for d in days if not target or d<=target]
        eligible_days=sorted(eligible_days,key=lambda d:(used.get(d,0)/capacity_kg if capacity_kg else 1,d))
        for day in eligible_days:
            if rem<=0:break
            free=max(capacity_kg-used.get(day,0),0)
            q=min(rem,math.floor(free/kgpc))
            if q<=0:continue
            kg=q*kgpc;used[day]=used.get(day,0)+kg;rem-=q
            rows.append({"Plan Date":day,"Section / กระบวนการ":"Preparation","Work Order":j["Work Order"],"Customer":j["Customer"],
                         "Specification":j["Specification"],"Type":j["Type"],"Priority":j["Priority"],
                         "Plan Qty":q,"Plan kg":kg,
                         "Capacity kg/day":capacity_kg,
                         "Derived Capacity pcs/day":math.floor(capacity_kg/kgpc) if kgpc>0 else 0,
                         "Capacity Used kg After WO":used[day],
                         "Capacity Remaining kg":max(capacity_kg-used[day],0),
                         "Product Family":family(j["Type"]),
                         "Target Date":target,"Planning Basis":"PULL FROM FIRING DATE",
                         "Operational Reason":"Required upstream work for earliest feasible firing/delivery sequence",
                         "Validation Status":"VALIDATED","Release Status":"RELEASE",
                         "Capacity Evidence — หลักฐานกำลังการผลิต":f"Preparation controlled fallback {capacity_kg:g} kg/day + WO kg/pc -> derived pcs/day; dedicated Preparation machine/category master not supplied","Firing Date":j["Firing Date"]})
        if rem>0:
            issues.append({"Section / กระบวนการ":"Preparation","Work Order":j["Work Order"],"Qty":rem,"Reason":"Insufficient Preparation kg/day before target"})
    return pd.DataFrame(rows),pd.DataFrame(issues)

def schedule_mixing(master,start,end,rates,prep,ot):
    rows=[];issues=[];used={}
    days=working_days(start,end,True)
    jobs=master[master["Mixing Remaining Qty"]>0].copy()
    jobs=operational_job_sort(jobs,"Mixing")
    for _,j in jobs.iterrows():
        rem=num(j["Mixing Remaining Qty"],0);kgpc=num(j["Unit kg/pc"],0)
        target=add_workdays(j["Firing Date"],-2) if j["Firing Date"] else None
        prev=latest_date(prep,j["Work Order"])
        release=add_workdays(prev,1) if prev else None
        if kgpc<=0:
            issues.append({"Section / กระบวนการ":"Mixing","Work Order":j["Work Order"],"Qty":rem,"Reason":"Missing kg/pc"})
            continue
        cand=rates.copy()
        fam=family(j["Type"])
        if not cand.empty:
            cand=cand[cand["Status"].astype(str).str.strip().eq("ใช้")]
            cand=cand[cand["Job"].apply(lambda x:mix_job_ok(x,fam))]
            cand=cand[(cand["CAP-โม่"]>0)&(cand["Max batch kg"]>0)]
            cand=cand.copy()
            cand["Abr OK"]=cand["Abrasive"].apply(lambda x:abrasive_ok(x,j["Specification"]))
            cand=cand.sort_values(["Abr OK","Max batch kg"],ascending=[False,True])
        if cand.empty:
            issues.append({"Section / กระบวนการ":"Mixing","Work Order":j["Work Order"],"Qty":rem,"Reason":"No active Mixing machine matches product family"})
            continue

        eligible_days=[d for d in days if (not target or d<=target) and (not release or d>=release)]
        def _mix_day_load(d):
            vals=[]
            for _,_m in cand.iterrows():
                _cap=max(int(num(_m["CAP-โม่"],0)),1)
                vals.append(used.get((d,_m["Machine"]),0)/_cap)
            return sum(vals)/len(vals) if vals else 1
        eligible_days=sorted(eligible_days,key=lambda d:(_mix_day_load(d),d))
        for day in eligible_days:
            if rem<=0:break
            for _,m in cand.iterrows():
                if rem<=0:break
                mc=m["Machine"]
                base=int(num(m["CAP-โม่"],0))
                cap=int(math.floor(base*(8+ot)/8))
                free=max(cap-used.get((day,mc),0),0)
                if free<=0:continue
                mn=num(m["Min batch kg"],0);mx=num(m["Max batch kg"],0)
                kgwant=min(rem*kgpc,free*mx)
                q=int(math.floor(kgwant/kgpc))
                if q<=0:continue
                kg=q*kgpc
                feasible=[b for b in range(1,free+1) if mn<=kg/b<=mx]
                if not feasible:continue
                b=min(feasible);avg=kg/b
                used[(day,mc)]=used.get((day,mc),0)+b;rem-=q
                abr=bool(m["Abr OK"])
                rows.append({"Plan Date":day,"Section / กระบวนการ":"Mixing","Work Order":j["Work Order"],"Customer":j["Customer"],
                             "Specification":j["Specification"],"Type":j["Type"],"Priority":j["Priority"],
                             "Plan Qty":q,"Plan kg":kg,"Machine":mc,"Mixing Job":m["Job"],
                             "Required Batches":b,"CAP-โม่ Available":cap,"CAP-โม่ Used":used[(day,mc)],
                             "Machine Utilization %":(used[(day,mc)]/cap*100) if cap else None,
                             "Average Batch kg":avg,"Batch Range":f"{mn:g}-{mx:g}","Abrasive Master":m["Abrasive"],
                             "Machine kg Master":m["Machine kg"],"Product Family":fam,
                             "Capacity Basis":"Active machine + Job/family + CAP-MO + min/max batch kg + abrasive + OT",
                             "Abrasive Check":"PASS" if abr else "VERIFY","Man (Master)":m["Man"],
                             "Target Date":target,"Earliest Release Date":release,
                             "Validation Status":"VALIDATED" if abr else "PROVISIONAL - ABRASIVE VERIFY",
                             "Release Status":"RELEASE" if abr else "RELEASE WITH CHECK",
                             "Capacity Evidence — หลักฐานกำลังการผลิต":"CAP ผสม: Job + CAP-โม่ + usable batch kg + abrasive","Firing Date":j["Firing Date"]})
        if rem>0:
            issues.append({"Section / กระบวนการ":"Mixing","Work Order":j["Work Order"],"Qty":rem,
                           "Reason":"No feasible machine/day under CAP-โม่, batch kg, Job, abrasive and sequence"})
    return pd.DataFrame(rows),pd.DataFrame(issues)

def schedule_forming(master,start,end,rates,mixing,ot):
    rows=[];issues=[];used={}
    days=working_days(start,end,True)
    jobs=master[master["Forming Remaining Qty"]>0].copy()
    jobs=operational_job_sort(jobs,"Forming")
    for _,j in jobs.iterrows():
        rem=num(j["Forming Remaining Qty"],0)
        target=add_workdays(j["Firing Date"],-1) if j["Firing Date"] else None
        prev=latest_date(mixing,j["Work Order"]);release=add_workdays(prev,1) if prev else None
        mr,score=forming_match(j,rates)
        if mr is None:
            issues.append({"Section / กระบวนการ":"Forming","Work Order":j["Work Order"],"Qty":rem,"Reason":"No CAP ขึ้นรูป spec/size match"})
            continue
        cap=num(mr["Normal pcs/8h"],0)+num(mr["pcs/hour"],0)*ot
        mold_key=txt(mr["Spec Pattern"]).upper()
        eligible_days=[d for d in days if (not target or d<=target) and (not release or d>=release)]
        def _form_day_load(d):
            _loads=[]
            for _mc in machines(mr["Machine"]):
                _loads.append(used.get((d,_mc),0)/cap if cap else 1)
            return min(_loads) if _loads else 1
        eligible_days=sorted(eligible_days,key=lambda d:(_form_day_load(d),d))
        for day in eligible_days:
            if rem<=0:break

            # Conservative tooling rule: one matched spec/mold can occupy only ONE
            # eligible forming machine on a day unless a future mold master says
            # multiple molds exist. This prevents the same physical mold being
            # scheduled simultaneously on H5 and H15, etc.
            if used.get((day,"MOLD",mold_key),0)>=1:
                continue
            free=[]
            for mc in machines(mr["Machine"]):
                free.append((max(cap-used.get((day,mc),0),0),mc))
            free.sort(reverse=True)
            if not free:continue
            avail,mc=free[0]
            q=min(rem,math.floor(avail))
            if q<=0:continue
            used[(day,mc)]=used.get((day,mc),0)+q
            used[(day,"MOLD",mold_key)]=1
            rem-=q
            rows.append({"Plan Date":day,"Section / กระบวนการ":"Forming","Work Order":j["Work Order"],"Customer":j["Customer"],
                             "Specification":j["Specification"],"Type":j["Type"],"Priority":j["Priority"],
                             "Plan Qty":q,"Plan kg":q*num(j["Unit kg/pc"],0),"Machine":mc,
                             "Capacity pcs/day":cap,"Machine Load After WO":used[(day,mc)],
                             "Utilization":used[(day,mc)]/cap if cap else None,
                             "Master Spec Match":mr["Spec Pattern"],"Match Score":score,
                             "Normal pcs/8h":mr["Normal pcs/8h"],"pcs/hour":mr["pcs/hour"],"Approved OT h":ot,
                             "Product D":j["D"],"Product T":j["T"],"Product H":j["H"],
                             "Eligible Machines":mr["Machine"],
                             "Mold / Spec Resource":mold_key,
                             "Capacity Basis":"Spec/size + product group + eligible machine + one-mold/spec lock + pcs/hour + normal shift + OT",
                             "Target Date":target,"Earliest Release Date":release,
                             "Planning Basis":"PULL FROM FIRING DATE",
                             "Operational Reason":"Scheduled only after previous process release and before firing requirement",
                             "Validation Status":"VALIDATED","Release Status":"RELEASE",
                             "Capacity Evidence — หลักฐานกำลังการผลิต":"CAP ขึ้นรูป: spec + eligible M/C + 8h capacity + approved OT","Firing Date":j["Firing Date"]})
        if rem>0:
            issues.append({"Section / กระบวนการ":"Forming","Work Order":j["Work Order"],"Qty":rem,"Reason":"Matched Forming machine capacity insufficient before firing"})
    return pd.DataFrame(rows),pd.DataFrame(issues)

def schedule_firing(master,forming,kiln_rates):
    rows=[];issues=[]
    tmp=[]
    for _,j in master[master["Firing Qty"]>0].iterrows():
        fire=j["Firing Date"];finish=j["Firing Complete"]
        rem=num(j["Forming Remaining Qty"],0)
        prev=latest_date(forming,j["Work Order"])
        release=add_workdays(prev,1) if prev else None
        hold=False
        if rem>0 and prev is None:
            hold=True;reason="Forming remaining > 0 but no feasible Forming plan"
        elif release and fire and fire<release:
            hold=True;reason=f"Earliest firing after Forming is {release}"
        else:reason=""
        tmp.append({"Plan Date":fire,"Section / กระบวนการ":"Firing","Work Order":j["Work Order"],"Customer":j["Customer"],
                    "Specification":j["Specification"],"Shape":j["Shape"],"Type":j["Type"],"D":j["D"],"T":j["T"],"H":j["H"],
                    "Priority":j["Priority"],"Plan Qty":j["Firing Qty"],
                    "Unit kg/pc":j["Unit kg/pc"],"Plan kg":j["Firing Qty"]*num(j["Unit kg/pc"],0),
                    "Kiln":j["Kiln"],"Program":j["Program"],"Firing Complete":finish,
                    "Earliest Release Date":release,"Validation Status":"VALIDATED FIRING SCHEDULE",
                    "Release Status":"HOLD / หยุด / EXPEDITE" if hold else "RELEASE",
                    "Sequence Status":"FAIL" if hold else "PASS",
                    "Capacity Evidence — หลักฐานกำลังการผลิต":"Firing Planner released load: kiln/program/date + compact volume/pattern decision; Daily Planner additionally checks program kg and upstream sequence","Reason":reason})
        if hold:issues.append({"Section / กระบวนการ":"Firing","Work Order":j["Work Order"],"Qty":j["Firing Qty"],"Reason":reason})

    df=pd.DataFrame(tmp)
    if df.empty:return df,pd.DataFrame(issues)

    # Executable firing work is surfaced first; HOLD/EXPEDITE rows remain visible
    # for upstream preparation but do not displace ready firing work.
    df["_ready_rank"]=df["Release Status"].apply(lambda x:0 if x=="RELEASE" else 1)
    df=df.sort_values(["Plan Date","_ready_rank","Priority"],na_position="last").drop(columns=["_ready_rank"])

    # Validate whole kiln-load weight by date/kiln/program.
    grp=df.groupby(["Plan Date","Kiln","Program"],dropna=False)["Plan kg"].sum().to_dict()
    df["Load Total kg"]=0.0
    df["Program Min kg"]=0.0
    df["Program Max kg"]=0.0
    df["Running Days"]=0.0
    df["Weight Capacity Check"]="VERIFY"

    for i,r in df.iterrows():
        key=(r["Plan Date"],r["Kiln"],r["Program"])
        total=num(grp.get(key,0),0)
        rule=firing_program_rule(r["Program"],r["Kiln"],kiln_rates)
        df.at[i,"Load Total kg"]=total
        if rule is not None:
            mn=num(rule["Min kg/load"],0);mx=num(rule["Max kg/load"],0)
            df.at[i,"Program Min kg"]=mn;df.at[i,"Program Max kg"]=mx
            df.at[i,"Running Days"]=num(rule["Running Days"],0)
            if mx>0 and total>mx:
                df.at[i,"Weight Capacity Check"]="OVER MAX"
                df.at[i,"Release Status"]="HOLD / หยุด / LOAD OVERWEIGHT"
                issues.append({"Section / กระบวนการ":"Firing","Work Order":r["Work Order"],"Qty":r["Plan Qty"],
                               "Reason":f"Kiln load total {total:.1f} kg exceeds program max {mx:.1f} kg."})
            elif mn>0 and total<mn:
                df.at[i,"Weight Capacity Check"]="BELOW TYPICAL MIN - VERIFY VOLUME/PATTERN"
            else:
                df.at[i,"Weight Capacity Check"]="PASS"

    return df,pd.DataFrame(issues)

def downstream_release_for_existing_wip(j, upstream_remaining_col, planned_upstream, planned_date_fallback=None):
    """
    Existing WIP must not wait for a newly generated upstream plan when Plan 2026
    says the upstream process is already complete. If upstream remaining <= 0,
    downstream can start at the planning start (subject to its own capacity).
    Otherwise it must wait one full working day after the latest planned upstream work.
    """
    upstream_rem=num(j.get(upstream_remaining_col,0),0)
    if upstream_rem<=0:
        return None, "UPSTREAM ALREADY COMPLETE / EXISTING WIP"
    prev=latest_date(planned_upstream,j["Work Order"])
    if prev:
        return add_workdays(prev,1), "1 WORKING DAY AFTER PLANNED UPSTREAM"
    if planned_date_fallback:
        return add_workdays(planned_date_fallback,1), "1 WORKING DAY AFTER UPSTREAM DATE"
    return None, "UPSTREAM NOT READY"

def grinding_resource_list(mr):
    resources=[]
    for n in range(1,7):
        op=txt(mr.get(f"Op{n}",""))
        machine=txt(mr.get(f"Op{n} Machine",""))
        cap=num(mr.get(f"Op{n} CAP/day",0),0)
        if machine and cap>0:
            resources.append((n,op,machine,cap))
    return resources


def schedule_grinding(master,firing,rates,start,end):
    """
    Multi-machine grinding scheduler.

    A WO may require several operations/machines. The same quantity consumes
    capacity on every required operation resource for that day. Daily WO qty is
    limited by the smallest remaining capacity across its required machines.

    Existing grinding-ready WIP = Effective Fired Qty - Grinding Actual Qty.
    Future fired quantities join the Grinding pool one working day later.
    """
    rows=[];issues=[];used={}
    days=working_days(start,end,False)
    jobs=master[master["Grinding / Cutting Remaining Qty"]>0].copy()
    jobs=operational_job_sort(jobs,"Grinding / Cutting")

    firing_by_wo={}
    if firing is not None and not firing.empty:
        for wo,g in firing.groupby("Work Order"):
            firing_by_wo[wo]=g.copy()

    for _,j in jobs.iterrows():
        total_rem=num(j["Grinding / Cutting Remaining Qty"],0)
        if total_rem<=0:continue
        initial_ready=min(num(j.get("Ready for Grinding Qty",0),0),total_rem)

        arrivals={}
        fg=firing_by_wo.get(j["Work Order"])
        if fg is not None and not fg.empty:
            for _,fr in fg.iterrows():
                fd=pdate(fr.get("Firing Complete")) or pdate(fr.get("Plan Date"))
                fq=num(fr.get("Plan Qty",fr.get("Firing Qty",0)),0)
                if fd and fq>0:
                    rd=add_workdays(fd,1)
                    arrivals[rd]=arrivals.get(rd,0)+fq

        mr,score=grinding_match(j,rates)
        fallback=False
        if mr is None or score<=0:
            cand=rates.copy() if rates is not None else pd.DataFrame()
            if not cand.empty:
                cand=cand[pd.to_numeric(cand["Bottleneck CAP/day"],errors="coerce").fillna(0)>0].copy()
            if not cand.empty:
                spec=txt(j["Specification"]).upper()
                cand["_fb"]=cand["Specification"].fillna("").astype(str).str.upper().apply(
                    lambda s:sum(1 for z in re.split(r"[^A-Z0-9]+",s) if len(z)>=3 and z in spec)
                )
                mr=cand.sort_values(["_fb","Bottleneck CAP/day"],ascending=[False,True]).iloc[0]
                score=num(mr["_fb"],0);fallback=True
            else:
                issues.append({"Section / กระบวนการ":"Grinding / Cutting","Work Order":j["Work Order"],
                               "Qty":total_rem,"Reason":"No usable Grinding capacity-master row"})
                continue

        resources=grinding_resource_list(mr)
        if not resources:
            issues.append({"Section / กระบวนการ":"Grinding / Cutting","Work Order":j["Work Order"],
                           "Qty":total_rem,"Reason":"Matched Grinding row has no machine + CAP/day resources"})
            continue

        ready=initial_ready;planned=0.0
        for day in days:
            if planned>=total_rem:break
            ready+=arrivals.get(day,0)
            ready=min(ready,total_rem-planned)
            if ready<=0:continue

            free_by_res=[]
            for n,op,machine,cap in resources:
                free=max(cap-used.get((day,machine),0),0)
                free_by_res.append((free,n,op,machine,cap))
            if not free_by_res:continue
            q=min(ready,total_rem-planned,math.floor(min(x[0] for x in free_by_res)))
            if q<=0:continue

            for free,n,op,machine,cap in free_by_res:
                used[(day,machine)]=used.get((day,machine),0)+q

            ready-=q;planned+=q
            bottleneck=min(free_by_res,key=lambda x:x[0])
            machine_sequence=" → ".join(f"{op}:{mc}" for _,_,op,mc,_ in sorted(free_by_res,key=lambda x:x[1]))
            machine_loads=" | ".join(
                f"{mc} {used[(day,mc)]:g}/{cap:g}"
                for _,_,op,mc,cap in sorted(free_by_res,key=lambda x:x[1])
            )

            rows.append({
                "Plan Date":day,"Section / กระบวนการ":("Cutting / ตัด" if str(j.get("Route",j.get("Post-Firing Route",""))).upper().startswith("CUT") else "Grinding / เจียร"),
                 "Work Order":j["Work Order"],"Product Code":j.get("Product Code",""),
                "Customer":j["Customer"],"Specification":j["Specification"],"Type":j["Type"],
                "Priority":j["Priority"],"Due Date":j["Delivery Date"],
                "Plan Qty":q,"Plan kg":q*num(j["Unit kg/pc"],0),
                "Machine":bottleneck[3],
                "Machine Sequence":machine_sequence,
                "Required Machines":len(resources),
                "Machine Loads After WO":machine_loads,
                "Bottleneck Operation":bottleneck[2],
                "Bottleneck Machine":bottleneck[3],
                "Bottleneck CAP/day":bottleneck[4],
                "Existing Ready WIP at Start":initial_ready,
                "Capacity Basis":"Every required grinding operation machine + CAP/day; shared machine/day capacity",
                "Release Basis":"Existing fired WIP + next-day firing arrivals",
                "Match Score":score,
                "Validation Status":"REVIEW FALLBACK MATCH" if fallback else "VALIDATED",
                "Release Status":"RELEASE",
                "Capacity Evidence — หลักฐานกำลังการผลิต":txt(mr.get("Operations","")),
            })

        if planned<total_rem:
            issues.append({
                "Section / กระบวนการ":"Grinding / Cutting","Work Order":j["Work Order"],
                "Qty":total_rem-planned,
                "Reason":"Grinding demand remains after multi-machine CAP/day and fired-WIP availability"
            })
    return pd.DataFrame(rows),pd.DataFrame(issues)

def schedule_packing(master,grinding,rates,start,end,people=1):
    """
    Quantity-flow packing plan.

    Existing packing-ready WIP at plan start =
        max(Grinding Actual Qty - Packing Actual Qty, 0)

    Each new Grinding plan quantity becomes available to Packing on the next
    working day. Therefore Packing runs every day when ready WIP exists instead
    of waiting until the entire WO's Grinding schedule is finished.
    """
    rows=[];issues=[];used={}
    days=working_days(start,end,False)
    jobs=master[master["Packing Remaining Qty"]>0].copy()
    jobs=operational_job_sort(jobs,"Packing")
    people=max(int(people),1)

    grinding_by_wo={}
    if grinding is not None and not grinding.empty:
        for wo,g in grinding.groupby("Work Order"):
            grinding_by_wo[wo]=g.copy()

    for _,j in jobs.iterrows():
        total_rem=num(j["Packing Remaining Qty"],0)
        if total_rem<=0:continue

        packing_actual=num(j.get("Packing Actual Qty",0),0)
        initial_ready=min(num(j.get("Ready for Packing Qty",0),0),total_rem)

        arrivals={}
        gg=grinding_by_wo.get(j["Work Order"])
        if gg is not None and not gg.empty:
            for _,gr in gg.iterrows():
                gd=pdate(gr.get("Plan Date"))
                gq=num(gr.get("Plan Qty",0),0)
                if gd and gq>0:
                    rd=add_workdays(gd,1)
                    arrivals[rd]=arrivals.get(rd,0)+gq

        mr,score=packing_match(j,rates)
        fallback_pack=False
        if mr is None or score<=0:
            cand=rates.copy() if rates is not None else pd.DataFrame()
            typ=txt(j["Type"]).upper()
            if not cand.empty:
                same=cand[cand["Type"].fillna("").astype(str).str.upper()==typ]
                if not same.empty:cand=same
                cand=cand[pd.to_numeric(cand["Bottleneck pcs/day/person"],errors="coerce").fillna(0)>0]
            if not cand.empty:
                mr=cand.sort_values("Bottleneck pcs/day/person",ascending=True).iloc[0]
                score=1;fallback_pack=True
            else:
                issues.append({"Section / กระบวนการ":"Packing","Work Order":j["Work Order"],"Qty":total_rem,
                               "Reason":"No usable packing capacity row in controlled master"})
                continue

        rate_pp=num(mr["Bottleneck pcs/day/person"],0)
        if rate_pp<=0:
            issues.append({"Section / กระบวนการ":"Packing","Work Order":j["Work Order"],"Qty":total_rem,
                           "Reason":"Matched packing master has no positive bottleneck pcs/day/person"})
            continue

        daily_cap=rate_pp*people
        # Packing people are a shared daily resource. Do not reset full manpower
        # for every specification. Capacity rate remains spec/type dependent.
        ready=initial_ready;planned=0.0
        for day in days:
            if planned>=total_rem:break
            ready+=arrivals.get(day,0)
            ready=min(ready,total_rem-planned)
            if ready<=0:continue

            # Convert the day's already-consumed labor to equivalent person-days.
            labor_used=used.get(day,0.0)
            labor_free=max(float(people)-labor_used,0)
            free_pcs=math.floor(labor_free*rate_pp)
            q=min(ready,total_rem-planned,free_pcs)
            if q<=0:continue
            labor=q/rate_pp
            used[day]=used.get(day,0.0)+labor
            ready-=q;planned+=q

            process_text=txt(mr.get("Processes",""))
            proc_pairs=[]
            for token in process_text.split("|"):
                token=token.strip()
                if ":" in token:
                    nme,val=token.rsplit(":",1)
                    try: proc_pairs.append((nme.strip(),float(val)))
                    except: pass
            bottleneck_station=min(proc_pairs,key=lambda x:x[1])[0] if proc_pairs else ""
            rows.append({
                "Plan Date":day,"Section / กระบวนการ":"Packing","Work Order":j["Work Order"],
                "Product Code":j.get("Product Code",""),"Customer":j["Customer"],"Specification":j["Specification"],"Type":j["Type"],
                "Priority":j["Priority"],"Due Date":j["Delivery Date"],
                "Plan Qty":q,"Plan kg":q*num(j["Unit kg/pc"],0),
                "Packing Match":mr["Spec Pattern"],"Packing Processes":mr.get("Processes",""),
                "Packing Station Sequence":" → ".join(x[0] for x in proc_pairs),
                "Bottleneck Station":bottleneck_station,
                "Bottleneck pcs/day/person":rate_pp,"Packing Manpower":people,
                "Labor Used person-day":labor,
                "Labor Remaining person-day":max(people-used[day],0),
                "Existing Ready WIP at Start":initial_ready,
                "Capacity Basis":"Existing ground WIP + daily grinding arrivals + product/size process rate + shared manpower",
                "Release Basis":"QUANTITY FLOW FROM GRINDING ACTUAL/PLAN",
                "Match Score":score,
                "Validation Status":"REVIEW FALLBACK MATCH" if fallback_pack else "VALIDATED",
                "Release Status":"RELEASE",
                "Capacity Evidence — หลักฐานกำลังการผลิต":f"Cap บรรจุ {rate_pp:g} pcs/day/person + Grinding Actual - Packing Actual",
                "Earliest Release Date":start if initial_ready>0 else None
            })

        if planned<total_rem:
            issues.append({
                "Section / กระบวนการ":"Packing","Work Order":j["Work Order"],"Qty":total_rem-planned,
                "Reason":"Packing demand remains: insufficient ground quantity arrival or shared manpower capacity in horizon"
            })
    return pd.DataFrame(rows),pd.DataFrame(issues)


# ---------------------------------------------------------------------
# KILN PATTERN / PLATE VISUAL VERIFICATION
# ---------------------------------------------------------------------
def product_footprint(row):
    typ=txt(row.get("Type","")).upper()
    shape=txt(row.get("Shape","")).upper()
    D=max(num(row.get("D"),0),1)
    T=max(num(row.get("T"),0),1)
    H=max(num(row.get("H"),0),1)

    rectangular=(typ in {"S","T"} or "RECT" in shape or "ตัด" in shape or "ลับ" in shape)
    if rectangular:
        # Rectangular product: D=length, T=width, H=height/thickness.
        return D,T,H,"RECTANGULAR"

    # Circular product footprint is diameter x diameter; vertical height = thickness.
    return D,D,T,"CIRCULAR"


def select_iblock(part_height, plate_t, kiln_h):
    """
    Choose the smallest available I-block that safely clears the part plus
    controlled top clearance. This maximizes vertical utilization without
    drawing an impossible floor pitch.
    """
    required=max(part_height + CLEARANCE_ABOVE_PART_MM, 1)
    candidates=[x for x in I_BLOCK_MASTER if x["Height mm"] >= required and x["Qty"] > 0]
    if not candidates:
        return None
    return min(candidates,key=lambda x:x["Height mm"])


def evaluate_plate(kiln,row,pl,plate_rotation=False,part_rotation=False):
    kd,kw,kh=kiln_dimensions(kiln)
    fpw,fpd,part_h,geom=product_footprint(row)

    L,W=(pl["L"],pl["W"]) if not plate_rotation else (pl["W"],pl["L"])
    if part_rotation and geom=="RECTANGULAR":
        fpw,fpd=fpd,fpw

    plate_cols=int((kw + PLATE_GAP_MM)//(W + PLATE_GAP_MM))
    plate_rows=int((kd + PLATE_GAP_MM)//(L + PLATE_GAP_MM))
    plates_floor=max(plate_cols,0)*max(plate_rows,0)
    if plates_floor<=0:
        return None

    pcs_across=int((W + PRODUCT_GAP_MM)//(fpw + PRODUCT_GAP_MM))
    pcs_along=int((L + PRODUCT_GAP_MM)//(fpd + PRODUCT_GAP_MM))
    pcs_plate=max(pcs_across,0)*max(pcs_along,0)
    if pcs_plate<=0:
        return None

    leg=select_iblock(part_h,pl["T"],kh)
    if leg is None:
        return None

    floor_pitch=leg["Height mm"] + pl["T"]
    max_floors=int(kh//floor_pitch)
    if max_floors<=0:
        return None

    pcs_floor=plates_floor*pcs_plate
    planned=max(int(math.ceil(num(row.get("Plan Qty"),0))),0)
    floors_required=int(math.ceil(planned/pcs_floor)) if planned>0 else 0

    # Furniture demand assumes one plate layer per floor.
    plates_required=plates_floor*floors_required
    # Four I-blocks per plate is a conservative visual/planning assumption.
    iblocks_required=plates_required*4

    physical_max=pcs_floor*max_floors
    plate_ok=plates_required <= pl["Qty"]
    leg_ok=iblocks_required <= leg["Qty"]
    height_ok=floors_required <= max_floors
    qty_ok=planned <= physical_max
    feasible=plate_ok and leg_ok and height_ok and qty_ok

    return {
        "Plate":pl["Plate"],
        "Plate L":L,"Plate W":W,"Plate T":pl["T"],
        "Plate Available Qty":pl["Qty"],
        "Plate Cols":plate_cols,"Plate Rows":plate_rows,
        "Plates/Floor":plates_floor,
        "Pcs/Plate":pcs_plate,"Pcs/Floor":pcs_floor,
        "Part Footprint W":fpw,"Part Footprint D":fpd,
        "Part Height":part_h,"Geometry":geom,
        "Parts Across Plate":pcs_across,"Parts Along Plate":pcs_along,
        "I-block in":leg["Leg in"],"I-block Height mm":leg["Height mm"],
        "I-block Available Qty":leg["Qty"],
        "Floor Pitch mm":floor_pitch,
        "Max Physical Floors":max_floors,
        "Floors Required":floors_required,
        "Plates Required":plates_required,
        "I-blocks Required":iblocks_required,
        "Physical Max Qty/Load":physical_max,
        "Planned Qty":planned,
        "Furniture Check":"PASS" if (plate_ok and leg_ok) else "FAIL",
        "Height/Floor Check":"PASS" if height_ok else "FAIL",
        "Quantity Fit Check":"PASS" if qty_ok else "FAIL",
        "Pattern Feasible":feasible,
        "Kiln D":kd,"Kiln W":kw,"Kiln H":kh,
    }


def best_pattern_for_part(kiln,row,plate_choice="AUTO"):
    candidates=[]
    plates=PLATE_MASTER if plate_choice=="AUTO" else [x for x in PLATE_MASTER if x["Plate"]==plate_choice]
    for pl in plates:
        for prot in [False,True]:
            for rrot in [False,True]:
                x=evaluate_plate(kiln,row,pl,prot,rrot)
                if x:
                    candidates.append(x)
    if not candidates:
        return None

    # Prefer feasible pattern first. Among feasible patterns choose the one
    # requiring fewer floors, then fewer plates, then higher pcs/floor.
    candidates.sort(key=lambda x:(
        0 if x["Pattern Feasible"] else 1,
        x["Floors Required"],
        x["Plates Required"],
        -x["Pcs/Floor"]
    ))
    return candidates[0]


def pattern_top_figure(kiln,row,pat):
    import plotly.graph_objects as go
    kd,kw,kh=kiln_dimensions(kiln)
    fig=go.Figure()
    fig.add_shape(type="rect",x0=0,y0=0,x1=kw,y1=kd,line=dict(width=3))

    L=pat["Plate L"];W=pat["Plate W"]
    fw=pat["Part Footprint W"];fd=pat["Part Footprint D"]

    for rr in range(pat["Plate Rows"]):
        for cc in range(pat["Plate Cols"]):
            x0=cc*(W+PLATE_GAP_MM);y0=rr*(L+PLATE_GAP_MM)
            fig.add_shape(type="rect",x0=x0,y0=y0,x1=x0+W,y1=y0+L,line=dict(width=1))
            for pr in range(pat["Parts Along Plate"]):
                for pc in range(pat["Parts Across Plate"]):
                    px=x0+pc*(fw+PRODUCT_GAP_MM)
                    py=y0+pr*(fd+PRODUCT_GAP_MM)
                    if pat["Geometry"]=="CIRCULAR":
                        fig.add_shape(type="circle",x0=px,y0=py,x1=px+fw,y1=py+fd,line=dict(width=1))
                    else:
                        fig.add_shape(type="rect",x0=px,y0=py,x1=px+fw,y1=py+fd,line=dict(width=1))

    fig.update_xaxes(range=[0,kw],title="Kiln width / ความกว้างเตา (mm)",scaleanchor="y",scaleratio=1)
    fig.update_yaxes(range=[0,kd],title="Kiln depth / ความลึกเตา (mm)")
    fig.update_layout(title=f"Top view / มุมมองด้านบน — {kiln} — {pat['Plate']}",
                      height=650,showlegend=False)
    return fig


def pattern_side_figure(kiln,row,pat):
    import plotly.graph_objects as go
    kd,kw,kh=kiln_dimensions(kiln)
    fig=go.Figure()

    # Kiln side boundary.
    fig.add_shape(type="rect",x0=0,y0=0,x1=kw,y1=kh,line=dict(width=3))

    floors=min(pat["Floors Required"],pat["Max Physical Floors"])
    pitch=pat["Floor Pitch mm"]
    plate_t=pat["Plate T"]
    part_h=pat["Part Height"]

    for fl in range(floors):
        y=fl*pitch
        # I-block/leg zone
        fig.add_shape(type="rect",x0=0,y0=y,x1=kw,y1=y+pat["I-block Height mm"],line=dict(width=1))
        # Plate
        py=y+pat["I-block Height mm"]
        fig.add_shape(type="rect",x0=0,y0=py,x1=kw,y1=py+plate_t,line=dict(width=1))
        # Product height indication above plate
        prod_y=py+plate_t
        fig.add_shape(type="rect",x0=kw*0.08,y0=prod_y,x1=kw*0.92,y1=min(prod_y+part_h,kh),line=dict(width=1))
        fig.add_annotation(x=kw*0.5,y=min(prod_y+part_h/2,kh-5),
                           text=f"Floor {fl+1} / ชั้น {fl+1}",showarrow=False)

    if pat["Floors Required"] > pat["Max Physical Floors"]:
        fig.add_annotation(x=kw*0.5,y=kh*0.95,
                           text=f"REQUIRED {pat['Floors Required']} FLOORS > PHYSICAL MAX {pat['Max Physical Floors']}",
                           showarrow=False)

    fig.update_xaxes(range=[0,kw],title="Kiln width / ความกว้างเตา (mm)")
    fig.update_yaxes(range=[0,kh],title="Kiln height / ความสูงเตา (mm)")
    fig.update_layout(title=f"Side elevation / มุมมองด้านข้าง — required floors {pat['Floors Required']}",
                      height=650,showlegend=False)
    return fig


def load_pattern_summary(load_df,plate_choice="AUTO"):
    """
    Evaluate every WO in one kiln/date/program load. This avoids the old
    misleading situation where a load total was large but only one WO or a few
    floors were visualized.
    """
    rows=[]
    for _,r in load_df.iterrows():
        pat=best_pattern_for_part(r["Kiln"],r,plate_choice)
        if pat is None:
            rows.append({"Work Order":r["Work Order"],"Plan Qty":r["Plan Qty"],
                         "Pattern Feasible":False,"Reason":"No plate/I-block pattern found"})
            continue
        x={"Work Order":r["Work Order"],"Specification":r["Specification"],
           "Shape":r["Shape"],"Type":r["Type"],"Plan Qty":r["Plan Qty"]}
        x.update(pat)
        rows.append(x)
    return pd.DataFrame(rows)


def add_shift_and_ot_fields(df):
    if df is None or df.empty:
        return df
    x=df.copy()
    x["Standard Shift"]="08:00-17:00"
    x["Lunch"]="12:00-13:00"
    x["Breaks"]="10:00-10:10; 15:00-15:10"
    x["Normal Net Working h"]=NORMAL_NET_HOURS

    # Required OT is derived from section evidence where an hourly rate exists.
    def req_ot(r):
        qty=num(r.get("Plan Qty",0),0)
        phr=num(r.get("pcs/hour",0),0)
        normal=num(r.get("Normal pcs/8h",0),0)
        if phr>0 and normal>0:
            return max(0.0,(qty-normal)/phr)
        return 0.0
    x["Required OT h"]=x.apply(req_ot,axis=1)
    x["OT Recommendation"]=x["Required OT h"].apply(
        lambda h:"NO OT" if h<=0.01 else ("OT {:.1f} h".format(h))
    )
    return x


def delivery_risk_table(master, plans, issues):
    rows=[]
    for _,r in master.iterrows():
        wo=r["Work Order"]; due=pdate(r.get("Delivery Date"))
        pack=plans.get("Packing",pd.DataFrame())
        p=pack[pack["Work Order"]==wo] if pack is not None and not pack.empty else pd.DataFrame()
        pack_qty=float(pd.to_numeric(p.get("Plan Qty",pd.Series(dtype=float)),errors="coerce").fillna(0).sum()) if not p.empty else 0
        pack_date=max([pdate(v) for v in p.get("Plan Date",[]) if pdate(v)],default=None) if not p.empty else None
        demand=num(r.get("Packing Remaining Qty",0),0)
        short=max(demand-pack_qty,0)
        risk="LOW"
        reason="Packing target covered"
        if short>0:
            risk="HIGH"; reason="Packing demand not fully covered in planning horizon"
        elif due and pack_date and pack_date>due:
            risk="HIGH"; reason="Packing completion planned after customer due date"
        elif due and pack_date and (due-pack_date).days<=1:
            risk="MEDIUM"; reason="Packing completion has <=1 day delivery buffer"
        rows.append({
            "Work Order":wo,"Customer":r.get("Customer",""),"Specification":r.get("Specification",""),
            "Due Date":due,"Firing Date":pdate(r.get("Firing Date")),
            "Packing Target Date":pack_date,"Packing Demand Qty":demand,
            "Packing Planned Qty":pack_qty,"Packing Short Qty":short,
            "Delivery Risk":risk,"Risk Reason":reason,
            "Priority":r.get("Priority","")
        })
    return pd.DataFrame(rows).sort_values(["Delivery Risk","Due Date"],ascending=[True,True],na_position="last")


def daily_capacity_summary(plans):
    rows=[]
    for sec,df in plans.items():
        if df is None or df.empty: continue
        z=add_shift_and_ot_fields(df)
        for day,g in z.groupby("Plan Date"):
            rows.append({
                "Plan Date":day,"Section / กระบวนการ":sec,
                "Planned pcs":float(pd.to_numeric(g.get("Plan Qty",0),errors="coerce").fillna(0).sum()),
                "Planned kg":float(pd.to_numeric(g.get("Plan kg",0),errors="coerce").fillna(0).sum()),
                "Work Orders":g["Work Order"].nunique() if "Work Order" in g else 0,
                "Max Required OT h":float(pd.to_numeric(g.get("Required OT h",0),errors="coerce").fillna(0).max()),
                "OT Recommendation":"OT REQUIRED" if float(pd.to_numeric(g.get("Required OT h",0),errors="coerce").fillna(0).max())>0.01 else "NORMAL SHIFT",
                "Load Balance Status":"REVIEW OVERLOAD" if float(pd.to_numeric(g.get("Required OT h",0),errors="coerce").fillna(0).max())>0.01 else "WITHIN NORMAL CAPACITY",
                "Standard Shift":"08:00-17:00","Lunch":"12:00-13:00","Breaks":"10:00-10:10; 15:00-15:10"
            })
    return pd.DataFrame(rows)


def _section_daily_capacity_pcs(df):
    """Conservative daily capacity from the actual resource evidence already used by each released plan row."""
    if df is None or df.empty:return pd.DataFrame(columns=["Plan Date","Capacity pcs"])
    x=df.copy(); out=[]
    for day,g in x.groupby("Plan Date"):
        sec=txt(g["Section / กระบวนการ"].iloc[0])
        cap=0.0
        if sec=="Preparation":
            # Sum derived capacity is wrong because same daily kg pool repeats per WO.
            kgcap=pd.to_numeric(g.get("Capacity kg/day"),errors="coerce").dropna()
            kgpc=pd.to_numeric(g.get("Unit kg/pc"),errors="coerce").replace(0,pd.NA).dropna()
            if len(kgcap) and len(kgpc): cap=float(kgcap.iloc[0]/kgpc.mean())
        elif sec=="Mixing":
            # CAP-MO is batches/day; convert each assigned row using its actual average batch kg and kg/pc.
            for mc,mg in g.groupby("Machine"):
                bcap=pd.to_numeric(mg.get("CAP-โม่ Available"),errors="coerce").dropna()
                avgkg=pd.to_numeric(mg.get("Average Batch kg"),errors="coerce").dropna()
                kgpc=pd.to_numeric(mg.get("Unit kg/pc"),errors="coerce").replace(0,pd.NA).dropna()
                if len(bcap) and len(avgkg) and len(kgpc): cap+=float(bcap.max()*avgkg.mean()/kgpc.mean())
        elif sec=="Forming":
            if "Machine" in g:
                cap=float(g.groupby("Machine")["Capacity pcs/day"].max().sum())
        elif sec=="Packing":
            if "Capacity pcs/day" in g: cap=float(pd.to_numeric(g["Capacity pcs/day"],errors="coerce").max())
            elif "Capacity pcs/day/person" in g: cap=float(pd.to_numeric(g["Capacity pcs/day/person"],errors="coerce").max())
        elif sec=="Grinding / Cutting":
            for c in ["Capacity pcs/day","CAP/day"]:
                if c in g: cap=float(pd.to_numeric(g[c],errors="coerce").fillna(0).sum());break
        else:
            # Firing capacity is governed by released kiln loads, geometry and kg; use released qty as safe displayed pcs capacity.
            cap=float(pd.to_numeric(g.get("Plan Qty"),errors="coerce").fillna(0).sum())
        out.append({"Plan Date":pdate(day),"Capacity pcs":max(cap,0)})
    return pd.DataFrame(out)


def capacity_plan_actual_dataset(plan_map, actual_log):
    rows=[]
    actual=actual_log.copy() if actual_log is not None and not actual_log.empty else pd.DataFrame()
    if not actual.empty:
        actual["Actual Date"]=actual["Actual Date"].apply(pdate)
    for sec,df in plan_map.items():
        if df is None or df.empty:continue
        capdf=_section_daily_capacity_pcs(df)
        plan_days={pdate(v) for v in df["Plan Date"] if pdate(v)}
        actual_days=set()
        if not actual.empty:
            actual_days={pdate(v) for v in actual.loc[actual["Section / กระบวนการ"]==sec,"Actual Date"] if pdate(v)}
        for dt in sorted(plan_days|actual_days):
            g=df[df["Plan Date"].apply(pdate)==dt]
            planpcs=float(pd.to_numeric(g.get("Plan Qty",0),errors="coerce").fillna(0).sum()) if not g.empty else 0
            plankg=float(pd.to_numeric(g.get("Plan kg",0),errors="coerce").fillna(0).sum()) if not g.empty else 0
            planwo=int(g["Work Order"].nunique()) if not g.empty else 0
            caprow=capdf[capdf["Plan Date"]==dt]
            cappcs=float(caprow["Capacity pcs"].iloc[0]) if not caprow.empty else 0
            avgkgpc=plankg/planpcs if planpcs>0 else 0
            capkg=cappcs*avgkgpc
            a=actual[(actual["Actual Date"]==dt)&(actual["Section / กระบวนการ"]==sec)] if not actual.empty else pd.DataFrame()
            actpcs=float(pd.to_numeric(a.get("Actual Qty",0),errors="coerce").fillna(0).sum()) if not a.empty else 0
            actkg=float(pd.to_numeric(a.get("Actual kg",0),errors="coerce").fillna(0).sum()) if not a.empty else 0
            actwo=int(a["Work Order"].nunique()) if not a.empty else 0

            # WO capacity is informational only: no fabricated physical WO/day limit.
            rows.append({"Date":dt,"Section":sec,
                         "Capacity pcs":cappcs,"Plan pcs":planpcs,"Actual pcs":actpcs,
                         "Capacity ton":capkg/1000,"Plan ton":plankg/1000,"Actual ton":actkg/1000,
                         "Capacity WO":None,"Plan WO":planwo,"Actual WO":actwo})
    return pd.DataFrame(rows)


def monthly_backorder_report(order_events, ref_date):
    if order_events is None or order_events.empty:
        return pd.DataFrame()
    x=order_events.copy()
    x=x[x["Open Date"].notna()].copy()
    if x.empty:return pd.DataFrame()
    start=min(x["Open Date"])
    end=max(ref_date,max([d for d in x["Close Date"] if d is not None],default=ref_date))
    months=pd.period_range(pd.Timestamp(start),pd.Timestamp(end),freq="M")
    rows=[]
    for p in months:
        mend=p.end_time.date()
        mstart=p.start_time.date()
        opened=int(x["Open Date"].apply(lambda d:d is not None and mstart<=d<=mend).sum())
        closed=int(x["Close Date"].apply(lambda d:d is not None and mstart<=d<=mend).sum())
        backlog=int(x.apply(lambda r:r["Open Date"]<=mend and (r["Close Date"] is None or r["Close Date"]>mend),axis=1).sum())
        rows.append({"Month":p.strftime("%b-%Y"),"Opened WO":opened,"Closed WO":closed,"Open Backlog WO":backlog})
    return pd.DataFrame(rows)

def aggregate_cpa(df,period):
    if df.empty:return df
    x=df.copy(); x["Date"]=pd.to_datetime(x["Date"])
    if period=="Daily": x["Period"]=x["Date"].dt.strftime("%d-%b")
    elif period=="Weekly": x["Period"]=x["Date"].dt.to_period("W-MON").apply(lambda p:f"{p.start_time:%d-%b}–{p.end_time:%d-%b}")
    else: x["Period"]=x["Date"].dt.strftime("%b-%Y")
    nums=["Capacity pcs","Plan pcs","Actual pcs","Capacity ton","Plan ton","Actual ton","Capacity WO","Plan WO","Actual WO"]
    return x.groupby(["Period","Section"],as_index=False)[nums].sum()


def upcoming_delivery_risk(master, plan_map, refdate):
    risk=delivery_risk_table(master,plan_map,pd.DataFrame())
    if risk.empty:return risk
    risk["Days to Due"]=risk["Due Date"].apply(lambda d:(d-refdate).days if d else None)
    risk["Upcoming Window"]=risk["Days to Due"].apply(lambda n: "OVERDUE" if n is not None and n<0 else ("0-3 DAYS" if n is not None and n<=3 else ("4-7 DAYS" if n is not None and n<=7 else ("8-14 DAYS" if n is not None and n<=14 else ">14 DAYS"))))
    return risk.sort_values(["Days to Due","Delivery Risk"],na_position="last")

# ---------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------