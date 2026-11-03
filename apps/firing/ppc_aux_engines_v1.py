from __future__ import annotations
from pathlib import Path
from datetime import date, datetime
import math
import re
import pandas as pd
import openpyxl

def txt(v):
    if v is None: return ""
    s=str(v).strip()
    return "" if s.lower()=="nan" else s

def num(v, default=0.0):
    try:
        if v is None or (isinstance(v,str) and not v.strip()): return default
        return float(v)
    except Exception:
        return default

def pdate(v):
    if v is None: return None
    if isinstance(v, datetime): return v.date()
    if isinstance(v, date): return v
    if isinstance(v, (int,float)) and v > 20000:
        try:
            return (datetime(1899,12,30)+pd.to_timedelta(float(v),unit="D")).date()
        except Exception:
            return None
    try:
        return pd.to_datetime(v,errors="coerce").date()
    except Exception:
        return None

def is_closed(v):
    s=txt(v).lower().replace(" ","")
    return ("ปิด" in s and "ยังไม่ปิด" not in s) or s in {"closed","complete","completed"}

def due_priority(due, start_date):
    d=pdate(due)
    if d is None: return "LAST",99999
    days=(d-start_date).days
    if days < 0: return "OVERDUE",days
    if days <= 7: return "HIGH",days
    if days <= 14: return "MEDIUM",days
    return "LOW",days

def _sheet_or_raise(wb, name):
    if name not in wb.sheetnames:
        raise ValueError(f"Sheet `{name}` not found.")
    return wb[name]

def read_packaging_plan(plan_path, standard_path, planning_start):
    """Generate WO-wise packaging material plan from Plan 2026 + Packaging Standard.

    Plan 2026:
      A WO, E revised due date, F customer, H spec, J order qty,
      K product code, BF category, KX packing plan, KY packing actual,
      KZ packing status, LH overall WO closure.

    Packaging standard sheet `มาตรฐานการบรรจุ`:
      C product code, D customer, E spec, F group, G pcs/box,
      H outer box, I outer qty/box, J inner box, K inner qty/box,
      L insert, M insert qty/box, N brand.
    """
    wb=openpyxl.load_workbook(plan_path,data_only=True,read_only=True,keep_links=False)
    ws=_sheet_or_raise(wb,"แผนการเผา")
    rows=[]
    for er in range(4,ws.max_row+1):
        wo=txt(ws.cell(er,1).value)
        if not wo: continue
        closed=is_closed(ws.cell(er,216).value)  # LH
        if closed: continue
        pack_plan=num(ws.cell(er,310).value,0)   # KX
        pack_actual=num(ws.cell(er,311).value,0) # KY
        pending=max(pack_plan-pack_actual,0)
        if pending <= 0: continue
        due=ws.cell(er,5).value
        pri,_=due_priority(due,planning_start)
        rows.append({
            "Work Order":wo,"Due Date":pdate(due),"Priority":pri,
            "Customer":txt(ws.cell(er,6).value),"Specification":txt(ws.cell(er,8).value),
            "Product Code":txt(ws.cell(er,11).value),"Category":txt(ws.cell(er,58).value).upper(), # BF
            "Packing Plan pcs":pack_plan,"Packed Actual pcs":pack_actual,"Pending Packing pcs":pending,
            "Packing Status":txt(ws.cell(er,312).value), # KZ
            "Source Row":er
        })
    wb.close()
    demand=pd.DataFrame(rows)

    swb=openpyxl.load_workbook(standard_path,data_only=True,read_only=True,keep_links=False)
    sws=_sheet_or_raise(swb,"มาตรฐานการบรรจุ")
    std=[]
    for er in range(4,sws.max_row+1):
        code=txt(sws.cell(er,3).value)
        if not code: continue
        std.append({
            "Product Code":code,
            "Standard Customer":txt(sws.cell(er,4).value),
            "Standard Spec":txt(sws.cell(er,5).value),
            "Product Group":txt(sws.cell(er,6).value),
            "Pcs per Box":num(sws.cell(er,7).value,0),
            "Outer Box":txt(sws.cell(er,8).value),
            "Outer Qty / Box":num(sws.cell(er,9).value,0),
            "Inner Box":txt(sws.cell(er,10).value),
            "Inner Qty / Box":num(sws.cell(er,11).value,0),
            "Insert":txt(sws.cell(er,12).value),
            "Insert Qty / Box":num(sws.cell(er,13).value,0),
            "Brand / Label":txt(sws.cell(er,14).value),
            "Standard Row":er
        })
    swb.close()
    standard=pd.DataFrame(std).drop_duplicates("Product Code",keep="first")

    if demand.empty:
        return demand,standard,pd.DataFrame(),pd.DataFrame()
    plan=demand.merge(standard,on="Product Code",how="left")
    plan["Standard Found"]=plan["Pcs per Box"].fillna(0).gt(0)
    plan["Boxes Required"]=plan.apply(
        lambda r: math.ceil(r["Pending Packing pcs"]/r["Pcs per Box"])
        if num(r.get("Pcs per Box"),0)>0 else 0,axis=1
    )
    plan["Outer Required"]=plan["Boxes Required"]*plan["Outer Qty / Box"].fillna(0)
    plan["Inner Required"]=plan["Boxes Required"]*plan["Inner Qty / Box"].fillna(0)
    plan["Insert Required"]=plan["Boxes Required"]*plan["Insert Qty / Box"].fillna(0)
    plan["Issue"]=plan.apply(
        lambda r: "" if r["Standard Found"] else "PACKAGING STANDARD NOT FOUND",axis=1
    )
    plan["_due"]=plan["Due Date"].apply(lambda d:d or date(2099,12,31))
    plan=plan.sort_values(["_due","Source Row"]).drop(columns=["_due"]).reset_index(drop=True)

    mat_rows=[]
    for _,r in plan.iterrows():
        for typ,codecol,qtycol in [
            ("Outer Box","Outer Box","Outer Required"),
            ("Inner Box","Inner Box","Inner Required"),
            ("Insert","Insert","Insert Required")
        ]:
            code=txt(r.get(codecol,""))
            q=num(r.get(qtycol,0),0)
            if code and code not in {"-","0"} and q>0:
                mat_rows.append({"Material Type":typ,"Material Code":code,"Required Qty":q})
    materials=pd.DataFrame(mat_rows)
    if not materials.empty:
        materials=materials.groupby(["Material Type","Material Code"],as_index=False)["Required Qty"].sum()
        materials=materials.sort_values(["Material Type","Required Qty"],ascending=[True,False])
    missing=plan[~plan["Standard Found"]][
        ["Work Order","Due Date","Priority","Customer","Product Code","Specification","Pending Packing pcs","Issue"]
    ].copy()
    return plan,standard,materials,missing

def _clean_code(v):
    return re.sub(r"\s+"," ",txt(v)).strip()

def read_diamond_tooling(diamond_master_path, issue_path=None, horizon_months=2, usage_basis="Higher of average/latest"):
    """Stock/usage based diamond tooling plan.

    The supplied files do not contain a verified Product/WO -> Diamond consumption
    mapping, therefore this is intentionally NOT a WO-specific tooling calculation.
    """
    wb=openpyxl.load_workbook(diamond_master_path,data_only=True,read_only=True,keep_links=False)

    # Historical monthly usage
    ws=_sheet_or_raise(wb,"ปริมาณการใช้")
    month_headers=[]
    for c in range(6,18):  # F:Q, month 1..12 when present
        h=ws.cell(2,c).value
        try:
            m=int(float(h))
            if 1 <= m <= 12: month_headers.append((c,m))
        except Exception:
            pass
    usage=[]
    for r in range(3,ws.max_row+1):
        code=_clean_code(ws.cell(r,2).value)
        if not code: continue
        vals={m:num(ws.cell(r,c).value,0) for c,m in month_headers}
        nonzero=[v for v in vals.values() if v>0]
        avg_all=(sum(vals.values())/len(vals)) if vals else 0
        avg_active=(sum(nonzero)/len(nonzero)) if nonzero else 0
        usage.append({
            "Code":code,"Category":txt(ws.cell(r,3).value),"Item":txt(ws.cell(r,4).value),
            "Unit":txt(ws.cell(r,5).value),"Average / month":avg_all,
            "Average active month":avg_active,**{f"M{m}":v for m,v in vals.items()}
        })
    usage=pd.DataFrame(usage)

    # Reservations
    rws=_sheet_or_raise(wb,"สรุปจอง")
    reservations={}
    for r in range(4,rws.max_row+1):
        code=_clean_code(rws.cell(r,2).value)
        if code: reservations[code]=num(rws.cell(r,6).value,0)

    # Current diamond stock
    sws=_sheet_or_raise(wb,"ยอดคงเหลือ Diamond")
    stock=[]
    for r in range(4,sws.max_row+1):
        code=_clean_code(sws.cell(r,1).value)
        if not code: continue
        stock.append({
            "Code":code,"Stock Category":txt(sws.cell(r,2).value),
            "Stock Item":txt(sws.cell(r,3).value),"Unit":txt(sws.cell(r,4).value),
            "On Hand":num(sws.cell(r,5).value,0),"Alias / Base Item":txt(sws.cell(r,6).value),
            "Reserved":reservations.get(code,0)
        })
    stock=pd.DataFrame(stock)
    wb.close()

    # Latest issue month actual, filtered to codes present in master/stock.
    latest={}
    if issue_path:
        iwb=openpyxl.load_workbook(issue_path,data_only=True,read_only=True,keep_links=False)
        iws=iwb[iwb.sheetnames[0]]
        known=set(stock["Code"].astype(str)) | set(usage["Code"].astype(str))
        for r in range(2,iws.max_row+1):
            code=_clean_code(iws.cell(r,4).value)
            if code in known:
                latest[code]=latest.get(code,0)+num(iws.cell(r,8).value,0)
        iwb.close()

    if stock.empty:
        return pd.DataFrame(),usage

    p=stock.merge(usage[["Code","Category","Item","Average / month","Average active month"]] if not usage.empty else pd.DataFrame(columns=["Code"]),on="Code",how="left")
    p["Latest Issue Month"]=p["Code"].map(latest).fillna(0)
    p["Available"]=p["On Hand"]-p["Reserved"]
    if usage_basis=="Historical average":
        p["Planning Usage / month"]=p["Average / month"].fillna(0)
    elif usage_basis=="Latest issue month":
        p["Planning Usage / month"]=p["Latest Issue Month"].fillna(0)
    else:
        p["Planning Usage / month"]=p[["Average / month","Latest Issue Month"]].fillna(0).max(axis=1)
    p["Horizon Months"]=int(horizon_months)
    p["Expected Use in Horizon"]=p["Planning Usage / month"]*int(horizon_months)
    p["Projected Balance"]=p["Available"]-p["Expected Use in Horizon"]
    p["Tooling Requirement"]=(-p["Projected Balance"]).clip(lower=0)
    p["Months Cover"]=p.apply(
        lambda r: (r["Available"]/r["Planning Usage / month"]) if r["Planning Usage / month"]>0 else 999,axis=1
    )
    p["Risk"]=p.apply(
        lambda r: "SHORTAGE" if r["Projected Balance"]<0 else ("LOW COVER" if r["Months Cover"]<1 else "OK"),axis=1
    )
    p=p.sort_values(["Risk","Months Cover","Code"],key=lambda s:s.map({"SHORTAGE":0,"LOW COVER":1,"OK":2}) if s.name=="Risk" else s)
    return p.reset_index(drop=True),usage

def export_packaging_excel(plan,materials,missing,path):
    with pd.ExcelWriter(path,engine="xlsxwriter") as w:
        plan.to_excel(w,index=False,sheet_name="Packaging Plan")
        materials.to_excel(w,index=False,sheet_name="Material Summary")
        missing.to_excel(w,index=False,sheet_name="Missing Standards")

def export_diamond_excel(plan,usage,path):
    with pd.ExcelWriter(path,engine="xlsxwriter") as w:
        plan.to_excel(w,index=False,sheet_name="Diamond Tooling Plan")
        usage.to_excel(w,index=False,sheet_name="Usage History")
