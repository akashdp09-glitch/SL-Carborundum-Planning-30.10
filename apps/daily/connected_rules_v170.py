from datetime import date
import re
import pandas as pd

def _txt(v):
    return '' if v is None else str(v).strip()

def pair_key(wo):
    m = re.match(r'^(.*?)([AB])(-\d{6}.*)$', _txt(wo).upper())
    return m.group(1) + m.group(3) if m else ''


def _next_workday(d,n=1):
    from datetime import timedelta
    x=d
    for _ in range(max(int(n),0)):
        x += timedelta(days=1)
        while x.weekday()==6: x += timedelta(days=1)
    return x

def synchronize_ab_layers(allp):
    """Synchronize A/B at Forming without exceeding controlled daily capacity.
    Preparation/Mixing remain independently capacity-planned. If an A/B Forming
    pair is larger than one day, both layers are split proportionally across
    consecutive working days so the pair remains synchronized and no artificial
    300-400% load is created.
    """
    if allp is None or allp.empty:return allp,pd.DataFrame()
    x=allp.copy();x['_pair']=x['Work Order'].map(pair_key);audit=[]
    for pk,g0 in list(x[x['_pair'].ne('')].groupby('_pair')):
        members=sorted(set(g0['Work Order'].astype(str)))
        if len(members)<2:continue
        ix=x.index[(x['_pair']==pk)&x['Section'].eq('Forming')]
        if len(ix)<2:continue
        pair=x.loc[ix].copy();ds=pd.to_datetime(pair['Plan Date'],errors='coerce').dropna()
        if ds.empty:continue
        candidate=ds.max().date();old=sorted(set(d.date() for d in ds))
        # Only WOs that actually have Forming rows can be rebuilt here.
        # `members` above is collected from every section in the A/B group; a WO can
        # legitimately be absent from Forming, so using it directly caused `.iloc[0]`
        # on an empty dataframe (single positional indexer out-of-bounds).
        forming_members=sorted(set(pair['Work Order'].astype(str)))
        if len(forming_members)<2:
            continue
        totals=pair.groupby(pair['Work Order'].astype(str))['Plan Qty'].sum().astype(float).to_dict();pairqty=sum(totals.values())
        # Controlled pair resource capacity: use distinct resource capacity represented in the pair.
        caps=[]
        if 'Resource Key' in pair.columns and 'Capacity Qty pcs' in pair.columns:
            for _,rg in pair.groupby(pair['Resource Key'].fillna('').astype(str)):
                cv=pd.to_numeric(rg['Capacity Qty pcs'],errors='coerce').dropna()
                if not cv.empty:caps.append(float(cv.max()))
        capq=sum(caps)
        if capq<=0:
            x.loc[ix,'Plan Date']=candidate
            audit.append({'Pair Key':pk,'Section':'Forming','Work Orders':', '.join(members),'Original Dates':', '.join(map(str,old)),'Common Date':candidate,'Rule':'A/B synchronized; capacity master unavailable — VERIFY'})
            continue
        # Remove old pair forming rows and rebuild synchronized daily chunks.
        templates={}
        for wo in forming_members:
            rows=pair[pair['Work Order'].astype(str).eq(wo)]
            if not rows.empty:
                templates[wo]=rows.iloc[0].to_dict()
        if len(templates)<2:
            continue
        remain=totals.copy();newrows=[];day=candidate
        for _ in range(180):
            if sum(remain.values())<=1e-9:break
            # capacity already consumed by non-pair Forming rows on this day
            daymask=x['Section'].eq('Forming')&pd.to_datetime(x['Plan Date'],errors='coerce').dt.date.eq(day)&(x['_pair']!=pk)
            other=float(pd.to_numeric(x.loc[daymask].get('Plan Qty',0),errors='coerce').fillna(0).sum()) if daymask.any() else 0.0
            free=max(capq-other,0.0)
            if free<=1e-9:day=_next_workday(day,1);continue
            totalrem=sum(remain.values());alloc=min(free,totalrem)
            # proportional A/B allocation, with final member receiving rounding residue
            left=alloc
            active=[wo for wo in forming_members if remain.get(wo,0)>1e-9 and wo in templates]
            for j,wo in enumerate(active):
                q=min(remain[wo], left if j==len(active)-1 else alloc*(remain[wo]/totalrem))
                if q<=1e-9:continue
                r=templates[wo].copy();oldq=float(r.get('Plan Qty') or 0);r['Plan Date']=day;r['Plan Qty']=q;r['Plan Qty pcs']=q
                if oldq>0:
                    for kc in ['Plan kg','Plan ton']:
                        if kc in r and pd.notna(r[kc]):r[kc]=float(r[kc])*q/oldq
                r['Utilization %']=round(q/float(r.get('Capacity Qty pcs') or capq)*100,1) if float(r.get('Capacity Qty pcs') or capq)>0 else None
                newrows.append(r);remain[wo]-=q;left-=q
            day=_next_workday(day,1)
        x=x.drop(index=ix)
        if newrows:x=pd.concat([x,pd.DataFrame(newrows)],ignore_index=True,sort=False)
        last=max(pd.to_datetime([r['Plan Date'] for r in newrows]).date) if newrows else candidate
        audit.append({'Pair Key':pk,'Section':'Forming','Work Orders':', '.join(members),'Original Dates':', '.join(map(str,old)),'Common Date':f'{candidate} → {last}','Rule':f'A/B synchronized and capacity-split; controlled capacity {capq:.0f} pcs/day'})
    # Recheck firing against latest synchronized forming completion.
    for pk,g in x[x['_pair'].ne('')].groupby('_pair'):
        members=set(g['Work Order'].astype(str))
        if len(members)<2:continue
        for wo in members:
            fw=x[(x['Work Order'].astype(str)==wo)&x['Section'].eq('Forming')];fire=x[(x['Work Order'].astype(str)==wo)&x['Section'].eq('Firing')]
            if fw.empty or fire.empty:continue
            fdate=pd.to_datetime(fw['Plan Date'],errors='coerce').max()
            if pd.isna(fdate):continue
            off=pd.to_numeric(fw.get('Forming→Firing WD',pd.Series([1])),errors='coerce').fillna(1).max();ready=_next_workday(fdate.date(),int(off))
            for ix in fire.index:
                fd=pd.to_datetime(x.at[ix,'Plan Date'],errors='coerce')
                if pd.notna(fd) and fd.date()<ready:
                    x.at[ix,'Release Status']='HOLD - A/B PAIR NOT READY';x.at[ix,'Source / Reason']=str(x.at[ix,'Source / Reason'])+f' | A/B capacity-split forming earliest firing {ready}'
                    audit.append({'Pair Key':pk,'Section':'Firing Gate','Work Orders':', '.join(sorted(members)),'Original Dates':str(fd.date()),'Common Date':ready,'Rule':'HOLD: firing cannot precede final synchronized Forming output'})
    return x.drop(columns=['_pair']),pd.DataFrame(audit)

def ot_suggestion(allp, normal_hours=7.4):
    if allp is None or allp.empty:
        return pd.DataFrame()
    x = allp.copy()
    x['Capacity Qty pcs'] = pd.to_numeric(x.get('Capacity Qty pcs'), errors='coerce')
    x['Plan Qty'] = pd.to_numeric(x.get('Plan Qty'), errors='coerce').fillna(0)
    out = []
    for (d, s), g in x.groupby(['Plan Date', 'Section']):
        # Sum distinct resource capacities, not repeated WO-row capacities.
        if 'Resource Key' in g.columns:
            caps=[]
            for _,rg in g.groupby(g['Resource Key'].fillna('').astype(str)):
                cv=pd.to_numeric(rg['Capacity Qty pcs'],errors='coerce').dropna()
                if not cv.empty:caps.append(float(cv.max()))
            capq=sum(caps)
        else:
            cap=pd.to_numeric(g['Capacity Qty pcs'],errors='coerce').dropna();capq=float(cap.max()) if not cap.empty else 0
        plan = float(g['Plan Qty'].sum())
        util = (plan / capq * 100) if capq > 0 else None
        oth = max((plan / capq - 1) * normal_hours, 0) if capq > 0 else 0
        out.append({
            'Plan Date': d,
            'Section': s,
            'Normal Hours': normal_hours,
            'Plan Qty pcs': plan,
            'Indicative Normal Capacity pcs': capq,
            'Load %': util,
            'Suggested OT hours': round(oth, 2),
            'OT Action': 'SUGGEST OT / CAPACITY RECOVERY' if oth > 0 else 'NORMAL DAY'
        })
    return pd.DataFrame(out)
