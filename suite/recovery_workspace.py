"""Recovery source reconciliation: only the owner-approved second sheet."""
from pathlib import Path
import pandas as pd
import streamlit as st
from openpyxl import load_workbook
from .production_evidence import number,clean
from .exporters import to_workbook
from .common import bkk_today
from .backorder_views import local_date


def read(path):
    w=load_workbook(path,read_only=True,data_only=True)
    try:
        if 'แผน Recovery' not in w.sheetnames:raise ValueError('Required sheet แผน Recovery is missing')
        s=w['แผน Recovery'];s.reset_dimensions();rows=[]
        for n,r in enumerate(s.iter_rows(min_row=4,max_col=176,values_only=True),4):
            wo=clean(r[1])
            if not wo or wo.upper() in {'N/A','#N/A','FAC NO'}:continue
            plan=number(r[168]);actual=number(r[170]);ordered=number(r[6])
            valid=plan is not None and plan>=0 and (actual is None or actual>=0)
            pending=max(plan-(actual or 0),0) if valid else None
            rows.append({'Work Order':wo,'Customer':clean(r[4]),'Specification':clean(r[5]),'Category':clean(r[7]),'Order pcs':ordered,
                'Original due':local_date(r[2]),'Recovery date / hold':clean(r[3]),
                'Plan date':local_date(r[167]),'Planned pcs':plan,
                'Actual date':local_date(r[169]),'Actual pcs':actual,'Pending planned pcs':pending,
                'Actual unrecorded':actual is None,'Source status':clean(r[172]) or 'Not recorded',
                'Reason':clean(r[175]),'Note':clean(r[174]),'Source row':n,
                'Source cells':f'แผน Recovery!B{n},E{n},G{n},FL{n}:FQ{n},FS{n}:FT{n}',
                'Quantity review':not valid,'Source file':Path(path).name})
        d=pd.DataFrame(rows)
        if not d.empty:
            from .wo_lookup import norm_wo
            d['_WO key']=d['Work Order'].map(norm_wo)
            d['Repeated WO']=d['_WO key'].duplicated(keep=False)
            counts=d.groupby('_WO key')['Source status'].nunique()
            d['WO status']=d['Source status'].where(d['_WO key'].map(counts).eq(1),'CONFLICT — inspect source rows')
            d['Actual applied pcs']=[min(p,a) if pd.notna(p) and pd.notna(a) and p>=0 and a>=0 else 0 if pd.notna(p) and p>=0 and pd.isna(a) else None for p,a in zip(d['Planned pcs'],d['Actual pcs'])]
            d['Unmatched actual pcs']=(d['Actual pcs']-d['Actual applied pcs']).clip(lower=0)
            d['Quantity status']=['NO PLAN' if pd.isna(p) else 'ACTUAL UNRECORDED' if pd.isna(a) else 'COMPLETE' if a>=p else 'PARTIAL' if a>0 else 'NO RECORDED OUTPUT' for p,a in zip(d['Planned pcs'],d['Actual pcs'])]
        return d
    finally:w.close()


@st.cache_data(show_spinner='Reading แผน Recovery…',max_entries=3)
def cached(path,mtime,size):return read(path)


def summary(d,group):
    if d.empty:return pd.DataFrame()
    return d.groupby(group,dropna=False).agg(Work_orders=('Work Order','nunique'),Source_rows=('Work Order','size'),Planned_pcs=('Planned pcs',lambda s:s.sum(min_count=1)),Actual_pcs=('Actual pcs',lambda s:s.sum(min_count=1)),Pending_pcs=('Pending planned pcs',lambda s:s.sum(min_count=1)),Unrecorded_actual_rows=('Actual unrecorded','sum')).reset_index()


def wo_reconciliation(d):
    if d.empty:return pd.DataFrame()
    key='_WO key' if '_WO key' in d else 'Work Order'
    x=d.groupby(key,dropna=False).agg(Work_Order=('Work Order','first'),Source_rows=('Work Order','size'),Planned_pcs=('Planned pcs',lambda s:s.sum(min_count=1)),Actual_pcs=('Actual pcs',lambda s:s.sum(min_count=1)),Applied_pcs=('Actual applied pcs',lambda s:s.sum(min_count=1)),Pending_pcs=('Pending planned pcs',lambda s:s.sum(min_count=1)),Unmatched_actual_pcs=('Unmatched actual pcs',lambda s:s.sum(min_count=1))).reset_index()
    x['Recovery completion']=['NO RECOVERY PLAN' if pd.isna(p) or p<=0 else 'COMPLETE PLAN ALLOCATION' if left==0 else 'PARTIAL / PENDING' if a>0 else 'NOT STARTED / PENDING' for p,a,left in zip(x.Planned_pcs,x.Applied_pcs,x.Pending_pcs)]
    return x


def report_sheets(d):
    out={'Source rows':d,'Customer':summary(d,['Customer']),'Category':summary(d,['Category']),'WO status':summary(d,['WO status']),'Quantity status':summary(d,['Quantity status'])}
    for mode,freq in [('Week','W-SUN'),('Month','M')]:
        x=d.copy();x[mode]=pd.to_datetime(x['Plan date'],errors='coerce').dt.to_period(freq).astype(str).replace('NaT','NO DATE');out[mode]=summary(x,[mode])
    out['WO reconciliation']=wo_reconciliation(d)
    out['Basis']=pd.DataFrame({'Rule':['Only แผน Recovery was analysed. Other sheets, including Cover and warehouse reports, are not read.','Plan FL/FM; actual FN/FO; source on-plan/late result FQ; reasons FS/FT.','Pending is planned quantity less recorded row-linked actual, floored at zero. Blank actual stays unknown; pending assumes no confirmed actual and is flagged.','Repeated WO rows are retained; distinct counts and row totals are separate. Check repeated rows before treating totals as unique physical orders.','No source weight in this approved sheet: no tonnes invented. On plan is not proof of completion/packing.']})
    return out


def render(st,path):
    import plotly.express as px
    st.header('📄 วิเคราะห์ Recovery / Recovery source reconciliation')
    p=Path(path);d=cached(str(p),p.stat().st_mtime_ns,p.stat().st_size)
    if d.empty:st.info('No source recovery rows');return
    st.caption(f'{p.name} · แผน Recovery only · row/cell evidence retained')
    c=st.columns(4);c[0].metric('ใบสั่งไม่ซ้ำ / Distinct WOs',d['Work Order'].nunique());c[1].metric('แถวต้นทาง / Source rows',len(d));c[2].metric('แผน (ชิ้น) / Planned',f"{d['Planned pcs'].sum(min_count=1):,.0f}");c[3].metric('ค้างตามแผน / Pending pcs',f"{d['Pending planned pcs'].sum(min_count=1):,.0f}")
    st.caption(f"Recorded actual {d['Actual pcs'].sum(min_count=1):,.0f} pcs · unrecorded actual rows {int(d['Actual unrecorded'].sum())} · repeated WO rows {int(d['Repeated WO'].sum())}. These are source row allocations, not inferred unique-order quantities.")
    st.caption('Source on-plan/late WO conflicts: '+str(d.loc[d["WO status"].str.startswith("CONFLICT"),'_WO key'].nunique()))
    st.dataframe(wo_reconciliation(d).groupby('Recovery completion').size().reset_index(name='WOs'),hide_index=True,use_container_width=True)
    fields=['Customer','Category','WO status','Quantity status']
    pick=st.selectbox('วิเคราะห์ตาม / Analyse by',fields+['Week','Month'],key='recovery55_group')
    if pick in ('Week','Month'):
        d=d.copy();d[pick]=d['Plan date'].dt.to_period('W-SUN' if pick=='Week' else 'M').astype(str).replace('NaT','NO DATE')
    result=summary(d,[pick]);st.dataframe(result,use_container_width=True,hide_index=True)
    for measure in ['Work_orders','Planned_pcs','Actual_pcs','Pending_pcs']:
        st.plotly_chart(px.bar(result,x=pick,y=measure,title=measure.replace('_',' '),color=pick),use_container_width=True)
    chosen=st.multiselect('กรองสถานะต้นทาง / Source status filter',sorted(d['Source status'].unique()),key='recovery55_status')
    detail=d[d['Source status'].isin(chosen)] if chosen else d
    st.dataframe(detail,use_container_width=True,hide_index=True,height=440)
    if st.button('เตรียมรายงานครบ / Prepare complete Excel',key='recovery55_export'):
        st.download_button('⬇ Excel — totals, pending, customers, categories, weeks, months',to_workbook(report_sheets(d)),'Recovery_Source_Analysis.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.info('Source on-plan/late status and quantity completion are separate. Blank actuals are flagged, not silently recorded as zero production. Weight is unavailable in the approved sheet; other sheets are not used.')
