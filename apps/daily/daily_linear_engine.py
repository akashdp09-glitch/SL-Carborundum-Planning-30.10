from __future__ import annotations
from datetime import date,timedelta
import math,re
import pandas as pd

SECTIONS=['Preparation','Mixing','Forming','Firing','Grinding / Cutting','Packing']

def txt(v):
    return '' if v is None or (isinstance(v,float) and math.isnan(v)) else str(v).strip()
def num(v,d=0.0):
    try:
        x=float(v); return d if math.isnan(x) or math.isinf(x) else x
    except:return d
def pdate(v):
    if v is None or v=='': return None
    z=pd.to_datetime(v,errors='coerce')
    return None if pd.isna(z) else z.date()
def workday(d): return d.weekday()!=6
def prev_workday(d,n=1):
    x=d
    for _ in range(n):
        x-=timedelta(days=1)
        while not workday(x): x-=timedelta(days=1)
    return x
def next_workday(d,n=1):
    x=d
    for _ in range(n):
        x+=timedelta(days=1)
        while not workday(x): x+=timedelta(days=1)
    return x

def priority_key(r,start):
    d=pdate(r.get('Due Date'))
    return (0,d) if d else (1,date(2099,12,31))

def route(r):
    s=' '.join(txt(r.get(k,'')) for k in ['Product Type','Specification','Shape','Category']).upper()
    compact=re.sub(r'[^A-Z0-9ก-๙]','',s)
    if any(x in compact for x in ['HONING','HONNING','HONE','SEGMENT','SEGMNT','SEGMEN','SEMENT']) or 'หินลับมีด' in s:
        return 'Cutting / ตัด'
    cat=txt(r.get('Category')).upper()
    if 'ขัดพื้น' in txt(r.get('Shape')) or cat in {'S','T'}:
        return 'Cleaning / ทำความสะอาด'
    return 'Grinding / เจียร'

def mixing_capacity_kg(mix,cat):
    if mix is None or mix.empty:return 0,'CAP ผสม missing'
    x=mix.copy(); x=x[x['Status'].astype(str).str.contains('ใช้',na=False) & ~x['Status'].astype(str).str.contains('ไม่ใช้',na=False)]
    c=txt(cat).upper()
    if c:
        m=x['Job'].astype(str).str.upper().str.contains(r'ผสม\s*'+re.escape(c)+r'(?:\b|,|$)',regex=True,na=False)
        y=x[m]
        if not y.empty:x=y
    cap=(pd.to_numeric(x['CAP-โม่'],errors='coerce').fillna(0)*pd.to_numeric(x['Machine kg'],errors='coerce').fillna(0)).sum()
    return float(cap), 'CAP ผสม: Σ(CAP-โม่ × Machine kg) for active compatible mixing resources'

def forming_capacity_pcs(form,r):
    if form is None or form.empty:return 0,'CAP ขึ้นรูป missing'
    typ=txt(r.get('Category')).upper(); spec=txt(r.get('Specification')).upper()
    x=form.copy();
    if typ:
        y=x[x['Type'].astype(str).str.upper().eq(typ)]
        if not y.empty:x=y
    # Prefer matching spec patterns; otherwise type pool conservative maximum row.
    if spec and 'Spec Pattern' in x.columns:
        mask=x['Spec Pattern'].astype(str).apply(lambda z: txt(z).upper() in spec or spec in txt(z).upper())
        if mask.any():x=x[mask]
    cap=pd.to_numeric(x['Normal pcs/8h'],errors='coerce').fillna(0)
    if cap.empty:return 0,'No compatible forming capacity row'
    # one controlled row may list multiple eligible machines; use maximum proven row, not sum duplicates
    return float(cap.max()), 'CAP ขึ้นรูป: matched Type/Specification normal 8h bottleneck'

def grinding_capacity_pcs(grind,r):
    if grind is None or grind.empty:return 0,'Cap เจีย missing'
    pc=txt(r.get('Product Code'))
    x=grind
    if pc and 'ProductionCode' in x.columns:
        y=x[x['ProductionCode'].astype(str).str.strip().eq(pc)]
        if not y.empty:x=y
    elif txt(r.get('Specification')):
        sp=txt(r.get('Specification')).upper(); y=x[x['Specification'].astype(str).str.upper().eq(sp)]
        if not y.empty:x=y
    c=pd.to_numeric(x.get('Bottleneck CAP/day',0),errors='coerce').fillna(0)
    return (float(c.max()) if len(c) else 0), 'Cap เจีย: matched WO/product bottleneck CAP/day'

def size_inch(r):
    d=num(r.get('D'),0)
    if d<=0:return None
    return d/25.4

def packing_capacity_pcs(pack,r,people=1):
    if pack is None or pack.empty:return 0,'Cap บรรจุ missing'
    typ=txt(r.get('Category')).upper(); sp=txt(r.get('Specification')).upper(); inch=size_inch(r)
    x=pack.copy()
    # exact/pattern first
    if 'Spec Pattern' in x.columns:
        masks=[]
        for i,z in x['Spec Pattern'].items():
            zz=txt(z).upper(); ok=False
            if zz and zz in sp: ok=True
            m=re.search(r'(\d+(?:\.\d+)?)\s*[\'\"”]?\s*$',zz)
            if inch and m:
                try: ok=ok or abs(float(m.group(1))-inch)<=0.8
                except: pass
            masks.append(ok)
        if any(masks):x=x[pd.Series(masks,index=x.index)]
    if 'Type' in x.columns and typ:
        y=x[x['Type'].astype(str).str.upper().str.contains(re.escape(typ),na=False)]
        if not y.empty:x=y
    c=pd.to_numeric(x.get('Bottleneck pcs/day/person',0),errors='coerce').fillna(0)
    return (float(c.max())*max(int(people),1) if len(c) else 0), 'Cap บรรจุ: matched bottleneck pcs/day/person × people'

def load_firing_excel(path):
    xls=pd.ExcelFile(path)
    sh='Firing Detail' if 'Firing Detail' in xls.sheet_names else ('WO DETAIL' if 'WO DETAIL' in xls.sheet_names else xls.sheet_names[0])
    d=pd.read_excel(path,sheet_name=sh)
    qty_col=next((c for c in ['Planned Firing Qty','Qty pcs','Firing Qty','Plan Qty'] if c in d.columns),None)
    date_col=next((c for c in ['Load Date','Firing Date'] if c in d.columns),None)
    finish_col=next((c for c in ['Program Finish Date','Firing Complete','Unload / Take-Out Date'] if c in d.columns),None)
    kg_col=next((c for c in ['kg/pc','Weight kg/pc'] if c in d.columns),None)
    if qty_col is None: raise ValueError('Firing Detail: quantity column not found')
    if date_col is None: raise ValueError('Firing Detail: Load Date not found')
    if finish_col is None: raise ValueError('Firing Detail: Program Finish Date not found')
    out=d.copy()
    out['Firing Qty']=pd.to_numeric(d[qty_col],errors='coerce').fillna(0)
    out['Firing Date']=d[date_col].apply(pdate)
    out['Firing Complete']=d[finish_col].apply(pdate)
    out['kg/pc']=pd.to_numeric(d[kg_col],errors='coerce').fillna(0) if kg_col else 0.0
    return out[out['Firing Qty']>0].copy()

def build_daily(plan, firing, mix, form, kiln, grind, pack, start, horizon=30, prep_kg=1200, packing_people=1):
    end=start+timedelta(days=horizon-1)
    pmap={str(r['Work Order']):r for _,r in plan.iterrows()}
    rows=[]; issues=[]
    # shared calendars; capacity is decremented when multiple WOs share day/resource group
    used_kg={}; used_form={}; used_grind={}; used_pack={}
    def addrow(day,sec,r,qty,kgpc,cap_qty,cap_t,basis,source,anchor='',resource_key=''):
        if day<start or day>end or qty<=0:return
        rows.append({'Plan Date':day,'Section':sec,'Work Order':r.get('Work Order',''),'Customer':r.get('Customer',''),
                     'Specification':r.get('Specification',''),'Category':r.get('Category',''),'Due Date':r.get('Due Date'),
                     'Plan Qty pcs':round(qty,2),'Plan ton':round(qty*kgpc/1000,4),'Capacity Qty pcs':round(cap_qty,2) if cap_qty is not None else None,
                     'Capacity ton':round(cap_t,4) if cap_t is not None else None,'Utilization %':round((qty*kgpc/1000)/cap_t*100,1) if cap_t and cap_t>0 else None,
                     'Capacity Basis':basis,'Source / Reason':source,'Firing Anchor':anchor,'Resource Key':resource_key})
    # anchor-driven plan: all sections support the firing release
    for _,f in firing.sort_values(['Firing Date','Due Date' if 'Due Date' in firing.columns else 'Firing Date'],kind='stable').iterrows():
        wo=txt(f.get('Work Order')); r=pmap.get(wo)
        if r is None:
            issues.append({'Work Order':wo,'Issue':'WO in firing output not found in Plan 2026'}); continue
        q=num(f.get('Firing Qty')); kgpc=num(f.get('kg/pc'),num(r.get('Gross Weight g/pc'))/1000)
        if q<=0:continue
        fd=pdate(f.get('Firing Date')); fc=pdate(f.get('Firing Complete'))
        if not fd or not fc:issues.append({'Work Order':wo,'Issue':'Firing date/finish missing'});continue
        anchor=f"{txt(f.get('Kiln'))} {txt(f.get('Program'))} {fd}"
        # Firing row is exact output anchor
        maxkg=0
        if kiln is not None and not kiln.empty:
            prog=txt(f.get('Program')).upper(); z=kiln[kiln['Program'].astype(str).str.upper().str.replace(' ','').str.startswith(prog.replace(' ',''))]
            if not z.empty:maxkg=float(pd.to_numeric(z['Max kg/load'],errors='coerce').fillna(0).max())
        addrow(fd,'Firing',r,q,kgpc,q,maxkg/1000 if maxkg else None,'Firing Planner + Cap เตา','Exact released firing output',anchor,resource_key='FIRE:'+anchor)
        # upstream, one working day minimum between stages. Split backwards if daily capacity binds.
        need=q
        # forming
        d=prev_workday(fd); rem=need; guard=0
        while rem>0 and d>=start and guard<30:
            cap,basis=forming_capacity_pcs(form,r); key=(d,txt(r.get('Specification')),txt(r.get('Category'))); avail=max(cap-used_form.get(key,0),0)
            take=min(rem,avail)
            if take>0:addrow(d,'Forming',r,take,kgpc,cap,cap*kgpc/1000,basis,'Required to support firing plan',anchor,resource_key='FORM:'+str(key[1:])); used_form[key]=used_form.get(key,0)+take; rem-=take
            d=prev_workday(d);guard+=1
        if rem>0:issues.append({'Work Order':wo,'Section':'Forming','Issue':'Capacity/WIP shortfall before firing','Qty short':rem,'Firing Date':fd})
        # mixing based on gross kg; schedule before earliest forming day used for this WO, conservatively fd-2
        d=prev_workday(fd,2); remkg=q*kgpc; guard=0
        while remkg>1e-9 and d>=start and guard<30:
            capkg,basis=mixing_capacity_kg(mix,r.get('Category')); key=(d,txt(r.get('Category')).upper()); avail=max(capkg-used_kg.get(('MIX',)+key,0),0); takekg=min(remkg,avail); take=takekg/kgpc if kgpc>0 else 0
            if take>0:addrow(d,'Mixing',r,take,kgpc,capkg/kgpc if kgpc else None,capkg/1000,basis,'Required to support forming/firing plan',anchor,resource_key='MIX:'+str(key[1])); used_kg[('MIX',)+key]=used_kg.get(('MIX',)+key,0)+takekg; remkg-=takekg
            d=prev_workday(d);guard+=1
        if remkg>1e-6:issues.append({'Work Order':wo,'Section':'Mixing','Issue':'Capacity shortfall before firing','kg short':remkg,'Firing Date':fd})
        # preparation shared plant kg/day, one day before mixing target
        d=prev_workday(fd,3); remkg=q*kgpc;guard=0
        while remkg>1e-9 and d>=start and guard<30:
            avail=max(prep_kg-used_kg.get(('PREP',d),0),0); takekg=min(remkg,avail); take=takekg/kgpc if kgpc>0 else 0
            if take>0:addrow(d,'Preparation',r,take,kgpc,prep_kg/kgpc if kgpc else None,prep_kg/1000,'Preparation controlled default capacity','Required to support mixing/forming/firing plan',anchor,resource_key='PREP:PLANT');used_kg[('PREP',d)]=used_kg.get(('PREP',d),0)+takekg;remkg-=takekg
            d=prev_workday(d);guard+=1
        if remkg>1e-6:issues.append({'Work Order':wo,'Section':'Preparation','Issue':'Capacity shortfall before firing','kg short':remkg,'Firing Date':fd})
        # downstream one working day after firing complete
        rt=route(r); d=next_workday(fc); rem=q;guard=0
        if rt.startswith('Grinding') or rt.startswith('Cutting'):
            while rem>0 and d<=end and guard<30:
                cap,basis=grinding_capacity_pcs(grind,r); key=(d,txt(r.get('Product Code')) or txt(r.get('Specification'))); avail=max(cap-used_grind.get(key,0),0);take=min(rem,avail)
                if take>0:addrow(d,rt,r,take,kgpc,cap,cap*kgpc/1000,basis,'Firing complete + next working day',anchor,resource_key='POST:'+str(key[1]));used_grind[key]=used_grind.get(key,0)+take;rem-=take
                d=next_workday(d);guard+=1
            post_finish=prev_workday(d) if rem<=0 else d
        else:
            addrow(d,rt,r,q,kgpc,q,q*kgpc/1000,'Factory route rule: cleaning after firing','Firing complete + next working day',anchor,resource_key='CLEAN:MANUAL'); rem=0; post_finish=d
        if rem>0:issues.append({'Work Order':wo,'Section':rt,'Issue':'Capacity shortfall after firing','Qty short':rem})
        # packing next working day after post-process completion
        d=next_workday(post_finish); rem=q;guard=0
        while rem>0 and d<=end and guard<30:
            cap,basis=packing_capacity_pcs(pack,r,packing_people); key=(d,txt(r.get('Category')).upper(),round(size_inch(r) or 0,1));avail=max(cap-used_pack.get(key,0),0);take=min(rem,avail)
            if take>0:addrow(d,'Packing',r,take,kgpc,cap,cap*kgpc/1000,basis,'After grinding/cutting/cleaning + next working day',anchor,resource_key='PACK:'+str(key[1:]));used_pack[key]=used_pack.get(key,0)+take;rem-=take
            d=next_workday(d);guard+=1
        if rem>0:issues.append({'Work Order':wo,'Section':'Packing','Issue':'Capacity shortfall within horizon','Qty short':rem})
    allp=pd.DataFrame(rows)
    if not allp.empty:
        allp=allp.sort_values(['Plan Date','Section','Due Date','Work Order'],na_position='last',kind='stable').reset_index(drop=True)
    # capacity summary from planned/effective rows. Capacity ton is max unique resource basis per section/day, not sum duplicated rows.
    if allp.empty: summary=pd.DataFrame()
    else:
        plans=allp.groupby(['Plan Date','Section'],as_index=False).agg({'Plan Qty pcs':'sum','Plan ton':'sum'})
        caps=(allp.groupby(['Plan Date','Section','Resource Key'],as_index=False)['Capacity ton'].max()
                 .groupby(['Plan Date','Section'],as_index=False)['Capacity ton'].sum())
        g=plans.merge(caps,on=['Plan Date','Section'],how='left')
        g['Utilization %']=g.apply(lambda r: round(r['Plan ton']/r['Capacity ton']*100,1) if num(r['Capacity ton'])>0 else None,axis=1)
        g['Gap ton']=g.apply(lambda r: round(num(r['Capacity ton'])-num(r['Plan ton']),4) if num(r['Capacity ton'])>0 else None,axis=1)
        summary=g
    # WIP analysis from physical cumulative flow
    w=[]
    for _,r in plan.iterrows():
        if bool(r.get('Overall Closed',False)):continue
        w.append({'Work Order':r.get('Work Order'),'Customer':r.get('Customer'),'Due Date':r.get('Due Date'),'Category':r.get('Category'),
                  'WIP Preparation':num(r.get('WIP Preparation')),'WIP Mixing':num(r.get('WIP Mixing')),'WIP Forming':num(r.get('WIP Forming')),
                  'WIP Firing':num(r.get('WIP Firing')),'WIP Grinding / Cutting':num(r.get('WIP Grinding / Cutting')),'WIP Packing':num(r.get('WIP Packing')),
                  'Open ton':num(r.get('Open Weight kg'))/1000})
    wip=pd.DataFrame(w)
    return {'all':allp,'capacity_summary':summary,'issues':pd.DataFrame(issues),'wip':wip}
