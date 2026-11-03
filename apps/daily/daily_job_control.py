"""Editable date-wise open/close evidence from the current monthly register.

The factory revises that workbook every day. Home stores today's revision once;
this page never asks for a second copy. Closed job count is a closure metric,
not a delivered count. Open Job = JOB; Close Job = Item — they are not netted.
"""
from pathlib import Path
from datetime import date
import pandas as pd
import calendar
import plotly.express as px
import streamlit as st
import sys

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from suite.central_paths import JOB_REGISTER_FILE, original_name_for, resolve_file
from suite.month_register import infer_register_month
from suite.common import bkk_now

GROUPS=['P','R','S','T','M','PB']
COLORS={'P':'#2563EB','R':'#16A34A','S':'#DC2626','T':'#7C3AED','M':'#0891B2','PB':'#EAB308'}

def _sheet_named(xlsx, *needles):
    for name in xlsx.sheet_names:
        low = str(name).strip().lower().replace(' ', '')
        if any(n.replace(' ', '') in low for n in needles):
            return name
    return None

def parse_monthly(path,year=None,month=None):
    if year is None or month is None:
        now=bkk_now()
        year=year or now.year
        month=month or now.month
    x=pd.ExcelFile(path)
    out=[]
    pairs=[(_sheet_named(x,'open job','openjob') or 'Open Job','Opened WOs'),
           (_sheet_named(x,'close job','closejob') or 'Close Job','Closed items')]
    last_day=calendar.monthrange(year,month)[1]
    for sheet,metric in pairs:
        if sheet not in x.sheet_names: continue
        d=pd.read_excel(x,sheet_name=sheet,header=None)
        days=pd.to_numeric(d.iloc[1,2:33],errors='coerce')
        group=None
        # Source has vertically merged MTO/MTS cells centered within their five-row groups.
        for i in range(2,min(len(d),12)):
            group='MTO' if i<7 else 'MTS'
            order_type=str(d.iat[i,0]).strip().upper() if pd.notna(d.iat[i,0]) else ''
            if order_type in ('MTO','MTS') and order_type!=group:
                raise ValueError('Unexpected merged MTO/MTS layout: inspect source row '+str(i+1))
            category=str(d.iat[i,1]).strip().upper() if pd.notna(d.iat[i,1]) else ''
            if category=='F':category='P'
            if category not in GROUPS or not group:continue
            for j,day in enumerate(days,2):
                if pd.isna(day) or not (1<=int(day)<=last_day):continue
                value=pd.to_numeric(d.iat[i,j],errors='coerce')
                out.append({'Date':pd.Timestamp(year,month,int(day)),'Order Type':group,'Category':category,'Metric':metric,'WOs':float(value) if pd.notna(value) else float('nan'),'Source Sheet':sheet,'Source Row':i+1,'Source Column':j+1})
    return pd.DataFrame(out)


@st.cache_data(show_spinner=False)
def _parse_monthly_cached(path,mtime_ns,size,year,month):
    """Cache parsed rows by file identity and change metadata; edits invalidate naturally."""
    return parse_monthly(path,year,month)

def render(st,base_dir):
    st.markdown('### 📅 Daily job opening & closing / เปิดและปิดใบสั่งผลิตรายวัน')
    st.warning('UNIT CHECK: Open Job sheet counts JOB; Close Job sheet heading says Item. They are not confirmed to be the same unit. Do not calculate open backlog as JOB minus Item until Production confirms the definitions. F is normalized to P.')
    src=resolve_file(JOB_REGISTER_FILE)
    if src is None:
        st.warning("The current month Open/Close register is not on Home yet. Upload today's copy once on Home → Upload / Replace Source Files. This page does not ask for a second copy.")
        return
    orig=original_name_for(JOB_REGISTER_FILE) or Path(src).name
    inferred=infer_register_month(orig, src)
    yy,mm=inferred if inferred else (bkk_now().year,bkk_now().month)
    st.success(f"Using the Home register `{src.name}` (original `{orig}`). Month {mm:02d}/{yy}. Daily does not ask for this file again.")
    st.caption("Replace the current month's register on Home when Planning sends the daily revision. The filename can change each month; each changed upload is retained as a revision.")
    if inferred is None:
        st.info(f"No month was found in the filename or workbook headers. The default is the current Thailand local month for Phan Thong, Chonburi ({mm:02d}/{yy}); adjust only if this register belongs to a different month.")
        yc,mc=st.columns(2)
        yy=yc.number_input('Register year (filename/header missing)',2020,2100,int(yy),key='job_year')
        mm=mc.number_input('Register month',1,12,int(mm),key='job_month')
    try:
        stat=Path(src).stat()
        raw=_parse_monthly_cached(str(src),int(stat.st_mtime_ns),int(stat.st_size),int(yy),int(mm))
    except Exception as e:st.error('Job register cannot be parsed: '+str(e));return
    if raw.empty:st.warning('No recognized Open Job / Close Job rows');return
    stat=Path(src).stat()
    fingerprint=(int(stat.st_mtime_ns),int(stat.st_size),yy,mm)
    if st.session_state.get('job_register_fingerprint')!=fingerprint:
        st.session_state.job_register_review=raw.copy();st.session_state.job_register_fingerprint=fingerprint
    df=st.session_state.job_register_review.copy()
    c1,c2=st.columns(2)
    f=c1.date_input('FROM / จากวันที่',value=date(yy,mm,1),key='job_date_from')
    t=c2.date_input('TO / ถึงวันที่',value=date(yy,mm,calendar.monthrange(yy,mm)[1]),key='job_date_to')
    if f>t:st.warning('FROM must be on or before TO');return
    with st.expander('✏️ EDIT ALL UNDERLYING JOB RECORDS / แก้ไขข้อมูลทั้งหมด',expanded=False):
        st.caption('Edits recalculate graphs immediately. Source file is unchanged. Export reviewed data for traceability.')
        e=st.data_editor(df,num_rows='dynamic',hide_index=True,use_container_width=True,key='job_register_editor',column_config={'Order Type':st.column_config.SelectboxColumn(options=['MTO','MTS']),'Category':st.column_config.SelectboxColumn(options=GROUPS),'Metric':st.column_config.SelectboxColumn(options=['Opened WOs','Closed items'])})
        if st.button('Apply reviewed job data / ใช้ข้อมูลที่ตรวจสอบ',key='job_apply'):
            e['WOs']=pd.to_numeric(e['WOs'],errors='coerce')
            e['Date']=pd.to_datetime(e['Date'],errors='coerce');e['Category']=e['Category'].replace('F','P')
            st.session_state.job_register_review=e.copy();st.rerun()
    df['Date']=pd.to_datetime(df['Date'],errors='coerce');df['WOs']=pd.to_numeric(df['WOs'],errors='coerce')
    df=df[df['Date'].between(pd.Timestamp(f),pd.Timestamp(t)) & df['Category'].isin(GROUPS)].copy()
    totals=df.groupby('Metric')['WOs'].sum();a,b,c=st.columns(3)
    a.metric('Opened WOs',f'{totals.get("Opened WOs",0):,.0f}');b.metric('Closed items',f'{totals.get("Closed items",0):,.0f}');c.metric('Unit reconciliation','PENDING',help='Open JOB and Closed ITEM may not be comparable')
    g=df.groupby(['Date','Metric','Category'],as_index=False)['WOs'].sum()
    g['Day / Status']=g['Date'].dt.strftime('%d %b')+' • '+g['Metric'].replace({'Opened WOs':'OPEN','Closed items':'CLOSED'})
    fig=px.bar(g,x='Day / Status',y='WOs',color='Category',barmode='stack',color_discrete_map=COLORS,category_orders={'Category':GROUPS},title='Daily OPEN / CLOSED — product-category stacks (JOB vs ITEM units)')
    total=g.groupby('Day / Status',sort=False,as_index=False)['WOs'].sum()
    fig.add_scatter(x=total['Day / Status'],y=total['WOs'],mode='text',text=[f'{v:,.0f}' for v in total['WOs']],textposition='top center',showlegend=False,hoverinfo='skip')
    fig.update_layout(height=490,font_size=15,xaxis_tickangle=-45,legend_title_text='Product category')
    st.plotly_chart(fig,use_container_width=True,config={'displaylogo':False,'toImageButtonOptions':{'format':'svg'}})
    cat=df.groupby(['Category','Metric'],as_index=False)['WOs'].sum()
    fig=px.bar(cat,x='Metric',y='WOs',color='Category',barmode='stack',color_discrete_map=COLORS,category_orders={'Category':GROUPS},title='Selected period OPEN vs CLOSED — category stacks')
    total=cat.groupby('Metric',as_index=False)['WOs'].sum()
    fig.add_scatter(x=total['Metric'],y=total['WOs'],mode='text',text=[f'{v:,.0f}' for v in total['WOs']],textposition='top center',showlegend=False,hoverinfo='skip')
    st.plotly_chart(fig,use_container_width=True)
    st.dataframe(df.pivot_table(index=['Date','Order Type','Category'],columns='Metric',values='WOs',aggfunc='sum',fill_value=0).reset_index(),use_container_width=True,hide_index=True)
    st.download_button('⬇️ Download reviewed job records CSV',st.session_state.job_register_review.to_csv(index=False).encode('utf-8-sig'),file_name=f'JOB_REGISTER_REVIEW_{yy}{mm:02d}.csv',mime='text/csv')
    return df
