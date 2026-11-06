"""One Excel/analysis basis for desktop and mobile observations/status events."""
from pathlib import Path
import os,sqlite3
import pandas as pd
from .common import bkk_today,bkk_now
from .exporters import to_workbook


def frames(db_path,data_dir,start,end):
    def table(path,name,field):
        if not Path(path).exists():return pd.DataFrame()
        with sqlite3.connect(path,timeout=15) as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone():return pd.DataFrame()
            return pd.read_sql_query(f'SELECT * FROM {name} WHERE substr({field},1,10) BETWEEN ? AND ? ORDER BY id DESC',c,params=(str(start),str(end)))
    audit=table(db_path,'mobile_audits','created_at');section=table(Path(data_dir)/'daily_status_entries.sqlite3','section_status','time');whole=table(db_path,'wo_status_events','recorded_at');events=table(db_path,'events','event_time')
    sheets={'WIP observations':audit,'Process open-close':section,'Whole WO decisions':whole,'Production events':events}
    for name,df,fields in [('Audit analysis',audit,['observed_process','physical_status','user_name']),('Process analysis',section,['section','status','user']),('Whole WO analysis',whole,['status','user'])]:
        if not df.empty:
            grouping=[c for c in fields if c in df]
            sheets[name]=df.groupby(grouping,dropna=False).size().reset_index(name='Recorded events')
    if not whole.empty:
        sheets['Latest whole WO']=whole.drop_duplicates('wo')
    if not section.empty:sheets['Latest process status']=section.drop_duplicates(['wo','section'])
    sheets['Basis']=pd.DataFrame({'Rule':['All records use the configured shared central databases.','Audit quantities are observations, not additive stock or production.','Process closure never closes the whole WO. Whole WO decisions require reasons and do not prove packed output.','Latest statuses in this date window are separately labelled; the full event history remains stored.','MD workbook open-close counts are a separate report; these transactions are not added to imported category totals.'], 'Database':[str(Path(db_path).resolve())]+['']*4})
    return sheets


def excel(db_path,data_dir,start,end):
    return to_workbook(frames(db_path,data_dir,start,end))


def render(st,db_path,data_dir):
    from datetime import timedelta
    import plotly.express as px
    st.header('📊 รายงานตรวจ WIP และเปิด–ปิด / WIP & status reports')
    period=st.date_input('ช่วงวันที่ / Date range',(bkk_today()-timedelta(days=30),bkk_today()),key='tracking_report_dates')
    if not isinstance(period,(tuple,list)) or len(period)!=2:return
    sheets=frames(db_path,data_dir,*period)
    for title in ['Audit analysis','Process analysis','Whole WO analysis']:
        df=sheets.get(title,pd.DataFrame())
        if not df.empty:
            st.subheader(title);st.dataframe(df,use_container_width=True,hide_index=True)
            st.plotly_chart(px.bar(df,x=df.columns[0],y='Recorded events',color=df.columns[1] if len(df.columns)>2 else None,barmode='stack'),use_container_width=True)
    data=to_workbook(sheets)
    st.download_button('⬇ Excel — ตรวจนับ / แผนก / ทั้งใบสั่ง',data,f'WIP_Status_{period[0]}_{period[1]}.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    with st.expander('หลักฐานรายการ / Event records'):
        for title,df in sheets.items():st.markdown('**'+title+'**');st.dataframe(df,use_container_width=True,hide_index=True)
