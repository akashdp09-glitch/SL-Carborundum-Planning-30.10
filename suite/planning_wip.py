"""Lightweight Plan-2026 open-order balance view for the central WIP page."""
from pathlib import Path
import pandas as pd

_STAGES=['Preparation','Mixing','Forming','Firing','Grinding / Cutting','Packing']

def open_order_wip(master):
    """Normalize a parsed Plan-2026 master into one current open-balance row per WO."""
    if not isinstance(master,pd.DataFrame) or master.empty:
        raise ValueError('Plan-2026 parser returned no work-order rows.')
    x=master.copy()
    if 'Work Order' not in x:
        raise ValueError('Parsed Plan-2026 has no Work Order field.')
    order=pd.to_numeric(x.get('Order Qty',pd.Series(0,index=x.index)),errors='coerce').fillna(0)
    packed=pd.to_numeric(x.get('Packing Actual Qty',x.get('Packing Actual',pd.Series(0,index=x.index))),errors='coerce').fillna(0)
    # The engine can return a stale/blank `pcs` column for some workbook layouts.
    # Prefer the source quantity less packed quantity whenever those fields exist.
    balance=(order-packed).clip(lower=0)
    raw_pcs=pd.to_numeric(x.get('pcs',x.get('Open Qty',balance)),errors='coerce')
    pcs=raw_pcs.where(raw_pcs.notna(),balance).fillna(0).clip(lower=0)
    closed=pd.Series(False,index=x.index)
    for col in ('Authoritative Closed','Strict Closed','Overall Closed','Packing Closed','Final Closed'):
        if col in x:
            values=x[col]
            if values.dtype==object:
                values=values.astype(str).str.strip().str.casefold().isin({'true','1','yes','closed','close','done','finished','ปิดใบสั่ง'})
            else:values=values.fillna(False).astype(bool)
            closed|=values
    pcs=pcs.mask(closed,0)
    x['pcs']=pcs
    if 'ton' in x:
        x['ton']=pd.to_numeric(x['ton'],errors='coerce')
    else:
        kgpc=pd.to_numeric(x.get('Plan2026 kg/pc',pd.Series(float('nan'),index=x.index)),errors='coerce')
        x['ton']=pcs*kgpc/1000.0
    x['ton']=pd.to_numeric(x['ton'],errors='coerce').where(~closed,0)
    category=next((c for c in ('Product Category','Category','Type') if c in x),None)
    x['Product Category']=x[category] if category else 'UNCLASSIFIED'
    x['Product Category']=x['Product Category'].fillna('UNCLASSIFIED').astype(str).str.upper().str.strip().replace({'':'UNCLASSIFIED','NAN':'UNCLASSIFIED','F':'P'})
    if 'Due Date' not in x:
        x['Due Date']=x.get('Delivery Date',pd.NaT)
    if 'Section' not in x:
        def _stage(row):
            for name in _STAGES:
                q=pd.to_numeric(pd.Series([row.get(name+' Remaining Qty',0)]),errors='coerce').fillna(0).iloc[0]
                if q>0:return name
            return 'Open / Check'
        x['Section']=x.apply(_stage,axis=1)
    x=x.loc[(~closed)&pcs.gt(0)&x['Work Order'].astype(str).str.strip().ne('')].copy()
    if x['Work Order'].duplicated().any():
        agg={'pcs':'max','ton':'max','Product Category':'first','Due Date':'min','Section':'first'}
        for c in ('Customer','Customer Thai','Customer English','Product Code','Specification','Plan2026 Source Row','Excel Sequence'):
            if c in x:agg[c]='first'
        x=x.groupby('Work Order',as_index=False,dropna=False).agg(agg)
    return x.reset_index(drop=True)

def read_plan_wip_fallback(path):
    """Use the supported Plan-2026 sheet reader without the heavier schedule/report transforms."""
    path=Path(path)
    if not path.is_file():raise FileNotFoundError(f'Active Plan-2026 file is not available: {path}')
    import sys
    daily=Path(__file__).resolve().parents[1]/'apps'/'daily'
    if str(daily) not in sys.path:sys.path.insert(0,str(daily))
    import sl_daily_engine_v3_22_from_v17 as engine
    master,_,_=engine.read_plan2026(path,{})
    return open_order_wip(master)
