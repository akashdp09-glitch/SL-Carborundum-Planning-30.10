"""Carry issued commitments into operational outputs before optimizing the remainder.

Original rows and quantities are retained as evidence. Reservations never change
production actuals. An invalid load is rejected atomically, with every row in the
review table; unknown physical evidence remains an explicit execution HOLD.
"""
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import pandas as pd
from apps.firing.previous_issued import _as_date, _column, _norm, _read_upload

ALIASES = {
    'Work Order': lambda n: n.startswith(('workorder','productioncode')) or n=='wo',
    'Kiln': lambda n: n.startswith('kiln') or n=='เตา',
    'Load Date': lambda n: n.startswith(('loadingdate','loaddate','firingdate','firingstartdate')),
    'Planned Firing Qty': lambda n: n.startswith(('plannedfiringqty','plannedqty','firingqty','planqty')) or n in {'qtypcs','quantity','qty'},
    'Program Finish Date': lambda n: n.startswith(('programfinishdate','firingfinishdate','firingcomplete','unloadtakeoutdate','unloaddate')),
    'Running Days': lambda n: n.startswith(('runningdays','cycledays','kilncycledays')),
    'Load ID': lambda n: n.startswith(('loadid','loadnumber','loadno')),
    'Program': lambda n: n.startswith('program'),
    'Customer': lambda n:n.startswith('customer'),
    'Specification': lambda n:n.startswith('specification'),
    'Category': lambda n:n.startswith(('productcategory','category')),
    'Weight kg': lambda n:n=='weightkg',
}


def read_commitments(files, start, through):
    """Use exactly one authoritative detail table per workbook, never its summary."""
    rows=[];seen_files=set()
    for upload in files or []:
        data=_read_upload(upload);digest=sha256(data).hexdigest()
        if digest in seen_files:continue
        seen_files.add(digest)
        filename=getattr(upload,'name',None) or (Path(upload).name if isinstance(upload,(str,Path)) else 'Previous issued plan')
        with pd.ExcelFile(BytesIO(data)) as book:
            found=False
            sheets=sorted(book.sheet_names,key=lambda s:('operatorprint' not in _norm(s),book.sheet_names.index(s)))
            for sheet in sheets:
                for header in range(12):
                    columns=pd.read_excel(book,sheet_name=sheet,header=header,nrows=0).columns
                    mapping={key:_column(columns,predicate) for key,predicate in ALIASES.items()}
                    if not all(mapping[k] for k in ('Work Order','Kiln','Load Date','Planned Firing Qty')):continue
                    table=pd.read_excel(book,sheet_name=sheet,header=header)
                    for pos,(_,record) in enumerate(table.iterrows(),header+2):
                        loaded=_as_date(record.get(mapping['Load Date']))
                        if not loaded or not start<=loaded<=through:continue
                        r=record.to_dict()
                        for key,col in mapping.items():
                            if col and col!=key:r.pop(col,None)
                        for key,col in mapping.items():
                            if col:r[key]=record.get(col)
                        r['Work Order']=str(r['Work Order']).strip();r['Kiln']=str(r['Kiln']).strip().upper();r['Load Date']=loaded
                        finish=_as_date(r.get('Program Finish Date'))
                        days=pd.to_numeric(r.get('Running Days'),errors='coerce')
                        if finish is None and pd.notna(days) and days>0:finish=loaded+timedelta(days=int(round(days)))
                        r['Program Finish Date']=finish;r['Firing Complete']=finish
                        r['Running Days']=(finish-loaded).days if finish else None
                        r['Planned Firing Qty']=pd.to_numeric(r.get('Planned Firing Qty'),errors='coerce');r['Qty pcs']=r['Planned Firing Qty']
                        original=r.get('Load ID');original='' if original is None or pd.isna(original) else str(original)
                        identity=f'{digest}|{r["Kiln"]}|{loaded}|{original}|{r.get("Program","")}'
                        r['Original Load ID']=original;r['Load ID']='ISSUED-'+sha256(identity.encode()).hexdigest()[:14]
                        r['Issued source']=str(filename);r['Issued sheet']=sheet;r['Issued row']=pos;r['Issued SHA256']=digest
                        r['Plan origin']='RETAINED ISSUED';rows.append(r)
                    found=True;break
                if found:break
            if not found:raise ValueError(f'No supported work-order detail table in previous plan: {filename}')
    return pd.DataFrame(rows)


def reconcile(commitments, plan, kiln_editor, blocks=None, starts=2, max_volume=.95):
    """Reserve only complete loads supported by remaining formed WIP and calendar.

    No proportional quantity clipping or fabricated capacity/finish evidence.
    Missing geometry is retained under HOLD and never called capacity-verified.
    """
    if commitments.empty:return commitments.copy(),pd.DataFrame(),{},dict(blocks or {})
    jobs={str(k).strip():g for k,g in plan.groupby('Work Order',sort=False)}
    remaining={};available={}
    for wo,g in jobs.items():
        if len(g)!=1:continue
        r=g.iloc[0]
        def amount(*names):
            for name in names:
                q=pd.to_numeric(r.get(name),errors='coerce')
                if pd.notna(q):return max(float(q),0)
            return 0.
        actual=amount('Eff Firing','Firing Actual');formed=amount('Eff Forming','Forming Actual')
        target=amount('Firing Plan','Order Qty')
        remaining[wo]=max(target-actual,0);available[wo]=min(max(formed-actual,0),remaining[wo])
    editors={str(r.get('Kiln','')).upper():r for _,r in kiln_editor.iterrows()}
    occupied=dict(blocks or {});reservations={};accepted=[];review=[];normal={};resin=set();t0=set()
    ordered=commitments.sort_values(['Load Date','Kiln','Load ID','Issued row'],kind='stable')
    for lid,g in ordered.groupby('Load ID',sort=False):
        row=g.iloc[0];kiln=row['Kiln'];day=row['Load Date'];finish=_as_date(row['Program Finish Date']);reasons=[];holds=[]
        quantities=g.groupby('Work Order')['Planned Firing Qty'].sum(min_count=1)
        if g['Planned Firing Qty'].isna().any() or g['Planned Firing Qty'].le(0).any():reasons.append('Missing/nonpositive issued quantity')
        if not finish or finish<day or g['Program Finish Date'].isna().any() or g['Program Finish Date'].nunique()!=1:reasons.append('Missing/conflicting cycle finish')
        if occupied.get(kiln) and day<occupied[kiln]:reasons.append(f'Kiln occupied until {occupied[kiln]}')
        editor=editors.get(kiln)
        if editor is None:reasons.append('Kiln absent from active master')
        else:
            available_day=_as_date(editor.get('Available From'))
            if available_day and available_day>day:reasons.append(f'Active kiln calendar unavailable until {available_day}')
            if not bool(editor.get('Enabled',True)):reasons.append('Kiln disabled in active master')
            allowed=str(editor.get('Programs',editor.get('Program',''))).upper()
            program=str(row.get('Program','')).strip().upper()
            if allowed and program and program not in [x.strip() for x in allowed.replace(';',',').replace('|',',').split(',')]:reasons.append('Program not compatible with active kiln master')
        for wo,q in quantities.items():
            job=jobs.get(wo)
            if job is None:reasons.append(f'{wo}: absent from current Plan 2026');continue
            if len(job)!=1:reasons.append(f'{wo}: duplicate current master rows');continue
            if bool(job.iloc[0].get('Overall Closed',False)):reasons.append(f'{wo}: whole order closed');continue
            if pd.isna(q) or q>available.get(wo,0)+1e-7:reasons.append(f'{wo}: issued {q:g} exceeds unreserved formed WIP {available.get(wo,0):g}')
        typ='resin' if kiln in {'R4','R5','R6'} else 't0' if kiln=='T0' else 'normal'
        if typ=='normal' and normal.get(day,0)>=starts:reasons.append('Normal kiln starts/day capacity exceeded')
        if typ=='resin' and (day,kiln) in resin:reasons.append('Repeated resin start on same kiln/day')
        if typ=='t0' and day in t0:reasons.append('Repeated T0 start/day')
        # Weight/geometry from an operator print is often incomplete. Never infer it.
        weight=pd.to_numeric(g.get('Weight kg',pd.Series(dtype=float)),errors='coerce').sum(min_count=1)
        limit=pd.to_numeric(editor.get('Weight Limit kg',editor.get('Physical kg')) if editor is not None else None,errors='coerce')
        if pd.notna(weight) and pd.notna(limit) and weight>limit+1e-7:reasons.append('Issued load exceeds active kiln weight limit')
        for field in ('Geometric Occupancy Util','Volume Util'):
            if field in g:
                occupancy=pd.to_numeric(g[field],errors='coerce')
                if occupancy.gt(max_volume+1e-7).any():reasons.append('Issued load exceeds selected maximum occupancy')
        holds.append('Physical placement/furniture and current capacity must be verified before release')
        for _,r in g.iterrows():
            review.append({'Load ID':lid,'Work Order':r['Work Order'],'Load Date':day,'Kiln':kiln,'Issued qty':r['Planned Firing Qty'],'Current unreserved formed WIP':available.get(r['Work Order'],None),'Result':'REJECTED' if reasons else 'RETAINED — EXECUTION HOLD','Reason':'; '.join(reasons or holds),'Source':r['Issued source'],'Sheet':r['Issued sheet'],'Row':r['Issued row'],'SHA256':r['Issued SHA256']})
        if reasons:continue
        for wo,q in quantities.items():available[wo]-=float(q);reservations[wo]=reservations.get(wo,0)+float(q)
        occupied[kiln]=finish+timedelta(days=1)
        if typ=='normal':normal[day]=normal.get(day,0)+1
        elif typ=='resin':resin.add((day,kiln))
        else:t0.add(day)
        kept=g.copy();kept['Release Gate']='HOLD — verify retained physical loading and drying';kept['Release Reason']='; '.join(holds)
        kept['Cutover / Previous Plan Protection']='RETAINED ISSUED — original date and quantity';accepted.append(kept)
    return (pd.concat(accepted,ignore_index=True) if accepted else commitments.iloc[:0].copy(),pd.DataFrame(review),reservations,occupied)


def reserve_frame(plan,reservations):
    out=plan.copy();out['Retained firing reservation Qty']=out['Work Order'].astype(str).str.strip().map(reservations).fillna(0)
    return out


def merge_operational(fr,retained,review,start,new_start):
    """Single output state drives UI, Excel, operator print and daily firing anchor."""
    fr['transition_review']=review
    fr['retained_transition']=retained
    fr['transition_control']=pd.DataFrame([{'Requested start':start,'New optimization begins':new_start,'Retained rows':len(retained),'Retained loads':retained['Load ID'].nunique() if not retained.empty else 0,'Quantity policy':'Retained quantities reserved before optimization; production actuals unchanged','Release policy':'Retained records remain HOLD until physical loading and drying verified'}])
    if retained.empty:return fr
    loads=[]
    for lid,g in retained.groupby('Load ID',sort=False):
        r=g.iloc[0].to_dict();r.pop('Work Order',None)
        r['Qty pcs']=g['Planned Firing Qty'].sum();r['WO Lines']=len(g)
        r['Weight kg']=pd.to_numeric(g.get('Weight kg',pd.Series(dtype=float)),errors='coerce').sum(min_count=1)
        loads.append(r)
    for key,data in [('loads',pd.DataFrame(loads)),('details',retained)]:
        prior=fr.get(key,pd.DataFrame()).copy()
        if not prior.empty:prior['Plan origin']='NEW OPTIMIZED'
        fr[key]=pd.concat([data,prior],ignore_index=True,sort=False).sort_values(['Load Date','Kiln','Load ID'],kind='stable').reset_index(drop=True)
    # Operator-print-only sources can lack summary metrics. Unknown must remain
    # unknown, while keeping summary views functional even when no new load fits.
    for col in ['Weight Limit kg','Weight Util','Geometric Occupancy Util','Height Util','Program Preferred Min kg','Program Upper kg','Gross m3','Usable m3']:
        if col not in fr['loads']:fr['loads'][col]=float('nan')
    floor=pd.DataFrame([{'Load ID':lid,'Note':'Retained issued load: original detail retained; top/front placement requires verification, no new geometry invented.'} for lid in retained['Load ID'].unique()])
    fr['floor']=pd.concat([floor,fr.get('floor',pd.DataFrame())],ignore_index=True,sort=False)
    return fr
