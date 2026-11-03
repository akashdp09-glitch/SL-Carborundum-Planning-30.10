"""Source-backed review of dated recovery snapshots and Sales/Production product masters."""
from pathlib import Path
import re
import pandas as pd
from openpyxl import load_workbook

def _norm(v):
    return re.sub(r'\s+','',str(v or '').strip()).upper()

def _number(v):
    try:
        if v is None or str(v).strip().lower() in {'','nan','none','-','ยังไม่ได้กำหนด'}: return None
        return float(str(v).replace(',',''))
    except Exception: return None

def read_sales_register(path):
    wb=load_workbook(path,read_only=True,data_only=True)
    rows=[]
    try:
        for name in wb.sheetnames:
            if not name.strip().startswith('สินค้าขึ้นทะเบียน รหัส'): continue
            ws=wb[name]; maxrow=ws.max_row or 10000; ws.reset_dimensions()
            for rn,row in enumerate(ws.iter_rows(min_row=3,max_row=maxrow,max_col=18,values_only=True),3):
                code=row[11] if len(row)>11 else None
                if not code or _norm(code) in {'#N/A','-','0'}: continue
                rows.append({'Product Code':str(code).strip(),'Sales Description':row[12] if len(row)>12 else None,'Sales Brand':row[13] if len(row)>13 else None,'Sales Pcs/Box':row[16] if len(row)>16 else None,'Sales Inner Box':row[14] if len(row)>14 else None,'Sales Outer Box':row[15] if len(row)>15 else None,'Sales Sheet':name,'Sales Source Row':rn})
    finally: wb.close()
    return pd.DataFrame(rows)

def compare_product_masters(sales_path, packaging_path):
    from apps.daily import packaging_standard_source as ps
    sales=read_sales_register(sales_path)
    prod=ps.read_tables(str(packaging_path))['Packaging standard'].copy()
    codecol=next((c for c in prod.columns if str(c).strip().lower() in {'product code','รหัสสินค้า'}),None)
    qtycol=next((c for c in prod.columns if str(c).strip().lower() in {'pcs/box','จำนวนบรรจุต่อกล่อง'}),None)
    if not codecol: raise ValueError('Production packaging standard has no Product Code field.')
    prod=prod[prod[codecol].notna()].copy(); prod['Product Code']=prod[codecol].map(lambda x:str(x).strip()); prod['_key']=prod['Product Code'].map(_norm)
    sales['_key']=sales['Product Code'].map(_norm)
    # Retain source-row multiplicity. A code with multiple conflicting entries is always flagged.
    pm={}
    for k,g in prod.groupby('_key',dropna=False):
        if not k: continue
        qvals=set(str(x).strip() for x in (g[qtycol].tolist() if qtycol else []) if x is not None and str(x).strip() not in {'','nan','-','ยังไม่ได้กำหนด'})
        row=g.iloc[-1]
        pm[k]={'qty':row[qtycol] if qtycol else None,'spec':row.get('Pack Spec'),'customer':row.get('Pack Customer'),'duplicate_count':len(g),'qty_conflict':len(qvals)>1,'source_row':int(g.index[-1])+4 if str(g.index[-1]).isdigit() else g.index[-1]}
    rows=[]
    for _,s in sales.iterrows():
        p=pm.get(s['_key']); sq=_number(s['Sales Pcs/Box']); pq=_number(p['qty']) if p else None
        if p is None: status='NO PRODUCTION STANDARD MATCH'
        elif p['qty_conflict']: status='DUPLICATE PRODUCTION CODE — REVIEW'
        elif sq is not None and pq is not None and sq!=pq: status='PACK QTY MISMATCH'
        elif sq is None or pq is None: status='PACK QTY MISSING / UNDEFINED'
        else: status='PACK QTY MATCH'
        rows.append({'Product Code':s['Product Code'],'Sales Description':s['Sales Description'],'Sales Brand':s['Sales Brand'],'Sales Pcs/Box':s['Sales Pcs/Box'],'Sales Inner Box':s['Sales Inner Box'],'Sales Outer Box':s['Sales Outer Box'],'Production Pcs/Box':p['qty'] if p else None,'Production Pack Spec':p['spec'] if p else None,'Production Pack Customer':p['customer'] if p else None,'Production Code Rows':p['duplicate_count'] if p else 0,'Sales Source Sheet':s['Sales Sheet'],'Sales Source Row':s['Sales Source Row'],'Production Source Sheet':'มาตรฐานการบรรจุ' if p else None,'Production Source Row':p['source_row'] if p else None,'Comparison':status})
    return pd.DataFrame(rows),prod

def read_recovery_snapshot(path):
    xls=pd.ExcelFile(path)
    if 'แผน Recovery' not in xls.sheet_names: raise ValueError('Recovery workbook has no แผน Recovery sheet.')
    d=pd.read_excel(path,sheet_name='แผน Recovery',header=2)
    d=d[d.get('Fac No').notna()].copy(); d['Recovery Source Row']=d.index+4
    d['Fac No']=d['Fac No'].astype(str).str.strip(); d['_key']=d['Fac No'].map(_norm)
    # Preserve historical and internal dates separately; text holds in the internal-date field are not dates.
    d['Original Due Date']=pd.to_datetime(d.get('กำหนดส่งมอบเดิม'),errors='coerce')
    d['Internal Recovery Date']=pd.to_datetime(d.get('กำหนดส่งใหม่'),errors='coerce')
    d['Internal Date / Hold Status']=d.get('กำหนดส่งใหม่').astype(str).replace('nan','')
    d['Recovery Result']=d.get('Achieve by Item').astype(str).replace('nan','Not recorded')
    d['Recovery result source cell']='FQ'+d['Recovery Source Row'].astype(str)
    d['Recovery reason (source)']=d.get('สาเหตุที่ตกแผน',pd.Series('',index=d.index)).fillna('').astype(str).str.strip()
    d['Recovery note (source)']=d.get('หมายเหตุ',pd.Series('',index=d.index)).fillna('').astype(str).str.strip()
    d['Reason source cell']=d['Recovery Source Row'].map(lambda r: f'FT{int(r)}' if 'สาเหตุที่ตกแผน' in d.columns else '')
    d['Note source cell']=d['Recovery Source Row'].map(lambda r: f'FS{int(r)}' if 'หมายเหตุ' in d.columns else '')
    def _cell_refs(r):
        n=int(r['Recovery Source Row']); refs=[f'B{n}',f'C{n}',f'D{n}',f'G{n}',f'I{n}',f'FQ{n}']
        if r.get('Note source cell'):refs.append(r['Note source cell'])
        if r.get('Reason source cell'):refs.append(r['Reason source cell'])
        return ', '.join(refs)
    d['Recovery source cell references']=d.apply(_cell_refs,axis=1)
    # Reported warehouse quantities are matched to the exact WO; units follow the source header and are not assumed.
    packed={}
    if 'Report เข้าคลัง' in xls.sheet_names:
        p=pd.read_excel(path,sheet_name='Report เข้าคลัง',header=1)
        if 'P/PB' in p and 'QTY.' in p:
            p=p[p['P/PB'].notna()].copy(); p['_key']=p['P/PB'].map(_norm); p['QTY.']=pd.to_numeric(p['QTY.'],errors='coerce').fillna(0)
            packed=p.groupby('_key')['QTY.'].sum().to_dict()
    d['Reported Warehouse QTY (source unit)']=d['_key'].map(packed).fillna(0)
    counts=d['_key'].value_counts(); d['Duplicate WO Rows']=d['_key'].map(counts); d['Duplicate WO Review']=d['Duplicate WO Rows'].gt(1)
    d['Recovery snapshot as-of date']=pd.NaT
    if 'สรุปแผนเข้าคลัง' in xls.sheet_names:
        try:
            snap=pd.read_excel(path,sheet_name='สรุปแผนเข้าคลัง',header=None,nrows=1).iloc[0,0]
            d['Recovery snapshot as-of date']=pd.to_datetime(snap,errors='coerce')
        except Exception:pass
    sheets=list(xls.sheet_names);xls.close()
    return d,sheets


def recovery_unique_orders(recovery):
    """One row per normalized WO; conflicting source statuses/reasons stay visible."""
    d=recovery.copy() if isinstance(recovery,pd.DataFrame) else pd.DataFrame()
    if d.empty:return pd.DataFrame()
    if '_key' not in d:d['_key']=d.get('Fac No',pd.Series('',index=d.index)).map(_norm)
    def one_value(series, conflict='CONFLICT — inspect source rows'):
        vals=[]
        for value in series:
            text=str(value).strip()
            if text and text.lower() not in {'nan','none','nat'} and text not in vals:vals.append(text)
        return vals[0] if len(vals)==1 else (conflict if len(vals)>1 else '')
    rows=[]
    for key,g in d[d['_key'].astype(str).ne('')].groupby('_key',sort=False):
        first=g.sort_values('Recovery Source Row').iloc[0] if 'Recovery Source Row' in g else g.iloc[0]
        status=one_value(g.get('Recovery Result',pd.Series(dtype=str))) or 'Not recorded'
        raw_reasons=[]
        for col in ['Recovery reason (source)','Recovery note (source)']:
            if col in g:
                vals=[str(v).strip() for v in g[col] if pd.notna(v) and str(v).strip() and str(v).strip().lower()!='nan']
                raw_reasons.extend(v for v in vals if v not in raw_reasons)
        rows.append({'_key':key,'Work Order':first.get('Fac No',''),'Recovery rows':len(g),
                     'Recovery status (source)':status,
                     'Recovery reason (source)':one_value(g.get('Recovery reason (source)',pd.Series(dtype=str))),
                     'Recovery note (source)':one_value(g.get('Recovery note (source)',pd.Series(dtype=str))),
                     'Recovery source WIP (unit not specified)':pd.to_numeric(g.get('Wip',pd.Series(dtype=float)),errors='coerce').max(),
                     'Recovery source order qty':pd.to_numeric(g.get('QTY',pd.Series(dtype=float)),errors='coerce').max(),
                     'Recovery reason / note':'; '.join(raw_reasons) if raw_reasons else 'No reason recorded in source',
                     'Original due date':first.get('Original Due Date'),
                     'Production proposed date / hold':one_value(g.get('Internal Date / Hold Status',pd.Series(dtype=str))),
                     'Recovery source row(s)':', '.join(map(str,g.get('Recovery Source Row',pd.Series(dtype=int)).tolist())),
                     'Recovery source cell references':'; '.join(g.get('Recovery source cell references',pd.Series(dtype=str)).astype(str).tolist())})
    out=pd.DataFrame(rows)
    # FQ is the source's per-item result; duplicate rows with conflicting values are not resolved by picking one.
    out.loc[out['Recovery status (source)'].str.contains('CONFLICT',na=False),'Recovery status (source)']='CONFLICT — inspect source rows'
    return out

def reconcile_recovery_to_plan(recovery, plan_master, overdue, as_of):
    """Bridge a dated Production recovery snapshot to the current Plan-2026 state.

    The recovery workbook is historical evidence; it is never used to overwrite
    Plan-2026 due dates or to infer Production approval. Work-order keys are
    normalized only for matching, while source IDs are retained for display.
    """
    asof=pd.Timestamp(as_of).normalize()
    r=recovery.copy() if isinstance(recovery,pd.DataFrame) else pd.DataFrame()
    p=plan_master.copy() if isinstance(plan_master,pd.DataFrame) else pd.DataFrame()
    o=overdue.copy() if isinstance(overdue,pd.DataFrame) else pd.DataFrame()
    if r.empty:
        return pd.DataFrame(),pd.DataFrame()
    if '_key' not in r:
        src='Fac No' if 'Fac No' in r else ('Work Order' if 'Work Order' in r else None)
        r['_key']=r[src].map(_norm) if src else ''
    if not p.empty:
        wc='Work Order' if 'Work Order' in p else ('WO' if 'WO' in p else None)
        if wc:
            p['_key']=p[wc].map(_norm)
            p=p[p['_key'].ne('')].copy()
    if not o.empty:
        wc='Work Order' if 'Work Order' in o else ('WO' if 'WO' in o else None)
        o['_key']=o[wc].map(_norm) if wc else ''
    overdue_keys=set(o.get('_key',pd.Series(dtype=str)).dropna().astype(str))

    def unanimous_date(x):
        z=pd.to_datetime(x,errors='coerce').dropna().dt.normalize().drop_duplicates()
        return z.iloc[0] if len(z)==1 else pd.NaT
    def unanimous_text(x):
        vals=[str(v).strip() for v in x if pd.notna(v) and str(v).strip() not in {'','nan','None'}]
        vals=list(dict.fromkeys(vals))
        return vals[0] if len(vals)==1 else ('CONFLICT — inspect source rows' if len(vals)>1 else '')
    def num_max(x):
        v=pd.to_numeric(x,errors='coerce').dropna()
        return float(v.max()) if not v.empty else None
    rg=[]
    for key,g in r[r['_key'].astype(str).ne('')].groupby('_key',sort=False):
        first=g.sort_values('Recovery Source Row').iloc[0] if 'Recovery Source Row' in g else g.iloc[0]
        rg.append({'_key':key,'Recovery Work Order':first.get('Fac No',first.get('Work Order','')),
                   'Recovery source rows':len(g),'Recovery source row(s)':', '.join(map(str,g['Recovery Source Row'].tolist())) if 'Recovery Source Row' in g else '',
                   'Historical due date (Recovery)':unanimous_date(g.get('Original Due Date',pd.Series(dtype=object))),
                   'Production proposed date / hold':unanimous_text(g.get('Internal Date / Hold Status',pd.Series(dtype=object))),
                   'Recovery result (source)':unanimous_text(g.get('Recovery Result',pd.Series(dtype=object))),
                   'Recovery QTY (source)':num_max(g.get('QTY',pd.Series(dtype=object))),
                   'Recovery WIP (source)':num_max(g.get('Wip',pd.Series(dtype=object))),
                   'Recovery customer (source)':unanimous_text(g.get('Custumer',pd.Series(dtype=object))),
                   'Recovery specification (source)':unanimous_text(g.get('Spec',pd.Series(dtype=object))),
                   'Recovery reason (source)':unanimous_text(g.get('Recovery reason (source)',pd.Series(dtype=object))),
                   'Recovery note (source)':unanimous_text(g.get('Recovery note (source)',pd.Series(dtype=object))),
                   'Recovery source cell references':'; '.join(g.get('Recovery source cell references',pd.Series(dtype=str)).astype(str).tolist()),
                   'Recovery result source cell(s)':', '.join(g.get('Recovery result source cell',pd.Series(dtype=str)).astype(str).tolist())})
    rec=pd.DataFrame(rg)
    pg=[]
    if not p.empty:
        for key,g in p.groupby('_key',sort=False):
            row=g.iloc[0]
            def first_col(names, default=None):
                for c in names:
                    if c in g:
                        vals=g[c].dropna()
                        if not vals.empty:return vals.iloc[0]
                return default
            due=pd.to_datetime(g.get('Due Date',pd.Series(dtype=object)),errors='coerce').dropna()
            closed=any(str(v).strip().casefold() in {'true','1','yes','closed','complete','completed'} for v in g.get('Authoritative Closed',pd.Series(False,index=g.index)))
            pcs=pd.to_numeric(g.get('pcs',pd.Series(0,index=g.index)),errors='coerce').fillna(0)
            pg.append({'_key':key,'Plan Work Order':first_col(['Work Order','WO'],''),
                       'Current Plan due date':due.min().normalize() if not due.empty else pd.NaT,
                       'Plan open balance (pcs)':float(pcs.max()),'Plan status':('CLOSED' if closed else ('OPEN' if pcs.max()>0 else 'NO POSITIVE BALANCE')),
                       'Plan section / location':first_col(['Section','Plan Location / Status'],''),
                       'Plan source row(s)':', '.join(map(str,g['Plan-2026 Source Row'].tolist())) if 'Plan-2026 Source Row' in g else ''})
    plan=pd.DataFrame(pg)
    if not plan.empty:
        rec=rec.merge(plan,on='_key',how='left')
    else:
        for c in ['Plan Work Order','Current Plan due date','Plan open balance (pcs)','Plan status','Plan section / location','Plan source row(s)']:
            rec[c]=None
    rec['Current overdue in Plan-2026']=rec['_key'].isin(overdue_keys)
    def explain(row):
        if pd.isna(row.get('Plan Work Order')) or not str(row.get('Plan Work Order') or '').strip(): return 'Not found in active Plan-2026'
        if row.get('Current overdue in Plan-2026'): return 'Still overdue: included in current Plan-2026 overdue list'
        if row.get('Plan status')=='CLOSED': return 'Plan-2026 marks the WO closed; historical recovery entry remains'
        if row.get('Plan status')=='NO POSITIVE BALANCE': return 'Plan-2026 has no positive open balance'
        due=row.get('Current Plan due date')
        if pd.isna(due): return 'Active Plan-2026 has no usable due date'
        if pd.Timestamp(due).normalize()>=asof:
            hist=row.get('Historical due date (Recovery)')
            if pd.notna(hist) and pd.Timestamp(due).normalize()>pd.Timestamp(hist).normalize():
                return 'Current Plan due date is later than Recovery historical due date; confirm authorized revision'
            return 'Open in Plan-2026 but due today or later; not currently overdue'
        return 'Review status/date mismatch against overdue rule'
    rec['Reconciliation result']=rec.apply(explain,axis=1)
    rec['As of date']=asof
    # Also return current overdue WOs absent from this Production snapshot.
    only=[]
    if not o.empty:
        seen=set(rec['_key'])
        for _,row in o.iterrows():
            key=row.get('_key','')
            if not key or key in seen: continue
            only.append({'Work Order':row.get('Work Order',''),'Current due date':row.get('Due Date'),
                         'Open balance (pcs)':row.get('pcs'),'Section / location':row.get('Section',''),
                         'Plan source row(s)':row.get('Plan-2026 Source Row',''),
                         'Reconciliation result':'Overdue in current Plan-2026; absent from this dated Production recovery snapshot'})
    return rec,pd.DataFrame(only)
