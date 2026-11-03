from __future__ import annotations
from pathlib import Path
from datetime import date, datetime, timedelta
import io, math, re
import pandas as pd
import numpy as np
import openpyxl
from openpyxl.utils import column_index_from_string

import firing_engine_desktop_v2 as fire
import sl_daily_engine_v3_22_from_v17 as dailyeng
import sl_mps_mrp_engine_v2_4 as longeng
import ppc_aux_engines_v1 as aux

SECTIONS=["Preparation","Mixing","Forming","Firing","Grinding / Cutting","Packing"]
DEFAULT_MAP={
    "sheet":"แผนการเผา","data_start_row":4,
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
    'Net Weight g/pc':'AF',
    'Gross Weight g/pc':'AH',
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
}

def txt(v):
    if v is None:return ""
    try:
        if pd.isna(v): return ""
    except Exception: pass
    return str(v).strip()

def num(v,d=0.0):
    try:
        if v is None or txt(v)=="":return d
        return float(v)
    except Exception:return d

def pdate(v):
    if v is None:return None
    if isinstance(v,datetime):return v.date()
    if isinstance(v,date):return v
    try:
        x=pd.to_datetime(v,errors="coerce")
        return None if pd.isna(x) else x.date()
    except Exception:return None

def closed(v):
    s=txt(v).upper().replace(" ","")
    if "ยังไม่ปิด" in txt(v): return False
    return ("ปิด" in txt(v)) or s in {"CLOSED","FINISHED","DONE","COMPLETE","COMPLETED"}

def due_priority(due,start):
    d=pdate(due)
    if d is None:return "LAST"
    n=(d-start).days
    if n<0:return "OVERDUE"
    if n<=7:return "HIGH"
    if n<=14:return "MEDIUM"
    return "LOW"

def _idx(col):
    c=txt(col).replace("$","").upper()
    if not re.fullmatch(r"[A-Z]{1,3}",c): return None
    return column_index_from_string(c)-1

def norm_category(v):
    s=txt(v).upper()
    if s == 'F': return 'P'
    if s.startswith('PB'): return 'PB'
    if s[:1] in {'P','R','S','T','M'}: return s[:1]
    return 'UNCLASSIFIED'

def read_plan2026(path, mapping=None, wip_weight="NET"):
    mp=DEFAULT_MAP.copy(); mp.update(mapping or {})
    wb=openpyxl.load_workbook(path,data_only=True,read_only=True,keep_links=False)
    if mp["sheet"] not in wb.sheetnames: raise ValueError(f"Sheet {mp['sheet']} not found")
    ws=wb[mp["sheet"]]
    # Recognize the expanded Plan2026 layout before interpreting legacy columns.
    # This is an import guard only; no automatic scheduling/mapping change.
    _hdr=list(ws.iter_rows(min_row=3,max_row=3,max_col=312,values_only=True))[0]
    _expanded={'Preparation':('DW','DX','DY'),'Mixing':('FH','FI','FJ'),
               'Forming':('GS','GT','GU'),'Firing':('IB','IC','IE'),
               'Grinding / Cutting':('JM','JN','JO'),'Packing':('KX','KY','KZ')}
    if all('จำนวน' in txt(_hdr[_idx(cs[0])]) for cs in _expanded.values()):
        _bad=[]
        for sec,cs in _expanded.items():
            for suffix,col in zip(('Plan','Actual','Status'),cs):
                if txt(mp.get(sec+' '+suffix)).upper()!=col:_bad.append(sec+' '+suffix+'='+col)
        if _bad:
            wb.close()
            raise ValueError('Plan2026 column layout differs from the selected mapping. Verify and set '+
                             ', '.join(_bad)+'. Also verify date, weight, closure and reject columns before planning. No plan was calculated.')
    idx={k:_idx(v) for k,v in mp.items() if k not in {"sheet","data_start_row"} and _idx(v) is not None}
    maxc=max(idx.values())+1
    rows=[]
    for er,vals in enumerate(ws.iter_rows(min_row=int(mp.get("data_start_row",4)),max_col=maxc,values_only=True),start=int(mp.get("data_start_row",4))):
        def g(k):
            i=idx.get(k); return vals[i] if i is not None and i<len(vals) else None
        wo=txt(g("WO"))
        if not wo:continue
        r={
            "Source Row":er,"Work Order":wo,"WO Date":pdate(g("WO Date")),"Warehouse Target":pdate(g("Warehouse Target")),"ORDER":txt(g("ORDER")),"Due Date":pdate(g("Due Date")),"Customer":txt(g("Customer")),
            "Specification":txt(g("Specification")),"Order Qty":num(g("Order Qty")),"Product Code":txt(g("Product Code")),
            "Product Type":txt(g("Product Type")),"D":num(g("D")),"T":num(g("T")),"H":num(g("H")),
            "Program":txt(g("Program")),"Category":norm_category(g("Category")),"Shape":txt(g("Shape")),"Cut Factor":num(g("Cut Factor"),1),
            "Net Weight g/pc":num(g("Net Weight g/pc")),"Gross Weight g/pc":num(g("Gross Weight g/pc")),
            "WO Closure":txt(g("WO Closure")),"Packing Status Raw":txt(g("Packing Status")),"Overall Closed":(closed(g("WO Closure")) or closed(g("Packing Status"))),
            "Plan2026 Firing Date":pdate(g("Plan2026 Firing Date")),"Firing Exit Date":pdate(g("Firing Exit Date")),"Firing Issue":txt(g("Firing Issue")),
            "Actual Warehouse Date":pdate(g("Actual Warehouse Date")),"NCR":num(g("NCR")),"APPROVE":num(g("APPROVE")),"REJECT":num(g("REJECT")),"Sales Delivery Date":pdate(g("Sales Delivery Date")),
        }
        for sec in SECTIONS:
            r[f"{sec} Plan"]=num(g(f"{sec} Plan")); r[f"{sec} Actual"]=num(g(f"{sec} Actual")); r[f"{sec} Status"]=txt(g(f"{sec} Status"))
        rows.append(r)
    wb.close()
    df=pd.DataFrame(rows)
    if df.empty:return df
    for sec in SECTIONS:
        df[f"{sec} Remaining"]=(df[f"{sec} Plan"]-df[f"{sec} Actual"]).clip(lower=0)
    a={s:pd.to_numeric(df[f"{s} Actual"],errors="coerce").fillna(0) for s in SECTIONS}
    df["Eff Preparation"]=pd.concat([a[s] for s in SECTIONS],axis=1).max(axis=1)
    df["Eff Mixing"]=pd.concat([a[s] for s in SECTIONS[1:]],axis=1).max(axis=1)
    df["Eff Forming"]=pd.concat([a[s] for s in SECTIONS[2:]],axis=1).max(axis=1)
    df["Eff Firing"]=pd.concat([a[s] for s in SECTIONS[3:]],axis=1).max(axis=1)
    df["Eff Grinding / Cutting"]=pd.concat([a[s] for s in SECTIONS[4:]],axis=1).max(axis=1)
    df["Eff Packing"]=a["Packing"]
    df["WIP Preparation"]=(df["Order Qty"]-df["Eff Preparation"]).clip(lower=0)
    df["WIP Mixing"]=(df["Eff Preparation"]-df["Eff Mixing"]).clip(lower=0)
    df["WIP Forming"]=(df["Eff Mixing"]-df["Eff Forming"]).clip(lower=0)
    df["WIP Firing"]=(df["Eff Forming"]-df["Eff Firing"]).clip(lower=0)
    df["WIP Grinding / Cutting"]=(df["Eff Firing"]-df["Eff Grinding / Cutting"]).clip(lower=0)
    df["WIP Packing"]=(df["Eff Grinding / Cutting"]-df["Eff Packing"]).clip(lower=0)
    for c in [f"WIP {s}" for s in SECTIONS]: df.loc[df["Overall Closed"],c]=0
    weightcol="Net Weight g/pc" if wip_weight.upper()=="NET" else "Gross Weight g/pc"
    df["Unit kg/pc"]=df[weightcol]/1000.0
    df["Open Qty"]=(df["Order Qty"]-df["Eff Packing"]).clip(lower=0).where(~df["Overall Closed"],0)
    df["Open Weight kg"]=df["Open Qty"]*df["Unit kg/pc"]
    df["Priority"]=df["Due Date"].apply(lambda d:due_priority(d,date.today()))
    return df

def firing_raw_from_plan(df, planning_start, gross=True):
    rows=[]
    for _,r in df.iterrows():
        ready=max(num(r["Eff Forming"])-num(r["Eff Firing"]),0)
        w=(num(r["Gross Weight g/pc"]) if gross else num(r["Net Weight g/pc"]))/1000.0
        rows.append({
            "Work Order":r["Work Order"],"Category":r["Category"],"Customer":r["Customer"],"Specification":r["Specification"],
            "Product Type":r["Product Type"],"Shape":r["Shape"],"D / Length mm":r["D"],"T / Width mm":r["T"],"H / Hole mm":r["H"],
            "Order Qty":r["Order Qty"],"Remaining Qty":ready,"Weight kg/pc":w,"Program":r["Program"],"Due Date":r["Due Date"],
            "Priority":due_priority(r["Due Date"],planning_start),"Compatible?":"YES","Notes":"","Order Status":"CLOSED" if r["Overall Closed"] else "OPEN",
            "Preparation Status":r["Preparation Status"],"Mixing Status":r["Mixing Status"],"Forming Status":r["Forming Status"],"Firing Status":r["Firing Status"],
            "Preparation Actual Qty":r["Preparation Actual"],"Mixing Actual Qty":r["Mixing Actual"],"Forming Actual Qty":r["Forming Actual"],
            "Firing Actual Qty":r["Firing Actual"],"Grinding Actual Qty":r["Grinding / Cutting Actual"],"Packing Actual Qty":r["Packing Actual"],
            "Geometry Override":""
        })
    return pd.DataFrame(rows)

def run_firing(plan_df, capacity_path, planning_start, target=.80,maxv=.95,partial=False,urgent_partial=True,starts=2,overrides=None,kiln_editor_override=None):
    settings=fire.Settings(planning_start=planning_start,target_volume=target,max_volume=maxv,allow_partial=partial,allow_urgent_partial=urgent_partial,vitrified_starts_per_day=int(starts))
    fire.CURRENT_SETTINGS=settings
    fire.load_firing_capacity_master(str(capacity_path))
    raw=firing_raw_from_plan(plan_df,planning_start,True)
    for wo,ov in (overrides or {}).items():
        m=raw["Work Order"].astype(str)==str(wo)
        for k,v in ov.items():
            if k in raw.columns: raw.loc[m,k]=v
    prepared=fire.prepare_orders(raw,settings)
    kiln_editor=kiln_editor_override.copy() if kiln_editor_override is not None else fire.default_kilns(settings)
    kilns=fire.prepare_kilns(kiln_editor,settings)
    result=fire.build_plan(prepared,kilns.copy(),settings)
    return {"settings":settings,"prepared":prepared,"kiln_editor":kiln_editor,"loads":result[0],"details":result[1],"floor":result[2],"exceptions":result[3],"final_kilns":result[4]}

def firing_anchor(fr):
    d=fr["details"].copy()
    if d.empty:return pd.DataFrame()
    ren={}
    if "Qty pcs" in d.columns:ren["Qty pcs"]="Firing Qty"
    elif "Qty" in d.columns:ren["Qty"]="Firing Qty"
    if "Load Date" in d.columns:ren["Load Date"]="Firing Date"
    if "Unload / Take-Out Date" in d.columns:ren["Unload / Take-Out Date"]="Firing Complete"
    d=d.rename(columns=ren)
    for c in ["Firing Qty","Firing Date","Firing Complete"]:
        if c not in d.columns:d[c]=0 if c=="Firing Qty" else None
    if "kg/pc" not in d.columns:
        d["kg/pc"]=d["Weight kg/pc"] if "Weight kg/pc" in d.columns else 0
    cols=[c for c in ["Work Order","Firing Qty","Firing Date","Firing Complete","kg/pc","Kiln","Program","Priority","Due Date"] if c in d.columns]
    a=d[cols].copy()
    agg={"Firing Qty":"sum","Firing Date":"min","Firing Complete":"max","kg/pc":"first"}
    for c in ["Kiln","Program","Priority","Due Date"]:
        if c in a.columns:agg[c]="first"
    return a.groupby("Work Order",as_index=False).agg(agg)

def run_daily(plan_path,capacity_path,planning_start,fr,horizon=30,prep_capacity=1200,packing_people=1,mapping=None):
    mp=DEFAULT_MAP.copy();mp.update(mapping or {})
    dm={"sheet":mp["sheet"],"data_start_row":mp["data_start_row"],"WO":mp["WO"],"Due Date":mp["Due Date"],"Customer":mp["Customer"],"Specification":mp["Specification"],"Order Qty":mp["Order Qty"],"Product Code":mp["Product Code"],"Product Type":mp["Product Type"],"D":mp["D"],"T":mp["T"],"H":mp["H"],"Category":mp["Category"],"Shape":mp["Shape"],"Weight g/pc":mp["Gross Weight g/pc"],"WO Closure":mp["WO Closure"],"Plan2026 Firing Date":mp["Plan2026 Firing Date"]}
    for sec in SECTIONS:
        dm[f"{sec} Plan"]=mp[f"{sec} Plan"];dm[f"{sec} Actual"]=mp[f"{sec} Actual"];dm[f"{sec} Status"]=mp[f"{sec} Status"]
    with open(plan_path,"rb") as f: plan,_,_=dailyeng.read_plan2026(f,dm)
    with open(capacity_path,"rb") as f: mix,form,kiln,grind,pack,evidence=dailyeng.read_capacity(f)
    anch=firing_anchor(fr)
    if anch.empty:raise ValueError("Create Firing Plan first; Daily Plan pulls backward from firing schedule.")
    master=dailyeng.merge_master(plan,anch,planning_start)
    end=planning_start+timedelta(days=int(horizon)-1)
    prep,ip=dailyeng.schedule_preparation(master,planning_start,end,float(prep_capacity))
    mixing,im=dailyeng.schedule_mixing(master,planning_start,end,mix,prep,0.0)
    forming,ifo=dailyeng.schedule_forming(master,planning_start,end,form,mixing,0.0)
    firing,ifi=dailyeng.schedule_firing(master,forming,kiln)
    grinding,ig=dailyeng.schedule_grinding(master,firing,grind,planning_start,end)
    packing,ipa=dailyeng.schedule_packing(master,grinding,pack,planning_start,end,int(packing_people))
    result={"Preparation":prep,"Mixing":mixing,"Forming":forming,"Firing":firing,"Grinding / Cutting":grinding,"Packing":packing,"master":master,"capacity_evidence":evidence}
    issues=[x for x in [ip,im,ifo,ifi,ig,ipa] if x is not None and not x.empty]
    result["issues"]=pd.concat(issues,ignore_index=True,sort=False) if issues else pd.DataFrame()
    frames=[]
    for sec in SECTIONS:
        x=result[sec]
        if x is not None and not x.empty:
            y=x.copy(); y["Section"]=sec; frames.append(y)
    result["all"]=pd.concat(frames,ignore_index=True,sort=False) if frames else pd.DataFrame()
    return result

def wip_summary(df):
    rows=[]
    for sec in SECTIONS:
        q=df[f"WIP {sec}"]
        rows.append(pd.DataFrame({"Category":df["Category"],"Section":sec,"Qty pcs":q,"Weight kg":q*df["Unit kg/pc"]}))
    x=pd.concat(rows,ignore_index=True)
    return x.groupby(["Category","Section"],as_index=False).agg(**{"Qty pcs":("Qty pcs","sum"),"Weight kg":("Weight kg","sum")})

def risk_analysis(df, planning_start=None):
    planning_start=planning_start or date.today(); rows=[]
    for _,r in df.iterrows():
        if r["Overall Closed"]:continue
        due=r["Due Date"]; days=(due-planning_start).days if due else 99999
        stage="Packing"
        for s in SECTIONS:
            if num(r[f"WIP {s}"])>0: stage=s;break
        openq=num(r["Open Qty"]); risk="LOW"; reason=""
        if due is None:risk="DATA";reason="No valid revised due date"
        elif days<0:risk="CRITICAL";reason="Overdue open WO"
        elif days<=3 and stage not in {"Packing"}:risk="HIGH";reason=f"Due in {days} d, WIP at {stage}"
        elif days<=7:risk="MEDIUM";reason=f"Due in {days} d"
        if num(r["Gross Weight g/pc"])<=0 and openq>0:
            reason=(reason+"; " if reason else "")+"Gross weight missing"
            if risk=="LOW":risk="DATA"
        rows.append({"Risk":risk,"Work Order":r["Work Order"],"Category":r["Category"],"Customer":r["Customer"],"Due Date":due,"Days to Due":days if days<90000 else None,"Current WIP Stage":stage,"Open Qty pcs":openq,"Open Weight kg":num(r["Open Weight kg"]),"Reason":reason})
    rank={"CRITICAL":0,"HIGH":1,"MEDIUM":2,"DATA":3,"LOW":4}
    out=pd.DataFrame(rows)
    if not out.empty:
        out["_r"]=out.Risk.map(rank).fillna(9);out=out.sort_values(["_r","Due Date"],na_position="last").drop(columns="_r")
    return out

def audit_compare(system_df,audit_path=None,wo_col="A",qty_col="B",sheet=None):
    # Theoretical current WIP = sum of process-position WIP from Plan2026.
    theo=system_df.copy(); theo["Theoretical WIP pcs"]=sum(theo[f"WIP {s}"] for s in SECTIONS)
    base=theo[["Work Order","Category","Customer","Theoretical WIP pcs","Unit kg/pc"]].copy()
    if not audit_path:
        base["Actual Audit pcs"]=np.nan;base["Difference pcs"]=np.nan;base["Difference kg"]=np.nan;base["Audit Status"]="AUDIT FILE NOT LOADED";return base
    wb=openpyxl.load_workbook(audit_path,data_only=True,read_only=True,keep_links=False)
    ws=wb[sheet] if sheet and sheet in wb.sheetnames else wb[wb.sheetnames[0]]
    wi=_idx(wo_col); qi=_idx(qty_col); maxc=max(wi,qi)+1; rows=[]
    for vals in ws.iter_rows(min_row=2,max_col=maxc,values_only=True):
        wo=txt(vals[wi] if wi<len(vals) else None); q=num(vals[qi] if qi<len(vals) else 0)
        if wo:rows.append((wo,q))
    wb.close(); actual=pd.DataFrame(rows,columns=["Work Order","Actual Audit pcs"]).groupby("Work Order",as_index=False)["Actual Audit pcs"].sum()
    out=base.merge(actual,on="Work Order",how="left");out["Actual Audit pcs"]=out["Actual Audit pcs"].fillna(0);out["Difference pcs"]=out["Actual Audit pcs"]-out["Theoretical WIP pcs"];out["Difference kg"]=out["Difference pcs"]*out["Unit kg/pc"];out["Audit Status"]=np.where(out["Difference pcs"].abs()<1e-9,"MATCH","DIFFERENCE")
    return out.sort_values("Difference pcs",key=lambda s:s.abs(),ascending=False)

def run_longterm(sales_path,plan_path,stock_path,capacity_path,year,start_month=1,mode="MAX(Sales Forecast, Firm Open Orders)",wd=26,hd=8):
    with open(sales_path,"rb") as f:sales_bytes=f.read()
    with open(stock_path,"rb") as f:stock_bytes=f.read()
    with open(plan_path,"rb") as f:plan_bytes=f.read()
    with open(capacity_path,"rb") as f:cap_bytes=f.read()
    sales_base,sales_long=longeng.parse_sales(sales_bytes)
    master,bom,form,meta=longeng.parse_product_capacity(cap_bytes)
    stock=longeng.parse_stock(stock_bytes);plan=longeng.parse_plan2026(plan_bytes)
    materials=sorted(set(bom.Material.tolist() if not bom.empty else [])|set(stock.Material.tolist() if not stock.empty else []))
    policy=pd.DataFrame({"Material":materials,"Supplier":"","Lead Time days":30.0,"Safety Stock t":0.0,"MOQ t":0.0,"Order Multiple t":0.0,"Price per kg":np.nan})
    model=longeng.build_model(sales_long,sales_base,master,bom,stock,plan,form,meta,int(year),int(start_month),mode,int(wd),float(hd),policy)
    return {"model":model,"sales_base":sales_base,"master":master,"bom":bom,"stock":stock,"policy":policy,"meta":meta}

def save_longterm(result,path):
    b=longeng.export_excel(result["model"],result["sales_base"],result["master"],result["bom"],result["stock"],result["policy"],result["meta"]);Path(path).write_bytes(b)

def export_frames(path,frames):
    with pd.ExcelWriter(path,engine="xlsxwriter") as w:
        used=set()
        for name,df in frames.items():
            if df is None:continue
            sn=re.sub(r'[:\\/?*\[\]]','_',str(name))[:31] or 'Sheet'
            base=sn;n=1
            while sn in used:n+=1;sn=(base[:27]+f'_{n}')[:31]
            used.add(sn)
            df.to_excel(w,index=False,sheet_name=sn)
