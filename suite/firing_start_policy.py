"""Keep already-formed lots distinct from future upstream lots of the same WO.

A whole-WO OPEN stage marker does not undo measured forming output. Planning
eligibility is separate from execution/drying approval; no quantities are added.
"""
import pandas as pd


def split_planning_lots(prepared,raw,planning_start):
    if prepared is None or prepared.empty:return prepared
    ready={};execution={}
    for _,r in raw.iterrows():
        wo=str(r['Work Order'])
        q=max(float(r.get('Current Planning WIP Qty',r.get('Candidate Ready Qty',0)) or 0),0)
        e=max(float(r.get('Current Shop-floor Release Qty',0) or 0),0)
        ready[wo]=max(ready.get(wo,0),q);execution[wo]=max(execution.get(wo,0),e)
    rows=[]
    for _,r in prepared.iterrows():
        wo=str(r['Work Order']);total=max(float(r.get('Effective Qty',0) or 0),0)
        current=min(total,ready.get(wo,0))
        if not bool(r.get('Include',False)):current=0
        if current>0:
            lot=r.copy();lot['Effective Qty']=current
            lot['Verified Ready for Firing Qty']=current # legacy geometry input: verified FORMED quantity, not drying approval
            lot['Execution-ready quantity']=min(current,execution.get(wo,0))
            lot['Planning lot']='Existing measured forming WIP'
            lot['Readiness']='READY / FIRING PREPARATION'
            lot['Earliest Normal Firing']=planning_start
            lot['Readiness Rank']=0;lot['Release Candidate']=True
            lot['Firing Ready Basis']='Planning uses measured formed WIP at selected start. Execution still requires drying/release confirmation.'
            rows.append(lot);ready[wo]-=current;execution[wo]=max(execution.get(wo,0)-lot['Execution-ready quantity'],0)
        future=total-current
        if future>0 or total==0:
            lot=r.copy();lot['Effective Qty']=future;lot['Verified Ready for Firing Qty']=0;lot['Execution-ready quantity']=0
            lot['Planning lot']='Future upstream production';lot['Release Candidate']=False
            lot['Firing Ready Basis']='Future quantity remains governed by upstream capacity, process lead times and drying; never added to existing WIP.'
            rows.append(lot)
    return pd.DataFrame(rows).reset_index(drop=True)


def start_diagnostic(fr,selected):
    loads=fr.get('loads',pd.DataFrame());prepared=fr.get('prepared',pd.DataFrame());calendar=fr.get('kiln_editor',pd.DataFrame())
    dates=pd.to_datetime(loads.get('Load Date',pd.Series(dtype=object)),errors='coerce')
    first=dates.min();on_day=int(dates.dt.date.eq(selected).sum())
    q=pd.to_numeric(prepared.get('Verified Ready for Firing Qty',pd.Series(dtype=float)),errors='coerce').sum()
    available=pd.to_datetime(calendar.get('Available From',pd.Series(dtype=object)),errors='coerce')
    free=int(available.dt.date.le(selected).sum())
    return pd.DataFrame([{'Selected planning start':selected,'First proposed load':first.date() if pd.notna(first) else None,
        'Loads on selected day':on_day,'Measured formed WIP in planning pool':q,'Kilns available by selected date':free,
        'Start status':'LOADS ON SELECTED DATE' if on_day else 'NO LOAD ON REQUESTED DAY — inspect exceptions, compatibility and minimum loading',
        'Policy':'Selected start is never rewritten. Existing formed portions are not delayed by whole-WO stage labels. Future portions retain upstream constraints; execution approval remains separate.'}])


def prior_availability(kilns,blocks,selected):
    """Protect issued cycles BEFORE selecting a kiln, so other free kilns compete."""
    out=kilns.copy()
    for i,r in out.iterrows():
        key=str(r.get('Kiln','')).strip().upper();block=blocks.get(key)
        if block is None:continue
        old=pd.to_datetime(r.get('Available From'),errors='coerce')
        old=old.date() if pd.notna(old) else selected
        end=pd.to_datetime(block,errors='coerce')
        if pd.isna(end):raise ValueError('Previous issued kiln availability is invalid for '+key)
        out.at[i,'Previous issued available from']=end.date()
        out.at[i,'Available From']=max(selected,old,end.date())
    return out
