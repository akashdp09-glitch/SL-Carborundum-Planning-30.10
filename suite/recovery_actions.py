"""Build a conservative, traceable cross-functional overdue-order recovery worksheet."""
from __future__ import annotations
import pandas as pd
import numpy as np

RISK_FIELDS=['Current Status / WIP','Bottleneck Process','Delivery Risk','Projected Finish','Suggested Safe Due Date','Detailed Reason','Recovery Action']
CONFIRM_FIELDS={
 'Sales Priority — confirm':'',
 'Sales Confirmed Customer Due Date':'',
 'Production Capacity / Bottleneck — confirm':'',
 'Production Earliest Feasible Finish — confirm':'',
 'Jointly Agreed Recovery Date':'',
 'Action Owner':'',
 'Agreement Status':'PENDING SALES + PRODUCTION CONFIRMATION',
 'Next Review Date':'',
 'Comments / Evidence':'',
}

def build_recovery_actions(master, delivery_risk, as_of):
    """Return only open urgent/risk WOs; missing data stays visible as a confirmation need."""
    if not isinstance(master,pd.DataFrame) or master.empty or 'Work Order' not in master.columns:return pd.DataFrame()
    m=master.copy(); m['Work Order']=m['Work Order'].astype(str).str.strip()
    m=m[m['Work Order'].ne('')].copy()
    m['_due']=pd.to_datetime(m.get('Due Date'),errors='coerce')
    m['_closed']=m.get('Overall Closed',pd.Series(False,index=m.index)).fillna(False).astype(bool)
    open_source=m.get('_open_qty',m.get('Remaining Packing',m.get('Order Qty',pd.Series(0,index=m.index))))
    m['_open_qty']=pd.to_numeric(open_source,errors='coerce').fillna(0).clip(lower=0)
    r=delivery_risk.copy() if isinstance(delivery_risk,pd.DataFrame) else pd.DataFrame()
    if not r.empty and 'Work Order' in r.columns:
        r['Work Order']=r['Work Order'].astype(str).str.strip()
        risk_col=r.get('Delivery Risk',pd.Series('',index=r.index)).fillna('').astype(str).str.upper()
        r['_risk_rank']=np.select([risk_col.str.contains('HIGH|OVERDUE|LATE|AT RISK|สูง|ล่าช้า|ค้างส่ง|เสี่ยง',regex=True),risk_col.str.contains('MEDIUM|WATCH|ปานกลาง|เฝ้าระวัง',regex=True)],[2,1],default=0)
        r=r.sort_values('_risk_rank',ascending=False).drop_duplicates('Work Order',keep='first')
        cols=['Work Order']+[c for c in RISK_FIELDS if c in r.columns]
        m=m.merge(r[cols],on='Work Order',how='left',suffixes=('','_risk'))
    for c in RISK_FIELDS:
        if c not in m.columns:m[c]=''
    asof=pd.Timestamp(as_of).normalize()
    m['_days_late']=(asof-m['_due']).dt.days
    risk=m.get('Delivery Risk',pd.Series('',index=m.index)).fillna('').astype(str).str.upper()
    urgent=(m['_due'].isna()) | (m['_due'].notna()&(m['_due']<=asof+pd.Timedelta(days=3))) | risk.str.contains('HIGH|LATE|OVERDUE|AT RISK|สูง|ล่าช้า|ค้างส่ง|เสี่ยง',regex=True)
    m=m[(~m['_closed'])&(m['_open_qty']>0)&urgent].copy()
    if m.empty:return pd.DataFrame()
    m['Recovery Priority']=np.select([m['_due'].notna()&(m['_due']<asof),m['_due'].notna()&(m['_due']<=asof+pd.Timedelta(days=3)),m['_due'].isna()],['1 OVERDUE','2 DUE WITHIN 3 DAYS','3 CONFIRM DUE DATE'],default='4 DELIVERY RISK')
    if 'Recovery Action' not in m.columns:m['Recovery Action']='Confirm next process, constraint, and earliest feasible completion.'
    else:m['Recovery Action']=m['Recovery Action'].fillna('').replace('', 'Confirm next process, constraint, and earliest feasible completion.')
    for c,v in CONFIRM_FIELDS.items():m[c]=v
    m['Snapshot as of (Thailand local date — Phan Thong, Chonburi)']=asof.date().isoformat()
    m['Days overdue (positive = late)']=m['_days_late']
    m['Open quantity (pcs)']=m['_open_qty']
    ordered=['Recovery Priority','Work Order','Product Code','Customer','Category','Due Date','Days overdue (positive = late)','Open quantity (pcs)',*RISK_FIELDS,*CONFIRM_FIELDS.keys(),'Snapshot as of (Thailand local date — Phan Thong, Chonburi)']
    result=m[[c for c in ordered if c in m.columns]].copy()
    return result.sort_values(['Recovery Priority','Due Date'],na_position='last').reset_index(drop=True)


def build_recovery_daily_allocation(master, delivery_risk, schedule, capacity, as_of):
    """Reconcile urgent open WOs to the existing finite-capacity daily schedule.

    This does not add demand to the plan. Backorders already present in Plan 2026
    are counted once in the unified schedule. The result labels capacity gaps,
    unrated timing steps, incomplete allocations, and late projected completion.
    """
    actions = build_recovery_actions(master, delivery_risk, as_of)
    empty = (pd.DataFrame(), pd.DataFrame())
    if actions.empty:
        return empty
    wos = set(actions['Work Order'].astype(str).str.strip())
    p = schedule.copy() if isinstance(schedule, pd.DataFrame) else pd.DataFrame()
    c = capacity.copy() if isinstance(capacity, pd.DataFrame) else pd.DataFrame()
    if p.empty or not {'Work Order', 'Section', 'Plan Date'}.issubset(p.columns):
        p = pd.DataFrame(columns=['Work Order', 'Section', 'Plan Date', 'Plan Qty'])
    p['Work Order'] = p['Work Order'].astype(str).str.strip()
    p = p[p['Work Order'].isin(wos)].copy()
    p['_date'] = pd.to_datetime(p['Plan Date'], errors='coerce').dt.normalize()
    p['_qty'] = pd.to_numeric(p.get('Plan Qty', 0), errors='coerce').fillna(0).clip(lower=0)
    p['_wo_plan_ton'] = pd.to_numeric(p.get('Plan ton', np.nan), errors='coerce')
    p = p.dropna(subset=['_date'])

    if not c.empty and {'Plan Date', 'Section'}.issubset(c.columns):
        c['_date'] = pd.to_datetime(c['Plan Date'], errors='coerce').dt.normalize()
        c['_section_key'] = c['Section'].astype(str).str.strip().str.casefold()
        c = c.dropna(subset=['_date']).drop_duplicates(['_date', '_section_key'], keep='last')
        p['_section_key'] = p['Section'].astype(str).str.strip().str.casefold()
        take = [x for x in ['_date','_section_key','Plan ton','Capacity ton','Utilization %','Mixing Plan MO','Mixing Capacity MO','Capacity Type','Reason / Limiting Factor'] if x in c.columns]
        p = p.merge(c[take], on=['_date','_section_key'], how='left', suffixes=('','_capacity'))
    else:
        p['Capacity ton'] = np.nan
        p['Utilization %'] = np.nan
        c = pd.DataFrame()

    # Build one date/section snapshot for the WHOLE daily plan and identify how
    # much of that already-loaded total belongs to urgent/recovery WOs. This is
    # reconciliation evidence, not an instruction to add a second copy.
    if not c.empty:
        c['_date'] = pd.to_datetime(c.get('_date', c.get('Plan Date')), errors='coerce').dt.normalize()
        c['_section_key'] = c.get('_section_key', c['Section'].astype(str).str.strip().str.casefold())
        c['_whole_plan_ton'] = pd.to_numeric(c.get('Plan ton', np.nan), errors='coerce')
        c['_whole_plan_pcs'] = pd.to_numeric(c.get('Plan pcs', np.nan), errors='coerce')
        c['_capacity_ton'] = pd.to_numeric(c.get('Capacity ton', np.nan), errors='coerce')
        c['_capacity_pcs'] = pd.to_numeric(c.get('Capacity pcs', np.nan), errors='coerce')
        c['_mix_plan_mills'] = pd.to_numeric(c.get('Mixing Plan MO', np.nan), errors='coerce')
        c['_mix_capacity_mills'] = pd.to_numeric(c.get('Mixing Capacity MO', np.nan), errors='coerce')
        c = c.dropna(subset=['_date']).drop_duplicates(['_date','_section_key'], keep='last')
    else:
        c = pd.DataFrame(columns=['_date','_section_key','_whole_plan_ton','_whole_plan_pcs','_capacity_ton','_capacity_pcs','_mix_plan_mills','_mix_capacity_mills'])

    weight_col = next((z for z in ('Net Weight g/pc','Gross Weight g/pc','Plan2026 kg/pc') if z in p.columns), None)
    if weight_col:
        weight = pd.to_numeric(p[weight_col], errors='coerce').fillna(0)
        factor = 1000.0 if weight_col == 'Plan2026 kg/pc' else 1_000_000.0
        p['_wo_plan_ton'] = p['_wo_plan_ton'].fillna(p['_qty'] * weight / factor)
    p['_wo_plan_ton'] = pd.to_numeric(p['_wo_plan_ton'], errors='coerce')
    p['_wo_plan_ton'] = p['_wo_plan_ton'].fillna(0.0)
    if not p.empty:
        _rec_daily = p.groupby(['_date','_section_key'], as_index=False).agg(
            _recovery_qty=('_qty','sum'), _recovery_ton=('_wo_plan_ton','sum'), _recovery_wos=('Work Order','nunique'))
    else:
        _rec_daily = pd.DataFrame(columns=['_date','_section_key','_recovery_qty','_recovery_ton','_recovery_wos'])
    _cap_lookup = c.set_index(['_date','_section_key']).to_dict('index') if not c.empty else {}
    _rec_lookup = _rec_daily.set_index(['_date','_section_key']).to_dict('index') if not _rec_daily.empty else {}
    p['_section_lower'] = p['Section'].astype(str).str.casefold()
    p['_timing_only'] = p['_section_lower'].str.contains('qc|quality|cleaning|ทำความสะอาด|ตรวจสอบคุณภาพ', regex=True)
    p['_util'] = pd.to_numeric(p['Utilization %'], errors='coerce') if 'Utilization %' in p.columns else np.nan
    if not isinstance(p['_util'], pd.Series):
        p['_util'] = pd.Series(p['_util'], index=p.index, dtype='float64')
    p['_cap_state'] = np.select(
        [p['_util'].gt(103), p['_util'].gt(100.01), p['_util'].notna(), p['_timing_only']],
        ['HARD GATE >103% — RESCHEDULE / APPROVE OT', 'OVER CAPACITY >100% — NOT NORMAL FEASIBLE', 'WITHIN RATED CAPACITY', 'TIMING GATE — NO RATED CAPACITY'],
        default='CAPACITY NOT VERIFIED')

    detail_rows = []
    summary_rows = []
    for _, a in actions.iterrows():
        wo = str(a['Work Order']).strip()
        g = p[p['Work Order'].eq(wo)].copy()
        due = pd.to_datetime(a.get('Due Date'), errors='coerce')
        if g.empty:
            summary_rows.append({**a.to_dict(), 'Scheduled Qty pcs': 0, 'Plan Coverage %': 0,
                                 'Planned Finish': pd.NaT, 'Due Date Result': 'NOT SCHEDULED — no daily allocation',
                                 'Capacity Result': 'NOT VERIFIED — no daily allocation',
                                 'Daily Plan Treatment': 'No additional recovery quantity inserted; resolve blockers/capacity first.'})
            continue
        # Completion is represented by the last packing allocation when available.
        end_rows = g[g['Section'].astype(str).str.contains('Packing|บรรจุ', case=False, regex=True)]
        finish = (end_rows['_date'].max() if not end_rows.empty else g['_date'].max())
        # A WO may be split over multiple dates within a process. Prefer the
        # terminal Packing allocation; otherwise use the largest process total.
        # Never sum the same pieces across different processes.
        scheduled = float(end_rows['_qty'].sum()) if not end_rows.empty else float(g.groupby('Section',dropna=False)['_qty'].sum().max())
        required = float(pd.to_numeric(a.get('Open quantity (pcs)', 0), errors='coerce') or 0)
        coverage = min(100.0, scheduled / required * 100) if required > 0 else 0.0
        late = pd.notna(due) and finish.normalize() > due.normalize()
        complete = coverage >= 99.99
        applicable = g[~g['_timing_only']]
        overload = applicable['_util'].gt(100.01).any()
        hard = applicable['_util'].gt(103).any()
        unknown = applicable['_util'].isna().any() or g['_cap_state'].str.startswith('CAPACITY NOT VERIFIED').any()
        timing_only = g['_timing_only'].any()
        if hard:
            cap_result = 'HARD GATE — daily section load >103%'
        elif overload:
            cap_result = 'NOT FEASIBLE — daily section load >100%'
        elif unknown:
            cap_result = 'UNVERIFIED — one or more rated section capacities missing'
        elif timing_only:
            cap_result = 'RATED STEPS WITHIN CAPACITY; QC/CLEANING are timing gates only'
        else:
            cap_result = 'ALL SCHEDULED RATED STEPS WITHIN CAPACITY'
        if not complete:
            due_result = 'INCOMPLETE — scheduled quantity below open quantity'
        elif pd.isna(due):
            due_result = 'DUE DATE MISSING — cannot confirm'
        elif late:
            due_result = 'LATE — planned finish after due date'
        else:
            due_result = 'ON TIME IN CURRENT PLAN — not a production guarantee'
        summary_rows.append({**a.to_dict(), 'Scheduled Qty pcs': scheduled, 'Plan Coverage %': round(coverage, 1),
                             'Planned Finish': finish.date(), 'Due Date Result': due_result,
                             'Capacity Result': cap_result,
                             'Daily Plan Treatment': 'Included once in unified daily schedule; no duplicate recovery load added.'})
        for _, r in g.iterrows():
            _key=(r['_date'],str(r.get('_section_key',r['Section'])).casefold())
            _cap=_cap_lookup.get(_key,{})
            _rec=_rec_lookup.get(_key,{})
            _whole_ton=pd.to_numeric(_cap.get('_whole_plan_ton',r.get('Plan ton_capacity',r.get('Plan ton',np.nan))),errors='coerce')
            _whole_pcs=pd.to_numeric(_cap.get('_whole_plan_pcs',np.nan),errors='coerce')
            _capacity_ton=pd.to_numeric(_cap.get('_capacity_ton',r.get('Capacity ton',np.nan)),errors='coerce')
            _capacity_pcs=pd.to_numeric(_cap.get('_capacity_pcs',np.nan),errors='coerce')
            _recovery_ton=float(_rec.get('_recovery_ton',0) or 0)
            _recovery_qty=float(_rec.get('_recovery_qty',0) or 0)
            _remaining_before=(_capacity_ton-(_whole_ton-_recovery_ton)) if pd.notna(_capacity_ton) and pd.notna(_whole_ton) else np.nan
            _remaining_after=(_capacity_ton-_whole_ton) if pd.notna(_capacity_ton) and pd.notna(_whole_ton) else np.nan
            _detail={'Work Order': wo, 'Section': r['Section'], 'Plan Date': r['_date'].date(),
                                'WO Plan Qty pcs': r['_qty'], 'WO Plan ton': r['_wo_plan_ton'],
                                'Recovery WOs in this day/section':int(_rec.get('_recovery_wos',0) or 0),
                                'Recovery allocation pcs this day/section':_recovery_qty,
                                'Recovery allocation ton this day/section':_recovery_ton,
                                'Whole-day plan pcs':_whole_pcs,
                                'Whole-day plan ton (includes listed recovery WOs)':_whole_ton,
                                'Controlled capacity ton':_capacity_ton,
                                'Implied headroom before listed recovery ton':_remaining_before,
                                'Headroom after current plan ton':_remaining_after,
                                'Over-capacity ton':max(0.0,-_remaining_after) if pd.notna(_remaining_after) else np.nan,
                                'Whole-day plan mills':_cap.get('_mix_plan_mills',np.nan),
                                'Mixing capacity mills/day':_cap.get('_mix_capacity_mills',np.nan),
                                'Mixing mills remaining':(_cap.get('_mix_capacity_mills',np.nan)-_cap.get('_mix_plan_mills',np.nan)) if pd.notna(_cap.get('_mix_capacity_mills',np.nan)) and pd.notna(_cap.get('_mix_plan_mills',np.nan)) else np.nan,
                                'Section Day Capacity ton': _capacity_ton,
                                'Section Utilization %': r.get('Utilization %', np.nan),
                                'Mixing Plan mills': _cap.get('_mix_plan_mills',r.get('Mixing Plan MO', np.nan)),
                                'Mixing Capacity mills': _cap.get('_mix_capacity_mills',r.get('Mixing Capacity MO', np.nan)),
                                'Capacity Check': r['_cap_state'],
                                'Capacity Basis / Limiting Factor': r.get('Reason / Limiting Factor', '')}
            detail_rows.append(_detail)
    summary = pd.DataFrame(summary_rows)
    detail = pd.DataFrame(detail_rows)
    if not summary.empty:
        summary = summary.sort_values(['Recovery Priority','Due Date'], na_position='last').reset_index(drop=True)
    if not detail.empty:
        detail = detail.sort_values(['Plan Date','Section','Work Order']).reset_index(drop=True)
    return summary, detail
