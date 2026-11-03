from __future__ import annotations
import math
import pandas as pd

# CONTROLLED SOURCE: Cap แต่ละแผนก(10).xlsx -> sheet "Lead Time", 10-Sep-2026.
# Values below are transcribed exactly from the supplied workbook.
# Daily planning uses whole working-day boundaries. A fractional duration such
# as 0.5 day therefore crosses to the next working day when it separates stages.
# The actual issued Firing Planner remains authoritative for kiln load/finish dates.

CATEGORY_ORDER=['S','T','P','R','PB','M']
CATEGORY_NAMES={
    'S':'Vitrified knife-sharpening stone',
    'T':'Vitrified rubber-cutting stone',
    'P':'Vitrified grinding wheel',
    'R':'Vitrified rice stone',
    'PB':'Resin product',
    'M':'Vitrified mounted stone',
}

# None = source says does not pass this process.
# String values are retained where the source is a range/exception.
LEAD_TIME = {
'S':  {'Preparation':1,'Mixing':1,'Forming':2,'Oven':2,'Resin Firing':None,'Vitrified Firing':5,'Screening':1,'Grinding':None,'QC':0.5,'Grinding/Packing':4},
'T':  {'Preparation':1,'Mixing':1,'Forming':5,'Oven':3,'Resin Firing':None,'Vitrified Firing':5,'Screening':1,'Grinding':None,'QC':0.5,'Grinding/Packing':4},
'P':  {'Preparation':1,'Mixing':1,'Forming':2,'Oven':3,'Resin Firing':None,'Vitrified Firing':7,'Screening':1,'Grinding':6,'QC':0.5,'Grinding/Packing':4},
'R':  {'Preparation':1,'Mixing':1,'Forming':3,'Oven':2,'Resin Firing':None,'Vitrified Firing':7,'Screening':1,'Grinding':6,'QC':0.5,'Grinding/Packing':4},
'PB': {'Preparation':1,'Mixing':1,'Forming':0.5,'Oven':None,'Resin Firing':3,'Vitrified Firing':None,'Screening':1,'Grinding':3,'QC':0.5,'Grinding/Packing':4},
    'M':  {'Preparation':1,'Mixing':1,'Forming':2,'Oven':1,'Resin Firing':'5-7','Vitrified Firing':7,'Screening':1,'Grinding':3,'QC':0.5,'Grinding/Packing':4},
}

SOURCE_NOTES=[
    'The Lead Time sheet defines PB as Resin and S/T/P/R/M as Vitrified.',
    'The Resin Firing row contains 5-7 Day under M even though the same sheet classifies M as Vitrified. This source conflict is retained for audit; Daily Planner follows M as Vitrified.',
    'Firing start/finish dates come from the issued Firing Planner. Lead Time firing days are comparison/audit references and never shorten an issued kiln cycle.',
    'Grinding and Grinding/Packing lead-time values are shown in the audit. Daily executable quantities remain governed by product-specific CAP/day, setup and manpower to avoid double-counting a fixed duration on top of rated capacity.',
    'Oven/Drying is an explicit TIME GATE after Forming from CAPACITY_DATABASE.xlsx / Lead Time row 6: S=2, T=3, P=3, R=2, M=1 source days; PB does not pass this process. The source does not define calendar vs working days; the current readiness calculation uses working-day offsets. No oven/dryer rated capacity is supplied.',
    'Q26-009 / reference WO P005-110826 has a project-specific reference Gantt: four calendar drying days and two calendar days for pre-firing checks (rows 9-10). This exception applies only to that exact WO; it does not replace the category-wide Lead Time master and does not establish a universal drying standard or drying capacity.',
]

# Source: Nordencent_Q26-009_Production_Gantt_Oct2026.xlsx, sheet "Q26-009 Gantt",
# rows 9-10; reference WO P005-110826. The source is an order-level plan example,
# so do not propagate it to every product in the category.
ORDER_PROCESS_OVERRIDES={
    'P005110826':{
        'project':'Q26-009',
        'drying_calendar_days':4,
        'pre_firing_check_calendar_days':2,
        'forming_to_firing_working_days':6,
        'source':'Nordencent_Q26-009_Production_Gantt_Oct2026 (1).xlsx / Q26-009 Gantt / rows 9-10',
    }
}

def _txt(v): return '' if v is None else str(v).strip()
def normcat(v):
    s=_txt(v).upper()
    if s.startswith('PB'): return 'PB'
    for c in ['S','T','P','R','M']:
        if s.startswith(c): return c
    return 'P'  # controlled fallback only when source category is missing; exported for review

def _ceilwd(v):
    try:return max(1,int(math.ceil(float(v))))
    except:return 1

def order_process_override(row):
    """Return a dated, order-specific process rule; never infer it from category."""
    raw=_txt(row.get('Work Order',row.get('WO',row.get('Factory No.','')))).upper()
    key=''.join(ch for ch in raw if ch.isalnum())
    return ORDER_PROCESS_OVERRIDES.get(key)

def applied_offsets(row):
    cat=normcat(row.get('Category',''))
    d=LEAD_TIME.get(cat,LEAD_TIME['P'])
    prep_to_mix=_ceilwd(d['Preparation'])
    mix_to_form=_ceilwd(d['Mixing'])
    # Daily Planner has no separate Oven section. For categories that pass Oven,
    # its duration is therefore part of the Forming -> Firing readiness gate.
    oven=0 if d['Oven'] is None else float(d['Oven'])
    form_to_fire=max(1,int(math.ceil(float(d['Forming'])+oven)))
    override=order_process_override(row)
    if override:
        form_to_fire=int(override['forming_to_firing_working_days'])
    firing_ref=d['Resin Firing'] if cat=='PB' else d['Vitrified Firing']
    return {
        'Lead Time Profile':f"ORDER OVERRIDE - {override['project']}" if override else f'CAPACITY WORKBOOK - {cat}',
        'Category':cat,
        'Category Description':CATEGORY_NAMES.get(cat,''),
        'Preparation→Mixing WD':prep_to_mix,
        'Mixing→Forming WD':mix_to_form,
        'Forming→Firing WD':form_to_fire,
        'Curing/Oven Gate WD':int(math.ceil(oven)) if oven>0 else 0,
        'Drying Gate Calendar Days':int(override['drying_calendar_days']) if override else int(math.ceil(oven)) if oven>0 else 0,
        'Pre-firing Check Calendar Days':int(override['pre_firing_check_calendar_days']) if override else 0,
        'Process Time Override Source':override['source'] if override else '',
        'Forming→Firing Basis':('Q26-009 reference Gantt: 4 calendar drying days + 2 calendar pre-firing-check days; exact WO only' if override else 'Capacity workbook category lead time; no separate pre-firing-check duration supplied'),
        'Forming Process WD':_ceilwd(d['Forming']),
        'Preparation→Firing WD':prep_to_mix+mix_to_form+form_to_fire,
        'Source Preparation days':d['Preparation'],
        'Source Mixing days':d['Mixing'],
        'Source Forming days':d['Forming'],
        'Source Oven days':d['Oven'],
        'Source Firing days':firing_ref,
        'Source Screening days':d['Screening'],
        'Source Grinding days':d['Grinding'],
        'Source QC days':d['QC'],
        'Source Grinding/Packing days':d['Grinding/Packing'],
        'Source':'Cap แต่ละแผนก(10).xlsx / Lead Time',
    }

def master_table():
    rows=[]
    for cat in CATEGORY_ORDER:
        d=LEAD_TIME[cat]
        r={'Category':cat,'Category Description':CATEGORY_NAMES[cat],**d}
        r.update(applied_offsets({'Category':cat}))
        rows.append(r)
    return pd.DataFrame(rows)

def applied_table(df):
    if df is None or df.empty:return pd.DataFrame()
    rows=[]
    for _,r in df.iterrows():
        a=applied_offsets(r)
        rows.append({'Work Order':r.get('Work Order',''),'Customer':r.get('Customer',''),'Program':r.get('Program',''),'Category Source':r.get('Category',''),'Specification':r.get('Specification',''),**a})
    return pd.DataFrame(rows).drop_duplicates(subset=['Work Order'],keep='first')
