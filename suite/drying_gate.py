"""Source-backed forming → drying → firing timing. No invented drier capacity.

Lead-time values are working days (same Mon–Sat calendar as the existing route).
Missing completion evidence or capacity remains visible, never silently validated.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import io
import math
import re
from functools import lru_cache
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook


def _day(value):
    if value is None or pd.isna(value):return None
    try:return pd.Timestamp(value).date()
    except (ValueError,TypeError):return None


def workdays_after(start, days):
    result=start
    for _ in range(math.ceil(days)):
        result+=dt.timedelta(days=1)
        while result.weekday()==6:result+=dt.timedelta(days=1)
    return result


@lru_cache(maxsize=3)
def _lead_rows(data):
    wb=load_workbook(io.BytesIO(data),data_only=True,read_only=True)
    try:
        if 'Lead Time' not in wb.sheetnames:return {}
        ws=wb['Lead Time']; headers=[str(ws.cell(2,c).value or '').replace('กลุ่ม','').strip().upper() for c in range(2,8)]
        rows={}
        for r in range(3,13):
            if 'อบสินค้า' not in str(ws.cell(r,1).value or ''):continue
            for c,group in enumerate(headers,2):
                raw=str(ws.cell(r,c).value or '').strip()
                nums=[float(x) for x in re.findall(r'\d+(?:\.\d+)?',raw)]
                days=0.0 if 'ไม่ผ่าน' in raw else max(nums) if nums else None
                form_raw=str(ws.cell(5,c).value or '')
                form_nums=[float(x) for x in re.findall(r'\d+(?:\.\d+)?',form_raw)]
                form_days=max(form_nums) if form_nums else None
                rows[group]=(days,raw,f"Lead Time!{ws.cell(r,c).coordinate}",form_days,f"Lead Time!{ws.cell(5,c).coordinate}")
        return rows
    finally:wb.close()


def drying_rules(capacity_path):
    data=Path(capacity_path).read_bytes()
    return _lead_rows(data),hashlib.sha256(data).hexdigest()


def forming_to_firing(end,wo,oven_days,form_days):
    from apps.daily.lead_time_control_v1 import order_process_override
    override=order_process_override({'Work Order':wo})
    if override:
        days=override['drying_calendar_days']+override['pre_firing_check_calendar_days']
        return end+dt.timedelta(days=days),override['source']
    # Same conservative route-offset interpretation as the existing Daily planner;
    # the workbook itself does not resolve calendar vs working-day basis.
    return workdays_after(end,max(1,form_days+oven_days)), 'forming + oven route offset; working-day convention'


def apply_upstream_drying(check, master, forming, capacity_path):
    """Replace a universal next-day rule with the supplied group-specific lead time."""
    if check is None or check.empty:return check
    rules,sha=drying_rules(capacity_path);out=check.copy()
    jobs={str(r['Work Order']):r for _,r in master.iterrows()}
    for i,r in out.iterrows():
        wo=str(r['Work Order']);j=jobs.get(wo,{})
        group=str(j.get('Category',j.get('Type',''))).strip().upper()
        days,raw,cell,form_days,form_cell=rules.get(group,(None,'','',None,''))
        dates=forming[forming['Work Order'].astype(str).eq(wo)]['Plan Date'] if forming is not None and not forming.empty else pd.Series(dtype=object)
        valid=[d for d in map(_day,dates) if d]
        end=max(valid) if valid else None
        out.at[i,'Drying lead working days']=days
        out.at[i,'Drying source']=f'{Path(capacity_path).name} {cell}: {raw}; {form_cell}: forming {form_days}; SHA256 {sha}; working-day convention (source day basis unstated)'
        out.at[i,'Drier capacity status']='NOT VERIFIED — no drier capacity in supplied master'
        if days is None or form_days is None:
            out.at[i,'Release Status']='HOLD — drying lead missing'
            out.at[i,'Reason']='No approved drying route/lead for group '+group
        elif end:
            release,basis=forming_to_firing(end,wo,days,form_days)
            existing=_day(r.get('Earliest Release Date'))
            # Route bypass (PB) must not erase another sequence constraint.
            release=max(release,existing) if existing else release
            out.at[i,'Earliest Release Date']=release
            fire=_day(r.get('Plan Date'))
            if fire and fire<release:
                out.at[i,'Release Status']='HOLD — drying until '+str(release)
                out.at[i,'Sequence Status']='FAIL'
                out.at[i,'Reason']=f'Forming {end} + drying {days:g} working days ({cell}); earliest firing {release}'
        out.at[i,'Validation Status']='PROVISIONAL — drying timing checked; drier resources not verified'
    return out


def evaluate_drying(details, plan_df, upstream, capacity_path, planning_start):
    """Per-load evidence. Already formed quantity alone does not confirm drying."""
    columns=['Load ID','Work Order','Category','Load Date','Forming date','Drying lead working days','Earliest drying completion','Timing status','Capacity status','Source','Reason']
    if details is None or details.empty:return pd.DataFrame(columns=columns)
    rules,sha=drying_rules(capacity_path)
    jobs={str(r['Work Order']):r for _,r in plan_df.iterrows()}
    rows=[];used={}
    for _,r in details.iterrows():
        wo=str(r.get('Work Order',''));j=jobs.get(wo,{})
        group=str(j.get('Category',r.get('Category',''))).strip().upper()
        days,raw,cell,form_days,form_cell=rules.get(group,(None,'','',None,''));load=_day(r.get('Load Date'))
        formed=None;complete=_day(j.get('Confirmed Drying Complete Date'))
        reason='';end=None
        if days is None or form_days is None:status='HOLD';reason='Approved drying lead missing for group '+group
        elif days==0:status='BYPASS';reason='Drying bypass explicitly stated by the capacity master'
        elif complete and complete<=planning_start and pd.notna(j.get('Confirmed Drying Qty')) and float(j.get('Confirmed Drying Qty',0))-used.get(wo,0)>=float(r.get('Planned Firing Qty',r.get('Qty pcs',r.get('Qty',0)))):
            end=complete;status='TIMING CONFIRMED';reason='Confirmed actual drying completion supplied';used[wo]=used.get(wo,0)+float(r.get('Planned Firing Qty',r.get('Qty pcs',r.get('Qty',0))))
        else:
            if upstream is not None and not upstream.empty and 'Work Order' in upstream:
                sec=upstream.get('Section',upstream.get('Section / กระบวนการ',pd.Series('',index=upstream.index))).astype(str)
                match=upstream[upstream['Work Order'].astype(str).eq(wo)&sec.eq('Forming')]
                valid=[d for d in map(_day,match.get('Plan Date',pd.Series(dtype=object))) if d]
                formed=max(valid) if valid else None
            if formed:
                end,basis=forming_to_firing(formed,wo,days,form_days)
                status='PROVISIONAL' if load and load>=end else 'HOLD'
                reason='Planned forming + source drying lead; drier resources require confirmation'
            else:status='HOLD';reason='Formed WIP has no confirmed drying completion or feasible forming date'
            if complete and complete>planning_start:reason+='; future actual drying completion is unconfirmed'
        rows.append([r.get('Load ID'),wo,group,load,formed,days,end,status,'BYPASS' if days==0 else 'NOT VERIFIED',f'{Path(capacity_path).name} {cell}={raw}; {form_cell}: forming {form_days}; SHA256 {sha}; working-day convention (source day basis unstated)',reason])
    return pd.DataFrame(rows,columns=columns)
