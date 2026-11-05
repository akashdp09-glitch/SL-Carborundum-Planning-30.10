from __future__ import annotations
from datetime import timedelta,date
import math
import pandas as pd
import sl_daily_engine_v3_22_from_v17 as de
import daily_linear_engine_v1_1 as oldeng
import sl_ppc_fast_store_v4_6 as store
import tempfile,os
import lead_time_control_v1 as lt
import connected_rules_v170 as cr

CATEGORY_ORDER=['P','R','PB','S','T','M','UNCLASSIFIED']

def txt(v):
    if v is None or (isinstance(v,float) and math.isnan(v)): return ''
    return str(v).strip()

def num(v,d=0.0):
    try:
        x=float(v)
        return d if math.isnan(x) or math.isinf(x) else x
    except: return d

def normcat(v):
    s=txt(v).upper()
    if s.startswith('PB'): return 'PB'
    if s.startswith('R'): return 'R'
    if s.startswith('S'): return 'S'
    if s.startswith('T'): return 'T'
    if s.startswith('M'): return 'M'
    if s.startswith('P'): return 'P'
    return 'UNCLASSIFIED'

def _section_capacity_ton(sec,g):
    """Capacity ton from the same physical resource evidence used to schedule the rows."""
    if g is None or g.empty: return 0.0,''
    plankg=float(pd.to_numeric(g.get('Plan kg',0),errors='coerce').fillna(0).sum())
    if sec=='Preparation':
        vals=pd.to_numeric(g.get('Capacity kg/day',pd.Series(dtype=float)),errors='coerce').dropna()
        capkg=float(vals.max()) if len(vals) else 0.0
        return capkg/1000.0,'Preparation plant kg/day limit'
    if sec=='Mixing':
        capkg=0.0; parts=[]
        if 'Machine' in g.columns:
            for mc,mg in g.groupby('Machine'):
                batches=pd.to_numeric(mg.get('CAP-โม่ Available',pd.Series(dtype=float)),errors='coerce').dropna()
                machinekg=pd.to_numeric(mg.get('Machine kg Master',pd.Series(dtype=float)),errors='coerce').dropna()
                if len(batches) and len(machinekg):
                    kg=float(batches.max()*machinekg.max());capkg+=kg;parts.append(f'{mc}:{kg:.0f}kg/d')
        return capkg/1000.0,('Mixer capacity '+'; '.join(parts)) if parts else 'Mixer capacity not matched'
    if sec=='Forming':
        capkg=0.0; parts=[]
        if 'Machine' in g.columns:
            for mc,mg in g.groupby('Machine'):
                cap=pd.to_numeric(mg.get('Capacity pcs/day',pd.Series(dtype=float)),errors='coerce').dropna()
                kgpc=pd.to_numeric(mg.get('Plan kg',0),errors='coerce').fillna(0).sum()/max(pd.to_numeric(mg.get('Plan Qty',0),errors='coerce').fillna(0).sum(),1)
                if len(cap):
                    kt=float(cap.max()*kgpc);capkg+=kt;parts.append(f'{mc}:{cap.max():.0f}pcs/d')
        return capkg/1000.0,('Forming machine capacity '+'; '.join(parts)) if parts else 'Forming machine not matched'
    if sec=='Firing':
        # released firing load capacity is weight/program specific
        # Sum capacity of distinct kiln starts. Multiple WO rows can belong to one kiln load,
        # so never sum Program Max kg row-by-row.
        if 'Firing Anchor' in g.columns:
            loads=g.drop_duplicates(subset=['Firing Anchor']).copy()
        else:
            loads=g.copy()
        mx=pd.to_numeric(loads.get('Program Max kg',pd.Series(dtype=float)),errors='coerce').fillna(0)
        if (mx>0).any(): return float(mx.sum())/1000.0,f'{int((mx>0).sum())} distinct kiln load(s), program max kg/load'
        return plankg/1000.0,'Released kiln load / physical firing plan'
    if sec in ['Grinding / เจียร','Cutting / ตัด','Grinding/Cutting / เจียร-ตัด']:
        # operation sequence: use bottleneck CAP/day converted by product mix weight
        capkg=0.0;parts=[]
        if 'Bottleneck Machine' in g.columns:
            for mc,mg in g.groupby('Bottleneck Machine'):
                caps=pd.to_numeric(mg.get('Bottleneck CAP/day',pd.Series(dtype=float)),errors='coerce').dropna()
                if not len(caps): caps=pd.to_numeric(mg.get('Capacity pcs/day',pd.Series(dtype=float)),errors='coerce').dropna()
                q=pd.to_numeric(mg.get('Plan Qty',0),errors='coerce').fillna(0).sum();kg=pd.to_numeric(mg.get('Plan kg',0),errors='coerce').fillna(0).sum();kgpc=kg/max(q,1)
                if len(caps): capkg+=float(caps.max()*kgpc);parts.append(f'{mc}:{caps.max():.0f}pcs/d')
        if capkg<=0:
            cap=pd.to_numeric(g.get('Capacity pcs/day',pd.Series(dtype=float)),errors='coerce').dropna();q=pd.to_numeric(g.get('Plan Qty',0),errors='coerce').fillna(0).sum();kg=pd.to_numeric(g.get('Plan kg',0),errors='coerce').fillna(0).sum();kgpc=kg/max(q,1)
            if len(cap):capkg=float(cap.max()*kgpc)
        label='Grinding' if sec.startswith('Grinding') else 'Cutting'
        return capkg/1000.0,(label+' bottleneck '+'; '.join(parts)) if parts else (label+' matched bottleneck')
    if sec=='QC / ตรวจสอบคุณภาพ':
        return 0.0,'Mandatory timing gate: one working day after kiln; QC physical capacity master not supplied'
    if sec=='Cleaning / ทำความสะอาด':
        return 0.0,'Factory route timing step; separate cleaning capacity master not supplied'
    if sec=='Packing':
        cap=pd.to_numeric(g.get('Capacity pcs/day',pd.Series(dtype=float)),errors='coerce').dropna()
        if not len(cap): cap=pd.to_numeric(g.get('Capacity pcs/day/person',pd.Series(dtype=float)),errors='coerce').dropna()
        q=pd.to_numeric(g.get('Plan Qty',0),errors='coerce').fillna(0).sum();kg=pd.to_numeric(g.get('Plan kg',0),errors='coerce').fillna(0).sum();kgpc=kg/max(q,1)
        c=float(cap.max()) if len(cap) else 0.0
        return c*kgpc/1000.0,'Packing matched size/type bottleneck × manpower'
    return 0.0,''

def capacity_summary(plans, issues):
    rows=[]
    issues=issues if issues is not None else pd.DataFrame()
    for sec,df in plans.items():
        if df is None or df.empty: continue
        for day,g in df.groupby('Plan Date'):
            plankg=float(pd.to_numeric(g.get('Plan kg',0),errors='coerce').fillna(0).sum())
            planpcs=float(pd.to_numeric(g.get('Plan Qty',0),errors='coerce').fillna(0).sum())
            capton,basis=_section_capacity_ton(sec,g)
            util=(plankg/1000.0/capton*100) if capton>0 else None
            reason='Within matched capacity'
            if sec=='QC / ตรวจสอบคุณภาพ':
                reason='Mandatory one-working-day QC timing gate after kiln; no separate QC rated-capacity master is assumed'
            elif sec=='Cleaning / ทำความสะอาด':
                reason='Factory route timing step; no separate cleaning rated-capacity master is assumed'
            elif capton<=0: reason='Capacity/resource could not be matched — verify master'
            elif util is not None and util>100.01: reason='OVERLOAD — planned demand exceeds matched capacity'
            elif util is not None and util<60: reason='Available capacity remains; may be due to WIP, material, sequence or firing requirement'
            # append relevant issue reasons for that section
            if not issues.empty and 'Section / กระบวนการ' in issues.columns:
                ii=issues[issues['Section / กระบวนการ'].astype(str).eq(sec)]
                if not ii.empty and 'Reason' in ii.columns:
                    rr=' | '.join(ii['Reason'].dropna().astype(str).drop_duplicates().head(3).tolist())
                    if rr: reason=reason+'; '+rr
            _mo=float(pd.to_numeric(g.get('Required Batches',pd.Series(dtype=float)),errors='coerce').fillna(0).sum()) if sec=='Mixing' else None
            _mocap=float(pd.to_numeric(g.get('CAP-โม่ Available',pd.Series(dtype=float)),errors='coerce').dropna().groupby(g.loc[pd.to_numeric(g.get('CAP-โม่ Available',pd.Series(dtype=float)),errors='coerce').notna(),'Machine'] if 'Machine' in g.columns else lambda x:0).max().sum()) if sec=='Mixing' and 'CAP-โม่ Available' in g.columns and 'Machine' in g.columns else None
            rows.append({'Plan Date':day,'Section':sec,'Plan pcs':planpcs,'Plan ton':plankg/1000.0,
                         'Capacity ton':capton,'Mixing Plan MO':_mo,'Mixing Capacity MO':_mocap,
                         'Utilization %':round(util,1) if util is not None else None,
                         'Gap ton':round(capton-plankg/1000.0,4) if capton>0 else None,
                         'Suggested Action':('SUGGEST OVERTIME / CAPACITY RECOVERY' if util is not None and util>100.01 else 'NORMAL CAPACITY'),
                         'Capacity Basis':basis,'Reason / Limiting Factor':reason,
                         'Capacity Type':('Timing gate / no invented rated capacity' if sec in ['Cleaning / ทำความสะอาด'] else 'Matched physical/rated resource capacity'),
                         'Plan Type':'Executable scheduled quantity'})
    out=pd.DataFrame(rows)
    if not out.empty: out=out.sort_values(['Plan Date','Section']).reset_index(drop=True)
    return out

def issue_management(issues):
    """Consolidate raw issue rows by WO so repeated partial rows do not look like separate orders."""
    if issues is None or issues.empty:
        return pd.DataFrame(columns=['Work Order','Sections','Affected Qty','Issue Rows','Reason Group','Reasons','Suggested Action'])
    x=issues.copy()
    if 'Qty' not in x.columns:x['Qty']=0
    x['Qty']=pd.to_numeric(x['Qty'],errors='coerce').fillna(0)
    def grp(v):
        t=str(v).lower()
        if 'forming' in t and ('capacity' in t or 'spec' in t or 'size' in t):return 'FORMING MACHINE / SIZE MATCH'
        if 'mixer' in t or 'batch' in t or 'abrasive' in t:return 'MIXER / MATERIAL FAMILY MATCH'
        if 'grinding' in t:return 'GRINDING MATCH'
        if 'cutting' in t:return 'CUTTING MATCH'
        if 'ncr' in t:return 'NCR HOLD / DISPOSITION'
        if 'packing' in t:return 'PACKING CAPACITY / SIZE MATCH'
        if 'preparation' in t:return 'PREPARATION CAPACITY'
        if 'not found' in t:return 'WO / DATA MATCH'
        return 'OTHER / VERIFY'
    x['Reason Group']=x['Reason'].apply(grp)
    rows=[]
    for wo,g in x.groupby('Work Order',dropna=False):
        groups=' | '.join(g['Reason Group'].drop_duplicates().astype(str))
        reasons=' | '.join(g['Reason'].dropna().astype(str).drop_duplicates().head(6))
        secs=' / '.join(g.get('Section / กระบวนการ',pd.Series(dtype=str)).dropna().astype(str).drop_duplicates())
        action='Check/edit Category, Specification, D/T/H or Product Code; if data is correct, adjust firing date so upstream capacity has enough time.'
        if 'MIXER' in groups: action='Check/edit Category, Specification/material family; verify mixer compatibility in Capacity Database.'
        elif 'GRINDING' in groups or 'CUTTING' in groups: action='Check/edit Product Code, Specification, D/T/H and WO route; verify matched post-firing resource.'
        elif 'NCR' in groups: action='Review NCR quantity/stage/disposition. Clear or change disposition only from verified QC/Production information.'
        elif 'PACKING' in groups: action='Check/edit Category, Specification, D/T/H or increase available packing manpower.'
        elif 'PREPARATION' in groups: action='Increase/edit Preparation kg/day only if real capacity supports it, or move firing later.'
        rows.append({'Work Order':wo,'Sections':secs,'Affected Qty':float(g['Qty'].sum()),'Issue Rows':len(g),'Reason Group':groups,'Reasons':reasons,'Suggested Action':action})
    return pd.DataFrame(rows).sort_values(['Affected Qty','Work Order'],ascending=[False,True],kind='stable').reset_index(drop=True)

def combine_plans(plans):
    frames=[]
    for sec,df in plans.items():
        if df is None or df.empty: continue
        x=df.copy(); x['Section']=sec
        if 'Section / กระบวนการ' not in x.columns:x['Section / กระบวนการ']=sec
        if 'Plan ton' not in x.columns:x['Plan ton']=pd.to_numeric(x.get('Plan kg',0),errors='coerce').fillna(0)/1000.0
        frames.append(x)
    if not frames:return pd.DataFrame()
    allp=pd.concat(frames,ignore_index=True,sort=False)
    sortcols=[c for c in ['Plan Date','Section','Priority','Work Order'] if c in allp.columns]
    return allp.sort_values(sortcols,na_position='last',kind='stable').reset_index(drop=True)

def _delivery_risk(plan,plans,issues=None,safe_buffer_workdays=2):
    """WO-level delivery risk plus conservative Sales due-date recommendation.

    Safe-date rule:
      * Use the latest planned Packing completion for the WO.
      * Require the full remaining open quantity to be covered by the visible Packing schedule.
      * Add configurable working-day protection buffer (default 2 days because <=1 day is already MEDIUM risk).
      * If the schedule cannot cover the WO or a blocking capacity/route issue remains, do not invent a date.
    """
    rows=[]
    issues = issues if isinstance(issues,pd.DataFrame) else pd.DataFrame()
    plan_frames=[]
    for sec,df in plans.items():
        if isinstance(df,pd.DataFrame) and not df.empty:
            x=df.copy(); x['_sec']=sec; plan_frames.append(x)
    ap=pd.concat(plan_frames,ignore_index=True,sort=False) if plan_frames else pd.DataFrame()
    pack=plans.get('Packing',pd.DataFrame()) if isinstance(plans,dict) else pd.DataFrame()
    for wo,g in plan.groupby(plan['Work Order'].astype(str).str.strip(),sort=False):
        if not wo: continue
        r=g.sort_values('Due Date',na_position='last').iloc[0]
        if bool(g.get('Overall Closed',pd.Series(False,index=g.index)).fillna(False).all()): continue
        due=oldeng.pdate(r.get('Due Date'))
        oq=float(pd.to_numeric(g.get('Order Qty',0),errors='coerce').fillna(0).sum())
        w={k:float(pd.to_numeric(g.get(k,0),errors='coerce').fillna(0).sum()) for k in ['WIP Preparation','WIP Mixing','WIP Forming','WIP Firing','WIP Grinding / Cutting','WIP Packing']}
        active=[(k.replace('WIP ',''),v) for k,v in w.items() if v>1e-9]
        current=', '.join(f'{a}: {v:,.0f}' for a,v in active) if active else 'No positive stage WIP / check status'
        bottleneck=max(active,key=lambda z:z[1])[0] if active else 'DATA / STATUS CHECK'
        xp=ap[ap.get('Work Order',pd.Series(dtype=str)).astype(str).eq(wo)] if not ap.empty and 'Work Order' in ap.columns else pd.DataFrame()
        finish=None
        if not xp.empty and 'Plan Date' in xp.columns:
            ds=pd.to_datetime(xp['Plan Date'],errors='coerce').dropna(); finish=ds.max().date() if not ds.empty else None
        packed=float(pd.to_numeric(g.get('Packing Actual',g.get('Packing Actual Qty',0)),errors='coerce').fillna(0).max()) if len(g) else 0
        openqty=max(oq-packed,0)

        pw=pack[pack.get('Work Order',pd.Series(dtype=str)).astype(str).eq(wo)].copy() if isinstance(pack,pd.DataFrame) and not pack.empty and 'Work Order' in pack.columns else pd.DataFrame()
        planned_pack=float(pd.to_numeric(pw.get('Plan Qty',0),errors='coerce').fillna(0).sum()) if not pw.empty else 0.0
        pack_finish=None
        if not pw.empty and 'Plan Date' in pw.columns:
            pds=pd.to_datetime(pw['Plan Date'],errors='coerce').dropna(); pack_finish=pds.max().date() if not pds.empty else None
        coverage=100.0 if openqty<=1e-9 else min(planned_pack/openqty*100.0,100.0)

        iw=issues[issues.get('Work Order',pd.Series(dtype=str)).astype(str).eq(wo)].copy() if not issues.empty and 'Work Order' in issues.columns else pd.DataFrame()
        blocking=' | '.join(iw.get('Reason',pd.Series(dtype=str)).dropna().astype(str).drop_duplicates().head(3).tolist()) if not iw.empty else ''

        safe_date=None; extension_days=None; sales_action='KEEP CURRENT REVISED DUE DATE'; safe_basis='Current schedule protects due date'; safe_conf='HIGH'
        fully_covered = openqty<=1e-9 or (planned_pack+1e-9>=openqty and pack_finish is not None)
        if fully_covered:
            basis_finish=pack_finish or finish
            if basis_finish:
                safe_date=oldeng.next_workday(basis_finish,max(int(safe_buffer_workdays),0)) if int(safe_buffer_workdays)>0 else basis_finish
                if due:
                    extension_days=(safe_date-due).days
                    if safe_date>due:
                        sales_action='REQUEST SALES TO REVISE DUE DATE'
                        safe_basis=f'Packing completes {basis_finish}; +{int(safe_buffer_workdays)} working-day protection buffer'
                    else:
                        sales_action='KEEP CURRENT REVISED DUE DATE'
                        safe_basis=f'Current due date is protected by scheduled Packing completion {basis_finish}'
                else:
                    sales_action='REQUEST SALES TO SET REVISED DUE DATE'
                    safe_basis=f'Packing completes {basis_finish}; +{int(safe_buffer_workdays)} working-day protection buffer'
            else:
                safe_conf='LOW'; sales_action='DATE NOT SAFE TO COMMIT'; safe_basis='No scheduled final completion date found'
        else:
            safe_conf='NOT COMMITTABLE'; sales_action='DATE NOT SAFE TO COMMIT'
            safe_basis=f'Visible Packing schedule covers {planned_pack:,.0f}/{openqty:,.0f} open pcs ({coverage:.1f}%)'
            if blocking: safe_basis += ' | Blocking issue: '+blocking

        risk='LOW'; reasons=[]
        if due is None: risk='MEDIUM'; reasons.append('Revised Due Date missing')
        elif due < date.today() and openqty>0: risk='HIGH'; reasons.append(f'BACK ORDER: due {due} with {openqty:,.0f} pcs still open')
        if due and finish and finish>due: risk='HIGH'; reasons.append(f'Latest planned process finishes {finish}, after due date')
        elif due and finish and 0 <= (due-finish).days <= 1 and risk!='HIGH': risk='MEDIUM'; reasons.append('Delivery buffer is <= 1 day')
        if not fully_covered and openqty>0:
            risk='HIGH'; reasons.append(f'Packing schedule covers only {planned_pack:,.0f}/{openqty:,.0f} open pcs')
        if active: reasons.append('Current stage WIP: '+current)
        if blocking: reasons.append('Blocking issue: '+blocking)
        if not reasons: reasons=['Open order currently covered within visible plan horizon']
        _sales_req = 'YES' if sales_action.startswith('REQUEST SALES') else ('HOLD - NOT COMMITTABLE' if sales_action=='DATE NOT SAFE TO COMMIT' else 'NO')
        rows.append({'Work Order':wo,'Customer':r.get('Customer',''),'Category':r.get('Category',''),'Due Date':due,'Full Order Qty':oq,'Packed Actual Qty':packed,'Open Qty':openqty,'Current Status / WIP':current,'Bottleneck Process':bottleneck,'Projected Finish':finish,
                     'Planned Packing Qty':planned_pack,'Packing Completion':pack_finish,'Schedule Coverage %':round(coverage,1),
                     'Suggested Safe Due Date':safe_date,'Extension vs Current Due (calendar days)':extension_days,
                     'Sales New Due Date Requested':_sales_req,'Requested New Due Date':safe_date if _sales_req=='YES' else None,
                     'Sales Due-Date Action':sales_action,'Safe Due-Date Basis':safe_basis,'Safe-Date Confidence':safe_conf,
                     'Delivery Risk':risk,'Detailed Reason':' | '.join(reasons)})
    out=pd.DataFrame(rows)
    if not out.empty:
        rank={'HIGH':0,'MEDIUM':1,'LOW':2}; out['_r']=out['Delivery Risk'].map(rank).fillna(9); out=out.sort_values(['_r','Due Date','Work Order'],na_position='last').drop(columns='_r')
    return out

def build_detailed(plan_path,firing_path,cap_path,start,horizon,prep_kg=1200.0,packing_people=1,mix_ot=0.0,form_ot=0.0,mapping=None,firing_override=None,plan_overrides=None,previous_firing=None,normal_hours=7.4,safe_buffer_workdays=2):
    fd,tmp=tempfile.mkstemp(prefix='sl_ppc_daily_',suffix='.db');os.close(fd)
    try:
        store.full_sync(plan_path,tmp,mapping=mapping);plan=store.load(tmp)
        # User corrections are planning-layer overrides only; source Plan 2026 is never overwritten.
        if isinstance(plan_overrides, pd.DataFrame) and not plan_overrides.empty and 'Work Order' in plan_overrides.columns:
            for _, ov in plan_overrides.iterrows():
                wo=txt(ov.get('Work Order'))
                if not wo: continue
                mask=plan['Work Order'].astype(str).str.strip().eq(wo)
                if not mask.any(): continue
                for fld in ['Due Date','Order Qty','Overall Closed','Category','Specification','Product Code','Shape','D','T','H','Net Weight g/pc','Gross Weight g/pc','Forced Forming Machine','Forced Forming Capacity pcs/day','Lead Time Profile','Post-Firing Route','QC Required','NCR Qty','NCR Stage','NCR Disposition','Route Note']:
                    if fld in ov.index and pd.notna(ov.get(fld)) and str(ov.get(fld)).strip()!='':
                        plan.loc[mask,fld]=ov.get(fld)
    finally:
        try:os.remove(tmp)
        except:pass
    firing=firing_override.copy() if isinstance(firing_override,pd.DataFrame) else oldeng.load_firing_excel(firing_path)
    with open(cap_path,'rb') as f:
        mix,form,kiln,grind,pack,evidence=de.read_capacity(f)
    from suite.lead_time_source import attach as _active_lead_times
    from suite.drying_confirmations import apply as _dry_confirmations
    from suite.central_paths import db_path as _shared_db_path
    plan=_dry_confirmations(_active_lead_times(plan,cap_path),_shared_db_path())
    core=oldeng.build_daily(plan,firing,mix,form,kiln,grind,pack,start,int(horizon),float(prep_kg),int(packing_people),previous_firing=previous_firing,normal_hours=float(normal_hours))
    allp=core['all']; allp,pair_audit=cr.synchronize_ab_layers(allp); core['all']=allp; ot=cr.ot_suggestion(allp,normal_hours); plans={}
    # Keep confirmed post-firing routes separate end-to-end. Do not merge
    # Grinding and Cutting at the integration boundary; the UI/capacity layer
    # must see the actual process that the core scheduler created.
    for sec in ['Preparation','Mixing','Forming','Firing','Grinding / เจียร','Cutting / ตัด','Packing']:
        plans[sec]=allp[allp['Section'].eq(sec)].copy() if not allp.empty else pd.DataFrame()
    issues=core['issues'];caps=capacity_summary(plans,issues);risk=_delivery_risk(plan,plans,issues=issues,safe_buffer_workdays=safe_buffer_workdays)
    # Controlled firing duration audit. Daily Planner never shortens an issued firing plan;
    # Cap เตา is the controlled source when its program running days are greater/more specific.
    lt_cap=pd.DataFrame()
    if kiln is not None and not kiln.empty:
        cols=[c for c in ['Program','Running Days','Min kg','Max kg'] if c in kiln.columns]
        lt_cap=kiln[cols].copy() if cols else pd.DataFrame()
        if not lt_cap.empty:
            lt_cap['Rule Used']='Issued Firing Plan + Cap เตา; never shorter than controlled kiln/program duration'
    return {'plan_source':plan,'master':plan,'plans':plans,'all':allp,'issues':issues,'capacity_summary':caps,'delivery_risk':risk,'capacity_evidence':evidence,'lead_time_master':lt.master_table(cap_path),'lead_time_applied':lt.applied_table(plan),'lead_time_capacity':lt_cap,
            'firing_source':firing,'capacity_raw':{'Mixing':mix,'Forming':form,'Kiln':kiln,'Grinding':grind,'Packing':pack},'actual_rows':pd.DataFrame(),'order_events':pd.DataFrame(),'ab_pair_audit':pair_audit,'ot_suggestion':ot,'normal_hours':normal_hours}

def wip_category(wip):
    if wip is None or wip.empty:return pd.DataFrame()
    x=wip.copy();x['Product Category']=x['Category'].apply(normcat)
    wcols=['WIP Preparation','WIP Mixing','WIP Forming','WIP Firing','WIP Grinding / Cutting','WIP Packing']
    for c in wcols:
        if c not in x.columns:x[c]=0.0
        x[c]=pd.to_numeric(x[c],errors='coerce').fillna(0)
    out=x.groupby('Product Category',as_index=False)[wcols].sum()
    order={k:i for i,k in enumerate(CATEGORY_ORDER)};out['_o']=out['Product Category'].map(order).fillna(99);out=out.sort_values('_o').drop(columns='_o')
    return out

def wip_category_ton(wip):
    if wip is None or wip.empty:return pd.DataFrame()
    x=wip.copy();x['Product Category']=x['Category'].apply(normcat)
    kgpc=pd.to_numeric(x.get('Net Weight g/pc',0),errors='coerce').fillna(0)/1000.0
    cols=[]
    for c in ['WIP Preparation','WIP Mixing','WIP Forming','WIP Firing','WIP Grinding / Cutting','WIP Packing']:
        tc=c+' ton';x[tc]=pd.to_numeric(x.get(c,0),errors='coerce').fillna(0)*kgpc/1000.0;cols.append(tc)
    out=x.groupby('Product Category',as_index=False)[cols].sum()
    order={k:i for i,k in enumerate(CATEGORY_ORDER)};out['_o']=out['Product Category'].map(order).fillna(99);return out.sort_values('_o').drop(columns='_o')

def classify_source(row):
    # Confirmed purchasing rule: RENWA and ART are imported; all other materials are domestic.
    import re
    s=' '.join(txt(row.get(c,'')) for c in ['Material','Description','Material Group','Type']).upper()
    if 'RENWA' in s or re.search(r'(^|[^A-Z0-9])ART([^A-Z0-9]|$)',s): return 'IMPORT'
    return 'DOMESTIC'

def make_material_policy(stock,bom,import_days=45,domestic_days=20):
    mats=sorted(set(stock['Material'].astype(str).tolist() if stock is not None and not stock.empty else []) | set(bom['Material'].astype(str).tolist() if bom is not None and not bom.empty else []))
    smap={txt(r['Material']):r for _,r in stock.iterrows()} if stock is not None and not stock.empty else {}
    rows=[]
    for m in mats:
        sr=smap.get(m,{})
        src=classify_source(sr)
        lead=int(import_days if src=='IMPORT' else domestic_days)
        rows.append({'Material':m,'Source Type':src,'Supplier':'','Lead Time days':lead,'Safety Stock t':0.0,'MOQ t':0.0,'Order Multiple t':0.0,'Price per kg':None,
                     'Policy Note':'RENWA/ART = IMPORT (45d); all other materials = DOMESTIC (20d)'})
    return pd.DataFrame(rows)

def apply_material_check(result,bom,stock):
    """Attach stock/BOM feasibility to Preparation and Mixing plan rows. Target plan remains visible; shortage becomes HOLD and quantified."""
    if bom is None or bom.empty or stock is None or stock.empty:
        for sec in ['Preparation','Mixing']:
            if sec in result['plans'] and result['plans'][sec] is not None and not result['plans'][sec].empty:
                d=result['plans'][sec].copy();d['Material Status']='UNVERIFIED - STOCK/BOM MISSING';d['Material Feasible Qty']=None;d['Material Shortage']='';result['plans'][sec]=d
        result['all']=combine_plans(result['plans']);return result
    master=result['master'];itemmap={txt(r['Work Order']):txt(r['Product Code']) for _,r in master.iterrows()}
    bgrp={k:g.copy() for k,g in bom.groupby('Item')}
    stock_g={txt(r['Material']):max(num(r.get('On Hand g'),0),0) for _,r in stock.iterrows()}
    # reserve material once on Preparation. Mixing inherits the WO feasibility; existing prepared WIP is not double-consumed.
    wo_status={}
    prep=result['plans'].get('Preparation',pd.DataFrame()).copy()
    if not prep.empty:
        sortcols=[c for c in ['Plan Date','Priority','Work Order'] if c in prep.columns];prep=prep.sort_values(sortcols,kind='stable')
        stat=[];feas=[];shorts=[];reqtxt=[]
        for _,r in prep.iterrows():
            wo=txt(r.get('Work Order'));item=itemmap.get(wo,'');q=num(r.get('Plan Qty'));bg=bgrp.get(item)
            if bg is None or bg.empty:
                stat.append('VERIFY - BOM MISSING');feas.append(q);shorts.append('BOM missing');reqtxt.append('');wo_status[wo]=('VERIFY - BOM MISSING',q,'BOM missing');continue
            maxq=q; reqs=[]; sh=[]
            for _,b in bg.iterrows():
                mat=txt(b['Material']);gpc=num(b.get('g per pc'));need=q*gpc;avail=stock_g.get(mat,0.0);reqs.append(f'{mat}:{need/1000:.1f}kg need/{avail/1000:.1f}kg avail')
                if gpc>0:maxq=min(maxq,avail/gpc)
            fq=max(math.floor(maxq),0); status='PASS' if fq>=q-1e-9 else 'HOLD - MATERIAL SHORTAGE'
            # reserve only feasible qty so later WOs see reduced stock
            for _,b in bg.iterrows():
                mat=txt(b['Material']);gpc=num(b.get('g per pc'));consume=fq*gpc;stock_g[mat]=max(stock_g.get(mat,0)-consume,0)
                if fq<q: sh.append(f'{mat} shortage {(q-fq)*gpc/1000:.1f}kg')
            shortage='; '.join(sh)
            stat.append(status);feas.append(fq);shorts.append(shortage);reqtxt.append(' | '.join(reqs));wo_status[wo]=(status,fq,shortage)
        prep['Material Status']=stat;prep['Material Feasible Qty']=feas;prep['Material Shortage']=shorts;prep['Material Requirement / Stock']=reqtxt
        if 'Release Status' in prep.columns:prep.loc[prep['Material Status'].str.startswith('HOLD'),'Release Status']='HOLD / MATERIAL SHORTAGE'
        result['plans']['Preparation']=prep
    mix=result['plans'].get('Mixing',pd.DataFrame()).copy()
    if not mix.empty:
        sts=[];fqs=[];shs=[]
        for _,r in mix.iterrows():
            wo=txt(r.get('Work Order'));q=num(r.get('Plan Qty'));st,fq,sh=wo_status.get(wo,('PASS - EXISTING PREP/WIP',q,''));sts.append(st);fqs.append(min(q,fq) if fq is not None else q);shs.append(sh)
        mix['Material Status']=sts;mix['Material Feasible Qty']=fqs;mix['Material Shortage']=shs
        if 'Release Status' in mix.columns:mix.loc[mix['Material Status'].str.startswith('HOLD'),'Release Status']='HOLD / MATERIAL SHORTAGE'
        result['plans']['Mixing']=mix
    result['all']=combine_plans(result['plans'])
    return result
