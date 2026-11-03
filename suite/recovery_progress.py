"""Traceable recovery execution summary from Production's dated recovery workbook.

Source semantics: sheet แผน Recovery, row 3 fields; planned FG date/qty at columns 168-169,
actual warehouse date/qty at columns 170-171 (1-based). Weights are estimated from Cover.GW
(total grams) / Cover.QTY when both are valid. Missing weights stay missing and are never zero-filled.
"""
from __future__ import annotations
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook


def _wo(x):
    if x is None: return ''
    return ''.join(str(x).strip().upper().split())

def _date(x):
    if isinstance(x, datetime): return x.date()
    if isinstance(x, date): return x
    if isinstance(x, str):
        s=x.strip()
        for fmt in ('%d/%m/%Y','%Y-%m-%d','%m/%d/%Y','%d-%m-%Y'):
            try:return datetime.strptime(s,fmt).date()
            except ValueError:pass
    return None

def read_recovery_progress(path: str | Path):
    """Return source-row detail plus month/week aggregations and a source manifest."""
    path=Path(path)
    wb=load_workbook(path,read_only=True,data_only=True)
    try:
        names={str(n).strip().casefold():n for n in wb.sheetnames}
        if 'แผน recovery' not in names:
            raise ValueError('Required sheet แผน Recovery is missing.')
        # Capture gross weight per piece from source Cover; column positions are validated by headers.
        weight={}
        if 'cover' in names:
            ws=wb[names['cover']]
            ws.reset_dimensions()
            header=next(ws.iter_rows(min_row=1,max_row=1,max_col=95,values_only=True),())
            h={str(v).strip().casefold():i for i,v in enumerate(header) if v is not None}
            wo_i=h.get('productioncode'); qty_i=h.get('qty'); gw_i=h.get('gw')
            if wo_i is not None and qty_i is not None and gw_i is not None:
                for row in ws.iter_rows(min_row=2,max_col=95,values_only=True):
                    key=_wo(row[wo_i] if wo_i<len(row) else None)
                    try:q=float(row[qty_i]); g=float(row[gw_i])
                    except (TypeError,ValueError):continue
                    if key and q>0 and g>0:
                        val=g/q/1000.0
                        weight.setdefault(key,[]).append(val)
        ws=wb[names['แผน recovery']]
        ws.reset_dimensions()
        rows=[]
        # read fixed 176-column range; use explicit source coordinates for the validated template
        for excel_row,row in enumerate(ws.iter_rows(min_row=4,max_col=176,values_only=True),4):
            key=_wo(row[1] if len(row)>1 else None)
            if not key or key in {'#N/A','N/A','NONE'}:continue
            try: plan=float(row[168] or 0)
            except (TypeError,ValueError): plan=0.0
            try: actual=float(row[170] or 0)
            except (TypeError,ValueError): actual=0.0
            plan=max(0,plan);actual=max(0,actual)
            pdte=_date(row[167]); adte=_date(row[169])
            # Remaining is row-linked so actuals on one recovery line cannot erase a different line's requirement.
            remain=max(plan-actual,0)
            per=weight.get(key,[])
            kgpc=(sorted(per)[len(per)//2] if per else None)
            rows.append({'Work Order':str(row[1]).strip(),'_key':key,'Source row':excel_row,
                'Customer':row[4] if len(row)>4 else None,'Specification':row[5] if len(row)>5 else None,
                'Recovery source qty (pcs)':row[6] if len(row)>6 else None,
                'Plan date':pdte,'Plan (pcs)':plan,'Actual date':adte,'Actual produced (pcs)':actual,'Actual applied to plan (pcs)':0.0,
                'Remaining planned (pcs)':remain,'kg/pc estimate':kgpc,
                'Plan (kg)':plan*kgpc if kgpc is not None else None,
                'Actual (kg)':actual*kgpc if kgpc is not None else None,
                'Remaining (kg)':remain*kgpc if kgpc is not None else None,
                'Recovery status':row[172] if len(row)>172 else None,
                'Reason':row[175] if len(row)>175 else None})
        detail=pd.DataFrame(rows)
        if detail.empty:return detail, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {'source':path.name,'sheet':'แผน Recovery','source_rows':0,'distinct_wos':0,'weight_coverage_wos':0}
        # Reconcile actual quantity at normalized WO level first, then consume that actual
        # against that WO's scheduled rows in date order. This avoids duplicate recovery
        # lines inflating the remaining quantity, while never using one WO's output for another.
        detail['Remaining planned (pcs)']=0.0
        for key, group in detail.groupby('_key',sort=False):
            plan_rows=group[pd.to_numeric(group['Plan (pcs)'],errors='coerce').fillna(0).gt(0)].copy()
            credit=float(pd.to_numeric(group['Actual produced (pcs)'],errors='coerce').fillna(0).sum())
            plan_rows['_sort_date']=pd.to_datetime(plan_rows['Plan date'],errors='coerce')
            plan_rows=plan_rows.sort_values(['_sort_date','Source row'],na_position='last')
            for idx, r in plan_rows.iterrows():
                q=float(r['Plan (pcs)']); used=min(q,credit); credit=max(0,credit-used)
                detail.loc[idx,'Actual applied to plan (pcs)']=used
                detail.loc[idx,'Remaining planned (pcs)']=max(0,q-used)
            matched=max(0.0,min(float(pd.to_numeric(group['Plan (pcs)'],errors='coerce').fillna(0).sum()),float(pd.to_numeric(group['Actual produced (pcs)'],errors='coerce').fillna(0).sum())))
            actual_rows=group[pd.to_numeric(group['Actual produced (pcs)'],errors='coerce').fillna(0).gt(0)].copy()
            actual_rows['_sort_actual']=pd.to_datetime(actual_rows['Actual date'],errors='coerce')
            actual_rows=actual_rows.sort_values(['_sort_actual','Source row'],na_position='last')
            for idx,r in actual_rows.iterrows():
                q=float(r['Actual produced (pcs)']); used=min(q,matched); matched=max(0,matched-used)
                detail.loc[idx,'Unmatched actual (pcs)']=q-used
        detail['Actual applied to plan (kg)']=detail['Actual applied to plan (pcs)']*detail['kg/pc estimate']
        detail['Unmatched actual (kg)']=detail['Unmatched actual (pcs)']*detail['kg/pc estimate']
        detail['Remaining (kg)']=detail['Remaining planned (pcs)']*detail['kg/pc estimate']
        def bucket(x, mode):
            if not isinstance(x,date): return 'Date missing'
            if mode=='Month': return x.strftime('%Y-%m')
            monday=x-timedelta(days=x.weekday()); sunday=monday+timedelta(days=6)
            return f'{monday:%Y-%m-%d} to {sunday:%Y-%m-%d}'
        def summarise(period_col, label, kind):
            d=detail.copy(); d[label]=d[period_col].map(lambda x:bucket(x,kind)); out=[]
            for period,g in d.groupby(label,sort=True,dropna=False):
                pg=g[g['Plan (pcs)']>0]; ag=g[g['Actual produced (pcs)']>0]; rg=g[g['Remaining planned (pcs)']>0]
                out.append({label:period,'Planned WOs':pg['_key'].nunique(),'Planned pcs':pg['Plan (pcs)'].sum(),
                    'Actual-produced WOs':ag['_key'].nunique(),'Actual pcs':g['Actual produced (pcs)'].sum(),'Actual applied to plan pcs':g['Actual applied to plan (pcs)'].sum(),'Unmatched actual pcs':g['Unmatched actual (pcs)'].sum(),
                    'Remaining WOs':rg['_key'].nunique(),'Remaining pcs':g['Remaining planned (pcs)'].sum(),
                    'Planned kg':pg['Plan (kg)'].sum(min_count=1),'Actual kg':g['Actual (kg)'].sum(min_count=1),'Actual applied to plan kg':g['Actual applied to plan (kg)'].sum(min_count=1),'Unmatched actual kg':g['Unmatched actual (kg)'].sum(min_count=1),
                    'Remaining kg':g['Remaining (kg)'].sum(min_count=1),
                    'Weight-covered WOs':g.loc[g['kg/pc estimate'].notna(),'_key'].nunique()})
            return pd.DataFrame(out)
        def periods(kind):
            # Plan and remaining belong to the committed plan date; production belongs to actual receipt date.
            actual_cols=['Actual-produced WOs','Actual pcs','Actual kg','Unmatched actual pcs','Unmatched actual kg']
            p=summarise('Plan date','Period',kind).drop(columns=['Actual-produced WOs','Actual pcs','Actual kg','Unmatched actual pcs','Unmatched actual kg'],errors='ignore')
            a=summarise('Actual date','Period',kind)[['Period']+actual_cols]
            if p.empty:return a
            if a.empty:return p
            return p.merge(a,on='Period',how='outer').sort_values('Period')
        weekly=periods('Week')
        months=periods('Month')
        # Total uses unique WOs overall; sums remain source-line totals (planned/actual values are line quantities).
        pg=detail[detail['Plan (pcs)']>0]; ag=detail[detail['Actual produced (pcs)']>0]; rg=detail[detail['Remaining planned (pcs)']>0]
        total=pd.DataFrame([{'Scope':'All recovery schedule rows','Planned WOs':pg['_key'].nunique(),'Planned pcs':pg['Plan (pcs)'].sum(),
            'Actual-produced WOs':ag['_key'].nunique(),'Actual pcs':detail['Actual produced (pcs)'].sum(),'Actual applied to plan pcs':detail['Actual applied to plan (pcs)'].sum(),'Unmatched actual pcs':detail['Unmatched actual (pcs)'].sum(),
            'Remaining WOs':rg['_key'].nunique(),'Remaining pcs':detail['Remaining planned (pcs)'].sum(),
            'Planned kg':pg['Plan (kg)'].sum(min_count=1),'Actual kg':detail['Actual (kg)'].sum(min_count=1),'Actual applied to plan kg':detail['Actual applied to plan (kg)'].sum(min_count=1),'Unmatched actual kg':detail['Unmatched actual (kg)'].sum(min_count=1),
            'Remaining kg':detail['Remaining (kg)'].sum(min_count=1),
            'Weight-covered WOs':detail.loc[detail['kg/pc estimate'].notna(),'_key'].nunique()}])
        meta={'source':path.name,'sheet':'แผน Recovery','plan_date':'column 168','planned_qty':'column 169','actual_date':'column 170','actual_qty':'column 171','weight':'Cover.GW / Cover.QTY (kg/pc)','source_rows':len(detail),'distinct_wos':detail['_key'].nunique(),'weight_coverage_wos':detail.loc[detail['kg/pc estimate'].notna(),'_key'].nunique()}
        return detail,weekly,months,total,meta
    finally: wb.close()
