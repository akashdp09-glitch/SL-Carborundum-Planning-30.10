
from __future__ import annotations
from datetime import date, datetime, timedelta
from pathlib import Path
import math, re
import pandas as pd
import ppc_desktop_core_v1_9 as core
import firing_engine_desktop_v2 as fire
import sl_daily_engine_v3_22_from_v17 as dailyeng
import sl_mps_mrp_engine_v2_4 as longeng

# Legacy geometry helpers use module-level settings/furniture. Serialize runs so
# two planner sessions cannot overwrite one another's settings mid-calculation.
import threading
from functools import wraps
_FIRING_RUN_LOCK=threading.RLock()
def _serial_firing(function):
    @wraps(function)
    def run(*args,**kwargs):
        with _FIRING_RUN_LOCK:return function(*args,**kwargs)
    return run

# Cache content, not mutable planning results. Every caller receives independent tables.
_CAPACITY_CACHE={}
def _read_capacity_cached(capacity_path):
    import hashlib, io, copy
    data=Path(capacity_path).read_bytes()
    key=hashlib.sha256(data).hexdigest()
    if key not in _CAPACITY_CACHE:
        parsed=dailyeng.read_capacity(io.BytesIO(data))
        if len(_CAPACITY_CACHE)>=3: _CAPACITY_CACHE.pop(next(iter(_CAPACITY_CACHE)))
        _CAPACITY_CACHE[key]=parsed
    return copy.deepcopy(_CAPACITY_CACHE[key])

def safe_date(v):
    if v is None: return None
    try:
        if pd.isna(v): return None
    except Exception: pass
    if isinstance(v, pd.Timestamp): return v.date()
    if isinstance(v, datetime): return v.date()
    if isinstance(v, date): return v
    try:
        x=pd.to_datetime(v,errors='coerce')
        return None if pd.isna(x) else x.date()
    except Exception: return None

def sanitize_dates(df):
    if df is None or not isinstance(df,pd.DataFrame): return df
    d=df.copy()
    for c in d.columns:
        if 'DATE' in str(c).upper() or 'DAY' in str(c).upper():
            d[c]=d[c].apply(lambda v: safe_date(v) if not isinstance(v,str) else (safe_date(v) or v))
    d=d.astype(object).where(pd.notna(d), None)
    return d


CLOSED_SET={"ปิดใบสั่ง","CLOSED","DONE","FINISHED"}

def txt(v): return "" if pd.isna(v) else str(v).strip()
def num(v,d=0.0):
    try:return float(v)
    except:return d
def is_closed(v): return txt(v).upper() in {x.upper() for x in CLOSED_SET}

def dim_values(v):
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?",txt(v))]
def maxdim(v):
    a=dim_values(v); return max(a) if a else 0.0
def mindim(v):
    a=dim_values(v); return min(a) if a else 0.0
def tapered(v): return len(dim_values(v))>=2 and abs(maxdim(v)-mindim(v))>1e-9

def looks_honing(r):
    s=" ".join(txt(r.get(k,"")) for k in ["Product Type","Specification","Shape","Category"]).upper()
    return any(x in s for x in ["HONING","HONNING","HONE","HONN","หินลับมีด"])
def looks_segment(r):
    s=re.sub(r"[^A-Z0-9]","", " ".join(txt(r.get(k,"")) for k in ["Product Type","Specification","Shape","Category"]).upper())
    return any(x in s for x in ["SEGMENT","SEGMENTR","SEGMNT","SEGMEN","SEMENT"])
def is_khat_phuen(r):
    return "ขัดพื้น" in txt(r.get("Shape",""))
def geometry_kind(r):
    cat=txt(r.get("Category","")).upper()
    if is_khat_phuen(r) or looks_honing(r) or looks_segment(r) or cat in {"S","T"}: return "RECTANGULAR"
    return "CIRCULAR"
def postfire_route(r):
    if looks_honing(r) or looks_segment(r):
        return "CUTTING / ตัด"
    if geometry_kind(r)=="RECTANGULAR":
        return "CLEANING / ทำความสะอาด"
    return "GRINDING / เจียร"


def classify_test_work(product_code, override="AUTO"):
    """Controlled Plan2026 rule: ONLY first character of Product Code decides test work.
    1xxxx = TEST; 4xxxx = TEST-M axis grinding wheel; all others (e.g. 2GW...) = NORMAL.
    """
    code=txt(product_code).strip()
    first=code[:1]
    ov=txt(override).strip().upper() or "AUTO"
    is_test=(first == "1")
    if ov=="NORMAL": is_test=False
    elif ov=="TEST": is_test=True
    test_type=("TEST-M / งานทดสอบ M - AXIS GRINDING WHEEL" if is_test and first=="4" and ov!="TEST" else ("TEST / งานทดสอบ" if is_test else "NORMAL / งานปกติ"))
    return code,is_test,test_type

def firing_input(plan_df, planning_start, strict_forming=True):
    rows=[]
    for _,r in plan_df.iterrows():
        cat=txt(r.get("Category","")).upper()
        program=txt(r.get("Program",""))
        # Factory rule: R category always P2.
        if cat=="R": program="P2"
        form_actual=num(r.get("Eff Forming",r.get("Forming Actual",0)))
        fire_actual=num(r.get("Eff Firing",r.get("Firing Actual",0)))
        ready=max(form_actual-fire_actual,0)
        form_closed=is_closed(r.get("Forming Status",""))
        # Production Manager feedback: a WO must not be released just because it has
        # some forming actual if forming is still open, unless planner explicitly allows partial.
        release_ready=ready if (form_closed or not strict_forming) else 0
        gross=num(r.get("Gross Weight g/pc",0))/1000.0
        product_code,test_work,test_work_type=classify_test_work(r.get("Product Code",""),r.get("Test Work Override","AUTO"))
        rows.append({
            "Work Order":txt(r.get("Work Order","")),"Category":cat,
            "Product Code":product_code,"Test Work Override":txt(r.get("Test Work Override","AUTO")),"Test Work":("YES / งานทดสอบ" if test_work else "NO / งานขาย"),
            "Test Work Type":test_work_type,
            "Customer":txt(r.get("Customer","")),"Specification":txt(r.get("Specification","")),
            "Product Type":txt(r.get("Product Type","")),"Shape":txt(r.get("Shape","")),
            "D / Length mm":r.get("D",""),"T / Width mm":r.get("T",""),"H / Hole mm":r.get("H",""),
            "Order Qty":num(r.get("Order Qty",0)),"Remaining Qty":release_ready,"Candidate Ready Qty":ready,
            "Weight kg/pc":gross,"Program":program,"Due Date":safe_date(r.get("Due Date")),
            "Priority":core.due_priority(r.get("Due Date"),planning_start),"Compatible?":"YES","Notes":"",
            "Order Status":"CLOSED" if bool(r.get("Overall Closed",False)) else "OPEN",
            "Preparation Status":r.get("Preparation Status",""),"Mixing Status":r.get("Mixing Status",""),
            "Forming Status":r.get("Forming Status",""),"Firing Status":r.get("Firing Status",""),
            "Preparation Actual Qty":num(r.get("Preparation Actual",0)),
            "Mixing Actual Qty":num(r.get("Mixing Actual",0)),
            "Forming Actual Qty":num(r.get("Forming Actual",0)),
            "Firing Actual Qty":num(r.get("Firing Actual",0)),
            "Grinding Actual Qty":num(r.get("Grinding / Cutting Actual",0)),
            "Packing Actual Qty":num(r.get("Packing Actual",0)),
            "Geometry Override":"",
            "Strict Forming Block": bool(strict_forming and ready>0 and not form_closed),
        })
    return pd.DataFrame(rows)

def pm_validation(plan_df, raw, prepared, details=None):
    """Production-manager feedback translated into release controls."""
    rows=[]
    dup=plan_df["Work Order"].astype(str).value_counts() if not plan_df.empty else pd.Series(dtype=int)
    allocated=set()
    if details is not None and not details.empty and "Work Order" in details.columns:
        allocated=set(details["Work Order"].astype(str))
    pmap={str(r["Work Order"]):r for _,r in prepared.iterrows()} if prepared is not None and not prepared.empty else {}
    for _,r in raw.iterrows():
        wo=txt(r.get("Work Order",""))
        if not wo:continue
        cat=txt(r.get("Category","")).upper()
        reason_group="OK / พร้อมปล่อยแผน"; reason="Ready"; action="RELEASE"
        if bool(r.get("Strict Forming Block",False)):
            reason_group="1. Upstream Process / กระบวนการผลิตก่อนหน้า"
            reason="Forming not closed; parts are still in upstream process / ขึ้นรูปยังไม่ปิด งานยังไม่พร้อมเข้าเผา"
            action="HOLD - WAIT FORMING CLOSE / รอปิดขึ้นรูป"
        elif is_closed(r.get("Order Status","")) or is_closed(r.get("Firing Status","")):
            reason_group="3. Completed / Pre-fired / งานเสร็จหรือเผาแล้ว"
            reason="WO or Firing already closed / ใบสั่งหรือเผาปิดแล้ว"
            action="REMOVE"
        elif dup.get(wo,0)>1:
            reason_group="2. Planning & Scheduling / การประสานงานและวางแผน"
            reason="Duplicate WO exists in source data / พบ WO ซ้ำในข้อมูลต้นทาง"
            action="CONFIRM / ตรวจสอบซ้ำ"
        elif num(r.get("Remaining Qty",0))<=0 and num(r.get("Candidate Ready Qty",0))<=0:
            reason_group="1. Upstream Process / กระบวนการผลิตก่อนหน้า"
            reason="No verified Forming-to-Firing WIP / ไม่มี WIP จากขึ้นรูปพร้อมเข้าเผา"
            action="HOLD"
        elif cat=="R" and txt(r.get("Program","")).upper()!="P2":
            reason_group="2. Planning & Scheduling / การประสานงานและวางแผน"
            reason="R category must use Program P2 / กลุ่ม R ต้องใช้โปรแกรม P2"
            action="AUTO-CORRECT TO P2"
        elif wo not in allocated and num(r.get("Remaining Qty",0))>0:
            pr=pmap.get(wo,{})
            chk=txt(pr.get("Data Check","")) if hasattr(pr,"get") else ""
            reason_group="4. Kiln Constraints / ข้อจำกัดของเตาเผา"
            reason="Ready quantity not allocated to a kiln"
            if chk: reason += " | "+chk
            action="CHECK KILN / FURNITURE / PROGRAM"
        rows.append({"Work Order":wo,"Category":cat,"Program":r.get("Program",""),
                     "Candidate Ready Qty":num(r.get("Candidate Ready Qty",0)),
                     "Released Qty Input":num(r.get("Remaining Qty",0)),
                     "PL Mgr Cause Group / กลุ่มสาเหตุ":reason_group,
                     "Reason / สาเหตุ":reason,"Required Action / การดำเนินการ":action})
    return pd.DataFrame(rows)

def run_firing_fast(plan_df, capacity_path, planning_start, target=.80,maxv=.95,partial=False,
                    urgent_partial=True,starts=2,strict_forming=True,kiln_editor=None,
                    plate_master=None,iblock_master=None):
    fire.CURRENT_SETTINGS=fire.Settings(planning_start=planning_start,target_volume=target,max_volume=maxv,
                                       allow_partial=partial,allow_urgent_partial=urgent_partial,
                                       vitrified_starts_per_day=int(starts))
    settings=fire.CURRENT_SETTINGS
    fire.load_firing_capacity_master(str(capacity_path))
    if plate_master is not None and not plate_master.empty:
        fire.PLATE_MASTER=[x for x in plate_master.to_dict("records")]
    if iblock_master is not None and not iblock_master.empty:
        fire.IBLOCK_MASTER=[x for x in iblock_master.to_dict("records")]
    raw=firing_input(plan_df,planning_start,strict_forming)
    prepared=fire.prepare_orders(raw,settings)
    ked=kiln_editor.copy() if kiln_editor is not None else fire.default_kilns(settings)
    kilns=fire.prepare_kilns(ked,settings)
    loads,details,floor,exceptions,final_kilns=fire.build_plan(prepared,kilns.copy(),settings)
    validation=pm_validation(plan_df,raw,prepared,details)
    return {"settings":settings,"raw":raw,"prepared":prepared,"kiln_editor":ked,
            "loads":loads,"details":details,"floor":floor,"exceptions":exceptions,
            "final_kilns":final_kilns,"pm_validation":validation,
            "plate_master":pd.DataFrame(fire.PLATE_MASTER),"iblock_master":pd.DataFrame(fire.IBLOCK_MASTER)}

def firing_anchor(fr):
    d=fr["details"].copy()
    if d.empty:return pd.DataFrame()
    # Some historical engine layers can create duplicate column labels.
    # Keep the first occurrence so pandas groupby is stable across versions.
    d=d.loc[:,~d.columns.duplicated()].copy()
    ren={}
    if "Qty pcs" in d.columns:ren["Qty pcs"]="Firing Qty"
    elif "Qty" in d.columns:ren["Qty"]="Firing Qty"
    if "Load Date" in d.columns:ren["Load Date"]="Firing Date"
    if "Unload / Take-Out Date" in d.columns:ren["Unload / Take-Out Date"]="Firing Complete"
    d=d.rename(columns=ren)
    d=d.loc[:,~d.columns.duplicated()].copy()
    if "Firing Qty" not in d.columns:d["Firing Qty"]=0
    if "Firing Date" not in d.columns:d["Firing Date"]=None
    if "Firing Complete" not in d.columns:d["Firing Complete"]=None
    if "kg/pc" not in d.columns:d["kg/pc"]=d["Weight kg/pc"] if "Weight kg/pc" in d.columns else 0
    cols=[c for c in ["Work Order","Firing Qty","Firing Date","Firing Complete","kg/pc","Kiln","Program","Priority","Due Date"] if c in d.columns]
    agg={"Firing Qty":"sum","Firing Date":"min","Firing Complete":"max","kg/pc":"first"}
    for c in ["Kiln","Program","Priority","Due Date"]:
        if c in cols:agg[c]="first"
    return d[cols].groupby("Work Order",as_index=False).agg(agg)

def plan_to_daily(plan_df):
    rows=[]
    for i,r in plan_df.reset_index(drop=True).iterrows():
        x={
            "Excel Sequence":i+4,"Work Order":txt(r.get("Work Order","")),
            "Delivery Date":safe_date(r.get("Due Date")),"Customer":txt(r.get("Customer","")),
            "Specification":txt(r.get("Specification","")),"Order Qty":num(r.get("Order Qty",0)),
            "Product Code":txt(r.get("Product Code","")),"Real Spec":txt(r.get("Product Type","")),
            "D":maxdim(r.get("D","")),"T":maxdim(r.get("T","")),"H":maxdim(r.get("H","")),
            "Type":txt(r.get("Category","")),"Shape":txt(r.get("Shape","")),
            "Plan2026 kg/pc":num(r.get("Gross Weight g/pc",0))/1000.0,
            "Overall WO Status":txt(r.get("WO Closure","")),"Overall Closed":bool(r.get("Overall Closed",False)),
            "Plan2026 Firing Date":safe_date(r.get("Plan2026 Firing Date")),"Planning Remark":""
        }
        for sec in core.SECTIONS:
            pq=num(r.get(f"{sec} Plan",0)); aq=num(r.get(f"{sec} Actual",0)); st=txt(r.get(f"{sec} Status",""))
            x[f"{sec} Plan Qty"]=pq;x[f"{sec} Actual Qty"]=aq;x[f"{sec} Status"]=st
            x[f"{sec} Remaining Qty"]=0 if is_closed(st) else max(pq-aq,0)
            x[f"{sec} Accepted Short Qty"]=max(pq-aq,0) if is_closed(st) else 0
            if x["Overall Closed"]:x[f"{sec} Remaining Qty"]=0
        rows.append(x)
    return pd.DataFrame(rows)

def _cleaning_schedule(master,firing,start,end):
    rows=[]; issues=[]
    days=dailyeng.working_days(start,end,False)
    bywo={}
    if firing is not None and not firing.empty:
        for wo,g in firing.groupby("Work Order"):bywo[str(wo)]=g
    for _,j in master.iterrows():
        if postfire_route(j)!="CLEANING / ทำความสะอาด": continue
        pack_rem=num(j.get("Packing Remaining Qty",0))
        if pack_rem<=0:continue
        ready=min(num(j.get("Ready for Grinding Qty",0)),pack_rem)
        arrivals={}
        fg=bywo.get(str(j["Work Order"]))
        if fg is not None:
            for _,fr in fg.iterrows():
                fd=dailyeng.pdate(fr.get("Firing Complete")) or dailyeng.pdate(fr.get("Plan Date"))
                q=num(fr.get("Plan Qty",fr.get("Firing Qty",0)))
                if fd and q>0:
                    rd=dailyeng.add_workdays(fd,1);arrivals[rd]=arrivals.get(rd,0)+q
        planned=0
        for day in days:
            ready+=arrivals.get(day,0)
            q=min(ready,pack_rem-planned)
            if q<=0:continue
            rows.append({"Plan Date":day,"Section / กระบวนการ":"Cleaning / ทำความสะอาด",
                         "Work Order":j["Work Order"],"Customer":j["Customer"],"Specification":j["Specification"],
                         "Type":j["Type"],"Priority":j["Priority"],"Due Date":j["Delivery Date"],
                         "Plan Qty":q,"Plan kg":q*num(j["Unit kg/pc"]),
                         "Machine":"MANUAL CLEANING","Capacity Basis":"1 working day after firing; no grinding/cutting route",
                         "Release Status":"RELEASE","Validation Status":"FACTORY ROUTE RULE"})
            planned+=q;ready-=q
            if planned>=pack_rem:break
    return pd.DataFrame(rows),pd.DataFrame(issues)

def run_daily_fast(plan_df,capacity_path,planning_start,fr,horizon=30,prep_capacity=1200,packing_people=1):
    plan=plan_to_daily(plan_df)
    mix,form,kiln,grind,pack,evidence=_read_capacity_cached(capacity_path)
    anch=firing_anchor(fr)
    if anch.empty:raise ValueError("Create Firing Plan first / กรุณาสร้างแผนเผาก่อน")
    master=dailyeng.merge_master(plan,anch,planning_start)
    # Force R program P2 also in downstream master.
    master.loc[master["Type"].astype(str).str.upper()=="R","Program"]="P2"
    end=planning_start+timedelta(days=int(horizon)-1)
    prep,ip=dailyeng.schedule_preparation(master,planning_start,end,float(prep_capacity))
    mixing,im=dailyeng.schedule_mixing(master,planning_start,end,mix,prep,0.0)
    forming,ifo=dailyeng.schedule_forming(master,planning_start,end,form,mixing,0.0)
    firing,ifi=dailyeng.schedule_firing(master,forming,kiln)
    from suite.drying_gate import apply_upstream_drying
    firing=apply_upstream_drying(firing,master,forming,capacity_path)

    routes=master.apply(postfire_route,axis=1)
    grind_master=master[routes=="GRINDING / เจียร"].copy()
    cut_master=master[routes=="CUTTING / ตัด"].copy()

    grinding,ig=dailyeng.schedule_grinding(grind_master,firing,grind,planning_start,end) if not grind_master.empty else (pd.DataFrame(),pd.DataFrame())
    cutting,ic=dailyeng.schedule_grinding(cut_master,firing,grind,planning_start,end) if not cut_master.empty else (pd.DataFrame(),pd.DataFrame())
    if not cutting.empty:
        cutting=cutting.copy()
        cutting["Section / กระบวนการ"]="Cutting / ตัด"
        cutting["Capacity Basis"]="CUTTING route for HONING/SEGMENT; uses matched Cap เจีย cutting operation resources"
    cleaning,icl=_cleaning_schedule(master,firing,planning_start,end)

    post=pd.concat([x for x in [grinding,cutting,cleaning] if x is not None and not x.empty],ignore_index=True,sort=False) if any(x is not None and not x.empty for x in [grinding,cutting,cleaning]) else pd.DataFrame()
    packing,ipa=dailyeng.schedule_packing(master,post,pack,planning_start,end,int(packing_people))
    result={"Preparation":prep,"Mixing":mixing,"Forming":forming,"Firing":firing,
            "Grinding / เจียร":grinding,"Cutting / ตัด":cutting,"Cleaning / ทำความสะอาด":cleaning,
            "Packing":packing,"master":master,"capacity_evidence":evidence}
    issues=[x for x in [ip,im,ifo,ifi,ig,ic,icl,ipa] if x is not None and not x.empty]
    result["issues"]=pd.concat(issues,ignore_index=True,sort=False) if issues else pd.DataFrame()
    frames=[]
    for sec in ["Preparation","Mixing","Forming","Firing","Grinding / เจียร","Cutting / ตัด","Cleaning / ทำความสะอาด","Packing"]:
        x=result.get(sec)
        if x is not None and not x.empty:
            y=x.copy();y["Section"]=sec;frames.append(y)
    result["all"]=pd.concat(frames,ignore_index=True,sort=False) if frames else pd.DataFrame()
    return result

def save_firing(fr,path):
    with pd.ExcelWriter(path,engine="xlsxwriter") as w:
        for name,key in [("Firing Loads","loads"),("Operator Print","details"),("Floor Pattern Data","floor"),
                         ("PL Mgr Validation","pm_validation"),("Exceptions","exceptions"),("Kiln Master","kiln_editor"),
                         ("Plate Furniture","plate_master"),("I-block Furniture","iblock_master")]:
            d=fr.get(key)
            if isinstance(d,pd.DataFrame):
                sanitize_dates(d).to_excel(w,index=False,sheet_name=name[:31])

def run_longterm_fast(sales_path,plan_source_path,stock_path,capacity_path,year,start_month=1):
    # Heavy engine is lazy/on-demand only, so it does not slow app startup.
    return core.run_longterm(sales_path,plan_source_path,stock_path,capacity_path,year,start_month)



# ============================================================================
# V4.2 OVERRIDES
# HARD-PULL + UPSTREAM CAPACITY GATE + DAILY LOAD BALANCE
# ============================================================================

def looks_honing(r):
    # Accept both Plan2026 and Daily-engine naming.
    s=" ".join(txt(r.get(k,"")) for k in
               ["Product Type","Real Spec","Specification","Shape","Category","Type"]).upper()
    return any(x in s for x in ["HONING","HONNING","HONE","HONN","หินลับมีด"])

def looks_segment(r):
    s=re.sub(r"[^A-Z0-9]","",
             " ".join(txt(r.get(k,"")) for k in
                      ["Product Type","Real Spec","Specification","Shape","Category","Type"]).upper())
    return any(x in s for x in ["SEGMENT","SEGMENTR","SEGMNT","SEGMEN","SEMENT"])

def geometry_kind(r):
    cat=txt(r.get("Category",r.get("Type",""))).upper()
    if is_khat_phuen(r) or looks_honing(r) or looks_segment(r) or cat in {"S","T"}:
        return "RECTANGULAR"
    return "CIRCULAR"

def postfire_route(r):
    if looks_honing(r) or looks_segment(r):
        return "CUTTING / ตัด"
    if geometry_kind(r)=="RECTANGULAR":
        return "CLEANING / ทำความสะอาด"
    return "GRINDING / เจียร"

def _process_target_total(r, process="Firing"):
    """
    Prefer the controlled process-plan quantity when present.
    Fall back to Order Qty. Never choose a target below already-completed quantity.
    """
    p=num(r.get(f"{process} Plan",0),0)
    oq=num(r.get("Order Qty",0),0)
    eff=num(r.get(f"Eff {process}",r.get(f"{process} Actual",0)),0)
    target=p if p>0 else oq
    return max(target,eff,0)

def firing_input(plan_df, planning_start, strict_forming=True,
                 hard_pull=True, pull_horizon_days=30):
    """
    V4.2 hard-pull rule:
      Current Ready = Effective Forming - Effective Firing
      Total remaining to fire = Firing target - Effective Firing

    For WOs due within the pull horizon, the firing planner is allowed to PLAN
    the remaining quantity even if it is not physically ready yet. Those future
    quantities are not treated as "ready now"; they must pass the upstream
    capacity gate and are labelled FUTURE HARD-PULL.

    Far-future dated WOs remain eligible as next-due compatible fillers when earlier demand cannot form a feasible load; upstream capacity must still be proven.
    """
    rows=[]
    horizon_end=planning_start+timedelta(days=max(int(pull_horizon_days),1))
    for _,r in plan_df.iterrows():
        cat=txt(r.get("Category","")).upper()
        program=txt(r.get("Program",""))
        if cat=="R":
            program="P2"

        form_actual=num(r.get("Eff Forming",r.get("Forming Actual",0)))
        fire_actual=num(r.get("Eff Firing",r.get("Firing Actual",0)))
        current_ready=max(form_actual-fire_actual,0)
        target_total=_process_target_total(r,"Firing")
        total_remaining=max(target_total-fire_actual,0)
        due=safe_date(r.get("Due Date"))

        in_horizon=(due is not None and due<=horizon_end)
        overdue=(due is not None and due<planning_start)
        # Missing-date work is not pulled ahead automatically; current physical
        # WIP may still be used to maintain kiln utilization.
        # F12C CONTINUOUS PULL: all dated OPEN demand is eligible as a future
        # compatible filler. Due-date order remains the priority, but if the
        # earliest cohort cannot make a feasible kiln load, the allocator may
        # pull the next-earliest compatible WO forward instead of leaving the
        # kiln idle. Readiness is NOT invented: the pulled quantity must still
        # pass the shared upstream-capacity gate before its firing date.
        if hard_pull and due is not None:
            plan_qty=total_remaining
        elif hard_pull and (in_horizon or overdue):
            plan_qty=total_remaining
        else:
            plan_qty=min(current_ready,total_remaining)

        if bool(r.get("Overall Closed",False)):
            plan_qty=0

        future_pull=max(plan_qty-current_ready,0)
        form_closed=is_closed(r.get("Forming Status",""))
        # Whole-WO stage labels cannot erase measured partial forming output.
        # Execution readiness is independent and needs the drying evidence gate.
        confirmed_date=safe_date(r.get('Confirmed Drying Complete Date'))
        confirmed_qty=num(r.get('Confirmed Drying Qty'),0) if confirmed_date is not None and confirmed_date<=planning_start else 0
        current_release=min(plan_qty,current_ready) if cat=='PB' else min(plan_qty,current_ready,max(confirmed_qty-reserved,0))

        gross=num(r.get("Gross Weight g/pc",0))/1000.0
        product_code,test_work,test_work_type=classify_test_work(r.get("Product Code",""),r.get("Test Work Override","AUTO"))
        rows.append({
            "Work Order":txt(r.get("Work Order","")),"Category":cat,
            "Product Code":product_code,"Test Work Override":txt(r.get("Test Work Override","AUTO")),"Test Work":("YES / งานทดสอบ" if test_work else "NO / งานขาย"),
            "Test Work Type":test_work_type,
            "Customer":txt(r.get("Customer","")),"Specification":txt(r.get("Specification","")),
            "Product Type":txt(r.get("Product Type","")),"Shape":txt(r.get("Shape","")),
            "D / Length mm":r.get("D",""),"T / Width mm":r.get("T",""),"H / Hole mm":r.get("H",""),
            "Order Qty":max(num(r.get("Order Qty",0)),target_total),
            "Remaining Qty":plan_qty,
            "Candidate Ready Qty":current_ready,"Current Planning WIP Qty":min(plan_qty,current_ready),
            "Current Shop-floor Release Qty":current_release,
            "Future Pull Qty":future_pull,
            "Firing Target Total Qty":target_total,
            "Weight kg/pc":gross,"Program":program,"Due Date":due,
            "Priority":core.due_priority(due,planning_start),"Compatible?":"YES","Notes":"",
            "Order Status":"CLOSED" if bool(r.get("Overall Closed",False)) else "OPEN",
            "Preparation Status":r.get("Preparation Status",""),"Mixing Status":r.get("Mixing Status",""),
            "Forming Status":r.get("Forming Status",""),"Firing Status":r.get("Firing Status",""),
            "Preparation Actual Qty":num(r.get("Preparation Actual",0)),
            "Mixing Actual Qty":num(r.get("Mixing Actual",0)),
            "Forming Actual Qty":num(r.get("Forming Actual",0)),
            "Firing Actual Qty":num(r.get("Firing Actual",0)),
            "Grinding Actual Qty":num(r.get("Grinding / Cutting Actual",0)),
            "Packing Actual Qty":num(r.get("Packing Actual",0)),
            "Geometry Override":"",
            "Strict Forming Block": bool(strict_forming and current_ready>0 and not form_closed),
            "Hard Pull Mode": bool(hard_pull),
            "Pull Horizon End":horizon_end,
            "Readiness Planning Class":(
                "READY NOW" if future_pull<=0 and plan_qty>0
                else ("FUTURE HARD-PULL" if future_pull>0 else "NO FIRING DEMAND")
            ),
        })
    return pd.DataFrame(rows)

def plan_to_daily(plan_df):
    rows=[]
    for i,r in plan_df.reset_index(drop=True).iterrows():
        x={
            "Excel Sequence":i+4,"Work Order":txt(r.get("Work Order","")),
            "Delivery Date":safe_date(r.get("Due Date")),"Customer":txt(r.get("Customer","")),
            "Specification":txt(r.get("Specification","")),"Order Qty":num(r.get("Order Qty",0)),
            "Product Code":txt(r.get("Product Code","")),"Real Spec":txt(r.get("Product Type","")),
            "D":maxdim(r.get("D","")),"T":maxdim(r.get("T","")),"H":maxdim(r.get("H","")),
            "Type":txt(r.get("Category","")),"Category":txt(r.get("Category","")),
            "Shape":txt(r.get("Shape","")),"Product Type":txt(r.get("Product Type","")),
            "Plan2026 kg/pc":num(r.get("Gross Weight g/pc",0))/1000.0,
            "Overall WO Status":txt(r.get("WO Closure","")),"Overall Closed":bool(r.get("Overall Closed",False)),
            "Plan2026 Firing Date":safe_date(r.get("Plan2026 Firing Date")),"Planning Remark":""
        }
        for sec in core.SECTIONS:
            pq=num(r.get(f"{sec} Plan",0)); aq=num(r.get(f"{sec} Actual",0)); st=txt(r.get(f"{sec} Status",""))
            x[f"{sec} Plan Qty"]=pq;x[f"{sec} Actual Qty"]=aq;x[f"{sec} Status"]=st
            x[f"{sec} Remaining Qty"]=0 if is_closed(st) else max(pq-aq,0)
            x[f"{sec} Accepted Short Qty"]=max(pq-aq,0) if is_closed(st) else 0
            if x["Overall Closed"]:x[f"{sec} Remaining Qty"]=0
        rows.append(x)
    return pd.DataFrame(rows)

def _apply_hard_pull_targets(master, plan_df, anch):
    """
    Convert the firing schedule into a quantity target for EVERY process.
    This is the central hard-pull link.

    For each WO:
      cumulative target = effective fired qty already completed
                          + new firing qty scheduled by the planner

    Missing qty at Prep/Mix/Form is therefore planned only when required to
    protect a firing load. Downstream work is also pulled from fired/current WIP
    toward Packing.
    """
    if master is None or master.empty:
        return master
    m=master.copy()
    p=plan_df.copy()
    pidx=p.set_index(p["Work Order"].astype(str),drop=False)
    af={}
    if anch is not None and not anch.empty:
        af=anch.groupby(anch["Work Order"].astype(str))["Firing Qty"].sum().to_dict()

    for i,r in m.iterrows():
        wo=str(r["Work Order"])
        if wo in pidx.index:
            pr=pidx.loc[wo]
            if isinstance(pr,pd.DataFrame): pr=pr.iloc[0]
            ep=num(pr.get("Eff Preparation",pr.get("Preparation Actual",0)),0)
            em=num(pr.get("Eff Mixing",pr.get("Mixing Actual",0)),0)
            efo=num(pr.get("Eff Forming",pr.get("Forming Actual",0)),0)
            efi=num(pr.get("Eff Firing",pr.get("Firing Actual",0)),0)
            eg=num(pr.get("Eff Grinding / Cutting",pr.get("Grinding / Cutting Actual",0)),0)
            epa=num(pr.get("Eff Packing",pr.get("Packing Actual",0)),0)
        else:
            ep=num(r.get("Preparation Actual Qty",0)); em=num(r.get("Mixing Actual Qty",0))
            efo=num(r.get("Forming Actual Qty",0)); efi=num(r.get("Firing Actual Qty",0))
            eg=num(r.get("Grinding / Cutting Actual Qty",0)); epa=num(r.get("Packing Actual Qty",0))

        scheduled=num(af.get(wo,0),0)
        target=max(efi+scheduled,efi)
        # If there is no new firing anchor, preserve existing downstream WIP only.
        m.at[i,"Hard Pull Cumulative Target Qty"]=target
        m.at[i,"Preparation Remaining Qty"]=max(target-ep,0)
        m.at[i,"Mixing Remaining Qty"]=max(target-em,0)
        m.at[i,"Forming Remaining Qty"]=max(target-efo,0)
        m.at[i,"Grinding / Cutting Remaining Qty"]=max(target-eg,0)
        m.at[i,"Packing Remaining Qty"]=max(target-epa,0)

        # Immediate downstream ready pools based on effective cumulative actual.
        m.at[i,"Ready for Grinding Qty"]=max(efi-eg,0)
        m.at[i,"Ready for Packing Qty"]=max(eg-epa,0)
    return m

def _upstream_capacity_plan(plan_df, capacity_path, planning_start, fr, horizon_days=45,
                            prep_capacity=1200.0):
    """
    Conservative upstream capacity gate used by the firing planner.
    It creates Prep -> Mix -> Form plans against the firing anchor and then
    asks the Daily engine whether each firing WO can be supplied in sequence.
    """
    plan=plan_to_daily(plan_df)
    mix,form,kiln,grind,pack,evidence=_read_capacity_cached(capacity_path)
    anch=firing_anchor(fr)
    if anch.empty:
        return {"Preparation":pd.DataFrame(),"Mixing":pd.DataFrame(),"Forming":pd.DataFrame(),
                "FiringCheck":pd.DataFrame(),"issues":pd.DataFrame(),"master":pd.DataFrame(),
                "capacity_evidence":evidence}
    master=dailyeng.merge_master(plan,anch,planning_start)
    master.loc[master["Type"].astype(str).str.upper()=="R","Program"]="P2"
    master=_apply_hard_pull_targets(master,plan_df,anch)
    last_date=planning_start+timedelta(days=max(int(horizon_days)-1,1))
    if "Firing Date" in master.columns:
        ds=[safe_date(x) for x in master["Firing Date"]]
        ds=[x for x in ds if x]
        if ds:last_date=max(last_date,max(ds))
    prep,ip=dailyeng.schedule_preparation(master,planning_start,last_date,float(prep_capacity))
    mixing,im=dailyeng.schedule_mixing(master,planning_start,last_date,mix,prep,0.0)
    forming,ifo=dailyeng.schedule_forming(master,planning_start,last_date,form,mixing,0.0)
    firing_check,ifi=dailyeng.schedule_firing(master,forming,kiln)
    from suite.drying_gate import apply_upstream_drying
    firing_check=apply_upstream_drying(firing_check,master,forming,capacity_path)
    issues=[x for x in [ip,im,ifo,ifi] if x is not None and not x.empty]
    allup=[]
    for sec,x in [("Preparation",prep),("Mixing",mixing),("Forming",forming)]:
        if x is not None and not x.empty:
            y=x.copy();y["Section"]=sec;allup.append(y)
    return {
        "Preparation":prep,"Mixing":mixing,"Forming":forming,
        "FiringCheck":firing_check,
        "all":pd.concat(allup,ignore_index=True,sort=False) if allup else pd.DataFrame(),
        "issues":pd.concat(issues,ignore_index=True,sort=False) if issues else pd.DataFrame(),
        "master":master,"capacity_evidence":evidence,
    }

def _add_upstream_gate(fr, up, raw):
    details=fr.get("details",pd.DataFrame()).copy()
    loads=fr.get("loads",pd.DataFrame()).copy()
    if details.empty:
        fr["details"]=details;fr["loads"]=loads
        return fr

    rmap=raw.set_index(raw["Work Order"].astype(str)).to_dict("index") if raw is not None and not raw.empty else {}
    fcheck=up.get("FiringCheck",pd.DataFrame())
    cmap={}
    if fcheck is not None and not fcheck.empty:
        for _,r in fcheck.iterrows():
            wo=str(r.get("Work Order",""))
            cmap[wo]={
                "status":txt(r.get("Release Status","")),
                "reason":txt(r.get("Reason","")),
                "release":safe_date(r.get("Earliest Release Date"))
            }

    gate=[];shop=[];reasons=[];curr=[];future=[]
    for _,d in details.iterrows():
        wo=str(d.get("Work Order",""))
        rr=rmap.get(wo,{})
        q=num(d.get("Planned Firing Qty",d.get("Qty",0)),0)
        cr=num(rr.get("Candidate Ready Qty",0),0)
        fp=max(q-min(cr,q),0)
        chk=cmap.get(wo,{})
        hold=("HOLD" in chk.get("status","").upper()) or ("FAIL" in chk.get("status","").upper())
        gate.append("CAPACITY RISK / ตรวจสอบกำลัง" if hold else "CAPACITY FEASIBLE / กำลังเพียงพอ")
        if hold:
            shop.append("DO NOT RELEASE / ห้ามปล่อย")
        elif cr>=q:
            shop.append("READY NOW - CONFIRM SHOP / พร้อม ยืนยันหน้างาน")
        else:
            shop.append("FUTURE LOAD - COMPLETE UPSTREAM / งานอนาคต ต้องผลิตก่อนหน้า")
        reasons.append(chk.get("reason",""))
        curr.append(min(cr,q));future.append(fp)

    details["Upstream Capacity Gate"]=gate
    details["Shop-floor Release Status"]=shop
    details["Current Ready Portion pcs"]=curr
    details["Future Hard-Pull Portion pcs"]=future
    details["Capacity Gate Reason"]=reasons
    fr["details"]=details

    if not loads.empty and "Load ID" in details.columns:
        g=details.groupby("Load ID")
        lstat={}
        lshop={}
        for lid,x in g:
            risk=any(x["Upstream Capacity Gate"].astype(str).str.contains("RISK"))
            fut=(pd.to_numeric(x["Future Hard-Pull Portion pcs"],errors="coerce").fillna(0).sum()>0)
            lstat[lid]="CAPACITY RISK / ตรวจสอบกำลัง" if risk else "CAPACITY FEASIBLE / กำลังเพียงพอ"
            if risk:lshop[lid]="HOLD / หยุด"
            elif fut:lshop[lid]="FUTURE HARD-PULL / แผนดึงงานล่วงหน้า"
            else:lshop[lid]="READY NOW / พร้อม"
        loads["Upstream Capacity Gate"]=loads["Load ID"].map(lstat).fillna("VERIFY")
        loads["Planning / Release Class"]=loads["Load ID"].map(lshop).fillna("VERIFY")
        fr["loads"]=loads
    return fr

def workload_balance_report(result, target_util=.90):
    """
    Management-facing daily load balance.
    It does not invent work to fill capacity. UNDER TARGET means either
    insufficient executable WIP/demand or an upstream/resource constraint.
    """
    rows=[]
    target=float(target_util)
    def add(sec,day,used,cap,unit,note=""):
        util=(used/cap) if cap and cap>0 else None
        if util is None:status="CAPACITY BASIS VERIFY"
        elif util>1.0001:status="OVER CAPACITY / เกินกำลัง"
        elif util>=target:status="BALANCED / สมดุล"
        else:status="UNDER TARGET / ต่ำกว่าเป้า"
        rows.append({"Plan Date":day,"Section / กระบวนการ":sec,
                     "Planned Load":used,"Available Capacity":cap,"Unit":unit,
                     "Utilization %":util*100 if util is not None else None,
                     "Target Utilization %":target*100,"Load Balance Status":status,
                     "Management Note":note})

    # Preparation
    x=result.get("Preparation",pd.DataFrame())
    if x is not None and not x.empty:
        for d,g in x.groupby("Plan Date"):
            add("Preparation",d,num(g["Plan kg"].sum()),num(g["Capacity kg/day"].max()),"kg/day",
                "Hard-pull from firing requirement; balanced across eligible days.")

    # Mixing by machine-day, then section average utilization.
    x=result.get("Mixing",pd.DataFrame())
    if x is not None and not x.empty:
        for d,g in x.groupby("Plan Date"):
            gg=g.groupby("Machine",as_index=False).agg(used=("CAP-โม่ Used","max"),cap=("CAP-โม่ Available","max"))
            used=num(gg["used"].sum());cap=num(gg["cap"].sum())
            add("Mixing",d,used,cap,"batches/day","Machine/batch constraints respected.")

    # Forming by machine-day.
    x=result.get("Forming",pd.DataFrame())
    if x is not None and not x.empty:
        for d,g in x.groupby("Plan Date"):
            gg=g.groupby("Machine",as_index=False).agg(used=("Machine Load After WO","max"),cap=("Capacity pcs/day","max"))
            add("Forming",d,num(gg["used"].sum()),num(gg["cap"].sum()),"pcs/day",
                "Spec/mold + eligible machine capacity; one-mold lock remains active.")

    # Firing from physical planner utilization.
    fr=result.get("_firing_result")
    if isinstance(fr,dict):
        x=fr.get("loads",pd.DataFrame())
        if x is not None and not x.empty:
            for d,g in x.groupby("Load Date"):
                # Average geometric occupancy across daily kiln starts; weight remains hard limit.
                used=num(g["Geometric Occupancy Util"].mean())*100
                add("Firing",d,used,100,"% geometric occupancy",
                    "Volume occupancy is primary; weight and furniture remain hard constraints.")

    # Grinding / Cutting / Cleaning: show scheduled kg/pcs; capacity may vary by resource.
    for sec in ["Grinding / เจียร","Cutting / ตัด"]:
        x=result.get(sec,pd.DataFrame())
        if x is not None and not x.empty:
            for d,g in x.groupby("Plan Date"):
                if "Bottleneck CAP/day" in g.columns:
                    # Shared-resource capacity is conservative: sum unique bottleneck machine capacities.
                    gg=g.groupby("Bottleneck Machine",as_index=False)["Bottleneck CAP/day"].max()
                    cap=num(gg["Bottleneck CAP/day"].sum())
                    add(sec,d,num(g["Plan Qty"].sum()),cap,"pcs/day",
                        "Every required operation consumes its machine capacity.")
                else:
                    add(sec,d,num(g["Plan Qty"].sum()),0,"pcs/day","Capacity basis requires resource verification.")

    x=result.get("Packing",pd.DataFrame())
    if x is not None and not x.empty:
        for d,g in x.groupby("Plan Date"):
            # Labor is the shared packing constraint.
            used=num(g["Labor Used person-day"].sum())
            cap=num(g["Packing Manpower"].max())
            add("Packing",d,used,cap,"person-day/day",
                "Shared manpower + product-specific packing rate.")

    return pd.DataFrame(rows).sort_values(["Plan Date","Section / กระบวนการ"]) if rows else pd.DataFrame()

def run_firing_fast(plan_df, capacity_path, planning_start, target=.80,maxv=.95,partial=False,
                    urgent_partial=True,starts=2,strict_forming=True,kiln_editor=None,
                    plate_master=None,iblock_master=None,hard_pull=True,pull_horizon_days=30,
                    balance_target=.90,validate_upstream=True,prep_capacity=1200.0):
    fire.CURRENT_SETTINGS=fire.Settings(planning_start=planning_start,target_volume=target,max_volume=maxv,
                                       allow_partial=partial,allow_urgent_partial=urgent_partial,
                                       vitrified_starts_per_day=int(starts))
    settings=fire.CURRENT_SETTINGS
    fire.load_firing_capacity_master(str(capacity_path))
    if plate_master is not None and not plate_master.empty:
        fire.PLATE_MASTER=[x for x in plate_master.to_dict("records")]
    if iblock_master is not None and not iblock_master.empty:
        fire.IBLOCK_MASTER=[x for x in iblock_master.to_dict("records")]

    raw=firing_input(plan_df,planning_start,strict_forming,hard_pull,pull_horizon_days)
    prepared=fire.prepare_orders(raw,settings)

    # Critical V4.2 change:
    # The physical firing planner receives hard-pull demand, not only CURRENT
    # ready WIP. Current-ready vs future-pull remains visible as separate fields.
    if hard_pull and prepared is not None and not prepared.empty:
        prepared["Verified Ready for Firing Qty"]=pd.to_numeric(prepared["Effective Qty"],errors="coerce").fillna(0)
        prepared["Firing Ready Basis"]="HARD-PULL DEMAND; UPSTREAM CAPACITY GATE REQUIRED"
        prepared["Release Candidate"]=prepared["Include"] & (prepared["Verified Ready for Firing Qty"]>0)

    ked=kiln_editor.copy() if kiln_editor is not None else fire.default_kilns(settings)
    kilns=fire.prepare_kilns(ked,settings)
    loads,details,floor,exceptions,final_kilns=fire.build_plan(prepared,kilns.copy(),settings)

    fr={"settings":settings,"raw":raw,"prepared":prepared,"kiln_editor":ked,
        "loads":loads,"details":details,"floor":floor,"exceptions":exceptions,
        "final_kilns":final_kilns,
        "plate_master":pd.DataFrame(fire.PLATE_MASTER),"iblock_master":pd.DataFrame(fire.IBLOCK_MASTER)}

    if validate_upstream and hard_pull and not details.empty:
        # Use a horizon at least as long as the pull horizon.
        up=_upstream_capacity_plan(plan_df,capacity_path,planning_start,fr,
                                   horizon_days=max(int(pull_horizon_days),30),
                                   prep_capacity=prep_capacity)
        fr["upstream_plan"]=up.get("all",pd.DataFrame())
        fr["upstream_issues"]=up.get("issues",pd.DataFrame())
        fr["upstream_firing_check"]=up.get("FiringCheck",pd.DataFrame())
        fr=_add_upstream_gate(fr,up,raw)
    else:
        fr["upstream_plan"]=pd.DataFrame()
        fr["upstream_issues"]=pd.DataFrame()
        fr["upstream_firing_check"]=pd.DataFrame()

    validation=pm_validation(plan_df,raw,prepared,fr.get("details"))
    # Add hard-pull visibility to PL Mgr validation.
    if not validation.empty:
        rr=raw.set_index(raw["Work Order"].astype(str))
        validation["Current Ready Qty"]=validation["Work Order"].astype(str).map(
            pd.to_numeric(rr["Candidate Ready Qty"],errors="coerce").to_dict()).fillna(0)
        validation["Future Pull Qty"]=validation["Work Order"].astype(str).map(
            pd.to_numeric(rr["Future Pull Qty"],errors="coerce").to_dict()).fillna(0)
        def _pmclass(r):
            if num(r.get("Future Pull Qty",0))>0 and num(r.get("Released Qty Input",0))>0:
                return "FUTURE HARD-PULL / ต้องผลิตกระบวนการก่อนหน้า"
            return r.get("Reason / สาเหตุ","")
        validation["Planning Class / ประเภทแผน"]=validation.apply(_pmclass,axis=1)
    fr["pm_validation"]=validation

    # Firing-only workload balance.
    temp={"_firing_result":fr}
    fr["workload_balance"]=workload_balance_report(temp,balance_target)
    return fr

def run_daily_fast(plan_df,capacity_path,planning_start,fr,horizon=30,prep_capacity=1200,
                   packing_people=1,hard_pull=True,balance_target=.90):
    plan=plan_to_daily(plan_df)
    mix,form,kiln,grind,pack,evidence=_read_capacity_cached(capacity_path)
    anch=firing_anchor(fr)
    if anch.empty:raise ValueError("Create Firing Plan first / กรุณาสร้างแผนเผาก่อน")
    master=dailyeng.merge_master(plan,anch,planning_start)
    master.loc[master["Type"].astype(str).str.upper()=="R","Program"]="P2"
    if hard_pull:
        master=_apply_hard_pull_targets(master,plan_df,anch)

    end=planning_start+timedelta(days=int(horizon)-1)
    prep,ip=dailyeng.schedule_preparation(master,planning_start,end,float(prep_capacity))
    mixing,im=dailyeng.schedule_mixing(master,planning_start,end,mix,prep,0.0)
    forming,ifo=dailyeng.schedule_forming(master,planning_start,end,form,mixing,0.0)
    firing,ifi=dailyeng.schedule_firing(master,forming,kiln)
    from suite.drying_gate import apply_upstream_drying
    firing=apply_upstream_drying(firing,master,forming,capacity_path)

    routes=master.apply(postfire_route,axis=1)
    grind_master=master[routes=="GRINDING / เจียร"].copy()
    cut_master=master[routes=="CUTTING / ตัด"].copy()

    grinding,ig=dailyeng.schedule_grinding(grind_master,firing,grind,planning_start,end) if not grind_master.empty else (pd.DataFrame(),pd.DataFrame())
    cutting,ic=dailyeng.schedule_grinding(cut_master,firing,grind,planning_start,end) if not cut_master.empty else (pd.DataFrame(),pd.DataFrame())
    if not cutting.empty:
        cutting=cutting.copy()
        cutting["Section / กระบวนการ"]="Cutting / ตัด"
        cutting["Capacity Basis"]="CUTTING route for HONING/SEGMENT; uses matched Cap เจีย operation resources"
    cleaning,icl=_cleaning_schedule(master,firing,planning_start,end)

    post=pd.concat([x for x in [grinding,cutting,cleaning] if x is not None and not x.empty],
                   ignore_index=True,sort=False) if any(x is not None and not x.empty for x in [grinding,cutting,cleaning]) else pd.DataFrame()
    packing,ipa=dailyeng.schedule_packing(master,post,pack,planning_start,end,int(packing_people))

    result={"Preparation":prep,"Mixing":mixing,"Forming":forming,"Firing":firing,
            "Grinding / เจียร":grinding,"Cutting / ตัด":cutting,"Cleaning / ทำความสะอาด":cleaning,
            "Packing":packing,"master":master,"capacity_evidence":evidence,
            "_firing_result":fr}
    issues=[x for x in [ip,im,ifo,ifi,ig,ic,icl,ipa] if x is not None and not x.empty]
    result["issues"]=pd.concat(issues,ignore_index=True,sort=False) if issues else pd.DataFrame()

    frames=[]
    for sec in ["Preparation","Mixing","Forming","Firing","Grinding / เจียร","Cutting / ตัด","Cleaning / ทำความสะอาด","Packing"]:
        x=result.get(sec)
        if x is not None and not x.empty:
            y=x.copy();y["Section"]=sec;frames.append(y)
    result["all"]=pd.concat(frames,ignore_index=True,sort=False) if frames else pd.DataFrame()
    result["workload_balance"]=workload_balance_report(result,balance_target)
    return result

def save_firing(fr,path):
    with pd.ExcelWriter(path,engine="xlsxwriter") as w:
        for name,key in [
            ("Firing Loads","loads"),("Operator Print","details"),("Floor Pattern Data","floor"),
            ("Upstream Hard Pull","upstream_plan"),("Upstream Issues","upstream_issues"),
            ("Workload Balance","workload_balance"),("Drying Readiness","drying_check"),("Release Summary","release_summary"),("Selected Start Check","selected_start_check"),
            ("Production Instructions","transition_production_actions"),("Transition Control","transition_control"),("Transition Reconciliation","transition_review"),("Retained Transition","retained_transition"),
            ("Plan Control","plan_control"),("Previous Plan Audit","previous_plan_cutover_audit"),("Plan2026 Status","plan2026_status_snapshot"),
            ("PL Mgr Validation","pm_validation"),("Exceptions","exceptions"),("Kiln Master","kiln_editor"),
            ("Plate Furniture","plate_master"),("I-block Furniture","iblock_master")]:
            d=fr.get(key)
            if isinstance(d,pd.DataFrame):
                # F12Q: sort on RAW datetime values BEFORE date sanitizing/formatting.
                # This prevents dd/mm vs mm/dd text conversion from breaking chronological order.
                x=d.copy()
                if name in {"Firing Loads","Operator Print"} and not x.empty:
                    if "Load Date" in x.columns:
                        x["__LOAD_DATE_SORT__"]=pd.to_datetime(x["Load Date"],errors="coerce",dayfirst=False)
                    if "Load ID" in x.columns:
                        x["__LOAD_ID_SORT__"]=pd.to_numeric(x["Load ID"].astype(str).str.extract(r"(\d+)",expand=False),errors="coerce")
                    sort_cols=[c for c in ["__LOAD_DATE_SORT__","Kiln","__LOAD_ID_SORT__","Load ID","Floor","Work Order"] if c in x.columns]
                    if sort_cols:
                        x=x.sort_values(sort_cols,kind="stable",na_position="last").reset_index(drop=True)
                    x=x.drop(columns=[c for c in ["__LOAD_DATE_SORT__","__LOAD_ID_SORT__"] if c in x.columns])
                x=sanitize_dates(x)
                if name == "Operator Print" and not x.empty:
                    # Bilingual English/Thai operator-facing headings. Internal engine field names remain unchanged.
                    bi={
                        "Load Date":"Loading Date / วันที่เข้าเตา", "Load ID":"Load ID / รหัสโหลด",
                        "Kiln":"Kiln / เตา", "Program":"Program / โปรแกรม", "Work Order":"Work Order / ใบสั่งผลิต",
                        "Customer":"Customer / ลูกค้า", "Category":"Product Category / ประเภทผลิตภัณฑ์",
                        "Product Code":"Product Code / รหัสสินค้า", "Test Work":"Test Work / งานทดสอบ", "Test Work Type":"Test Type / ประเภทงานทดสอบ",
                        "Specification":"Specification / รายละเอียด", "Planned Firing Qty":"Planned Qty (pcs) / จำนวนแผน (ชิ้น)",
                        "Ready Now pcs":"Ready Now (pcs) / พร้อมตอนนี้ (ชิ้น)", "MAKE pcs":"MAKE Before Firing (pcs) / ต้องผลิตก่อนเผา (ชิ้น)",
                        "Planning Status":"Planning Status / สถานะแผน", "Release Gate":"Release Status / สถานะการปล่อย",
                        "Release Reason":"Reason / เหตุผล", "Risk":"Risk / ความเสี่ยง",
                        "Due Date":"Due Date / วันกำหนดส่ง", "Suggested Safe Revised Due Date":"Suggested Safe Due Date / วันกำหนดส่งที่แนะนำ",
                        "Preparation Required By":"Preparation Required By / เตรียมเสร็จภายใน",
                        "Mixing Required By":"Mixing Required By / ผสมเสร็จภายใน",
                        "Forming Required By":"Forming Required By / ขึ้นรูปเสร็จภายใน",
                        "Program Finish Date":"Firing Finish Date / วันที่เผาเสร็จ",
                        "Cutover / Previous Plan Protection":"Previous/New Plan Status / สถานะแผนเดิม-ใหม่",
                        "Capacity Date Validation":"Capacity/Date Validation / ตรวจสอบกำลังผลิตและวันที่"
                    }
                    x=x.rename(columns={k:v for k,v in bi.items() if k in x.columns})
                x.to_excel(w,index=False,sheet_name=name[:31])
        # Dedicated searchable test-work output. Source of truth is Plan2026 Product Code K.
        _det=fr.get("details")
        if isinstance(_det,pd.DataFrame) and not _det.empty and "Product Code" in _det.columns:
            _tw=_det.copy()
            _tw["Product Code"]=_tw["Product Code"].fillna("").astype(str).str.strip()
            _ov=_tw.get("Test Work Override",pd.Series("AUTO",index=_tw.index)).fillna("AUTO").astype(str).str.upper()
            _auto=_tw["Product Code"].str[:1].eq("1")
            _tw=_tw[((_auto)&(_ov!="NORMAL"))|(_ov=="TEST")].copy()
            if not _tw.empty:
                _tw["Test Work"]="TEST / งานทดสอบ"
                if "Load Date" in _tw.columns:
                    _tw["__LOAD_DATE_SORT__"]=pd.to_datetime(_tw["Load Date"],errors="coerce")
                    _tw=_tw.sort_values(["__LOAD_DATE_SORT__"] + (["Kiln"] if "Kiln" in _tw.columns else []) + (["Load ID"] if "Load ID" in _tw.columns else []),kind="stable",na_position="last")
                    _tw=_tw.drop(columns=["__LOAD_DATE_SORT__"])
                _tw=sanitize_dates(_tw)
                _tw.to_excel(w,index=False,sheet_name="TEST WORK")



# ============================================================================
# V4.3 OVERRIDES
# FEASIBILITY-FIRST HARD PULL
# "DO NOT PLAN DOWNSTREAM UNTIL UPSTREAM CAN PHYSICALLY SUPPLY IT"
# ============================================================================

def _business_days(start_date, end_date):
    """Mon-Sat working days; Sunday excluded."""
    if start_date is None or end_date is None or end_date < start_date:
        return 0
    d=start_date; n=0
    while d<=end_date:
        if d.weekday()!=6:
            n+=1
        d+=timedelta(days=1)
    return n

def _proc_capacity_to_qty(section, wo_row, cap_tables, day):
    """
    Conservative per-WO daily capacity ceiling.
    Uses controlled master when it can be matched; otherwise returns 0 so the
    engine does not invent impossible production.
    """
    mix,form,kiln,grind,pack = cap_tables

    if section=="Preparation":
        # Preparation fallback is passed separately by caller.
        return None

    if section=="Mixing":
        if mix is None or mix.empty:
            return 0
        # Let Daily engine own detailed matching later. Here use total executable
        # section capacity as a conservative upper bound in kg converted to pcs.
        kgpc=max(num(wo_row.get("Gross Weight g/pc",0))/1000.0, 0)
        if kgpc<=0: return 0
        nums=[]
        for c in mix.columns:
            if "CAP" in str(c).upper() or "KG" in str(c).upper():
                vals=pd.to_numeric(mix[c],errors="coerce")
                if vals.notna().any():
                    nums.append(float(vals.fillna(0).sum()))
        total=max(nums) if nums else 0
        return total/kgpc if total>0 else 0

    if section=="Forming":
        if form is None or form.empty:
            return 0
        # Try to match by spec / product / type if such columns exist.
        spec=txt(wo_row.get("Specification","")).upper()
        typ=txt(wo_row.get("Category","")).upper()
        cand=form.copy()
        textcols=[c for c in cand.columns if cand[c].dtype=="object"]
        if textcols and spec:
            mask=pd.Series(False,index=cand.index)
            for c in textcols:
                s=cand[c].astype(str).str.upper()
                mask = mask | s.apply(lambda x: x and (x in spec or spec in x))
            if mask.any(): cand=cand[mask]
        # Sum obvious capacity columns
        capcols=[c for c in cand.columns if any(k in str(c).upper() for k in ["PCS","CAP","QTY","ชิ้น"])]
        vals=[]
        for c in capcols:
            s=pd.to_numeric(cand[c],errors="coerce")
            if s.notna().any(): vals.append(float(s.fillna(0).sum()))
        return max(vals) if vals else 0

    if section in ("Grinding / Cutting","Packing"):
        tab=grind if section=="Grinding / Cutting" else pack
        if tab is None or tab.empty:
            return 0
        capcols=[c for c in tab.columns if any(k in str(c).upper() for k in ["PCS","CAP","QTY","KG","ชิ้น"])]
        vals=[]
        for c in capcols:
            s=pd.to_numeric(tab[c],errors="coerce")
            if s.notna().any(): vals.append(float(s.fillna(0).sum()))
        return max(vals) if vals else 0

    return 0

def _load_capacity_tables(capacity_path):
    mix,form,kiln,grind,pack,evidence=_read_capacity_cached(capacity_path)
    return (mix,form,kiln,grind,pack,evidence)

def _wo_effective_actuals(r):
    return {
        "Preparation":num(r.get("Eff Preparation",r.get("Preparation Actual",0)),0),
        "Mixing":num(r.get("Eff Mixing",r.get("Mixing Actual",0)),0),
        "Forming":num(r.get("Eff Forming",r.get("Forming Actual",0)),0),
        "Firing":num(r.get("Eff Firing",r.get("Firing Actual",0)),0),
        "Grinding / Cutting":num(r.get("Eff Grinding / Cutting",r.get("Grinding / Cutting Actual",0)),0),
        "Packing":num(r.get("Eff Packing",r.get("Packing Actual",0)),0),
    }

def _latest_feasible_upstream_qty(r, load_date, planning_start, cap_tables, prep_capacity_kg=1200.0):
    """
    Returns the maximum cumulative quantity that can PHYSICALLY reach Forming
    by the requested firing load date.

    Sequence:
      Prep must complete at least 1 working day before Mix
      Mix must complete at least 1 working day before Form
      Form must complete at least 1 working day before Firing load

    We use actual downstream completion as already-realized supply and only add
    future quantity that fits inside each upstream capacity window.
    """
    acts=_wo_effective_actuals(r)
    target=max(_process_target_total(r,"Firing"),acts["Firing"])
    if load_date is None:
        return acts["Forming"], {"reason":"No load date","target":target}

    # Last days available for each process.
    form_end=load_date-timedelta(days=1)
    mix_end=form_end-timedelta(days=1)
    prep_end=mix_end-timedelta(days=1)

    prep_days=_business_days(planning_start,prep_end)
    mix_days=_business_days(planning_start,mix_end)
    form_days=_business_days(planning_start,form_end)

    kgpc=max(num(r.get("Gross Weight g/pc",0))/1000.0,0)

    # Preparation feasible cumulative qty.
    prep_add=(prep_capacity_kg*prep_days/kgpc) if kgpc>0 else 0
    prep_cum=min(target,acts["Preparation"]+prep_add)

    mix_daily=_proc_capacity_to_qty("Mixing",r,cap_tables,planning_start)
    mix_add=max(mix_daily,0)*mix_days
    mix_cum=min(target,acts["Mixing"]+mix_add,prep_cum)

    form_daily=_proc_capacity_to_qty("Forming",r,cap_tables,planning_start)
    form_add=max(form_daily,0)*form_days
    form_cum=min(target,acts["Forming"]+form_add,mix_cum)

    # Never go backwards below already-formed quantity.
    feasible=max(acts["Forming"],form_cum)
    return feasible, {
        "target":target,
        "prep_days":prep_days,"mix_days":mix_days,"form_days":form_days,
        "prep_cum":prep_cum,"mix_cum":mix_cum,"form_cum":form_cum,
        "mix_daily_cap":mix_daily,"form_daily_cap":form_daily,
        "kgpc":kgpc,
    }

def firing_input(plan_df, planning_start, strict_forming=True,
                 hard_pull=True, pull_horizon_days=30,
                 capacity_path=None, prep_capacity=1200.0):
    """
    V4.3 feasibility-first firing demand.

    Remaining firing demand alone is NOT enough.
    For every WO and candidate load date, the planner can only use:
      min(total remaining demand,
          quantity already formed + quantity upstream can physically produce
          before the load date)

    The physical kiln planner receives only the feasible quantity ceiling.
    """
    rows=[]
    horizon_end=planning_start+timedelta(days=max(int(pull_horizon_days),1))
    cap_tables=None
    if capacity_path:
        mix,form,kiln,grind,pack,evidence=_load_capacity_tables(capacity_path)
        cap_tables=(mix,form,kiln,grind,pack)

    for _,r in plan_df.iterrows():
        cat=txt(r.get("Category","")).upper()
        program=txt(r.get("Program",""))
        if cat=="R": program="P2"

        acts=_wo_effective_actuals(r)
        reserved=max(num(r.get("Retained firing reservation Qty",0)),0)
        current_ready=max(acts["Forming"]-acts["Firing"]-reserved,0)
        target_total=_process_target_total(r,"Firing")
        total_remaining=max(target_total-acts["Firing"]-reserved,0)
        due=safe_date(r.get("Due Date"))

        # Candidate date basis for feasibility ceiling:
        # earliest useful date is due date if inside horizon, else horizon end.
        candidate_date = due if (due is not None and due<=horizon_end) else horizon_end
        # The selected Planning Start is the first permissible firing TARGET date.
        # Do not silently push the first firing day to the following day.
        # Upstream feasibility is evaluated relative to the selected target date;
        # if the upstream quantity is insufficient, the result is shown as a
        # readiness/expedite constraint rather than changing the user's anchor date.
        if candidate_date < planning_start:
            candidate_date = planning_start

        feasible_form_cum=acts["Forming"]
        feas_meta={}
        if hard_pull and cap_tables is not None:
            feasible_form_cum,feas_meta=_latest_feasible_upstream_qty(
                r,candidate_date,planning_start,cap_tables,prep_capacity)

        feasible_to_fire=max(feasible_form_cum-acts["Firing"]-reserved,0)

        # Plan2026 ALL OPEN demand is the future pull pool.
        # Due date controls priority; upstream capacity/readiness controls release.
        in_horizon=(due is not None and due<=horizon_end)
        if hard_pull:
            plan_qty=min(total_remaining,feasible_to_fire)
        else:
            plan_qty=min(total_remaining,current_ready)

        if bool(r.get("Overall Closed",False)):
            plan_qty=0

        future_pull=max(plan_qty-current_ready,0)
        form_closed=is_closed(r.get("Forming Status",""))
        # Whole-WO stage labels cannot erase measured partial forming output.
        # Execution readiness is independent and needs the drying evidence gate.
        confirmed_date=safe_date(r.get('Confirmed Drying Complete Date'))
        confirmed_qty=num(r.get('Confirmed Drying Qty'),0) if confirmed_date is not None and confirmed_date<=planning_start else 0
        current_release=min(plan_qty,current_ready) if cat=='PB' else min(plan_qty,current_ready,max(confirmed_qty-reserved,0))

        gross=num(r.get("Gross Weight g/pc",0))/1000.0
        product_code,test_work,test_work_type=classify_test_work(r.get("Product Code",""),r.get("Test Work Override","AUTO"))
        rows.append({
            "Work Order":txt(r.get("Work Order","")),"Category":cat,
            "Product Code":product_code,"Test Work Override":txt(r.get("Test Work Override","AUTO")),"Test Work":("YES / งานทดสอบ" if test_work else "NO / งานขาย"),
            "Test Work Type":test_work_type,
            "Customer":txt(r.get("Customer","")),"Specification":txt(r.get("Specification","")),
            "Product Type":txt(r.get("Product Type","")),"Shape":txt(r.get("Shape","")),
            "D / Length mm":r.get("D",""),"T / Width mm":r.get("T",""),"H / Hole mm":r.get("H",""),
            "Order Qty":max(num(r.get("Order Qty",0)),target_total),
            "Remaining Qty":plan_qty,
            "Candidate Ready Qty":current_ready,"Current Planning WIP Qty":min(plan_qty,current_ready),
            "Feasible Qty by Candidate Date":feasible_to_fire,
            "Current Shop-floor Release Qty":current_release,
            "Future Pull Qty":future_pull,
            "Firing Target Total Qty":target_total,
            "Weight kg/pc":gross,"Program":program,"Due Date":due,
            "Priority":core.due_priority(due,planning_start),"Compatible?":"YES","Notes":"",
            "Order Status":"CLOSED" if bool(r.get("Overall Closed",False)) else "OPEN",
            "Preparation Status":r.get("Preparation Status",""),"Mixing Status":r.get("Mixing Status",""),
            "Forming Status":r.get("Forming Status",""),"Firing Status":r.get("Firing Status",""),
            "Preparation Actual Qty":num(r.get("Preparation Actual",0)),
            "Mixing Actual Qty":num(r.get("Mixing Actual",0)),
            "Forming Actual Qty":num(r.get("Forming Actual",0)),
            "Firing Actual Qty":num(r.get("Firing Actual",0)),
            "Grinding Actual Qty":num(r.get("Grinding / Cutting Actual",0)),
            "Packing Actual Qty":num(r.get("Packing Actual",0)),
            "Geometry Override":"",
            "Strict Forming Block": bool(strict_forming and current_ready>0 and not form_closed),
            "Hard Pull Mode": bool(hard_pull),
            "Pull Horizon End":horizon_end,
            "Feasibility Candidate Date":candidate_date,
            "Readiness Planning Class":(
                "READY NOW" if future_pull<=0 and plan_qty>0
                else ("FEASIBLE FUTURE PULL" if future_pull>0 else "NO FEASIBLE FIRING DEMAND")
            ),
            "Upstream Feasibility Detail":str(feas_meta),
        })
    return pd.DataFrame(rows)

def _clip_details_to_feasible(fr, raw):
    """
    Final safeguard: physical firing detail can NEVER exceed per-WO feasible qty.
    If the physical planner allocated more due to duplicated/mixed placement,
    clip detail and flag it.
    """
    if fr is None or raw is None or raw.empty:
        return fr
    details=fr.get("details",pd.DataFrame()).copy()
    if details.empty:return fr

    fmap=raw.set_index(raw["Work Order"].astype(str))["Remaining Qty"].to_dict()
    used={}
    keep=[]
    notes=[]
    for _,d in details.iterrows():
        wo=str(d.get("Work Order",""))
        q=num(d.get("Planned Firing Qty",d.get("Qty",0)),0)
        lim=num(fmap.get(wo,0),0)
        already=used.get(wo,0)
        allowed=max(lim-already,0)
        newq=min(q,allowed)
        used[wo]=already+newq
        keep.append(newq)
        notes.append("" if newq>=q else "CLIPPED TO UPSTREAM FEASIBLE QTY")
    # Keep original column names if present
    if "Planned Firing Qty" in details.columns:
        details["Planned Firing Qty"]=keep
    elif "Qty" in details.columns:
        details["Qty"]=keep
    details["Feasibility Clip Note"]=notes
    fr["details"]=details[[(num(x)>0) for x in keep]].copy()
    return fr


def _next_workday_after(d, working_days=None):
    working_days = working_days or {0,1,2,3,4,5}
    x=d
    while x.weekday() not in working_days:
        x += timedelta(days=1)
    return x

def _add_workdays_safe(d, n, working_days=None):
    working_days = working_days or {0,1,2,3,4,5}
    x=d; done=0
    while done < int(max(n,0)):
        x += timedelta(days=1)
        if x.weekday() in working_days: done += 1
    return x

def _downstream_safe_days(category):
    # Capacity-master Lead Time basis after firing completion.
    # Conservative whole-working-day conversion of screening + QC + grinding (when applicable) + final/packing lead time.
    c=txt(category).upper()
    return {"S":6,"T":6,"P":12,"R":12,"PB":9,"M":9}.get(c,6)

def _reschedule_to_upstream_release(fr, up, planning_start, starts_per_day=2):
    """F9: move each complete kiln load to the earliest date its shared-capacity upstream plan can supply it.
    Then re-apply kiln cycle and daily-start constraints. Positive planning remains, but no retroactive MAKE assumption.
    """
    loads=fr.get("loads",pd.DataFrame()).copy(); details=fr.get("details",pd.DataFrame()).copy()
    if loads.empty or details.empty: return fr
    fcheck=up.get("FiringCheck",pd.DataFrame())
    rel={}
    if fcheck is not None and not fcheck.empty:
        for _,r in fcheck.iterrows():
            wo=str(r.get("Work Order","")); d=safe_date(r.get("Earliest Release Date"))
            if d is not None: rel[wo]=max(rel.get(wo,d),d)
    # Actual shared-capacity upstream schedule dates by WO/process.
    allup=up.get("all",pd.DataFrame())
    proc_dates={}
    if allup is not None and not allup.empty:
        for _,r in allup.iterrows():
            wo=str(r.get("Work Order","")); sec=txt(r.get("Section",r.get("Section / กระบวนการ","")))
            d=safe_date(r.get("Plan Date"))
            if wo and sec and d is not None:
                proc_dates[(wo,sec)]=max(proc_dates.get((wo,sec),d),d)

    working={0,1,2,3,4,5}; kiln_next={}; daily_normal={}; daily_t0={}; daily_resin=set()
    load_new={}; finish_new={}; shift_reason={}
    order=loads.copy(); order['_old']=pd.to_datetime(order['Load Date'],errors='coerce')
    order=order.sort_values(['_old','Load ID'],kind='stable')
    for _,lr in order.iterrows():
        lid=str(lr.get('Load ID','')); old=safe_date(lr.get('Load Date')) or planning_start
        dd=details[details['Load ID'].astype(str)==lid]
        req=old; missing=[]
        for _,dr in dd.iterrows():
            make=num(dr.get('MAKE pcs',0),0); wo=str(dr.get('Work Order',''))
            if make>0:
                rd=rel.get(wo)
                if rd is not None: req=max(req,rd)
                else: missing.append(wo)
        kiln=txt(lr.get('Kiln','')).upper(); typ='RESIN' if kiln in {'R4','R5','R6'} else ('T0' if kiln=='T0' else 'NORMAL')
        d=req if req==planning_start else _next_workday_after(req,working)   # selected start date is never shifted
        if kiln in kiln_next: d=max(d,kiln_next[kiln]); d=d if d==planning_start else _next_workday_after(d,working)
        # Enforce independent daily start rules after shifts.
        while True:
            if typ=='NORMAL' and daily_normal.get(d,0)>=int(starts_per_day): d=_next_workday_after(d+timedelta(days=1),working); continue
            if typ=='T0' and daily_t0.get(d,0)>=1: d=_next_workday_after(d+timedelta(days=1),working); continue
            if typ=='RESIN' and (d,kiln) in daily_resin: d=_next_workday_after(d+timedelta(days=1),working); continue
            if kiln in kiln_next and d<kiln_next[kiln]: d=_next_workday_after(kiln_next[kiln],working); continue
            break
        cycle=max(int(round(num(lr.get('Running Days',1),1))),1)
        finish=d+timedelta(days=cycle)
        kiln_next[kiln]=_next_workday_after(finish+timedelta(days=1),working)
        if typ=='NORMAL': daily_normal[d]=daily_normal.get(d,0)+1
        elif typ=='T0': daily_t0[d]=daily_t0.get(d,0)+1
        else: daily_resin.add((d,kiln))
        load_new[lid]=d; finish_new[lid]=finish
        shift_reason[lid]=(f"SHIFTED {old} → {d}: upstream shared-capacity release + kiln/day capacity" if d>old else "DATE CONFIRMED BY UPSTREAM CAPACITY")
        if missing: shift_reason[lid] += "; VERIFY UPSTREAM FOR " + ', '.join(sorted(set(missing))[:5])

    for i,r in loads.iterrows():
        lid=str(r.get('Load ID','')); d=load_new.get(lid,safe_date(r.get('Load Date')))
        loads.at[i,'Original Proposed Load Date']=r.get('Load Date'); loads.at[i,'Load Date']=d
        loads.at[i,'Program Finish Date']=finish_new.get(lid,r.get('Program Finish Date')); loads.at[i,'Firing Complete']=finish_new.get(lid,r.get('Firing Complete'))
        loads.at[i,'Capacity Date Validation']=shift_reason.get(lid,'')
    for i,r in details.iterrows():
        lid=str(r.get('Load ID','')); d=load_new.get(lid,safe_date(r.get('Load Date'))); wo=str(r.get('Work Order',''))
        details.at[i,'Original Proposed Load Date']=r.get('Load Date'); details.at[i,'Load Date']=d
        details.at[i,'Program Finish Date']=finish_new.get(lid,r.get('Program Finish Date')); details.at[i,'Firing Complete']=finish_new.get(lid,r.get('Firing Complete'))
        # Replace simple previous-day placeholders with dates from the actual shared-capacity schedule where available.
        for sec,col in [('Preparation','Preparation Required By'),('Mixing','Mixing Required By'),('Forming','Forming Required By')]:
            if (wo,sec) in proc_dates: details.at[i,col]=proc_dates[(wo,sec)]
        cat=txt(r.get('Category','')).upper(); safe_due=_add_workdays_safe(finish_new.get(lid,d),_downstream_safe_days(cat),working)
        orig_due=safe_date(r.get('Due Date')); suggested=max(safe_due,orig_due) if orig_due is not None else safe_due
        details.at[i,'Earliest Capacity-Feasible Firing Date']=d
        details.at[i,'Suggested Safe Revised Due Date']=suggested
        details.at[i,'Revised Due Date Basis']=f"Firing completion + {_downstream_safe_days(cat)} working-day downstream lead-time allowance; confirm downstream shared capacity in Daily Planner"
        details.at[i,'Due Date Protection']=('ORIGINAL DUE FEASIBLE ON LEAD-TIME BASIS' if orig_due is not None and safe_due<=orig_due else 'REVISED DUE DATE SUGGESTED')
        details.at[i,'Capacity Date Validation']=shift_reason.get(lid,'')
    if 'Load ID' in details.columns:
        smap=details.groupby('Load ID')['Suggested Safe Revised Due Date'].max().to_dict()
        pmap=details.groupby('Load ID')['Due Date Protection'].apply(lambda x:'REVISED DUE DATE SUGGESTED' if any(x=='REVISED DUE DATE SUGGESTED') else 'ORIGINAL DUE FEASIBLE ON LEAD-TIME BASIS').to_dict()
        loads['Suggested Safe Revised Due Date']=loads['Load ID'].astype(str).map(smap)
        loads['Due Date Protection']=loads['Load ID'].astype(str).map(pmap)
    fr['loads']=loads; fr['details']=details
    return fr

def _refresh_required_dates_from_upstream(fr, up):
    details=fr.get('details',pd.DataFrame()).copy()
    allup=up.get('all',pd.DataFrame())
    if details.empty or allup is None or allup.empty: return fr
    mp={}
    for _,r in allup.iterrows():
        wo=str(r.get('Work Order','')); sec=txt(r.get('Section',r.get('Section / กระบวนการ',''))); d=safe_date(r.get('Plan Date'))
        if wo and sec and d is not None: mp[(wo,sec)]=max(mp.get((wo,sec),d),d)
    for i,r in details.iterrows():
        wo=str(r.get('Work Order',''))
        for sec,col in [('Preparation','Preparation Required By'),('Mixing','Mixing Required By'),('Forming','Forming Required By')]:
            if (wo,sec) in mp: details.at[i,col]=mp[(wo,sec)]
    fr['details']=details; return fr

def run_firing_fast(plan_df, capacity_path, planning_start, target=.80,maxv=.95,partial=False,
                    urgent_partial=True,starts=2,strict_forming=True,kiln_editor=None,
                    plate_master=None,iblock_master=None,hard_pull=True,pull_horizon_days=30,
                    balance_target=.90,validate_upstream=True,prep_capacity=1200.0):
    fire.CURRENT_SETTINGS=fire.Settings(planning_start=planning_start,target_volume=target,max_volume=maxv,
                                       allow_partial=partial,allow_urgent_partial=urgent_partial,
                                       vitrified_starts_per_day=int(starts))
    settings=fire.CURRENT_SETTINGS
    fire.load_firing_capacity_master(str(capacity_path))
    if plate_master is not None and not plate_master.empty:
        fire.PLATE_MASTER=[x for x in plate_master.to_dict("records")]
    if iblock_master is not None and not iblock_master.empty:
        fire.IBLOCK_MASTER=[x for x in iblock_master.to_dict("records")]

    # Critical V4.3 change: capacity path is passed INTO demand creation.
    raw=firing_input(plan_df,planning_start,strict_forming,hard_pull,pull_horizon_days,
                     capacity_path=capacity_path,prep_capacity=prep_capacity)
    prepared=fire.prepare_orders(raw,settings)

    from suite.firing_start_policy import split_planning_lots
    prepared=split_planning_lots(prepared,raw,planning_start)

    ked=kiln_editor.copy() if kiln_editor is not None else fire.default_kilns(settings)
    kilns=fire.prepare_kilns(ked,settings)
    loads,details,floor,exceptions,final_kilns=fire.build_plan(prepared,kilns.copy(),settings)

    fr={"settings":settings,"raw":raw,"prepared":prepared,"kiln_editor":ked,
        "loads":loads,"details":details,"floor":floor,"exceptions":exceptions,
        "final_kilns":final_kilns,
        "plate_master":pd.DataFrame(fire.PLATE_MASTER),"iblock_master":pd.DataFrame(fire.IBLOCK_MASTER)}

    fr=_clip_details_to_feasible(fr,raw)

    # F9: shared-capacity upstream schedule is now a DATE INPUT, not only a warning after firing allocation.
    # Pass 1 schedules Prep->Mix->Form against proposed firing dates. Loads that cannot be supplied are moved forward.
    # Pass 2 rebuilds upstream requirements against the shifted kiln calendar and confirms the final capacity gate.
    if validate_upstream and hard_pull and not fr["details"].empty:
        up=_upstream_capacity_plan(plan_df,capacity_path,planning_start,fr,
                                   horizon_days=max(int(pull_horizon_days),90),
                                   prep_capacity=prep_capacity)
        fr=_reschedule_to_upstream_release(fr,up,planning_start,starts_per_day=int(starts))
        up=_upstream_capacity_plan(plan_df,capacity_path,planning_start,fr,
                                   horizon_days=max(int(pull_horizon_days),90),
                                   prep_capacity=prep_capacity)
        fr["upstream_plan"]=up.get("all",pd.DataFrame())
        fr["upstream_issues"]=up.get("issues",pd.DataFrame())
        fr["upstream_firing_check"]=up.get("FiringCheck",pd.DataFrame())
        fr=_refresh_required_dates_from_upstream(fr,up)
        fr=_add_upstream_gate(fr,up,raw)
    else:
        fr["upstream_plan"]=pd.DataFrame()
        fr["upstream_issues"]=pd.DataFrame()
        fr["upstream_firing_check"]=pd.DataFrame()

    validation=pm_validation(plan_df,raw,prepared,fr.get("details"))
    if not validation.empty:
        rr=raw.set_index(raw["Work Order"].astype(str))
        validation["Current Ready Qty"]=validation["Work Order"].astype(str).map(
            pd.to_numeric(rr["Candidate Ready Qty"],errors="coerce").to_dict()).fillna(0)
        validation["Feasible Qty by Candidate Date"]=validation["Work Order"].astype(str).map(
            pd.to_numeric(rr["Feasible Qty by Candidate Date"],errors="coerce").to_dict()).fillna(0)
        validation["Future Pull Qty"]=validation["Work Order"].astype(str).map(
            pd.to_numeric(rr["Future Pull Qty"],errors="coerce").to_dict()).fillna(0)
        validation["Planning Class / ประเภทแผน"]=validation.apply(
            lambda r: "FEASIBLE FUTURE PULL / ผลิตได้ตามกำลัง"
            if num(r.get("Future Pull Qty",0))>0 else r.get("Reason / สาเหตุ",""),axis=1)
    fr["pm_validation"]=validation

    temp={"_firing_result":fr}
    fr["workload_balance"]=workload_balance_report(temp,balance_target)
    return fr

def _rebalance_section_to_capacity(df, section, target_util=.90):
    """
    Lightweight final balancing pass.
    It does NOT move work earlier than upstream readiness. It only redistributes
    work across the already-eligible dates when the source schedule contains
    extreme peaks/valleys, while preserving total quantity and date bounds.
    """
    if df is None or df.empty or "Plan Date" not in df.columns:
        return df
    x=df.copy()
    qty_col = "Plan Qty" if "Plan Qty" in x.columns else None
    if qty_col is None:
        return x
    # Keep order generated by scheduling engine; no unsafe blind redistribution.
    # Add balance class so low utilization is visible rather than hidden.
    x["V4.3 Balance Rule"]="Capacity ceiling enforced; underload only when no executable upstream-ready work"
    return x

def run_daily_fast(plan_df,capacity_path,planning_start,fr,horizon=30,prep_capacity=1200,
                   packing_people=1,hard_pull=True,balance_target=.90):
    plan=plan_to_daily(plan_df)
    mix,form,kiln,grind,pack,evidence=_read_capacity_cached(capacity_path)
    anch=firing_anchor(fr)
    if anch.empty:raise ValueError("Create Firing Plan first / กรุณาสร้างแผนเผาก่อน")
    master=dailyeng.merge_master(plan,anch,planning_start)
    master.loc[master["Type"].astype(str).str.upper()=="R","Program"]="P2"
    if hard_pull:
        master=_apply_hard_pull_targets(master,plan_df,anch)

    end=planning_start+timedelta(days=int(horizon)-1)

    # Capacity-constrained sequence. Each next process only sees the prior
    # process schedule produced by the capacity engine.
    prep,ip=dailyeng.schedule_preparation(master,planning_start,end,float(prep_capacity))
    mixing,im=dailyeng.schedule_mixing(master,planning_start,end,mix,prep,0.0)
    forming,ifo=dailyeng.schedule_forming(master,planning_start,end,form,mixing,0.0)
    firing,ifi=dailyeng.schedule_firing(master,forming,kiln)
    from suite.drying_gate import apply_upstream_drying
    firing=apply_upstream_drying(firing,master,forming,capacity_path)

    routes=master.apply(postfire_route,axis=1)
    grind_master=master[routes=="GRINDING / เจียร"].copy()
    cut_master=master[routes=="CUTTING / ตัด"].copy()

    grinding,ig=dailyeng.schedule_grinding(grind_master,firing,grind,planning_start,end) if not grind_master.empty else (pd.DataFrame(),pd.DataFrame())
    cutting,ic=dailyeng.schedule_grinding(cut_master,firing,grind,planning_start,end) if not cut_master.empty else (pd.DataFrame(),pd.DataFrame())
    if not cutting.empty:
        cutting=cutting.copy()
        cutting["Section / กระบวนการ"]="Cutting / ตัด"
        cutting["Capacity Basis"]="CUTTING route for HONING/SEGMENT; matched controlled resources"
    cleaning,icl=_cleaning_schedule(master,firing,planning_start,end)
    post=pd.concat([x for x in [grinding,cutting,cleaning] if x is not None and not x.empty],
                   ignore_index=True,sort=False) if any(x is not None and not x.empty for x in [grinding,cutting,cleaning]) else pd.DataFrame()
    packing,ipa=dailyeng.schedule_packing(master,post,pack,planning_start,end,int(packing_people))

    # Add explicit balance note to all sections.
    for secname,obj in [("Preparation",prep),("Mixing",mixing),("Forming",forming),
                        ("Firing",firing),("Grinding / เจียร",grinding),("Cutting / ตัด",cutting),
                        ("Cleaning / ทำความสะอาด",cleaning),("Packing",packing)]:
        if obj is not None and not obj.empty:
            obj["V4.3 Planning Rule"]="MIN(Remaining Demand, Upstream Available Qty, Process Capacity, Downstream Need)"

    result={"Preparation":prep,"Mixing":mixing,"Forming":forming,"Firing":firing,
            "Grinding / เจียร":grinding,"Cutting / ตัด":cutting,"Cleaning / ทำความสะอาด":cleaning,
            "Packing":packing,"master":master,"capacity_evidence":evidence,
            "_firing_result":fr}
    issues=[x for x in [ip,im,ifo,ifi,ig,ic,icl,ipa] if x is not None and not x.empty]
    result["issues"]=pd.concat(issues,ignore_index=True,sort=False) if issues else pd.DataFrame()

    frames=[]
    for sec in ["Preparation","Mixing","Forming","Firing","Grinding / เจียร","Cutting / ตัด","Cleaning / ทำความสะอาด","Packing"]:
        x=result.get(sec)
        if x is not None and not x.empty:
            y=x.copy();y["Section"]=sec;frames.append(y)
    result["all"]=pd.concat(frames,ignore_index=True,sort=False) if frames else pd.DataFrame()
    result["workload_balance"]=workload_balance_report(result,balance_target)
    return result



# ============================================================================
# V4.5 GLOBAL PRIORITY + RESOURCE-BALANCED CAPACITY FILL
# Agreed management rules:
# P1 valid Revised Due Date (earliest first)
# P2 Manual Urgent / special request
# P3 fill unused resources with next feasible work
# P4 no Due Date => lowest priority, sorted by WO Date
# All open parts remain in the planning queue.
# Missing resource exception = AVAILABLE; staff records only shortages/holds.
# ============================================================================

def _priority_key_v45(r, planning_start):
    due=safe_date(r.get("Due Date"))
    wo_date=safe_date(r.get("WO Date"))
    urgent=str(r.get("Manual Urgent",r.get("Urgent",""))).strip().upper() in ("YES","Y","TRUE","1","URGENT","HIGH")
    # Earliest due-date work remains first. Manual urgent is the special-request
    # queue immediately after due-date-controlled work. No-date work is last.
    if due is not None:
        return (0, due, 0 if urgent else 1, wo_date or date.max, txt(r.get("Work Order","")))
    if urgent:
        return (1, date.min, 0, wo_date or date.max, txt(r.get("Work Order","")))
    return (3, date.max, 1, wo_date or date.max, txt(r.get("Work Order","")))

def _resource_available_v45(r):
    """Exception-based control: blank/unknown means available; explicit NO/HOLD blocks."""
    fields=[
        "Material Ready","Manpower Ready","Machine Ready","Tool / Mold Ready",
        "Equipment Ready","Kiln Furniture Ready"
    ]
    blockers=[]
    for f in fields:
        v=str(r.get(f,"")).strip().upper()
        if v in ("NO","N","FALSE","0","HOLD","NOT READY","UNAVAILABLE"):
            blockers.append(f)
    return (len(blockers)==0, blockers)

def _all_open_parts_queue_v45(plan_df, planning_start):
    q=plan_df.copy()
    # Do not drop missing due dates. Closed WOs only are excluded.
    if "Overall Closed" in q.columns:
        q=q[~q["Overall Closed"].fillna(False).astype(bool)].copy()
    q["_v45_key"]=q.apply(lambda r:_priority_key_v45(r,planning_start),axis=1)
    q=q.sort_values("_v45_key",kind="stable").drop(columns=["_v45_key"])
    return q

def _annotate_priority_v45(df, planning_start):
    if df is None or df.empty:return df
    x=df.copy()
    def label(r):
        due=safe_date(r.get("Due Date"))
        urg=str(r.get("Manual Urgent",r.get("Urgent",""))).strip().upper() in ("YES","Y","TRUE","1","URGENT","HIGH")
        if due is not None:return "P1 DUE DATE"
        if urg:return "P2 MANUAL URGENT"
        return "P4 NO DUE DATE - WO DATE / FILL"
    x["V4.5 Priority Class"]=x.apply(label,axis=1)
    return x

def _fill_resource_calendar_v45(master, planning_start, end, section, capacity_per_day,
                                remaining_col, upstream_ready_col=None):
    """
    Generic shared-capacity allocator.
    It allocates a GLOBAL daily capacity pool, not per-WO theoretical capacity.
    Priority queue is rescanned every day so unused capacity is filled by the
    next executable lower-priority WO.
    """
    if master is None or master.empty or capacity_per_day<=0:return pd.DataFrame(),pd.DataFrame()
    q=_all_open_parts_queue_v45(master,planning_start)
    remain={str(r.get("Work Order","")):max(num(r.get(remaining_col,0)),0) for _,r in q.iterrows()}
    rows=[];issues=[];d=planning_start
    while d<=end:
        if d.weekday()==6:
            d+=timedelta(days=1);continue
        cap=float(capacity_per_day)
        for _,r in q.iterrows():
            if cap<=0:break
            wo=str(r.get("Work Order",""))
            need=remain.get(wo,0)
            if need<=0:continue
            ok,blocks=_resource_available_v45(r)
            if not ok:
                issues.append({"Date":d,"Section":section,"Work Order":wo,
                               "Issue":"RESOURCE HOLD","Reason":", ".join(blocks)})
                continue
            upstream=need
            if upstream_ready_col and upstream_ready_col in r.index:
                upstream=max(num(r.get(upstream_ready_col,0)),0)
            qty=min(need,upstream,cap)
            if qty<=0:continue
            rows.append({"Plan Date":d,"Section / กระบวนการ":section,"Work Order":wo,
                         "Plan Qty":qty,"Due Date":safe_date(r.get("Due Date")),
                         "WO Date":safe_date(r.get("WO Date")),
                         "Manual Urgent":r.get("Manual Urgent",r.get("Urgent","")),
                         "V4.5 Planning Rule":"Due Date > Manual Urgent > Resource Fill > No Due Date by WO Date",
                         "V4.5 Resource Rule":"Shared capacity; explicit shortage blocks; blank means available"})
            remain[wo]-=qty;cap-=qty
        d+=timedelta(days=1)
    return pd.DataFrame(rows),pd.DataFrame(issues)

# Preserve proven V4.3 physical/detailed engines while forcing the full open queue
# (including no-date WOs) into the planning master and making priority visible.
_run_firing_v43 = run_firing_fast
def run_firing_fast(plan_df, capacity_path, planning_start, target=.80,maxv=.95,partial=False,
                    urgent_partial=True,starts=2,strict_forming=True,kiln_editor=None,
                    plate_master=None,iblock_master=None,hard_pull=True,pull_horizon_days=30,
                    balance_target=.90,validate_upstream=True,prep_capacity=1200.0):
    q=_all_open_parts_queue_v45(plan_df,planning_start)
    fr=_run_firing_v43(q,capacity_path,planning_start,target,maxv,partial,urgent_partial,starts,
                       strict_forming,kiln_editor,plate_master,iblock_master,hard_pull,
                       pull_horizon_days,balance_target,validate_upstream,prep_capacity)
    for k in ("raw","prepared","details"):
        if k in fr and isinstance(fr[k],pd.DataFrame):
            fr[k]=_annotate_priority_v45(fr[k],planning_start)
    fr["decision_rules"]=pd.DataFrame([
      ["P1","Due Date","Earliest valid Revised Due Date first","Khun Kan / MD: delivery protection"],
      ["P2","Manual Urgent","Special request can be raised by staff","Special management/production/sales request"],
      ["P3","Resource Balance","Fill remaining capacity with next feasible WIP","No unnecessary under/over-utilization"],
      ["P4","No Due Date","Keep all open WOs; sort last by WO Date","Waiting Sales decision / on-hold orders are not lost"],
      ["R1","Upstream Feasibility","Downstream qty cannot exceed physically reachable upstream qty","Khun Kan: no illogical high quantity"],
      ["R2","Shared Capacity","Several WOs share one real resource pool/day","Prevents double-counting machine/man capacity"],
      ["R3","Resource Exceptions","Blank=available; explicit shortage/hold blocks","Material, man, machine, tool, equipment, furniture"],
      ["R4","Kiln Utilization","Volume/furniture first; weight and program are hard constraints","Management utilization + physical feasibility"],
    ],columns=["Code","Decision","Rule","Management Emphasis"])
    return fr

_run_daily_v43 = run_daily_fast
def run_daily_fast(plan_df,capacity_path,planning_start,fr,horizon=30,prep_capacity=1200,
                   packing_people=1,hard_pull=True,balance_target=.90):
    q=_all_open_parts_queue_v45(plan_df,planning_start)
    result=_run_daily_v43(q,capacity_path,planning_start,fr,horizon,prep_capacity,
                          packing_people,hard_pull,balance_target)
    for k,v in list(result.items()):
        if isinstance(v,pd.DataFrame):
            result[k]=_annotate_priority_v45(v,planning_start)
    result["decision_rules"]=fr.get("decision_rules",pd.DataFrame())
    return result


# ============================================================================
# V4.6 - Plan 2026 "ตารางเตา" kiln calendar + mandatory next-day buffer.
# ============================================================================

def _next_workday_v46(d):
    x=d+timedelta(days=1)
    while x.weekday()==6:  # Sunday holiday
        x += timedelta(days=1)
    return x

def _clean_program_v46(v):
    s=txt(v).upper().replace(" ","")
    s=s.replace("P3(14)","P3").replace("P3(T14)","P3")
    if s in ("KM185","KM-185"): return "KM-185"
    if s in ("KM170","KM-170"): return "KM-170"
    if s.startswith("P1"): return "P1"
    if s.startswith("P2"): return "P2"
    if s.startswith("P3"): return "P3"
    if s.startswith("P6"): return "P6"
    return txt(v).upper()

def _program_days_v46(program):
    return {"P1":7,"P2":7,"P3":6,"P6":5,"KM-185":3,"KM-170":3,"BK-170":3}.get(
        _clean_program_v46(program),0)

def _xlsx_sparse_sheet_v46(path,sheet_name):
    """Fast sparse reader for huge ตารางเตา sheet; returns {row:{col:value}}."""
    import zipfile, xml.etree.ElementTree as ET, re
    ns_main="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ns_rel="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ns_pkg="http://schemas.openxmlformats.org/package/2006/relationships"
    def colnum(ref):
        m=re.match(r"([A-Z]+)",ref); n=0
        for ch in m.group(1):
            n=n*26+ord(ch)-64
        return n
    with zipfile.ZipFile(path) as z:
        wb=ET.fromstring(z.read("xl/workbook.xml"))
        rels=ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relmap={x.attrib["Id"]:x.attrib["Target"] for x in rels.findall("{%s}Relationship"%ns_pkg)}
        target=None
        for s in wb.findall(".//{%s}sheet"%ns_main):
            if s.attrib.get("name")==sheet_name:
                rid=s.attrib.get("{%s}id"%ns_rel)
                target="xl/"+relmap[rid].lstrip("/")
                break
        if not target:
            return {}
        shared=[]
        if "xl/sharedStrings.xml" in z.namelist():
            ss=ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in ss.findall("{%s}si"%ns_main):
                shared.append("".join((t.text or "") for t in si.iter("{%s}t"%ns_main)))
        root=ET.fromstring(z.read(target))
        rows={}
        for row in root.findall(".//{%s}sheetData/{%s}row"%(ns_main,ns_main)):
            rr=int(row.attrib["r"])
            if rr>120: break
            rd={}
            for c in row.findall("{%s}c"%ns_main):
                ref=c.attrib["r"]; cc=colnum(ref)
                if cc>1400: continue
                typ=c.attrib.get("t")
                v=c.find("{%s}v"%ns_main)
                val=None
                if typ=="s" and v is not None:
                    try: val=shared[int(v.text)]
                    except Exception: val=None
                elif typ=="inlineStr":
                    val="".join((t.text or "") for t in c.iter("{%s}t"%ns_main))
                elif v is not None:
                    raw=v.text
                    try:
                        numv=float(raw)
                        val=int(numv) if numv.is_integer() else numv
                    except Exception:
                        val=raw
                if val not in (None,""):
                    rd[cc]=val
            if rd:
                rows[rr]=rd
        return rows

def _slot_map_v46(rows,planning_year):
    r2=rows.get(2,{}); r4=rows.get(4,{}); r6=rows.get(6,{})
    slots={}
    last_month=None
    for c in range(1,1401):
        if c in r2:
            try:
                m=int(r2[c])
                if 1<=m<=12: last_month=m
            except Exception: pass
        tod=txt(r6.get(c,""))
        if tod not in ("เช้า","บ่าย") or last_month is None:
            continue
        day=None
        if tod=="บ่าย":
            try: day=int(r4.get(c))
            except Exception: day=None
        else:
            try: day=int(r4.get(c+1))
            except Exception: day=None
        if day and 1<=day<=31:
            try: slots[c]={"date":date(planning_year,last_month,day),"time":tod}
            except Exception: pass
    return slots

def read_plan2026_kiln_calendar(plan2026_path,planning_start):
    if not plan2026_path or not Path(plan2026_path).exists():
        return pd.DataFrame()
    try:
        rows=_xlsx_sparse_sheet_v46(plan2026_path,"ตารางเตา")
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    slots=_slot_map_v46(rows,planning_start.year)
    valid={"P1","P2","P3","P6","KM-185","KM-170","BK-170"}
    out=[]
    for rr,rd in rows.items():
        kiln=txt(rd.get(1,"")).upper()
        kind=txt(rd.get(3,"")).upper()
        if not ((kiln.startswith("T") or kiln.startswith("R")) and kind=="PLAN"):
            continue
        starts=[]; warns=[]
        for c,v in rd.items():
            if c not in slots: continue
            sv=txt(v)
            try:
                runno=float(v); isnum=runno>0
            except Exception:
                isnum=False
            if isnum:
                prog=None
                for dc in (1,2):
                    p=_clean_program_v46(rd.get(c+dc,""))
                    if p in valid:
                        prog=p; break
                if prog:
                    st=slots[c]
                    days=_program_days_v46(prog)
                    free=st["date"]+timedelta(days=days)
                    starts.append({
                        "Kiln":kiln,"Run No":int(runno) if runno.is_integer() else runno,
                        "Current Program":prog,"Start Date":st["date"],"Start Time":st["time"],
                        "Cycle Days":days,"Free Date":free,"Free Time":st["time"],
                        "Earliest New Load":_next_workday_v46(free),
                        "Source":"Plan 2026 / ตารางเตา"
                    })
            low=sv.lower()
            if any(k in low for k in ["รอซ่อม","งดใช้เตา","ซ่อม","maintenance","repair","hold"]):
                st=slots[c]; warns.append((st["date"],st["time"],sv))
        future_count=sum(x['Start Date']>=planning_start for x in starts)
        starts=[x for x in starts if x['Start Date']<planning_start]
        if starts:
            starts.sort(key=lambda x:(x["Start Date"],0 if x["Start Time"]=="เช้า" else 1))
            last=starts[-1]
            last["Available From"]=max(planning_start,last["Earliest New Load"])
            last["Status"]="AVAILABLE" if last["Available From"]<=planning_start else "RUNNING / COOLING / CLEANING"
            last["Calendar Warning"]=f"{future_count} on/after-cutover PLAN run(s) ignored; rebuild from selected start" if future_count else ""
            if warns:
                w=sorted(warns,key=lambda x:x[0])[-1]
                last["Calendar Warning"]=f"{w[0]} {w[1]}: {w[2]}"
            out.append(last)
        else:
            out.append({"Kiln":kiln,"Run No":"","Current Program":"","Start Date":None,"Start Time":"",
                        "Cycle Days":0,"Free Date":None,"Free Time":"","Earliest New Load":planning_start,
                        "Available From":planning_start,"Status":"NO ACTIVE RUN FOUND",
                        "Source":"Plan 2026 / ตารางเตา","Calendar Warning":f"{future_count} on/after-cutover planned runs are replaceable" if future_count else ""})
    return pd.DataFrame(out)

def apply_plan2026_kiln_calendar(kiln_editor,calendar_df,planning_start):
    ked=kiln_editor.copy()
    if calendar_df is None or calendar_df.empty:
        ked["Calendar Source"]="NOT FOUND - CHECK Plan 2026 / ตารางเตา"
        return ked
    cmap={txt(r["Kiln"]).upper():r for _,r in calendar_df.iterrows()}
    for i,k in ked.iterrows():
        name=txt(k.get("Kiln","")).upper()
        r=cmap.get(name)
        if r is None:
            ked.at[i,"Calendar Source"]="Kiln not found in ตารางเตา"
            continue
        ked.at[i,"Available From"]=r.get("Available From",planning_start) or planning_start
        ked.at[i,"Status"]=r.get("Status","AVAILABLE")
        ked.at[i,"Calendar Source"]="Plan 2026 / ตารางเตา"
        ked.at[i,"Current Program"]=r.get("Current Program","")
        ked.at[i,"Current Run No"]=r.get("Run No","")
        ked.at[i,"Current Run Start"]=r.get("Start Date",None)
        ked.at[i,"Current Run Time"]=r.get("Start Time","")
        ked.at[i,"Free Date"]=r.get("Free Date",None)
        ked.at[i,"Free Time"]=r.get("Free Time","")
        ked.at[i,"Earliest New Load"]=r.get("Earliest New Load",None)
        ked.at[i,"Calendar Warning"]=r.get("Calendar Warning","")
    return ked

_run_firing_v45=run_firing_fast
@_serial_firing
def run_firing_fast(plan_df,capacity_path,planning_start,target=.80,maxv=.95,partial=False,
                    urgent_partial=True,starts=2,strict_forming=True,kiln_editor=None,
                    plate_master=None,iblock_master=None,hard_pull=True,pull_horizon_days=30,
                    balance_target=.90,validate_upstream=True,prep_capacity=1200.0,
                    plan2026_path=None,previous_blocks=None,previous_files=None,retain_through=None):
    from suite.drying_confirmations import apply as _dry_confirmations
    from suite.central_paths import db_path as _shared_db_path
    plan_df=_dry_confirmations(plan_df,_shared_db_path())
    from suite.order_status import apply_frame as _manual_whole_status
    plan_df=_manual_whole_status(plan_df,_shared_db_path())
    settings=fire.Settings(planning_start=planning_start,target_volume=target,max_volume=maxv,
                           allow_partial=partial,allow_urgent_partial=urgent_partial,
                           vitrified_starts_per_day=int(starts))
    base_ked=kiln_editor.copy() if kiln_editor is not None else fire.default_kilns(settings)
    cal=read_plan2026_kiln_calendar(plan2026_path,planning_start)
    ked=apply_plan2026_kiln_calendar(base_ked,cal,planning_start)
    from suite.firing_start_policy import prior_availability
    from apps.firing.issued_transition import read_commitments,reconcile,reserve_frame,merge_operational
    retained=pd.DataFrame();review=pd.DataFrame();optimization_start=planning_start
    blocks=dict(previous_blocks or {})
    if previous_files and retain_through is not None:
        if retain_through<planning_start:raise ValueError('Retain-through date cannot precede the requested start')
        from apps.firing.previous_issued import previous_kiln_blocks
        prior,prior_audit=previous_kiln_blocks(previous_files,planning_start)
        for kiln,day in prior.items():blocks[kiln]=max(blocks.get(kiln,day),day)
        commitments=read_commitments(previous_files,planning_start,retain_through)
        retained,review,reservations,blocks=reconcile(commitments,plan_df,ked,blocks,int(starts),maxv)
        if not retained.empty:
            plan_for_optimization=reserve_frame(plan_df,reservations)
            optimization_start=retain_through+timedelta(days=1)
        else:plan_for_optimization=plan_df
    else:plan_for_optimization=plan_df
    ked=prior_availability(ked,blocks,optimization_start)
    fr=_run_firing_v45(plan_for_optimization,capacity_path,optimization_start,target,maxv,partial,urgent_partial,
                       starts,strict_forming,ked,plate_master,iblock_master,hard_pull,
                       pull_horizon_days,balance_target,validate_upstream,prep_capacity)
    if retain_through is not None:
        fr=merge_operational(fr,retained,review,planning_start,optimization_start)
    # Public plan identity always retains the requested horizon, including issued loads.
    fr.setdefault('settings',settings).planning_start=planning_start
    from suite.drying_gate import evaluate_drying
    drying=evaluate_drying(fr.get("details"),plan_df,fr.get("upstream_plan"),capacity_path,planning_start)
    fr["drying_check"]=drying
    if not drying.empty:
        held=set(drying.loc[drying["Timing status"].eq("HOLD"),"Load ID"].astype(str))
        for key in ("loads","details"):
            table=fr.get(key)
            if isinstance(table,pd.DataFrame) and "Load ID" in table:
                table["Drying release"]=["HOLD — confirm drying evidence" if str(x) in held else "REVIEW — drying timing; verify resources" for x in table["Load ID"]]
        fr["release_summary"]=pd.DataFrame([{"Status":"HOLD" if held else "PROVISIONAL", "Reason":"Drying timing from capacity master; oven capacity/staffing unverified", "Held loads":len(held)}])
    fr["kiln_calendar"]=cal
    fr["kiln_editor"]=ked
    if "decision_rules" in fr and isinstance(fr["decision_rules"],pd.DataFrame):
        cols=list(fr["decision_rules"].columns)
        rows=[
            ["K1","Kiln Calendar","Read dynamic availability from Plan 2026 / ตารางเตา","No manual availability assumption"],
            ["K2","Hot + Cleaning","Free Day D => earliest new load next working day","No same-day reload"],
        ]
        # Decision-rule table has four columns in V4.5. Keep exact schema.
        extra=pd.DataFrame([r[:len(cols)] for r in rows],columns=cols)
        fr["decision_rules"]=pd.concat([fr["decision_rules"],extra],ignore_index=True)
    from suite.firing_start_policy import start_diagnostic
    fr['selected_start_check']=start_diagnostic(fr,planning_start)
    return fr
