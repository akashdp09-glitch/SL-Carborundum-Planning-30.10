"""Plan-2026 revision from physical audit (mobile/scanner). Non-destructive: never edits the original workbook and never
auto-closes a section. It produces a standalone revised workbook with proposed corrections + full change log."""
from __future__ import annotations
import datetime as dt, re, sqlite3
import pandas as pd
from .plan_reader import ORDER, norm_wo

_PROC = {'prep':'Preparation','เตรียม':'Preparation','mix':'Mixing','ผสม':'Mixing','form':'Forming','press':'Forming','ขึ้นรูป':'Forming',
         'dry':'Forming','fir':'Firing','kiln':'Firing','เตา':'Firing','เผา':'Firing','grind':'Grinding','cut':'Grinding','finish':'Grinding',
         'เจียร':'Grinding','ตัด':'Grinding','pack':'Packing','บรรจุ':'Packing','แพ็ค':'Packing'}
def to_section(txt):
    t = str(txt or '').lower()
    for k, v in _PROC.items():
        if k in t: return v
    return ''

def read_latest_audits(db_path) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    try:
        a = pd.read_sql_query("SELECT * FROM mobile_audits", con)
        ph = pd.read_sql_query("SELECT audit_id, filename FROM mobile_audit_photos", con)
    finally: con.close()
    if a.empty: return a
    ph = ph.groupby('audit_id')['filename'].last().rename('photo_file').reset_index()
    a = a.merge(ph, left_on='id', right_on='audit_id', how='left')
    a['wo'] = a['wo_id'].map(norm_wo)
    return a.sort_values('created_at').groupby('wo', as_index=False).last()

def revise(plan: pd.DataFrame, audits: pd.DataFrame, since: dt.date | None = None):
    """Returns (revised_plan_df, changes_df)."""
    rev = plan.copy()
    for c in ['audit_status','audit_qty','audit_section','audit_location','audit_time','audit_user','audit_photo','audit_notes','revised_section','proposed_action']:
        rev[c] = pd.Series([''] * len(rev), index=rev.index, dtype=object)
    rev['revised_section'] = rev['current_section'].astype(object)
    ch = []
    if audits is not None and len(audits):
        a = audits.set_index('wo')
        for i, r in rev[rev['wo'].isin(a.index)].iterrows():
            x = a.loc[r['wo']]
            if since and str(x['created_at'])[:10] < since.isoformat(): continue
            obs = to_section(x.get('observed_process')); cur = r['current_section']; vq = x.get('verified_qty')
            act = []
            status = str(x.get('physical_status') or 'OK').upper()
            if status not in ('OK', ''): act.append(f'Physical status {status} - investigate')
            if obs and cur != 'Done' and obs in ORDER and cur in ORDER:
                if ORDER.index(obs) > ORDER.index(cur): act.append(f'Plan says {cur} but part physically at {obs} - confirm & close earlier section(s)'); rev.at[i, 'revised_section'] = obs
                elif ORDER.index(obs) < ORDER.index(cur): act.append(f'Plan says {cur} but part physically at {obs} - plan may be ahead of reality')
            ref = (r[f'{cur}.plan_qty'] if cur in ORDER and r[f'{cur}.plan_qty'] > 0 else r['qty']) - (r[f'{cur}.done'] if cur in ORDER else 0)
            if pd.notna(vq) and cur in ORDER and abs(float(vq) - ref) > 1e-6: act.append(f'Verified qty {vq:g} vs plan remaining {ref:g} (diff {float(vq)-ref:+g})')
            rev.at[i, 'audit_status'] = status; rev.at[i, 'audit_qty'] = '' if pd.isna(vq) else vq
            rev.at[i, 'audit_section'] = obs or str(x.get('observed_process') or ''); rev.at[i, 'audit_location'] = x.get('physical_location') or ''
            rev.at[i, 'audit_time'] = x.get('created_at'); rev.at[i, 'audit_user'] = x.get('user_name'); rev.at[i, 'audit_photo'] = x.get('photo_file') or ''
            rev.at[i, 'audit_notes'] = x.get('notes') or ''; rev.at[i, 'proposed_action'] = '; '.join(act) or 'Audit agrees with plan'
            ch.append(dict(wo=r['wo'], plan_section=cur, revised_section=rev.at[i, 'revised_section'], verified_qty=vq, location=x.get('physical_location'),
                           status=status, audited_at=x.get('created_at'), by=x.get('user_name'), photo=x.get('photo_file'), proposed_action=rev.at[i, 'proposed_action']))
    return rev, pd.DataFrame(ch)
