"""Planners built on plan_reader. Pure pandas (no Streamlit) so they can be tested headless."""
from __future__ import annotations
import datetime as dt, math, re
import openpyxl, pandas as pd
from .plan_reader import ORDER, SECTIONS

def _lot_from_remark(txt):
    m = re.search(r'(\d+(?:\.\d+)?)\s*KG', str(txt or ''), re.I)
    return float(m.group(1)) if m else 0.0

def _num(v):
    try:
        f = float(v); return 0.0 if f != f else f
    except Exception: return 0.0

def _known_num(v):
    try:
        f=float(v)
        return f if math.isfinite(f) and f>=0 else None
    except (ValueError,TypeError): return None

# ---------------------------------------------------------------- BOND
def read_bond_mrp(path, sheet=None):
    """Reads the bond ordering sheet (CODE in col A from row 7). Units: kg."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    rows = []
    for r in ws.iter_rows(min_row=7, max_col=19, values_only=True):
        code = str(r[0] or '').strip()
        if not code or not re.match(r'^B', code): continue
        rows.append(dict(bond=code, name=r[1], on_hand_kg=_known_num(r[2]), avg_month_kg=_num(r[3]), on_order_kg=_num(r[4]),
                         typed_mrp_kg=_num(r[5]), lot_kg=_lot_from_remark(r[18]), remark=r[18]))
    return pd.DataFrame(rows)

def bond_plan(plan: pd.DataFrame, bond_stock: pd.DataFrame, today: dt.date, horizon_days=45, uplift=0.20, safety_x=1.5, stale_days=180):
    """Demand = bond grams (Plan col BE) of open WOs whose Mixing is not closed, split by due bucket.
    Suggested order = max(0, (overdue+horizon demand)*(1+uplift) + safety - on_hand - on_order) rounded UP to lot size.
    WOs overdue by more than stale_days are shown in a separate Stale column and NOT counted (verify/close them first)."""
    p = plan[plan['open'] & ~plan['Mixing.closed'] & (plan['mix_bond_g'] > 0)].copy()
    end = today + dt.timedelta(days=horizon_days)
    def bucket(d):
        if d is None or d is pd.NaT: return 'No date'
        if d < today - dt.timedelta(days=stale_days): return 'Stale'
        if d < today: return 'Overdue'
        if d <= end: return 'In horizon'
        return 'Later'
    p['bucket'] = p['due'].map(bucket)
    p['bond_kg'] = p['mix_bond_g'] / 1000
    piv = p.pivot_table(index='bond', columns='bucket', values='bond_kg', aggfunc='sum', fill_value=0)
    for c in ['Stale', 'Overdue', 'In horizon', 'No date', 'Later']:
        if c not in piv: piv[c] = 0.0
    piv['WOs'] = p.groupby('bond')['wo'].count()
    out = bond_stock.merge(piv.reset_index(), on='bond', how='outer').fillna(0)
    out['bond'] = out['bond'].astype(str).str.strip()
    out['demand_kg'] = out['Overdue'] + out['In horizon']
    out['safety_kg'] = out['avg_month_kg'] * safety_x
    need = out['demand_kg'] * (1 + uplift) + out['safety_kg'] - out['on_hand_kg'] - out['on_order_kg']
    out['shortfall_kg'] = need.clip(lower=0)
    out['suggest_order_kg'] = [math.ceil(s / l) * l if (s > 0 and l > 0) else (s if s > 0 else 0.0) for s, l in zip(out['shortfall_kg'], out['lot_kg'])]
    out['lots'] = [int(round(s / l)) if l > 0 else 0 for s, l in zip(out['suggest_order_kg'], out['lot_kg'])]
    out['status'] = ['ORDER NOW' if s > 0 and d > h else ('ORDER (safety)' if s > 0 else 'OK') for s, d, h in zip(out['shortfall_kg'], out['demand_kg'], out['on_hand_kg'])]
    cols = ['bond','name','on_hand_kg','on_order_kg','avg_month_kg','safety_kg','Overdue','In horizon','demand_kg','Stale','No date','Later','WOs','shortfall_kg','lot_kg','lots','suggest_order_kg','status','typed_mrp_kg','remark']
    detail = p[['wo','customer','spec','due','bond','bond_kg','bucket','current_section']].sort_values(['bond','due'])
    return out[[c for c in cols if c in out]].sort_values('demand_kg', ascending=False), detail

# ---------------------------------------------------------------- MATERIAL (abrasive grain etc.)
def read_material_stock(path, sheet='Abrasive'):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True); ws = wb[sheet]; rows = []
    for r in ws.iter_rows(min_row=2, max_col=16, values_only=True):
        if not r[0]: continue
        rows.append(dict(material=str(r[0]).strip(), name=r[4], group=r[5], move=r[8], sheet_open_wo_g=_num(r[9]),
                         stock_g=_known_num(r[10]), incoming_g=_num(r[11]), lab_g=_num(r[12]), balance_g=_num(r[13]), note=r[15]))
    wb.close(); return pd.DataFrame(rows)

def material_plan(plan: pd.DataFrame, stock: pd.DataFrame):
    """Requirement = material grams of open WOs whose Mixing is not closed (Plan R..AA code/gram pairs)."""
    p = plan[plan['open'] & ~plan['Mixing.closed']]
    parts = []
    for n in range(1, 6):
        q = p[p[f'mat{n}_g'] > 0][['wo', 'due', f'mat{n}', f'mat{n}_g']]
        q.columns = ['wo', 'due', 'material', 'g']; parts.append(q)
    use = pd.concat(parts); use['material'] = use['material'].astype(str).str.strip()
    use = use[~use['material'].isin(['', '0', 'None', 'nan'])]
    need = use.groupby('material', as_index=False).agg(need_kg=('g', lambda s: s.sum() / 1000), WOs=('wo', 'nunique'))
    out = need.merge(stock, on='material', how='outer').fillna({'need_kg': 0, 'WOs': 0})
    for c in ['stock_g', 'incoming_g', 'lab_g', 'sheet_open_wo_g']: out[c] = out[c].fillna(0)
    out['stock_kg'] = out['stock_g'] / 1000; out['incoming_kg'] = out['incoming_g'] / 1000; out['lab_kg'] = out['lab_g'] / 1000
    out['short_kg'] = (out['need_kg'] - out['stock_kg']).clip(lower=0)
    out['short_after_incoming_kg'] = (out['need_kg'] - out['stock_kg'] - out['incoming_kg']).clip(lower=0)
    out['short_after_lab_kg'] = (out['need_kg'] - out['stock_kg'] - out['incoming_kg'] - out['lab_kg']).clip(lower=0)
    out['status'] = ['SHORT / CONFIRM INCOMING DATE' if a > 0 else ('INCOMING DATE / RELEASE REQUIRED' if s > 0 else 'OK') for a, s in zip(out['short_after_incoming_kg'], out['short_kg'])]
    out['plan_vs_stocksheet_kg'] = out['need_kg'] - out['sheet_open_wo_g'] / 1000
    out = out[(out['need_kg'] > 0) | (out['sheet_open_wo_g'] > 0)]
    return out.sort_values('short_after_lab_kg', ascending=False), use

# ---------------------------------------------------------------- BACKORDER / WEEKLY / MONTHLY / SECTION DAILY
def remaining_qty(plan, section):
    return (plan[f'{section}.plan_qty'].where(plan[f'{section}.plan_qty'] > 0, plan['qty']) - plan[f'{section}.done']).clip(lower=0)

def backorder_plan(plan: pd.DataFrame, today: dt.date):
    p = plan[plan['open'] & (plan['current_section'] != 'Done')].copy()
    p['days_late'] = [(today - d).days if d else None for d in p['due']]
    p = p[p['days_late'].map(lambda x: x is not None and x > 0)]
    p['remaining_qty'] = [r[f'{r.current_section}.plan_qty'] - r[f'{r.current_section}.done'] if r[f'{r.current_section}.plan_qty'] > 0 else r['qty'] for _, r in p.iterrows()]
    p['remaining_qty'] = p['remaining_qty'].clip(lower=0)
    p['age_bucket'] = pd.cut(p['days_late'], [0, 7, 30, 90, 365, 10**6], labels=['1-7 d', '8-30 d', '31-90 d', '91-365 d', '>1 year'])
    p['sales_due'] = p['sales_due']
    return p[['wo', 'customer', 'spec', 'due', 'sales_due', 'days_late', 'age_bucket', 'current_section', 'qty', 'remaining_qty', 'status', 'remark']].sort_values('days_late', ascending=False)

def period_plan(plan: pd.DataFrame, today: dt.date, freq='W'):
    """Open work by due period and the section it is currently waiting in."""
    p = plan[plan['open'] & (plan['current_section'] != 'Done')].copy()
    def per(d):
        if d is None: return 'No date'
        if d < today: return 'OVERDUE'
        if freq == 'W':
            mon = d - dt.timedelta(days=d.weekday()); return f'{mon.isoformat()} (wk)'
        return d.strftime('%Y-%m')
    p['period'] = p['due'].map(per)
    p['remaining_qty'] = [max(0, (r[f'{r.current_section}.plan_qty'] if r[f'{r.current_section}.plan_qty'] > 0 else r['qty']) - r[f'{r.current_section}.done']) for _, r in p.iterrows()]
    t = p.pivot_table(index='period', columns='current_section', values='wo', aggfunc='count', fill_value=0)
    t = t[[c for c in ORDER if c in t]]; t['Total WOs'] = t.sum(axis=1)
    return t.sort_index(key=lambda s: s.map(lambda x: ('0' if x == 'OVERDUE' else '9' if x == 'No date' else '5') + x)), p

def section_daily(plan: pd.DataFrame, section: str, today: dt.date, capacity_per_day, unit='pcs', days=5,
                  non_working_weekdays=(), holidays=()):
    """Queue of WOs waiting in `section`, priority: overdue, earliest due.
    capacity_per_day is in `unit` PER DAY and MUST come from the capacity registry (with source cell) or an explicit user entry.
    capacity_per_day None/0 -> the queue is returned UNSCHEDULED (no date invented). No weekday is assumed to be a day off:
    pass non_working_weekdays (Mon=0..Sun=6) and holidays explicitly from the factory calendar.
    unit 'mills' = the WO's mill count (จำนวนโม่) compared with mills/day; it is NOT converted to batches or kg."""
    p = plan[plan['open'] & (plan['current_section'] == section)].copy()
    p['remaining_qty'] = [max(0, (r[f'{section}.plan_qty'] if r[f'{section}.plan_qty'] > 0 else r['qty']) - r[f'{section}.done']) for _, r in p.iterrows()]
    if unit == 'mills': p['load'] = p['mills']
    elif unit == 'kg': p['load'] = p['remaining_qty'] * p['piece_g'] / 1000
    else: p['load'] = p['remaining_qty']
    p['sort_due'] = p['due'].map(lambda d: d or dt.date(2999, 1, 1)); p = p.sort_values(['sort_due', 'wo'])
    off_days, hol = set(non_working_weekdays), set(holidays)
    def working(d): return d.weekday() not in off_days and d not in hol
    def nxt(d):
        d += dt.timedelta(days=1)
        for _ in range(400):
            if working(d): return d
            d += dt.timedelta(days=1)
        return d
    if capacity_per_day and capacity_per_day > 0:
        day = today if working(today) else nxt(today)
        used, plan_day = 0.0, []
        for ld in p['load']:
            if used > 0 and used + ld > capacity_per_day: day, used = nxt(day), 0.0
            plan_day.append(day); used += ld
        p['plan_date'] = plan_day if len(p) else []
        p['schedule_status'] = 'PROVISIONAL (sequence by due date against the stated capacity; routing, bookings and materials not yet checked)'
    else:
        p['plan_date'] = None
        p['schedule_status'] = 'UNSCHEDULED - no capacity with a unit and time basis was supplied'
    p['late'] = [('LATE' if d and d < today else '') for d in p['due']]
    return p[['plan_date', 'schedule_status', 'wo', 'customer', 'spec', 'due', 'late', 'qty', 'remaining_qty', 'mills', 'load', 'bond', 'remark']].rename(columns={'load': f'load_{unit}'})
