"""Dated requirements netting. No recipe inference or inventory/lead-time defaults.
Quantity unit is kg; dates are ISO or explicit day/month/year. Proposed purchases
are not confirmed receipts. Unknown inputs block release, not silently zero.
"""
from __future__ import annotations
import datetime as dt
import math
import pandas as pd

DEMAND_COLUMNS=['code','need_date','gross_kg','reference','source','basis']
STOCK_COLUMNS=['code','available_kg','safety_kg','lead_days','lot_kg','minimum_order_kg','source']
RECEIPT_COLUMNS=['code','receipt_date','receipt_kg','confirmed','reference','source']

def parse_date(value):
    if value is None or pd.isna(value) or value == '': return None
    if isinstance(value,dt.datetime): return value.date()
    if isinstance(value,dt.date): return value
    text=str(value).strip()
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y'):
        try: return dt.datetime.strptime(text,fmt).date()
        except ValueError: pass
    raise ValueError(f'Invalid date {value!r}; use YYYY-MM-DD or DD/MM/YYYY.')

def number(value, name, required=True):
    if value is None or pd.isna(value) or str(value).strip()=='':
        if required: raise ValueError(f'{name} is missing')
        return None
    n=float(value)
    if not math.isfinite(n) or n<0: raise ValueError(f'{name} must be finite and >= 0')
    return n

def code(value): return '' if value is None or pd.isna(value) else str(value).strip().upper()

def net_requirements(demand, inventory, receipts, today, horizon_end):
    """One chronological ledger per code. Past demand remains backlog at today's start.
    Known available stock only; confirmed dated receipts only. No LAB stock inclusion.
    Firm balance excludes suggestions, proposed balance includes them for non-duplicate netting.
    Same-day confirmed receipts available before demand (explicit operational assumption).
    Missing stock/lot/lead-time inputs return blocking diagnostics for that code.
    """
    today=parse_date(today); horizon_end=parse_date(horizon_end)
    if horizon_end<today: raise ValueError('Horizon end must be on/after planning date')
    problems=[]; needs=[]; supplies=[]; stock={}
    def issue(kind,row,c,message): problems.append(dict(kind=kind,row=row,code=c,diagnostic=message))
    for idx,r in inventory.iterrows():
        c=code(r.get('code'))
        if not c: continue
        try:
            if c in stock: raise ValueError('Duplicate stock code: consolidate inventory explicitly')
            stock[c]={k:number(r.get(k),k) for k in ['available_kg','safety_kg','lead_days','lot_kg','minimum_order_kg']}
            if not stock[c]['lead_days'].is_integer(): raise ValueError('lead_days must be whole calendar days')
            stock[c]['source']=str(r.get('source',''))
        except (ValueError,TypeError) as e: stock.pop(c,None); issue('Inventory',idx+1,c,str(e))
    # Any duplicate code blocks it, even when a third row exists.
    duplicates=inventory['code'].map(code).value_counts() if 'code' in inventory else pd.Series(dtype=int)
    for c in duplicates[duplicates>1].index: stock.pop(c,None)
    for idx,r in demand.iterrows():
        c=code(r.get('code'))
        if not c: continue
        try:
            d=parse_date(r.get('need_date')); q=number(r.get('gross_kg'),'gross_kg')
            if d is None: raise ValueError('Demand need_date is missing; not assigned to an invented day')
            needs.append(dict(code=c,date=max(today,d),original_date=d,kg=q,reference=str(r.get('reference','')),source=str(r.get('source','')),basis=str(r.get('basis',''))))
        except (ValueError,TypeError) as e: issue('Demand',idx+1,c,str(e))
    for idx,r in receipts.iterrows():
        c=code(r.get('code'))
        if not c: continue
        try:
            d=parse_date(r.get('receipt_date')); q=number(r.get('receipt_kg'),'receipt_kg')
            confirmed=str(r.get('confirmed','')).strip().lower() in ('true','1','yes','confirmed')
            if d is None: raise ValueError('Receipt date missing; excluded from available supply')
            if not confirmed: raise ValueError('Unconfirmed/held receipt excluded from available supply')
            if d<today: raise ValueError('Overdue receipt: confirm arrival and include in available stock, or revise receipt date')
            supplies.append(dict(code=c,date=d,kg=q,reference=str(r.get('reference','')),source=str(r.get('source',''))))
        except (ValueError,TypeError) as e: issue('Receipt',idx+1,c,str(e))
    ledger=[]; orders=[]
    for c in sorted(set(a['code'] for a in needs)):
        if c not in stock: issue('Blocked code',0,c,'Available stock / safety / lead / lot / minimum not fully confirmed; no order proposal'); continue
        st=stock[c];firm=proposed=st['available_kg']
        # A code with invalid demand cannot claim a complete executable proposal.
        partial=any(p['kind']=='Demand' and p['code']==c for p in problems)
        dates=sorted({a['date'] for a in needs+supplies if a['code']==c and a['date']<=horizon_end})
        for d in dates:
            nd=[a for a in needs if a['code']==c and a['date']==d];rc=[a for a in supplies if a['code']==c and a['date']==d]
            gross=sum(a['kg'] for a in nd);incoming=sum(a['kg'] for a in rc)
            opening=proposed;firm+=incoming-gross;proposed+=incoming-gross
            short=max(0,st['safety_kg']-proposed);purchase=0
            if short>0:
                purchase=max(short,st['minimum_order_kg'])
                if st['lot_kg']>0: purchase=math.ceil((purchase-1e-10)/st['lot_kg'])*st['lot_kg']
                release=d-dt.timedelta(days=int(st['lead_days']));proposed+=purchase
                orders.append(dict(code=c,required_receipt=d,suggested_release=release,proposal_kg=purchase,net_need_kg=short,lead_days=st['lead_days'],lot_kg=st['lot_kg'],status='PARTIAL INPUT — REVIEW' if partial else ('EXPEDITE / FEASIBILITY CHECK' if release<today else 'PROPOSED — NOT RELEASED'),references='; '.join(a['reference'] for a in nd),stock_source=st['source']))
            ledger.append(dict(code=c,date=d,opening_proposed_kg=opening,confirmed_receipts_kg=incoming,gross_need_kg=gross,firm_balance_kg=firm,proposal_kg=purchase,proposed_balance_kg=proposed,safety_kg=st['safety_kg'],backlog_need_kg=sum(a['kg'] for a in nd if a['original_date']<today),references='; '.join(a['reference'] for a in nd),demand_sources='; '.join(a['source'] for a in nd),receipt_sources='; '.join(a['source'] for a in rc)))
    return pd.DataFrame(ledger),pd.DataFrame(orders),pd.DataFrame(problems)

def seed_demands(plan,kind,source):
    rows=[]
    p=plan[plan['open'] & ~plan['Mixing.closed']]
    for _,r in p.iterrows():
        need=r.get('Mixing.plan') or r.get('due')
        if pd.isna(need): need=r.get('due')
        basis='Full WO requirement from source; verify remaining unconsumed quantity before release. '+('Mixing planned date' if r.get('Mixing.plan') else 'Due date fallback: replace with material need date')
        pairs=[(r.get('bond'),r.get('mix_bond_g'))] if kind=='Bond' else [(r.get(f'mat{n}'),r.get(f'mat{n}_g')) for n in range(1,6)]
        for c,q in pairs:
            if code(c) and q and q>0: rows.append([code(c),need.isoformat() if need else '',q/1000,r['wo'],source,basis])
    return pd.DataFrame(rows,columns=DEMAND_COLUMNS)

def explode_recipe(bond_proposals, recipes):
    """Approved recipe ratios only: each component kg / output kg in one batch.
    Never infer chemistry from a bond code. Batch rounding at bond level prevents
    arbitrary component rounding. Receipt date is bond completion; components
    needed by proposed start/release (planner must confirm production lead time).
    """
    out=[];errors=[]
    for _,p in bond_proposals.iterrows():
        c=code(p['code']);r=recipes[recipes['bond'].map(code)==c]
        if r.empty:errors.append([c,'No approved recipe supplied; component requirements not invented']);continue
        try:
            if not r['approved'].map(lambda v:str(v).lower() in ('true','1','yes')).all():raise ValueError('Recipe approval missing')
            outputs=[number(v,'output_kg_per_batch') for v in r['output_kg_per_batch']]
            if not outputs or outputs[0]<=0 or len(set(outputs))!=1:raise ValueError('Recipe output kg per batch must be one positive value')
            if r['component'].map(code).duplicated().any():raise ValueError('Duplicate component: consolidate recipe lines')
            batches=math.ceil((p['proposal_kg']-1e-10)/outputs[0])
            for _,line in r.iterrows():
                component=code(line['component'])
                if not component:raise ValueError('Component code missing')
                quantity=number(line['component_kg_per_batch'],'component kg per batch')*batches
                if not str(line.get('source') or '').strip():raise ValueError('Approved recipe source/reference is missing')
                out.append([component,p['suggested_release'].isoformat(),quantity,c,str(line['source']),f'Approved recipe; {batches} batches × {outputs[0]} kg output; bond plan start requires capacity confirmation'])
        except (ValueError,TypeError) as e:errors.append([c,str(e)]);out=[a for a in out if a[3]!=c]
    return pd.DataFrame(out,columns=DEMAND_COLUMNS),pd.DataFrame(errors,columns=['bond','diagnostic'])
