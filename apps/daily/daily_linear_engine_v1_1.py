from __future__ import annotations
from datetime import date,timedelta
import math,re
import pandas as pd
import sl_daily_engine_v3_22_from_v17 as de
import lead_time_control_v1 as lt
from date_and_wo_rules import parse_date, normalize_wo, resolve_wo, joined_parts

SECTIONS=['Preparation','Mixing','Forming','Firing','Grinding / เจียร','Cutting / ตัด','Packing']

def txt(v):
    return '' if v is None or (isinstance(v,float) and math.isnan(v)) else str(v).strip()
def num(v,d=0.0):
    try:
        x=float(v); return d if math.isnan(x) or math.isinf(x) else x
    except:return d
def pdate(v):
    return parse_date(v)
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
    """Confirmed post-firing routing. CP > 1 = Cutting. CP <= 1 + S/T/Honing/Segment = direct QC->Packing. Otherwise Grinding."""
    ov=txt(r.get('Post-Firing Route')).strip(); ovu=ov.upper()
    if ov and ovu not in {'AUTO','DEFAULT','AUTOMATIC'}:
        if 'DIRECT' in ovu and ('PACK' in ovu or 'บรรจุ' in ov): return 'Direct Packing / บรรจุโดยตรง'
        if 'CUT' in ovu or 'ตัด' in ov: return 'Cutting / ตัด'
        if 'GRIND' in ovu or 'เจียร' in ov: return 'Grinding / เจียร'
    cp=num(r.get('Cut Factor'),1)
    if cp>1: return 'Cutting / ตัด'
    s=' '.join(txt(r.get(k,'')) for k in ['Product Type','Specification','Shape','Category']).upper()
    compact=re.sub(r'[^A-Z0-9ก-๙]','',s)
    cat=txt(r.get('Category')).upper()
    direct_tokens=['HONING','HONNING','HONNIG','HONIN','HONE','SEGMENT','SEGMENTR','SEGMNTR','SEGMNT','SEGMEN','SEMENT']
    if cat in {'S','T'} or any(x in compact for x in direct_tokens) or 'หินลับมีด' in s:
        return 'Direct Packing / บรรจุโดยตรง'
    return 'Grinding / เจียร'

def pair_key(wo):
    """PM024A-010126 and PM024B-010126 are one two-layer forming family."""
    x=txt(wo).upper()
    m=re.match(r'^(.*?)([AB])(-\d{6}.*)$',x)
    return (m.group(1)+m.group(3)) if m else ''

def qc_required(r):
    v=txt(r.get('QC Required','YES')).upper()
    return v not in {'NO','N','FALSE','0','SKIP','ไม่'}

def ncr_disposition(r):
    return txt(r.get('NCR Disposition','HOLD')).upper() or 'HOLD'

def ncr_stage(r):
    return txt(r.get('NCR Stage','QC')).upper() or 'QC'

def mixing_candidates(mix,r):
    if mix is None or mix.empty:return pd.DataFrame()
    x=mix.copy()
    x=x[x['Status'].astype(str).str.strip().eq('ใช้')]
    fam=de.family(r.get('Category'))
    x=x[x['Job'].apply(lambda z:de.mix_job_ok(z,fam))]
    x=x[(pd.to_numeric(x['CAP-โม่'],errors='coerce').fillna(0)>0)&(pd.to_numeric(x['Max batch kg'],errors='coerce').fillna(0)>0)].copy()
    if x.empty:return x
    x['Abrasive OK']=x['Abrasive'].apply(lambda z:de.abrasive_ok(z,r.get('Specification')))
    x['Daily kg']=pd.to_numeric(x['CAP-โม่'],errors='coerce').fillna(0)*pd.to_numeric(x['Machine kg'],errors='coerce').fillna(0)
    return x.sort_values(['Abrasive OK','Daily kg'],ascending=[False,False])

def forming_match(form,r):
    rr=pd.Series({'Specification':r.get('Specification',''),'Type':r.get('Category',''),'D':num(r.get('D')),'T':num(r.get('T')),'H':num(r.get('H'))})
    mr,score=de.forming_match(rr,form)
    return mr,score

def grinding_match(grind,r):
    rr=pd.Series({'Product Code':r.get('Product Code',''),'Specification':r.get('Specification',''),'Real Spec':r.get('Product Type',''),'Type':r.get('Category',''),'Shape':r.get('Shape','')})
    return de.grinding_match(rr,grind)

def packing_match(pack,r):
    rr=pd.Series({'Specification':r.get('Specification',''),'Real Spec':r.get('Product Type',''),'Type':r.get('Category',''),'D':num(r.get('D')),'T':num(r.get('T')),'H':num(r.get('H'))})
    return de.packing_match(rr,pack)

def size_inch(r):
    d=num(r.get('D'),0)
    return d/25.4 if d>0 else None

def load_firing_excel(path):
    """
    Read Firing Planner output by header names instead of one rigid sheet layout.

    Supported sources include the current V1.8 ``Firing Detail`` sheet and the
    operator-print formats used by earlier firing planners.  Planning must not
    fail merely because an operator sheet calls the quantity ``Qty pcs`` rather
    than ``Planned Firing Qty``.
    """
    xls=pd.ExcelFile(path)

    def norm(v):
        # Keep Thai characters, remove punctuation/spacing, and compare case-insensitively.
        return re.sub(r'[^0-9A-Za-zก-๙]+','',txt(v)).lower()

    preferred=[
        'Firing Detail','WO DETAIL','Released Operator Print','Operator Print',
        'Firing plan Operator print','Firing Plan Operator Print',
        'Auto Firing Plan','Released Firing Plan'
    ]
    by_norm={norm(sh):sh for sh in xls.sheet_names}
    sheet_order=[]
    for want in preferred:
        got=by_norm.get(norm(want))
        if got and got not in sheet_order: sheet_order.append(got)
    for sh in xls.sheet_names:
        if sh not in sheet_order: sheet_order.append(sh)

    aliases={
        'wo':['Work Order','Work Order / ใบสั่งผลิต','ProductionCode','Production Code','WO','WorkOrder','เลขที่ใบสั่งผลิต'],
        'qty':['Planned Firing Qty','Planned Qty (pcs) / จำนวนแผน (ชิ้น)','Firing Qty','Qty pcs','Plan Qty','Planned Qty','Quantity','Qty','จำนวน','จำนวนแผน','จำนวน PLAN','จำนวน PLANรวม'],
        'date':['Load Date','Loading Date / วันที่เข้าเตา','Firing Date','Firing Start Date','วันที่เข้าเผา','วันที่เผา'],
        'finish':['Program Finish Date','Firing Finish Date / วันที่เผาเสร็จ','Firing Complete','Unload / Take-Out Date','Firing Finish Date','Finish Date','วันที่ออกเตา'],
        'kgpc':['kg/pc','kg/pc / กก./ชิ้น','Weight kg/pc','Gross kg/pc','น้ำหนัก/ก้อน'],
        'weightkg':['Weight kg','Load Weight kg','น้ำหนัก kg'],
    }
    alias_norm={k:{norm(v) for v in vals} for k,vals in aliases.items()}

    def pick(cols,key):
        for c in cols:
            if norm(c) in alias_norm[key]: return c
        return None

    attempts=[]
    for sh in sheet_order:
        # Header 0 is the normal/current format. Header 1 is tolerated for old
        # operator sheets that have a bilingual/title row above the real header.
        for hdr in (0,1):
            try:
                d=pd.read_excel(path,sheet_name=sh,header=hdr)
            except Exception as e:
                attempts.append(f'{sh}[header={hdr}]: read error {e}')
                continue
            if d is None or d.empty:
                attempts.append(f'{sh}[header={hdr}]: empty')
                continue
            d.columns=[txt(c) for c in d.columns]
            wo_col=pick(d.columns,'wo'); qty_col=pick(d.columns,'qty'); date_col=pick(d.columns,'date'); finish_col=pick(d.columns,'finish')
            kg_col=pick(d.columns,'kgpc'); weight_col=pick(d.columns,'weightkg')

            # A Firing Loads summary has Qty pcs but no Work Order. It is not a
            # valid daily-planner anchor because the process flow is WO based.
            if wo_col is None:
                attempts.append(f'{sh}[header={hdr}]: Work Order not found')
                continue
            if date_col is None:
                attempts.append(f'{sh}[header={hdr}]: firing/load date not found')
                continue
            if finish_col is None:
                attempts.append(f'{sh}[header={hdr}]: program finish date not found')
                continue

            out=d.copy()
            if wo_col!='Work Order': out['Work Order']=d[wo_col]

            # Quantity is normally explicit.  As a compatibility fallback only,
            # reconstruct pcs from total load weight / kg-per-piece when both are
            # present and physically meaningful.
            if qty_col is not None:
                out['Firing Qty']=pd.to_numeric(d[qty_col],errors='coerce').fillna(0)
                qty_basis=qty_col
            elif kg_col is not None and weight_col is not None:
                kgpc=pd.to_numeric(d[kg_col],errors='coerce')
                wkg=pd.to_numeric(d[weight_col],errors='coerce')
                q=(wkg/kgpc).replace([float('inf'),float('-inf')],pd.NA)
                out['Firing Qty']=pd.to_numeric(q,errors='coerce').fillna(0).round(0)
                qty_basis=f'derived {weight_col}/{kg_col}'
            else:
                attempts.append(f'{sh}[header={hdr}]: quantity column not found; columns={list(d.columns)[:25]}')
                continue

            out['Firing Date']=d[date_col].apply(pdate)
            out['Firing Complete']=d[finish_col].apply(pdate)
            out['kg/pc']=pd.to_numeric(d[kg_col],errors='coerce').fillna(0) if kg_col else 0.0
            out['Work Order']=out['Work Order'].fillna('').astype(str).str.strip()
            out=out[(out['Work Order']!='') & (out['Firing Qty']>0)].copy()
            out=out[out['Firing Date'].notna() & out['Firing Complete'].notna()].copy()
            if out.empty:
                attempts.append(f'{sh}[header={hdr}]: mapped but no usable positive-WO firing rows')
                continue
            out['Firing Source Sheet']=sh
            out['Firing Qty Source']=qty_basis
            # F12R+ compatibility: retain Test Work / work-type metadata when present.
            # These columns are informational and must never break the firing anchor.
            optional_aliases={
                'Test Work':['Test Work','Test Work / งานทดสอบ'],
                'Test Work Type':['Test Work Type','Test Type / ประเภทงานทดสอบ'],
                'Product Code':['Product Code','Product Code / รหัสสินค้า'],
                'Customer':['Customer','Customer / ลูกค้า'],
                'Category':['Category','Product Category / ประเภทผลิตภัณฑ์'],
                'Kiln':['Kiln','Kiln / เตา'],
                'Program':['Program','Program / โปรแกรม'],
                'Due Date':['Due Date','Due Date / วันกำหนดส่ง'],
            }
            for target,names in optional_aliases.items():
                if target in out.columns: continue
                c=next((cc for cc in d.columns if norm(cc) in {norm(n) for n in names}),None)
                if c is not None: out[target]=d[c]
            return out

    detail=' | '.join(attempts[:12])
    raise ValueError(
        'Firing output could not be mapped. Please use the Excel downloaded from the Firing Planner. '
        'Supported sheets include Firing Detail, Released Operator Print, Operator Print and Firing Plan Operator Print. '
        f'Diagnostic: {detail}'
    )

def build_daily(plan, firing, mix, form, kiln, grind, pack, start, horizon=30, prep_kg=1200, packing_people=1):
    plan=plan.copy();firing=firing.copy()
    if 'Work Order' in plan:plan['Work Order']=plan['Work Order'].apply(normalize_wo)
    if 'Work Order' in firing:firing['Work Order']=firing['Work Order'].apply(normalize_wo)
    """Fast linked daily planner with Plan2026 existing-WIP priority.

    V1.3.0 corrections:
    * Planning start is authoritative for EXISTING downstream WIP from Plan 2026.
      A firing file that begins on the same date cannot postpone already-fired WIP.
    * New kiln output receives one working day for QC, then becomes available to its
      selected post-firing route on the following working day.
    * Grinding and Cutting are separate plan sections.
    * Per-WO route override + NCR hold are planning-layer controls.
    """
    end=start+timedelta(days=horizon-1)
    # PLAN 2026 is authoritative for existing physical WIP at the selected start date.
    # A WO may appear on multiple rows for partial deliveries, so never let the last
    # row silently replace the others.  Keep one metadata row per WO, but SUM the
    # row-level WIP quantities across all open rows for execution.
    pmap={}
    for wo,g in plan.groupby(plan['Work Order'].astype(str).str.strip(), sort=False):
        if not wo: continue
        gg=g.copy()
        if 'Due Date' in gg.columns:
            gg['_d']=gg['Due Date'].apply(lambda x:pdate(x) or date(2099,12,31))
            gg=gg.sort_values('_d',kind='stable')
        pmap[wo]=gg.iloc[0]
    rows=[];issues=[]
    used_prep={};used_mix_batches={};used_form={};used_mold={}
    # Shared downstream resources use utilization fractions so different products
    # cannot each consume 100% of the same machine/manpower day.
    used_post_frac={};used_pack_frac={}; active_post_machines={}; used_post_people={}
    buffers={}
    _open_mask=~plan.get('Overall Closed',pd.Series(False,index=plan.index)).fillna(False)
    _open_rows=plan[_open_mask].copy()
    for wo,g in _open_rows.groupby(_open_rows['Work Order'].astype(str).str.strip(), sort=False):
        if not wo: continue
        buffers[wo]={
            'fire':float(pd.to_numeric(g.get('WIP Firing',0),errors='coerce').fillna(0).sum()),
            'form':float(pd.to_numeric(g.get('WIP Forming',0),errors='coerce').fillna(0).sum()),
            'mix':float(pd.to_numeric(g.get('WIP Mixing',0),errors='coerce').fillna(0).sum())
        }

    grind_by_prod={}
    if grind is not None and not grind.empty and 'ProductionCode' in grind.columns:
        for _,_gr in grind.iterrows():
            _pc=txt(_gr.get('ProductionCode')).upper()
            if _pc and _pc not in grind_by_prod:grind_by_prod[_pc]=_gr
    _form_cache={};_pack_cache={};_mix_cache={};_grind_cache={}

    def addrow(day,sec,r,qty,kgpc,cap_qty,cap_t,basis,source,anchor='',resource_key='',extra=None):
        if day<start or day>end or qty<=0:return
        rec={'Plan Date':day,'Section':sec,'Work Order':r.get('Work Order',''),'Customer':r.get('Customer',''),
             'Specification':r.get('Specification',''),'Category':r.get('Category',''),'Due Date':r.get('Due Date'),
             'D':num(r.get('D')),'T':num(r.get('T')),'H':num(r.get('H')),'Shape':r.get('Shape',''),'Cut Factor':num(r.get('Cut Factor'),1),'Product Code':r.get('Product Code',''),
             'Plan Qty':round(qty,2),'Plan Qty pcs':round(qty,2),'Plan kg':round(qty*kgpc,3),'Plan ton':round(qty*kgpc/1000,4),
             'Capacity Qty pcs':round(cap_qty,2) if cap_qty is not None else None,'Capacity ton':round(cap_t,4) if cap_t is not None else None,
             'Utilization %':round((qty/cap_qty)*100,1) if cap_qty and cap_qty>0 else None,
             'Capacity Basis':basis,'Source / Reason':source,'Firing Anchor':anchor,'Resource Key':resource_key,
             'Post-Firing Route':route(r),'QC Required':'YES' if qc_required(r) else 'NO',
             'Planning Priority Class':_balance_class(day,r),
             'Planning Policy':'DUE DATE FIRST; BALANCE WITH LOWER/FAR-DUE WORK ONLY AFTER EARLIER-DUE EXECUTABLE DEMAND',
             **lt.applied_offsets(r)}
        if extra:rec.update(extra)
        rows.append(rec)

    # NCR is a visible quantity HOLD, never silently deleted. ACCEPT/USE does not block flow.
    ncr_rem={}
    for wo,r in pmap.items(): ncr_rem[wo]=max(num(r.get('NCR Qty')),0)
    def apply_ncr(wo,r,stage,qty):
        q=max(float(qty),0);rem=ncr_rem.get(wo,0)
        if q<=0 or rem<=0:return q,0.0
        disp=ncr_disposition(r)
        if 'ACCEPT' in disp or 'USE' in disp:return q,0.0
        want=ncr_stage(r).replace(' / ',' ').upper();got=str(stage).replace(' / ',' ').upper()
        # Accept broad stage names (QC, FIRING, GRINDING, CUTTING, CLEANING, PACKING).
        if not (want in got or got in want):return q,0.0
        hold=min(q,rem);ncr_rem[wo]=max(rem-hold,0)
        issues.append({'Work Order':wo,'Section / กระบวนการ':stage,'Qty':hold,
                       'Reason':f'NCR {disp}: {hold:g} pcs held at {stage}; downstream quantity reduced until disposition is cleared'})
        return q-hold,hold

    post_jobs=[];pack_jobs=[]
    # Existing physical WIP is independent of the newly uploaded firing schedule.
    # This is the key 8-Sep correction: if Plan2026 shows already-fired WIP, it can
    # start Grinding/Cutting/Cleaning on planning start, subject to its own capacity.
    open_plan=_open_rows.copy()
    # Aggregate EXISTING downstream WIP by WO. This is independent of the uploaded
    # firing plan and therefore can start on the user-selected Planning Start date.
    _existing=[]
    for wo,g in open_plan.groupby(open_plan['Work Order'].astype(str).str.strip(), sort=False):
        if not wo: continue
        r=pmap.get(wo,g.iloc[0])
        qpost=float(pd.to_numeric(g.get('WIP Grinding / Cutting',0),errors='coerce').fillna(0).sum())
        qpack=float(pd.to_numeric(g.get('WIP Packing',0),errors='coerce').fillna(0).sum())
        _existing.append((r,qpost,qpack))
    _existing.sort(key=lambda z:(pdate(z[0].get('Due Date')) or date(2099,12,31), txt(z[0].get('Work Order'))))
    for r,qpost,qpack in _existing:
        wo=txt(r.get('Work Order'));kgpc=num(r.get('Net Weight g/pc'))/1000.0
        qpost=max(qpost,0);qpack=max(qpack,0)
        rt=route(r)
        if qpost>0:
            if rt.startswith('Direct Packing'):
                pack_jobs.append({'wo':wo,'r':r,'qty':qpost,'arrival':start,'source':'Existing Plan 2026 post-firing WIP at planning start','anchor':''})
            else:
                post_jobs.append({'wo':wo,'r':r,'qty':qpost,'arrival':start,'route':rt,'source':'Existing Plan 2026 post-firing WIP at planning start','anchor':''})
        if qpack>0:
            pack_jobs.append({'wo':wo,'r':r,'qty':qpack,'arrival':start,'source':'Existing Plan 2026 packing-ready WIP at planning start','anchor':''})

    firing=firing.copy()
    if 'Due Date' not in firing.columns:firing['Due Date']=None
    firing=firing.sort_values(['Firing Date','Due Date','Work Order'],na_position='last',kind='stable')
    for _,f in firing.iterrows():
        wo=normalize_wo(f.get('Work Order'));r,_legacy_parts=resolve_wo(wo,pmap)
        if r is None:
            issues.append({'Work Order':wo,'Section / กระบวนการ':'Firing','Qty':num(f.get('Firing Qty')),'Reason':'WO in firing output not found in Plan 2026'});continue
        q=num(f.get('Firing Qty'));kgpc=num(f.get('kg/pc'),num(r.get('Gross Weight g/pc'))/1000)
        fd=pdate(f.get('Firing Date'));fc=pdate(f.get('Firing Complete'))
        if q<=0 or not fd or not fc:continue
        anchor=f"{txt(f.get('Kiln'))} {txt(f.get('Program'))} {fd}"
        maxkg=0;run_days=None
        if kiln is not None and not kiln.empty:
            rule=de.firing_program_rule(f.get('Program'),f.get('Kiln'),kiln)
            if rule is not None:maxkg=num(rule.get('Max kg/load'));run_days=num(rule.get('Running Days'))
        addrow(fd,'Firing',r,q,kgpc,q,maxkg/1000 if maxkg else q*kgpc/1000,'Firing Planner + Cap เตา','Exact firing planner anchor',anchor,'FIRE:'+anchor,
               {'Kiln':f.get('Kiln',''),'Program':f.get('Program',''),'Running Days':run_days,'Program Finish Date':fc,'Program Max kg':maxkg})

        b=buffers.setdefault(wo,{'fire':0,'form':0,'mix':0})
        fire_from_wip=min(q,b['fire']);b['fire']-=fire_from_wip
        form_need=max(q-fire_from_wip,0)
        form_from_wip=min(form_need,b['form']);b['form']-=form_from_wip
        mix_need=max(form_need-form_from_wip,0)
        mix_from_wip=min(mix_need,b['mix']);b['mix']-=mix_from_wip
        prep_need=max(mix_need-mix_from_wip,0)

        # Preparation — lead-time controlled from Delivery Control Process source
        _lt=lt.applied_offsets(r)
        _form_off=int(_lt['Forming→Firing WD']); _mix_off=_form_off+int(_lt['Mixing→Forming WD']); _prep_off=_mix_off+int(_lt['Preparation→Mixing WD'])
        rem=prep_need;d=prev_workday(fd,_prep_off);guard=0
        while rem>0 and d>=start and guard<60:
            availkg=max(float(prep_kg)-used_prep.get(d,0),0);take=min(rem,math.floor(availkg/kgpc) if kgpc>0 else 0)
            if take>0:
                kg=take*kgpc;used_prep[d]=used_prep.get(d,0)+kg
                addrow(d,'Preparation',r,take,kgpc,prep_kg/kgpc if kgpc else None,prep_kg/1000,'Preparation controlled kg/day + Delivery Control lead time',f"New preparation required; profile={_lt['Lead Time Profile']}; Prep→Mix={_lt['Preparation→Mixing WD']}WD",anchor,'PREP:PLANT',{'Capacity kg/day':prep_kg,'Capacity Used kg':used_prep[d]});rem-=take
            d=prev_workday(d);guard+=1
        if rem>0:issues.append({'Work Order':wo,'Section / กระบวนการ':'Preparation','Qty':rem,'Reason':'Preparation kg/day insufficient before firing after existing WIP'})

        # Mixing — cannot be placed immediately after Preparation when source lead time requires more time
        rem=mix_need;d=prev_workday(fd,_mix_off);guard=0;_mk=(txt(r.get('Category')).upper(),txt(r.get('Specification')).upper());cand=_mix_cache.get(_mk)
        if cand is None:cand=mixing_candidates(mix,r);_mix_cache[_mk]=cand
        while rem>0 and d>=start and guard<60:
            if cand.empty:break
            progress=False
            for _,m in cand.iterrows():
                mc=txt(m.get('Machine'));base=max(int(num(m.get('CAP-โม่'))),0);used=used_mix_batches.get((d,mc),0);free=max(base-used,0)
                if free<=0:continue
                mn=num(m.get('Min batch kg'));mx=num(m.get('Max batch kg'));choice=None
                if kgpc>0:
                    for bb in range(1,free+1):
                        qmax=min(rem,math.floor((bb*mx)/kgpc));qmin=math.ceil((bb*mn)/kgpc) if mn>0 else 1
                        if qmax>=qmin and qmax>0 and (choice is None or qmax>choice[0]):choice=(qmax,bb)
                if choice is None:continue
                take,batches=choice;kg=take*kgpc;avg=kg/batches;used_mix_batches[(d,mc)]=used+batches;rem-=take;progress=True;capkg=base*num(m.get('Machine kg'))
                addrow(d,'Mixing',r,take,kgpc,capkg/kgpc if kgpc else None,capkg/1000,'CAP ผสม: mixer + job/family + CAP-โม่ + batch range + abrasive',f"Mixing required; profile={_lt['Lead Time Profile']}; Mix→Form={_lt['Mixing→Forming WD']}WD",anchor,'MIX:'+mc,
                       {'Machine':mc,'Mixing Job':m.get('Job',''),'Required Batches':batches,'CAP-โม่ Available':base,'CAP-โม่ Used':used_mix_batches[(d,mc)],'Machine Utilization %':round(used_mix_batches[(d,mc)]/base*100,1) if base else None,'Average Batch kg':avg,'Batch Range':f"{mn:g}-{mx:g}",'Machine kg Master':num(m.get('Machine kg')),'Abrasive Master':m.get('Abrasive',''),'Abrasive Check':'PASS' if bool(m.get('Abrasive OK')) else 'VERIFY'})
                if rem<=0:break
            d=prev_workday(d);guard+=1
            if not progress and guard>2:break
        if rem>0:issues.append({'Work Order':wo,'Section / กระบวนการ':'Mixing','Qty':rem,'Reason':'No feasible mixer/day under Job/family, CAP-โม่, batch range and abrasive'})

        # Forming — drying/pre-curing + pre-firing loading lead time must finish before Firing
        rem=form_need;d=prev_workday(fd,_form_off);guard=0;_fk=(txt(r.get('Category')).upper(),txt(r.get('Specification')).upper(),round(num(r.get('D')),3),round(num(r.get('T')),3),round(num(r.get('H')),3));_fm=_form_cache.get(_fk)
        if _fm is None:_fm=forming_match(form,r);_form_cache[_fk]=_fm
        mr,score=_fm;forced_mc=txt(r.get('Forced Forming Machine'));forced_cap=num(r.get('Forced Forming Capacity pcs/day'))
        if forced_mc and forced_cap>0:mr={'Normal pcs/8h':forced_cap,'Spec Pattern':'MANUAL VERIFIED OVERRIDE','Machine':forced_mc,'pcs/hour':forced_cap/8.0};score=9999
        no_match=mr is None
        while rem>0 and d>=start and guard<60:
            if mr is None:break
            cap=num(mr.get('Normal pcs/8h'));mold=txt(mr.get('Spec Pattern')).upper();machines=de.machines(mr.get('Machine'));best=None
            if used_mold.get((d,mold),0)<1:
                for mc in machines:
                    av=max(cap-used_form.get((d,mc),0),0)
                    if best is None or av>best[0]:best=(av,mc)
            if best and best[0]>0:
                take=min(rem,math.floor(best[0]));mc=best[1];used_form[(d,mc)]=used_form.get((d,mc),0)+take;used_mold[(d,mold)]=1;rem-=take
                addrow(d,'Forming',r,take,kgpc,cap,cap*kgpc/1000,'CAP ขึ้นรูป: category + spec/size + D/T/H evidence + eligible M/C + 8h capacity + mold lock',f"Forming required; profile={_lt['Lead Time Profile']}; Form→Fire={_lt['Forming→Firing WD']}WD",anchor,'FORM:'+mc,
                       {'Machine':mc,'Eligible Machines':mr.get('Machine',''),'Master Spec Match':mr.get('Spec Pattern',''),'Match Score':score,'Capacity pcs/day':cap,'pcs/hour':num(mr.get('pcs/hour')),'Machine Load After WO':used_form[(d,mc)],'Mold / Spec Resource':mold})
            d=prev_workday(d);guard+=1
        if rem>0:
            _reason='NO FORMING MACHINE/SIZE MATCH - verify Category, Specification, D/T/H or verified machine override' if no_match else 'FORMING CAPACITY/TIME INSUFFICIENT BEFORE FIRING - move firing later or verify real capacity'
            issues.append({'Work Order':wo,'Section / กระบวนการ':'Forming','Qty':rem,'Reason':_reason})

        # QC belongs to the QC department and is NOT issued as a PPC production section.
        # Its duration remains a scheduling buffer between Firing completion and the next PPC-controlled process.
        usable,held=apply_ncr(wo,r,'Firing',q)
        if usable<=0:continue
        if qc_required(r):
            qcday=next_workday(fc)
            usable2,held2=apply_ncr(wo,r,'QC',usable)
            arrival=next_workday(qcday)
        else:
            usable2=usable;arrival=next_workday(fc)
        if usable2<=0:continue
        rt=route(r)
        if rt.startswith('Direct Packing'):
            pack_jobs.append({'wo':wo,'r':r,'qty':usable2,'arrival':arrival,'source':'New firing output after QC','anchor':anchor})
        else:
            post_jobs.append({'wo':wo,'r':r,'qty':usable2,'arrival':arrival,'route':rt,'source':'New firing output after QC','anchor':anchor})

    # ---------- GLOBAL POST-FIRING SCHEDULER ----------
    # Existing WIP and new arrivals compete together, day-by-day, by due date.
    for j in post_jobs:
        j['remaining']=float(j['qty']);j['due']=pdate(j['r'].get('Due Date')) or date(2099,12,31)
        j['match']=None
        rt=j['route'];r=j['r']
        if rt.startswith('Grinding') or rt.startswith('Cutting'):
            gk=(txt(r.get('Product Code')).upper(),txt(r.get('Specification')).upper(),txt(r.get('Category')).upper(),txt(r.get('Shape')).upper())
            if gk in _grind_cache:
                j['match']=_grind_cache[gk]
            else:
                pc=txt(r.get('Product Code')).upper();gm=_fast_grinding_match(r);_grind_cache[gk]=gm;j['match']=gm
    days=[];dday=start
    while dday<=end:
        if workday(dday) or dday==start:days.append(dday)   # selected start date is always day 1
        dday+=timedelta(days=1)
    for d in days:
        eligible=[j for j in post_jobs if j['remaining']>0 and j['arrival']<=d]
        eligible.sort(key=lambda j:(j['due'],j['arrival'],j['wo']))
        for j in eligible:
            r=j['r'];wo=j['wo'];rt=j['route'];kgpc=num(r.get('Net Weight g/pc'))/1000.0
            qty=j['remaining']
            stage='Cutting' if rt.startswith('Cutting') else ('Grinding' if rt.startswith('Grinding') else 'Cleaning')
            usable,held=apply_ncr(wo,r,stage,qty)
            # NCR is consumed once; keep the unblocked portion available. Held quantity leaves this job.
            if held>0:j['remaining']-=held
            if usable<=0:continue
            if rt.startswith('Cleaning'):
                take=usable
                addrow(d,'Cleaning / ทำความสะอาด',r,take,kgpc,take,take*kgpc/1000,'Factory route: one working-day cleaning step','Existing/future post-firing WIP by route',j['anchor'],'CLEAN:'+wo,{'Route':rt,'Machine Sequence':'Cleaning'})
                j['remaining']-=take
                pack_jobs.append({'wo':wo,'r':r,'qty':take,'arrival':next_workday(d),'source':'After Cleaning + next working day','anchor':j['anchor']})
                continue
            gr,score=j['match'] if j['match'] is not None else (None,0)
            if gr is None:continue
            cap=max(num(gr.get('Bottleneck CAP/day')),0)
            machine=next((txt(gr.get(f'Op{i} Machine')) for i in range(1,7) if num(gr.get(f'Op{i} CAP/day'))==cap and txt(gr.get(f'Op{i} Machine'))),txt(gr.get('ProductionCode')) or 'UNRESOLVED')
            if cap<=0:continue
            key=(d,machine);frac=used_post_frac.get(key,0.0);avail=max(1.0-frac,0.0)*cap;take=min(usable,math.floor(avail+1e-9))
            if take<=0:continue
            used_post_frac[key]=frac+take/cap;j['remaining']-=take
            sec=('Cutting / ตัด' if rt.startswith('Cutting') else 'Grinding / เจียร')
            addrow(d,sec,r,take,kgpc,cap,cap*kgpc/1000,'Cap เจีย: matched product/spec operation sequence; shared bottleneck machine utilization','Existing/future post-firing WIP by due date and arrival',j['anchor'],f'{sec}:{machine}',
                   {'Route':rt,'Machine Sequence':gr.get('Operations',''),'Bottleneck CAP/day':cap,'Bottleneck Machine':machine,'Setup Time hr':setup_hr,'Required Workers':req_workers,'Grinding Current People':dept_people,'Grinding People Used':used_post_people.get(day,0),'Match Score':score,'Shared Machine Utilization %':round(used_post_frac[key]*100,1)})
            pack_jobs.append({'wo':wo,'r':r,'qty':take,'arrival':next_workday(d),'source':f'After {sec} + next working day','anchor':j['anchor']})
    for j in post_jobs:
        if j['remaining']>0:
            issues.append({'Work Order':j['wo'],'Section / กระบวนการ':j['route'],'Qty':j['remaining'],'Reason':'Post-firing route capacity/resource match insufficient within planning horizon'})

    # ---------- GLOBAL PACKING SCHEDULER ----------
    for j in pack_jobs:
        j['remaining']=float(j['qty']);j['due']=pdate(j['r'].get('Due Date')) or date(2099,12,31)
        r=j['r'];pk=(txt(r.get('Category')).upper(),txt(r.get('Specification')).upper(),round(num(r.get('D')),3),round(num(r.get('T')),3),round(num(r.get('H')),3))
        if pk in _pack_cache:j['match']=_pack_cache[pk]
        else:pm=packing_match(pack,r);_pack_cache[pk]=pm;j['match']=pm
    for d in days:
        eligible=[j for j in pack_jobs if j['remaining']>0 and j['arrival']<=d]
        eligible.sort(key=lambda j:(j['due'],j['arrival'],j['wo']))
        for j in eligible:
            r=j['r'];wo=j['wo'];kgpc=num(r.get('Net Weight g/pc'))/1000.0
            usable,held=apply_ncr(wo,r,'Packing',j['remaining'])
            if held>0:j['remaining']-=held
            if usable<=0:continue
            pr,pscore=j['match'] if j['match'] is not None else (None,0)
            if pr is None:continue
            per=max(num(pr.get('Bottleneck pcs/day/person')),0);cap=per*max(int(packing_people),1)
            if cap<=0:continue
            frac=used_pack_frac.get(d,0.0);avail=max(1.0-frac,0.0)*cap;take=min(usable,math.floor(avail+1e-9))
            if take<=0:continue
            used_pack_frac[d]=frac+take/cap;j['remaining']-=take
            addrow(d,'Packing',r,take,kgpc,cap,cap*kgpc/1000,'Cap บรรจุ: matched size/type bottleneck × shared manpower','Packing-ready WIP by due date and arrival',j['anchor'],'PACK:SHARED',
                   {'Capacity pcs/day':cap,'Capacity pcs/day/person':per,'Packing People':packing_people,'Master Spec Match':pr.get('Spec Pattern',''),'Master Type':pr.get('Type',''),'Packing Processes':pr.get('Processes',''),'Match Score':pscore,'Shared Packing Utilization %':round(used_pack_frac[d]*100,1)})
    for j in pack_jobs:
        if j['remaining']>0:
            issues.append({'Work Order':j['wo'],'Section / กระบวนการ':'Packing','Qty':j['remaining'],'Reason':'Packing size/type/manpower capacity insufficient within horizon or no master match'})

    allp=pd.DataFrame(rows)
    if not allp.empty:allp=allp.sort_values(['Plan Date','Section','Due Date','Work Order'],na_position='last',kind='stable').reset_index(drop=True)
    w=[]
    for _,r in plan.iterrows():
        if bool(r.get('Overall Closed',False)):continue
        w.append({'Work Order':r.get('Work Order'),'Customer':r.get('Customer'),'Due Date':r.get('Due Date'),'Category':r.get('Category'),
                  'WIP Preparation':num(r.get('WIP Preparation')),'WIP Mixing':num(r.get('WIP Mixing')),'WIP Forming':num(r.get('WIP Forming')),
                  'WIP Firing':num(r.get('WIP Firing')),'WIP Grinding / Cutting':num(r.get('WIP Grinding / Cutting')),'WIP Packing':num(r.get('WIP Packing')),
                  'Open ton':num(r.get('Open Weight kg'))/1000})
    return {'all':allp,'capacity_summary':pd.DataFrame(),'issues':pd.DataFrame(issues),'wip':pd.DataFrame(w)}


# =====================================================================
# V1.4.0 GLOBAL START-DATE ENGINE
# Every process uses the user-selected Planning Start for EXISTING Plan2026 WIP.
# Firing remains anchored to the uploaded Firing Planner. New inter-process output
# becomes available only on the next working day. This definition intentionally
# overrides the earlier build_daily above without changing helper/matching code.
# =====================================================================
def build_daily(plan, firing, mix, form, kiln, grind, pack, start, horizon=30, prep_kg=1200, packing_people=1, previous_firing=None, normal_hours=7.6667):
    plan=plan.copy();firing=firing.copy()
    if 'Work Order' in plan:plan['Work Order']=plan['Work Order'].apply(normalize_wo)
    if 'Work Order' in firing:firing['Work Order']=firing['Work Order'].apply(normalize_wo)
    end=start+timedelta(days=int(horizon)-1)
    days=[]; d=start
    while d<=end:
        if workday(d): days.append(d)
        d+=timedelta(days=1)

    # One metadata row per WO, but physical WIP is SUMMED over all open Plan2026 rows.
    open_mask=~plan.get('Overall Closed',pd.Series(False,index=plan.index)).fillna(False)
    op=plan[open_mask].copy()
    pmap={}
    for wo,g in op.groupby(op['Work Order'].astype(str).str.strip(),sort=False):
        if not wo: continue
        gg=g.copy(); gg['_due']=gg.get('Due Date',pd.Series(None,index=gg.index)).apply(lambda x:pdate(x) or date(2099,12,31))
        pmap[wo]=gg.sort_values('_due',kind='stable').iloc[0]

    wip_cols=['WIP Preparation','WIP Mixing','WIP Forming','WIP Firing','WIP Grinding / Cutting','WIP Packing']
    wip={}
    for wo,g in op.groupby(op['Work Order'].astype(str).str.strip(),sort=False):
        if not wo: continue
        wip[wo]={c:float(pd.to_numeric(g.get(c,0),errors='coerce').fillna(0).sum()) for c in wip_cols}

    rows=[]; issues=[]
    used_prep={}; used_mix_batches={}; used_form={}; used_mold={}; used_post_frac={}; used_pack_frac={}; active_post_machines={}; used_post_people={}
    _mix_cache={}; _form_cache={}; _grind_cache={}; _pack_cache={}

    # Due date remains primary. Current firing anchors are the secondary synchronization signal.
    _anchor_by_wo={}
    if firing is not None and not firing.empty:
        for _,_fr in firing.iterrows():
            _wo=txt(_fr.get('Work Order'));_fd=pdate(_fr.get('Firing Date'))
            if _wo and _fd and (_wo not in _anchor_by_wo or _fd<_anchor_by_wo[_wo]):_anchor_by_wo[_wo]=_fd
    def duekey(wo):
        # HARD PRIORITY: valid Due Date first. Plan2026 process/firing date is
        # fallback only when Due Date is unavailable. Capacity remains a hard gate.
        r=pmap[wo]
        due=pdate(r.get('Due Date'))
        fallback=pdate(r.get('Plan2026 Firing Date')) or _anchor_by_wo.get(wo,date(2099,12,31))
        return (0 if due else 1, due or fallback or date(2099,12,31), _anchor_by_wo.get(wo,date(2099,12,31)), wo)

    def _balance_class(day,r):
        due=pdate(r.get('Due Date'))
        if due is None:return 'P4 FILL - NO DUE DATE'
        delta=(due-day).days
        if delta<0:return 'P1 OVERDUE'
        if delta<=7:return 'P1 DUE SOON'
        if delta<=14:return 'P2 DUE PROTECTED'
        return 'P3 BALANCE PULL - FAR DUE'

    def addrow(day,sec,r,qty,kgpc,cap_qty=None,cap_t=None,basis='',source='',anchor='',resource_key='',extra=None):
        if not day or day<start or day>end or qty<=0:return
        rec={'Plan Date':day,'Section':sec,'Work Order':r.get('Work Order',''),'Customer':r.get('Customer',''),
             'Specification':r.get('Specification',''),'Category':r.get('Category',''),'Due Date':r.get('Due Date'),
             'D':num(r.get('D')),'T':num(r.get('T')),'H':num(r.get('H')),'Shape':r.get('Shape',''),'Cut Factor':num(r.get('Cut Factor'),1),'Product Code':r.get('Product Code',''),
             'Plan Qty':round(qty,2),'Plan Qty pcs':round(qty,2),'Plan kg':round(qty*kgpc,3),'Plan ton':round(qty*kgpc/1000,4),
             'Capacity Qty pcs':round(cap_qty,2) if cap_qty is not None else None,'Capacity ton':round(cap_t,4) if cap_t is not None else None,
             'Utilization %':round((qty/cap_qty)*100,1) if cap_qty and cap_qty>0 else None,
             'Capacity Basis':basis,'Source / Reason':source,'Firing Anchor':anchor,'Resource Key':resource_key,
             'Post-Firing Route':route(r),'QC Required':'YES' if qc_required(r) else 'NO',**lt.applied_offsets(r)}
        if extra:rec.update(extra)
        rows.append(rec)

    # NCR = explicit hold at selected stage.
    ncr_rem={wo:max(num(r.get('NCR Qty')),0) for wo,r in pmap.items()}
    def apply_ncr(wo,r,stage,qty):
        q=max(float(qty),0); rem=ncr_rem.get(wo,0)
        if q<=0 or rem<=0:return q,0.0
        disp=ncr_disposition(r)
        if 'ACCEPT' in disp or 'USE' in disp:return q,0.0
        want=ncr_stage(r).replace(' / ',' ').upper(); got=str(stage).replace(' / ',' ').upper()
        if not (want in got or got in want):return q,0.0
        hold=min(q,rem); ncr_rem[wo]=max(rem-hold,0)
        issues.append({'Work Order':wo,'Section / กระบวนการ':stage,'Qty':hold,'Reason':f'NCR {disp}: {hold:g} pcs held at {stage}'})
        return q-hold,hold

    # Initial physical queues from Plan2026. All are eligible on Planning Start.
    prep_need={wo:wip[wo]['WIP Preparation'] for wo in wip}
    mix_ready={wo:wip[wo]['WIP Mixing'] for wo in wip}
    form_ready={wo:wip[wo]['WIP Forming'] for wo in wip}
    fire_ready={wo:wip[wo]['WIP Firing'] for wo in wip}
    # Firing WIP includes drying/in-process, not proof that drying is complete.
    for wo in fire_ready:
        r=pmap[wo];profile=lt.applied_offsets(r)
        if profile['Curing/Oven Gate WD']<=0:continue
        done=pdate(r.get('Confirmed Drying Complete Date'))
        qty=num(r.get('Confirmed Drying Qty'),0) if done and done<=start else 0
        held=max(fire_ready[wo]-qty,0)
        fire_ready[wo]=min(fire_ready[wo],qty)
        if held>0:issues.append({'Work Order':wo,'Section / กระบวนการ':'Drying / Curing','Qty':held,'Reason':'Firing WIP is not confirmed dried; record actual drying completion and ready quantity in All functions → Confirm drying readiness'})

    post_ready={wo:wip[wo]['WIP Grinding / Cutting'] for wo in wip}
    pack_ready={wo:wip[wo]['WIP Packing'] for wo in wip}

    # Previous ISSUED firing plan bridge. This is evidence of material already fired before
    # the selected planning start. It may increase post-firing ready WIP, but never double
    # counts Plan2026: for each WO we take MAX(Plan2026 post-WIP, prior-fired evidence less
    # downstream actual). Duplicate historical firing rows are removed first.
    if previous_firing is not None and not previous_firing.empty:
        pf=previous_firing.copy()
        for c in ['Firing Date','Firing Complete']:
            if c in pf.columns: pf[c]=pf[c].apply(pdate)
        keys=[c for c in ['Work Order','Firing Date','Firing Complete','Kiln','Program','Firing Qty'] if c in pf.columns]
        if keys: pf=pf.drop_duplicates(keys)
        pf=pf[pf.get('Firing Complete',pd.Series(None,index=pf.index)).apply(lambda d: bool(d and d < start))]
        for wo,g in pf.groupby(pf['Work Order'].astype(str).str.strip(),sort=False):
            if wo not in pmap: continue
            prior=float(pd.to_numeric(g.get('Firing Qty',0),errors='coerce').fillna(0).sum())
            r=pmap[wo]
            down=max(num(r.get('Grinding / Cutting Actual')),num(r.get('Packing Actual')))
            evidence=max(prior-down,0.0)
            if evidence>post_ready.get(wo,0):
                post_ready[wo]=evidence
                issues.append({'Work Order':wo,'Section / กระบวนการ':'Post-firing','Qty':evidence,'Reason':'Previous ISSUED firing plan confirms fired quantity available before planning start; post-firing WIP bridged without double-counting Plan2026'})
    arrivals_mix={}; arrivals_form={}; arrivals_fire={}; arrivals_post={}; arrivals_pack={}

    # Firing input by date; exact uploaded schedule remains authoritative.
    fire_by_day={}
    if firing is not None and not firing.empty:
        ff=firing.copy()
        ff['Firing Date']=ff['Firing Date'].apply(pdate); ff['Firing Complete']=ff['Firing Complete'].apply(pdate)
        for _,fr in ff.iterrows():
            fd=fr.get('Firing Date')
            if fd: fire_by_day.setdefault(fd,[]).append(fr)

    # Fast product-code map for grinding/cutting master.
    grind_by_prod={}
    _grind_records=[]
    if grind is not None and not grind.empty:
        if 'ProductionCode' in grind.columns:
            for _,gr in grind.iterrows():
                pc=txt(gr.get('ProductionCode')).upper()
                if pc and pc not in grind_by_prod:grind_by_prod[pc]=gr
        # Precompute strings/tokens once. Scoring below is intentionally identical to
        # sl_daily_engine.grinding_match; this removes repeated DataFrame.iterrows scans
        # without changing the selection rule.
        for idx,gr in grind.iterrows():
            pat=txt(gr.get('Specification')).upper()
            if not pat: continue
            toks=[x for x in re.split(r'[^A-Z0-9]+',pat) if len(x)>=3]
            _grind_records.append((idx,pat,txt(gr.get('Type')).upper(),txt(gr.get('Shape')).upper(),toks))

    def _fast_grinding_match(r):
        pc=txt(r.get('Product Code')).upper()
        if pc in grind_by_prod: return grind_by_prod[pc],1200
        spec=(txt(r.get('Specification'))+' '+txt(r.get('Product Type'))).upper()
        typ=txt(r.get('Category')).upper(); shp=txt(r.get('Shape')).upper()
        best_idx=None; bs=0
        for idx,pat,rtyp,rshp,toks in _grind_records:
            if pat==spec: score=900
            elif pat in spec or spec in pat: score=500
            else: score=sum(1 for x in toks if x in spec)*10
            if rtyp==typ: score+=25
            if rshp==shp: score+=15
            if score>bs: best_idx=idx; bs=score
        return (grind.loc[best_idx],bs) if best_idx is not None else (None,0)

    for day in days:
        # Previous working-day outputs become available now.
        for wo,q in arrivals_mix.pop(day,{}).items(): mix_ready[wo]=mix_ready.get(wo,0)+q
        for wo,q in arrivals_form.pop(day,{}).items(): form_ready[wo]=form_ready.get(wo,0)+q
        for wo,q in arrivals_fire.pop(day,{}).items(): fire_ready[wo]=fire_ready.get(wo,0)+q
        for wo,q in arrivals_post.pop(day,{}).items(): post_ready[wo]=post_ready.get(wo,0)+q
        for wo,q in arrivals_pack.pop(day,{}).items(): pack_ready[wo]=pack_ready.get(wo,0)+q

        # ---------------- PREPARATION: existing unprepared demand starts on selected date ----------------
        free_kg=max(float(prep_kg)-used_prep.get(day,0),0)
        for wo in sorted([w for w,q in prep_need.items() if q>0],key=duekey):
            if free_kg<=1e-9: break
            r=pmap[wo]; kgpc=num(r.get('Net Weight g/pc'))/1000.0
            if kgpc<=0:
                issues.append({'Work Order':wo,'Section / กระบวนการ':'Preparation','Qty':prep_need[wo],'Reason':'Missing net weight g/pc; cannot convert Preparation kg/day to pcs'}); continue
            take=min(prep_need[wo],math.floor(free_kg/kgpc))
            if take<=0:continue
            prep_need[wo]-=take; kg=take*kgpc; free_kg-=kg; used_prep[day]=used_prep.get(day,0)+kg
            addrow(day,'Preparation',r,take,kgpc,float(prep_kg)/kgpc,float(prep_kg)/1000,'Preparation shared kg/day','Existing Plan2026 WIP Preparation at planning start / global due-date queue','','PREP:PLANT',{'Capacity kg/day':float(prep_kg),'Capacity Used kg':used_prep[day]})
            _lt=lt.applied_offsets(r); nd=next_workday(day,int(_lt['Preparation→Mixing WD'])); arrivals_mix.setdefault(nd,{})[wo]=arrivals_mix.setdefault(nd,{}).get(wo,0)+take

        # ---------------- MIXING: existing ready WIP + previous-day preparation ----------------
        for wo in sorted([w for w,q in mix_ready.items() if q>0],key=duekey):
            r=pmap[wo]; rem=mix_ready[wo]; kgpc=num(r.get('Net Weight g/pc'))/1000.0
            if kgpc<=0:continue
            mk=(txt(r.get('Category')).upper(),txt(r.get('Specification')).upper())
            cand=_mix_cache.get(mk)
            if cand is None: cand=mixing_candidates(mix,r); _mix_cache[mk]=cand
            if cand is None or cand.empty:
                issues.append({'Work Order':wo,'Section / กระบวนการ':'Mixing','Qty':rem,'Reason':'No active Mixing machine matches product family'}); continue
            made=0.0
            for _,m in cand.iterrows():
                if rem<=0:break
                mc=txt(m.get('Machine')); base=max(int(num(m.get('CAP-โม่'))),0); used=used_mix_batches.get((day,mc),0); free=max(base-used,0)
                if free<=0:continue
                mn=num(m.get('Min batch kg')); mx=num(m.get('Max batch kg')); best=None
                for b in range(1,free+1):
                    qmax=min(rem,math.floor((b*mx)/kgpc)); qmin=math.ceil((b*mn)/kgpc) if mn>0 else 1
                    if qmax>=qmin and qmax>0 and (best is None or qmax>best[0]):best=(qmax,b)
                if best is None:continue
                take,batches=best; rem-=take; made+=take; used_mix_batches[(day,mc)]=used+batches
                capkg=base*num(m.get('Machine kg'))
                addrow(day,'Mixing',r,take,kgpc,capkg/kgpc if kgpc else None,capkg/1000,'CAP ผสม: mixer + job/family + CAP-โม่ + batch range + abrasive','Existing/arrived Mixing WIP from Plan2026 flow','','MIX:'+mc,{'Machine':mc,'Mixing Job':m.get('Job',''),'Required Batches':batches,'CAP-โม่ Available':base,'CAP-โม่ Used':used_mix_batches[(day,mc)],'Abrasive Check':'PASS' if bool(m.get('Abrasive OK')) else 'VERIFY'})
            mix_ready[wo]=rem
            if made>0:
                _lt=lt.applied_offsets(r); nd=next_workday(day,int(_lt['Mixing→Forming WD'])); arrivals_form.setdefault(nd,{})[wo]=arrivals_form.setdefault(nd,{}).get(wo,0)+made

        # ---------------- FORMING: existing ready WIP + previous-day mixing ----------------
        for wo in sorted([w for w,q in form_ready.items() if q>0],key=duekey):
            r=pmap[wo]; rem=form_ready[wo]; kgpc=num(r.get('Net Weight g/pc'))/1000.0
            fk=(txt(r.get('Category')).upper(),txt(r.get('Specification')).upper(),round(num(r.get('D')),3),round(num(r.get('T')),3),round(num(r.get('H')),3))
            fm=_form_cache.get(fk)
            if fm is None: fm=forming_match(form,r); _form_cache[fk]=fm
            mr,score=fm; forced_mc=txt(r.get('Forced Forming Machine')); forced_cap=num(r.get('Forced Forming Capacity pcs/day'))
            if forced_mc and forced_cap>0: mr={'Normal pcs/8h':forced_cap,'Spec Pattern':'MANUAL VERIFIED OVERRIDE','Machine':forced_mc,'pcs/hour':forced_cap/8.0}; score=9999
            if mr is None:
                issues.append({'Work Order':wo,'Section / กระบวนการ':'Forming','Qty':rem,'Reason':'NO FORMING MACHINE/SIZE MATCH'}); continue
            cap=num(mr.get('Normal pcs/8h')); mold=txt(mr.get('Spec Pattern')).upper(); best=None
            if used_mold.get((day,mold),0)<1:
                for mc in de.machines(mr.get('Machine')):
                    av=max(cap-used_form.get((day,mc),0),0)
                    if best is None or av>best[0]:best=(av,mc)
            if not best or best[0]<=0:continue
            take=min(rem,math.floor(best[0])); mc=best[1]
            if take<=0:continue
            form_ready[wo]-=take; used_form[(day,mc)]=used_form.get((day,mc),0)+take; used_mold[(day,mold)]=1
            addrow(day,'Forming',r,take,kgpc,cap,cap*kgpc/1000,'CAP ขึ้นรูป: category + spec/size + machine + mold lock','Existing/arrived Forming WIP from Plan2026 flow','','FORM:'+mc,{'Machine':mc,'Eligible Machines':mr.get('Machine',''),'Master Spec Match':mr.get('Spec Pattern',''),'Match Score':score,'Capacity pcs/day':cap,'Machine Load After WO':used_form[(day,mc)]})
            _lt=lt.applied_offsets(r); nd=lt.forming_release_date(day,r); arrivals_fire.setdefault(nd,{})[wo]=arrivals_fire.setdefault(nd,{}).get(wo,0)+take

        # ---------------- FIRING: exact firing plan; verify upstream physical availability ----------------
        for fr in fire_by_day.get(day,[]):
            wo=normalize_wo(fr.get('Work Order'));r,_parts=resolve_wo(wo,pmap);_ab_parts=list(_parts)
            if r is None:
                _present=set(plan['Work Order'].astype(str))
                if _ab_parts and all(p in _present for p in _ab_parts):
                    _reason='Two-layer A/B WO exists in Plan2026; one or both layer rows are closed/not open for scheduling: '+', '.join(_ab_parts)
                elif _ab_parts:
                    _reason='Two-layer A/B WO requires both Plan2026 layer rows; missing: '+', '.join(p for p in _ab_parts if p not in _present)
                else:_reason='WO in Firing Plan not found in active Plan2026 rows'
                issues.append({'Work Order':wo,'Section / กระบวนการ':'Firing','Qty':num(fr.get('Firing Qty')),'Reason':_reason});continue
            q=num(fr.get('Firing Qty'))
            if _ab_parts:
                _avail=[float(fire_ready.get(_w,0)) for _w in _ab_parts]
                ready=min(_avail) if _avail else 0.0
            else: ready=fire_ready.get(wo,0)
            executable=min(q,ready)
            kgpc=num(fr.get('kg/pc'),num(r.get('Gross Weight g/pc'))/1000.0); fc=pdate(fr.get('Firing Complete')); anchor=f"{txt(fr.get('Kiln'))} {txt(fr.get('Program'))} {day}"
            maxkg=0; run_days=None
            if kiln is not None and not kiln.empty:
                rule=de.firing_program_rule(fr.get('Program'),fr.get('Kiln'),kiln)
                if rule is not None:maxkg=num(rule.get('Max kg/load'));run_days=num(rule.get('Running Days'))
            status=('PROVISIONAL - VERIFY DRYING RESOURCES' if lt.applied_offsets(r)['Curing/Oven Gate WD']>0 else 'RELEASE') if executable+1e-9>=q else 'HOLD - UPSTREAM / DRYING NOT READY'
            addrow(day,'Firing',r,q,kgpc,q,maxkg/1000 if maxkg else q*kgpc/1000,'Firing Planner + Cap เตา','Exact uploaded Firing Plan; checked against Plan2026/forming-ready WIP',anchor,'FIRE:'+anchor,{'Kiln':fr.get('Kiln',''),'Program':fr.get('Program',''),'Running Days':run_days,'Program Finish Date':fc,'Program Max kg':maxkg,'Executable Qty':executable,'Release Status':status})
            if executable<q:
                issues.append({'Work Order':wo,'Section / กระบวนการ':'Firing','Qty':q-executable,'Reason':f'Firing anchor {q:g} pcs but only {ready:g} pcs physically ready by {day}; DO NOT RELEASE shortage'})
            if _ab_parts:
                for _w in _ab_parts: fire_ready[_w]=max(float(fire_ready.get(_w,0))-executable,0)
            else: fire_ready[wo]=max(ready-executable,0)
            usable,_=apply_ncr(wo,r,'Firing',executable)
            if usable>0 and fc:
                if qc_required(r):
                    # QC duration is respected but QC is intentionally hidden from PPC section plans.
                    qcday=next_workday(fc)
                    usable2,_=apply_ncr(wo,r,'QC',usable); arr=next_workday(qcday)
                else: usable2=usable; arr=next_workday(fc)
                if usable2>0:
                    rt=route(r)
                    if rt.startswith('Direct Packing'): arrivals_pack.setdefault(arr,{})[wo]=arrivals_pack.setdefault(arr,{}).get(wo,0)+usable2
                    else: arrivals_post.setdefault(arr,{})[wo]=arrivals_post.setdefault(arr,{}).get(wo,0)+usable2

        # ---------------- POST-FIRING: existing WIP begins at selected start ----------------
        for wo in sorted([w for w,q in post_ready.items() if q>0],key=duekey):
            r=pmap[wo]; rem=post_ready[wo]; kgpc=num(r.get('Net Weight g/pc'))/1000.0; rt=route(r)
            stage='Cutting' if rt.startswith('Cutting') else ('Grinding' if rt.startswith('Grinding') else 'Cleaning')
            usable,held=apply_ncr(wo,r,stage,rem); post_ready[wo]-=held
            if usable<=0:continue
            if rt.startswith('Direct Packing'):
                post_ready[wo]-=usable; pack_ready[wo]=pack_ready.get(wo,0)+usable; continue
            if rt.startswith('Cleaning'):
                take=usable; post_ready[wo]-=take
                addrow(day,'Cleaning / ทำความสะอาด',r,take,kgpc,take,take*kgpc/1000,'Factory route timing step','Existing/arrived post-firing WIP', '', 'CLEAN:'+wo,{'Route':rt})
                nd=next_workday(day); arrivals_pack.setdefault(nd,{})[wo]=arrivals_pack.setdefault(nd,{}).get(wo,0)+take; continue
            gk=(txt(r.get('Product Code')).upper(),txt(r.get('Specification')).upper(),txt(r.get('Category')).upper(),txt(r.get('Shape')).upper())
            gm=_grind_cache.get(gk)
            if gm is None:
                pc=txt(r.get('Product Code')).upper(); gm=_fast_grinding_match(r); _grind_cache[gk]=gm
            gr,score=gm
            if gr is None:
                issues.append({'Work Order':wo,'Section / กระบวนการ':stage,'Qty':usable,'Reason':'No usable Grinding/Cutting master match'}); continue
            cap=max(num(gr.get('Bottleneck CAP/day')),0)
            if cap<=0:
                issues.append({'Work Order':wo,'Section / กระบวนการ':stage,'Qty':usable,'Reason':txt(gr.get('Route Status')) or 'Grinding route capacity unavailable'})
                continue
            machine=txt(gr.get('Bottleneck Machine')) or next((txt(gr.get(f'Op{i} Machine')) for i in range(1,7) if num(gr.get(f'Op{i} CAP/day'))==cap and txt(gr.get(f'Op{i} Machine'))),txt(gr.get('ProductionCode')) or 'UNRESOLVED')
            setup_hr=max(num(gr.get('Bottleneck Setup hr')),0); req_workers=max(int(num(gr.get('Bottleneck Workers'))),0); dept_people=max(int(num(gr.get('Grinding Dept Current People'))),0)
            active=active_post_machines.setdefault(day,set())
            if machine not in active and dept_people>0 and used_post_people.get(day,0)+req_workers>dept_people:
                issues.append({'Work Order':wo,'Section / กระบวนการ':stage,'Qty':usable,'Reason':f'Grinding manpower limit: need {req_workers} more worker(s), current department capacity {dept_people}'})
                continue
            key=(day,machine); frac=used_post_frac.get(key,0.0)
            setup_frac=(setup_hr/max(float(normal_hours),0.1))
            avail=max(1.0-frac-setup_frac,0.0)*cap; take=min(usable,math.floor(avail+1e-9))
            if take<=0:continue
            if machine not in active:
                active.add(machine); used_post_people[day]=used_post_people.get(day,0)+req_workers
            used_post_frac[key]=frac+setup_frac+take/cap; post_ready[wo]-=take
            sec='Cutting / ตัด' if rt.startswith('Cutting') else 'Grinding / เจียร'
            addrow(day,sec,r,take,kgpc,cap,cap*kgpc/1000,'Cap เจีย: product/spec operation + shared bottleneck machine','Existing Plan2026 post-firing WIP starts on Planning Start; new firing arrivals follow QC', '',f'{sec}:{machine}',{'Route':rt,'Machine Sequence':gr.get('Operations',''),'Bottleneck CAP/day':cap,'Bottleneck Machine':machine,'Match Score':score,'Shared Machine Utilization %':round(used_post_frac[key]*100,1)})
            nd=next_workday(day); arrivals_pack.setdefault(nd,{})[wo]=arrivals_pack.setdefault(nd,{}).get(wo,0)+take

        # ---------------- PACKING: existing ready WIP begins at selected start ----------------
        for wo in sorted([w for w,q in pack_ready.items() if q>0],key=duekey):
            r=pmap[wo]; rem=pack_ready[wo]; kgpc=num(r.get('Net Weight g/pc'))/1000.0
            usable,held=apply_ncr(wo,r,'Packing',rem); pack_ready[wo]-=held
            if usable<=0:continue
            pk=(txt(r.get('Category')).upper(),txt(r.get('Specification')).upper(),round(num(r.get('D')),3),round(num(r.get('T')),3),round(num(r.get('H')),3))
            pm=_pack_cache.get(pk)
            if pm is None: pm=packing_match(pack,r); _pack_cache[pk]=pm
            pr,score=pm
            if pr is None:
                issues.append({'Work Order':wo,'Section / กระบวนการ':'Packing','Qty':usable,'Reason':'No packing size/type master match'}); continue
            per=max(num(pr.get('Bottleneck pcs/day/person')),0); cap=per*max(int(packing_people),1)
            if cap<=0:continue
            frac=used_pack_frac.get(day,0.0); avail=max(1.0-frac,0.0)*cap; take=min(usable,math.floor(avail+1e-9))
            if take<=0:continue
            used_pack_frac[day]=frac+take/cap; pack_ready[wo]-=take
            addrow(day,'Packing',r,take,kgpc,cap,cap*kgpc/1000,'Cap บรรจุ: matched size/type bottleneck × shared manpower','Existing/arrived packing-ready WIP from Plan2026 flow','','PACK:SHARED',{'Capacity pcs/day':cap,'Capacity pcs/day/person':per,'Packing People':packing_people,'Master Spec Match':pr.get('Spec Pattern',''),'Master Type':pr.get('Type',''),'Packing Processes':pr.get('Processes',''),'Match Score':score,'Shared Packing Utilization %':round(used_pack_frac[day]*100,1)})

    # Any residual physical queues are explicit issues, not silently dropped.
    for sec,qmap in [('Preparation',prep_need),('Mixing',mix_ready),('Forming',form_ready),('Firing-ready WIP',fire_ready),('Post-firing',post_ready),('Packing',pack_ready)]:
        for wo,q in qmap.items():
            if q>1e-9:
                issues.append({'Work Order':wo,'Section / กระบวนการ':sec,'Qty':q,'Reason':f'{sec} WIP remains after horizon due to capacity/resource/route or no firing anchor'})

    allp=pd.DataFrame(rows)
    if not allp.empty: allp=allp.sort_values(['Plan Date','Section','Due Date','Work Order'],na_position='last',kind='stable').reset_index(drop=True)
    w=[]
    for wo in sorted(wip.keys()):
        r=pmap[wo]; z={'Work Order':wo,'Customer':r.get('Customer'),'Due Date':r.get('Due Date'),'Category':r.get('Category')}
        z.update(wip[wo]); z['Open ton']=float(sum(wip[wo].values()))*num(r.get('Net Weight g/pc'))/1e6
        w.append(z)
    return {'all':allp,'capacity_summary':pd.DataFrame(),'issues':pd.DataFrame(issues),'wip':pd.DataFrame(w)}
