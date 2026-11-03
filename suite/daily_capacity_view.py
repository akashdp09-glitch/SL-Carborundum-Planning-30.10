"""Normalize daily plan/capacity data for unit-safe section graphs."""
import numpy as np
import pandas as pd


def collapse_capacities(frame):
    """Aggregate by date/process without dropping native pcs or mills basis."""
    if frame is None or frame.empty:
        return frame
    x=frame.copy(); rows=[]
    for (day,section),group in x.groupby(['Plan Date','Section'],dropna=False):
        def total(name):
            return float(pd.to_numeric(group.get(name,pd.Series(0,index=group.index)),errors='coerce').fillna(0).sum())
        ton=total('Plan ton'); cap_t=total('Capacity ton')
        mixing_plan=pd.to_numeric(group.get('Mixing Plan MO',pd.Series(dtype=float)),errors='coerce').dropna()
        mixing_cap=pd.to_numeric(group.get('Mixing Capacity MO',pd.Series(dtype=float)),errors='coerce').dropna()
        util=ton/cap_t*100 if cap_t>0 else None
        rows.append({'Plan Date':day,'Section':section,'Plan pcs':total('Plan pcs'),'Capacity pcs':total('Capacity pcs'),
            'Plan ton':ton,'Capacity ton':cap_t,'Mixing Plan MO':float(mixing_plan.max()) if len(mixing_plan) else None,
            'Mixing Capacity MO':float(mixing_cap.max()) if len(mixing_cap) else None,'Utilization %':round(util,1) if util is not None else None,
            'Gap ton':cap_t-ton if cap_t>0 else None,
            'Capacity Basis':' | '.join(group.get('Capacity Basis',pd.Series(dtype=str)).dropna().astype(str).drop_duplicates()),
            'Reason / Limiting Factor':' | '.join(group.get('Reason / Limiting Factor',pd.Series(dtype=str)).dropna().astype(str).drop_duplicates()),
            'Capacity Type':group.get('Capacity Type',pd.Series([''])).iloc[0] if len(group) else '',
            'Plan Type':'Executable scheduled quantity'})
    return pd.DataFrame(rows).sort_values(['Plan Date','Section']).reset_index(drop=True)


def capacity_validation(plans,caps):
    """Compare each section/date in compatible units; Mixing stays a native-unit graph."""
    if plans is None or plans.empty:return pd.DataFrame()
    p=plans.copy()
    if 'Plan Date' not in p or 'Section' not in p:return pd.DataFrame()
    p['_d']=pd.to_datetime(p['Plan Date'],errors='coerce').dt.date
    rows=[]
    for (day,section),group in p.groupby(['_d','Section']):
        pcs=float(pd.to_numeric(group.get('Plan Qty',pd.Series(0,index=group.index)),errors='coerce').fillna(0).sum())
        ton=float(pd.to_numeric(group.get('Plan ton',pd.Series(0,index=group.index)),errors='coerce').fillna(0).sum())
        cap_pcs=cap_t=0.0
        if caps is not None and not caps.empty and 'Section' in caps:
            dates=pd.to_datetime(caps.get('Plan Date'),errors='coerce').dt.date
            matched=caps[caps['Section'].astype(str).eq(str(section)) & dates.eq(day)]
            cap_pcs=float(pd.to_numeric(matched.get('Capacity pcs',pd.Series(0,index=matched.index)),errors='coerce').fillna(0).sum())
            cap_t=float(pd.to_numeric(matched.get('Capacity ton',matched.get('Capacity t',pd.Series(0,index=matched.index))),errors='coerce').fillna(0).sum())
        if cap_t>0 and ton>0:load=ton/cap_t*100;basis='ton'
        elif cap_pcs>0:load=pcs/cap_pcs*100;basis='pcs'
        else:load=np.nan;basis='not directly comparable'
        rows.append({'Date':day,'Section':section,'Plan pcs':pcs,'Plan ton':ton,'Capacity pcs':cap_pcs,'Capacity ton':cap_t,
            'Load %':load,'Basis':basis,'Result':'PASS' if pd.notna(load) and load<=100.0001 else ('FAIL' if pd.notna(load) else 'CHECK')})
    return pd.DataFrame(rows)
