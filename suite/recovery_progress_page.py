from __future__ import annotations
import pandas as pd
import plotly.express as px
import os
import streamlit as st
from suite.recovery_progress import read_recovery_progress

@st.cache_data(show_spinner='Reading dated recovery plan…')
def _cached_progress(path, mtime_ns, size):
    return read_recovery_progress(path)

def render(st, path):
    stat=os.stat(path)
    detail, weekly, monthly, total, meta = _cached_progress(str(path), stat.st_mtime_ns, stat.st_size)
    st.subheader('Recovery execution — plan vs actual vs remaining / แผนกู้คืน: แผนเทียบผลิตจริงและคงเหลือ')
    st.caption('Plan date/quantity: แผน Recovery columns 168–169. Actual warehouse date/quantity: columns 170–171. Remaining is reconciled per WO, then allocated against that WO’s schedule rows in date order; a different WO’s actual output never reduces it. Weight is estimated from Cover.GW ÷ Cover.QTY; missing weight stays blank.')
    if total.empty:
        st.info('No recovery schedule rows to summarize.')
        return
    t=total.iloc[0]
    def fmt_t(col):
        v=t.get(col); return '—' if pd.isna(v) else f'{v/1000:,.2f} t'
    c1,c2,c3=st.columns(3)
    c1.metric('Planned / วางแผน',f"{t['Planned pcs']:,.0f} pcs · {fmt_t('Planned kg')}",f"{t['Planned WOs']:,.0f} WOs")
    c2.metric('Actual produced / ผลิตจริง',f"{t['Actual pcs']:,.0f} pcs · {fmt_t('Actual kg')}",f"{t['Actual-produced WOs']:,.0f} WOs")
    c3.metric('Remaining / คงเหลือ',f"{t['Remaining pcs']:,.0f} pcs · {fmt_t('Remaining kg')}",f"{t['Remaining WOs']:,.0f} WOs")
    st.caption(f"Source {meta['source']} · sheet {meta['sheet']} · {meta['source_rows']:,} source rows / {meta['distinct_wos']:,} distinct WOs · weight coverage {meta['weight_coverage_wos']:,} WOs. Of {t['Actual pcs']:,.0f} pcs recorded actual, {t['Actual applied to plan pcs']:,.0f} are matched to scheduled recovery demand; {t['Unmatched actual pcs']:,.0f} are surplus or lack a matching planned recovery quantity. Planned quantity = matched actual + remaining. WO counts can overlap across periods.")
    mode=st.radio('Period / ช่วงเวลา',['Week / สัปดาห์','Month / เดือน'],horizontal=True,key='recovery_progress_period')
    data=weekly if mode.startswith('Week') else monthly
    if data.empty:
        st.info('No dated plan or actual records are available.')
        return
    shown=data.copy()
    # Merge reports plan/remaining by planned date and actuals by actual date.
    cols=['Period','Planned WOs','Actual-produced WOs','Remaining WOs','Planned pcs','Actual pcs','Actual applied to plan pcs','Unmatched actual pcs','Remaining pcs','Planned kg','Actual kg','Actual applied to plan kg','Unmatched actual kg','Remaining kg']
    shown=shown[[x for x in cols if x in shown.columns]]
    for col in ['Planned kg','Actual kg','Remaining kg']:
        if col in shown: shown[col]=shown[col]/1000
    st.dataframe(shown,use_container_width=True,hide_index=True)
    for vals, ylabel, title in [
        (['Planned pcs','Actual pcs','Remaining pcs'],'Pieces','recovery pieces planned / actual / remaining'),
        (['Planned kg','Actual kg','Remaining kg'],'Weight (ton)','recovery weight planned / actual / remaining (ton)'),
        (['Planned WOs','Actual-produced WOs','Remaining WOs'],'Distinct WOs','distinct recovery WOs planned / produced / remaining')]:
        chart=shown.melt(id_vars=['Period'],value_vars=[x for x in vals if x in shown],var_name='Measure',value_name=ylabel)
        if not chart.empty: st.plotly_chart(px.bar(chart,x='Period',y=ylabel,color='Measure',barmode='group',title=f'{mode}: {title}'),use_container_width=True)
    st.download_button('⬇ Download period analysis CSV',shown.to_csv(index=False).encode('utf-8-sig'),'recovery_plan_actual_remaining_by_period.csv','text/csv',key='recovery_progress_period_download')
    with st.expander('Recovery schedule row evidence'):
        cols=['Work Order','Customer','Specification','Source row','Plan date','Plan (pcs)','Actual date','Actual produced (pcs)','Actual applied to plan (pcs)','Unmatched actual (pcs)','Remaining planned (pcs)','Plan (kg)','Actual (kg)','Actual applied to plan (kg)','Unmatched actual (kg)','Remaining (kg)','Recovery status','Reason']
        st.dataframe(detail[[x for x in cols if x in detail]],use_container_width=True,hide_index=True,height=360)
        st.download_button('⬇ Download row evidence CSV',detail.to_csv(index=False).encode('utf-8-sig'),'recovery_plan_row_evidence.csv','text/csv',key='recovery_progress_detail_download')
