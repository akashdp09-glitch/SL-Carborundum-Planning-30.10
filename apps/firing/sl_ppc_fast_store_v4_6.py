
from __future__ import annotations
from pathlib import Path
from datetime import date, datetime
import sqlite3, json, re
import pandas as pd
import ppc_desktop_core_v1_9 as core

DEFAULT_DB = Path.home() / "SL_PPC_DATA" / "SL_PPC_FAST_DATA.db"

KEY_COLS = [
    "Work Order","Due Date","Customer","Specification","Order Qty","Product Code","Product Type",
    "D","T","H","Program","Category","Shape","Cut Factor","Net Weight g/pc","Gross Weight g/pc","WO Closure",
    "Plan2026 Firing Date","WO Date","Warehouse Target","Actual Warehouse Date","Sales Delivery Date","Firing Exit Date","Firing Issue","NCR","APPROVE","REJECT",
    "Preparation Plan","Preparation Actual","Preparation Status",
    "Mixing Plan","Mixing Actual","Mixing Status",
    "Forming Plan","Forming Actual","Forming Status",
    "Firing Plan","Firing Actual","Firing Status",
    "Grinding / Cutting Plan","Grinding / Cutting Actual","Grinding / Cutting Status",
    "Packing Plan","Packing Actual","Packing Status"
]

ALIASES = {
    "WO":"Work Order","WORKORDER":"Work Order","WORK ORDER":"Work Order","PRODUCTIONCODE":"Work Order",
    "DUE":"Due Date","DUE DATE":"Due Date","REVISED DUE DATE":"Due Date","กำหนดส่งใหม่":"Due Date",
    "CUSTOMER":"Customer","SPEC":"Specification","SPECIFICATION":"Specification",
    "QTY":"Order Qty","ORDER QTY":"Order Qty","ORDER":"Order Qty",
    "PRODUCT CODE":"Product Code","PRODUCTCODE":"Product Code",
    "PRODUCT TYPE":"Product Type","PROGRAM":"Program","CATEGORY":"Category","SHAPE":"Shape",
    "NET WEIGHT":"Net Weight g/pc","NET WEIGHT G/PC":"Net Weight g/pc","NW":"Net Weight g/pc",
    "GROSS WEIGHT":"Gross Weight g/pc","GROSS WEIGHT G/PC":"Gross Weight g/pc","GW":"Gross Weight g/pc",
    "CLOSURE":"WO Closure","WO CLOSURE":"WO Closure","STATUS":"WO Closure",
    "PREP PLAN":"Preparation Plan","PREPARATION PLAN":"Preparation Plan",
    "PREP ACTUAL":"Preparation Actual","PREPARATION ACTUAL":"Preparation Actual",
    "PREP STATUS":"Preparation Status","PREPARATION STATUS":"Preparation Status",
    "MIXING PLAN":"Mixing Plan","MIXING ACTUAL":"Mixing Actual","MIXING STATUS":"Mixing Status",
    "FORMING PLAN":"Forming Plan","FORMING ACTUAL":"Forming Actual","FORMING STATUS":"Forming Status",
    "FIRING PLAN":"Firing Plan","FIRING ACTUAL":"Firing Actual","FIRING STATUS":"Firing Status",
    "GRINDING PLAN":"Grinding / Cutting Plan","GRINDING ACTUAL":"Grinding / Cutting Actual",
    "GRINDING STATUS":"Grinding / Cutting Status","CUTTING PLAN":"Grinding / Cutting Plan",
    "CUTTING ACTUAL":"Grinding / Cutting Actual","CUTTING STATUS":"Grinding / Cutting Status",
    "PACKING PLAN":"Packing Plan","PACKING ACTUAL":"Packing Actual","PACKING STATUS":"Packing Status",
}

def db_path(path=None):
    p = Path(path) if path else DEFAULT_DB
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def _conn(path=None):
    return sqlite3.connect(db_path(path))

def _ensure_meta(c):
    c.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")

def _serialize_dates(df):
    d=df.copy()
    for c in d.columns:
        if "Date" in str(c):
            d[c]=d[c].apply(lambda x: x.isoformat() if hasattr(x,"isoformat") else ("" if pd.isna(x) else str(x)))
    return d

def _deserialize_dates(df):
    d=df.copy()
    for c in ["Due Date","Plan2026 Firing Date","WO Date","Warehouse Target","Actual Warehouse Date","Sales Delivery Date","Firing Exit Date"]:
        if c in d.columns:
            x=pd.to_datetime(d[c],errors="coerce")
            # IMPORTANT: never allow pandas.NaT to leave the data layer.
            d[c]=x.apply(lambda v: None if pd.isna(v) else v.date())
    return d

def calculate(df, wip_weight="NET"):
    if df is None or df.empty: return pd.DataFrame()
    d=df.copy()
    for c in ["Order Qty","Net Weight g/pc","Gross Weight g/pc"] + \
             [f"{s} Plan" for s in core.SECTIONS] + [f"{s} Actual" for s in core.SECTIONS]:
        if c not in d.columns: d[c]=0
        d[c]=pd.to_numeric(d[c],errors="coerce").fillna(0)
    for c in ["Work Order","Customer","Specification","Product Code","Product Type","Program","Category","Shape","WO Closure"] + \
             [f"{s} Status" for s in core.SECTIONS]:
        if c not in d.columns: d[c]=""
        d[c]=d[c].fillna("").astype(str)
    # Authoritative WO closure: Packing Status EU OR Overall WO Closure FC.
    # A packed/closed WO must never return to the OPEN firing queue.
    _fc=d["WO Closure"].apply(core.closed)
    _eu=d["Packing Status"].apply(core.closed) if "Packing Status" in d.columns else False
    d["Overall Closed"]=_fc | _eu
    for sec in core.SECTIONS:
        d[f"{sec} Remaining"]=(d[f"{sec} Plan"]-d[f"{sec} Actual"]).clip(lower=0)
    a={s:pd.to_numeric(d[f"{s} Actual"],errors="coerce").fillna(0) for s in core.SECTIONS}
    d["Eff Preparation"]=pd.concat([a[s] for s in core.SECTIONS],axis=1).max(axis=1)
    d["Eff Mixing"]=pd.concat([a[s] for s in core.SECTIONS[1:]],axis=1).max(axis=1)
    d["Eff Forming"]=pd.concat([a[s] for s in core.SECTIONS[2:]],axis=1).max(axis=1)
    d["Eff Firing"]=pd.concat([a[s] for s in core.SECTIONS[3:]],axis=1).max(axis=1)
    d["Eff Grinding / Cutting"]=pd.concat([a[s] for s in core.SECTIONS[4:]],axis=1).max(axis=1)
    d["Eff Packing"]=a["Packing"]
    d["WIP Preparation"]=(d["Order Qty"]-d["Eff Preparation"]).clip(lower=0)
    d["WIP Mixing"]=(d["Eff Preparation"]-d["Eff Mixing"]).clip(lower=0)
    d["WIP Forming"]=(d["Eff Mixing"]-d["Eff Forming"]).clip(lower=0)
    d["WIP Firing"]=(d["Eff Forming"]-d["Eff Firing"]).clip(lower=0)
    d["WIP Grinding / Cutting"]=(d["Eff Firing"]-d["Eff Grinding / Cutting"]).clip(lower=0)
    d["WIP Packing"]=(d["Eff Grinding / Cutting"]-d["Eff Packing"]).clip(lower=0)
    for c in [f"WIP {s}" for s in core.SECTIONS]:
        d.loc[d["Overall Closed"],c]=0
    weightcol="Net Weight g/pc" if str(wip_weight).upper()=="NET" else "Gross Weight g/pc"
    d["Unit kg/pc"]=pd.to_numeric(d[weightcol],errors="coerce").fillna(0)/1000.0
    d["Open Qty"]=(d["Order Qty"]-d["Eff Packing"]).clip(lower=0).where(~d["Overall Closed"],0)
    d["Open Weight kg"]=d["Open Qty"]*d["Unit kg/pc"]
    d["Priority"]=d["Due Date"].apply(lambda x: core.due_priority(x,date.today()))
    return d

def full_sync(plan_path, path=None, mapping=None):
    df=core.read_plan2026(plan_path, mapping=mapping)
    raw=df[[c for c in KEY_COLS if c in df.columns]].copy()
    raw=_serialize_dates(raw)
    with _conn(path) as c:
        _ensure_meta(c)
        raw.to_sql("orders",c,if_exists="replace",index=False)
        c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('plan_path',?)",(str(plan_path),))
        c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('plan_mtime',?)",(str(Path(plan_path).stat().st_mtime),))
        c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('last_sync',?)",(datetime.now().isoformat(timespec="seconds"),))
    return len(raw)

def load(path=None, wip_weight="NET"):
    p=db_path(path)
    if not p.exists(): return pd.DataFrame()
    with _conn(path) as c:
        try: df=pd.read_sql_query("SELECT * FROM orders",c)
        except Exception: return pd.DataFrame()
    df=_deserialize_dates(df)
    return calculate(df,wip_weight)

def meta(path=None):
    if not db_path(path).exists(): return {}
    with _conn(path) as c:
        _ensure_meta(c)
        return dict(c.execute("SELECT k,v FROM meta").fetchall())

def source_changed(path=None):
    m=meta(path); fp=m.get("plan_path")
    if not fp or not Path(fp).exists(): return False
    try: return str(Path(fp).stat().st_mtime) != m.get("plan_mtime")
    except Exception: return False

def normalize_columns(df):
    d=df.copy()
    ren={}
    for c in d.columns:
        k=str(c).strip()
        ku=re.sub(r"\s+"," ",k.upper())
        ren[c]=ALIASES.get(k,ALIASES.get(ku,k))
    return d.rename(columns=ren)

def parse_clipboard_text(text):
    from io import StringIO
    if not str(text).strip(): return pd.DataFrame()
    d=pd.read_csv(StringIO(text),sep="\t",dtype=object)
    return normalize_columns(d)

def apply_updates(updates, path=None, allow_decrease=False):
    if updates is None or updates.empty: return {"updated":0,"new":0,"unchanged":0,"conflicts":pd.DataFrame()}
    u=normalize_columns(updates)
    if "Work Order" not in u.columns: raise ValueError("Update data must contain Work Order column.")
    u["Work Order"]=u["Work Order"].astype(str).str.strip()
    u=u[u["Work Order"]!=""].copy()
    old=load(path)
    # Keep stored/raw columns, not calculated columns.
    raw_cols=[c for c in KEY_COLS if c in old.columns]
    if old.empty:
        base=pd.DataFrame(columns=KEY_COLS)
    else:
        base=old[raw_cols].copy()
    base=base.set_index("Work Order",drop=False)
    conflicts=[]; updated=0; new=0; unchanged=0
    actual_cols=[f"{s} Actual" for s in core.SECTIONS]
    for _,r in u.iterrows():
        wo=str(r.get("Work Order","")).strip()
        if not wo: continue
        if wo not in base.index:
            nr={c:"" for c in KEY_COLS}; nr["Work Order"]=wo
            for c in u.columns:
                if c in KEY_COLS and pd.notna(r[c]): nr[c]=r[c]
            base.loc[wo]=pd.Series(nr)
            new+=1; continue
        changed=False
        for c in u.columns:
            if c=="Work Order" or c not in KEY_COLS or pd.isna(r[c]) or str(r[c]).strip()=="":
                continue
            ov=base.at[wo,c] if c in base.columns else ""
            nv=r[c]
            if c in actual_cols:
                try:
                    of=float(ov or 0); nf=float(nv)
                    if nf < of and not allow_decrease:
                        conflicts.append({"Work Order":wo,"Field":c,"Current":of,"New":nf,"Reason":"ACTUAL DECREASE"})
                        continue
                except Exception: pass
            if c=="WO Closure" and core.closed(ov) and not core.closed(nv):
                conflicts.append({"Work Order":wo,"Field":c,"Current":ov,"New":nv,"Reason":"CLOSED -> OPEN"})
                continue
            if str(ov) != str(nv):
                if c not in base.columns: base[c]=""
                base.at[wo,c]=nv; changed=True
        if changed: updated+=1
        else: unchanged+=1
    out=base.reset_index(drop=True)
    out=_serialize_dates(out)
    with _conn(path) as c:
        _ensure_meta(c)
        out.to_sql("orders",c,if_exists="replace",index=False)
        c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('last_update',?)",(datetime.now().isoformat(timespec="seconds"),))
    return {"updated":updated,"new":new,"unchanged":unchanged,"conflicts":pd.DataFrame(conflicts)}

def update_from_file(update_path, path=None, allow_decrease=False):
    p=Path(update_path)
    if p.suffix.lower()==".csv": u=pd.read_csv(p)
    else: u=pd.read_excel(p)
    return apply_updates(u,path,allow_decrease)

def write_update_template(path):
    cols=["Work Order","Due Date","Customer","Order Qty","Program","Category",
          "Preparation Actual","Mixing Actual","Forming Actual","Firing Actual",
          "Grinding / Cutting Actual","Packing Actual","WO Closure"]
    pd.DataFrame(columns=cols).to_excel(path,index=False)


# --- V4 override: preserve raw D/T/H strings such as 300/250 for taper ---
def full_sync(plan_path, path=None, mapping=None):
    import openpyxl
    from openpyxl.utils import column_index_from_string
    mp=core.DEFAULT_MAP.copy()
    if mapping:
        for k, v in mapping.items():
            if v not in (None, ""):
                mp[k] = v
    wb=openpyxl.load_workbook(plan_path,data_only=True,read_only=True,keep_links=False)
    if mp["sheet"] not in wb.sheetnames:
        wb.close(); raise ValueError(f"Sheet {mp['sheet']} not found")
    ws=wb[mp["sheet"]]
    idx={k:column_index_from_string(v)-1 for k,v in mp.items() if k not in {"sheet","data_start_row"} and isinstance(v,str)}
    maxc=max(idx.values())+1
    def gv(vals,k):
        i=idx[k]; return vals[i] if i<len(vals) else None
    rows=[]
    for vals in ws.iter_rows(min_row=int(mp.get("data_start_row",4)),max_col=maxc,values_only=True):
        wo=str(gv(vals,"WO") or "").strip()
        if not wo:continue
        r={
            "Work Order":wo,"Due Date":gv(vals,"Due Date"),"Customer":gv(vals,"Customer"),
            "Specification":gv(vals,"Specification"),"Order Qty":gv(vals,"Order Qty"),
            "Product Code":gv(vals,"Product Code"),"Product Type":gv(vals,"Product Type"),
            "D":gv(vals,"D"),"T":gv(vals,"T"),"H":gv(vals,"H"),
            "Program":gv(vals,"Program"),"Category":gv(vals,"Category"),"Shape":gv(vals,"Shape"),"Cut Factor":gv(vals,"Cut Factor"),
            "Net Weight g/pc":gv(vals,"Net Weight g/pc"),"Gross Weight g/pc":gv(vals,"Gross Weight g/pc"),
            "WO Closure":gv(vals,"WO Closure"),"Plan2026 Firing Date":gv(vals,"Plan2026 Firing Date"),"WO Date":gv(vals,"WO Date"),"Warehouse Target":gv(vals,"Warehouse Target"),"Actual Warehouse Date":gv(vals,"Actual Warehouse Date"),"Sales Delivery Date":gv(vals,"Sales Delivery Date"),"Firing Exit Date":gv(vals,"Firing Exit Date"),"Firing Issue":gv(vals,"Firing Issue"),"NCR":gv(vals,"NCR"),"APPROVE":gv(vals,"APPROVE"),"REJECT":gv(vals,"REJECT"),
        }
        for sec in core.SECTIONS:
            r[f"{sec} Plan"]=gv(vals,f"{sec} Plan");r[f"{sec} Actual"]=gv(vals,f"{sec} Actual");r[f"{sec} Status"]=gv(vals,f"{sec} Status")
        rows.append(r)
    wb.close()
    raw=pd.DataFrame(rows)
    raw=_serialize_dates(raw)
    with _conn(path) as c:
        _ensure_meta(c)
        raw.to_sql("orders",c,if_exists="replace",index=False)
        c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('plan_path',?)",(str(plan_path),))
        c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('plan_mtime',?)",(str(Path(plan_path).stat().st_mtime),))
        c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('last_sync',?)",(datetime.now().isoformat(timespec="seconds"),))
    return len(raw)
