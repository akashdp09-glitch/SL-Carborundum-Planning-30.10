"""English production evidence page. Heavy views render only when selected."""
from __future__ import annotations

import io
import json
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as streamlit

from . import production_evidence as store
from .common import bkk_today

COLORS = ["#F58220", "#12395B", "#3977A6", "#E5A351", "#4D948A", "#7E6599", "#9C5737"]


@streamlit.cache_data(show_spinner="Loading retained production evidence…",max_entries=2)
def retained_frame(location,production_source_id):
    return store.production_frame(location)


def production_revision(sources):
    subset=sources[sources.role.eq("production_status")] if not sources.empty else sources
    return int(subset.id.max()) if not subset.empty else 0


def evidence_path(db_path):
    return Path(db_path).resolve().parent / "production_analytics.sqlite"


def source_controls(st, path, can_edit, user):
    sources=store.source_list(path)
    with st.expander("📂 Retained sources and revised KPI uploads",expanded=sources.empty):
        st.caption("Files are stored once, including originals, SHA-256, parsed evidence, source rows and revisions. An unchanged upload adds no duplicate records. Old formats are historical evidence, not active department definitions.")
        if not sources.empty:
            st.dataframe(sources.drop(columns=["inventory","config"]),hide_index=True,use_container_width=True)
            sid=st.selectbox("Download a retained original",sources.id.tolist(),format_func=lambda x: sources.loc[sources.id.eq(x),"filename"].iloc[0]+f" · source #{x}",key="production_original_id")
            if st.button("Prepare original download",key="prepare_evidence_original"):
                with store.connect(path) as con:
                    original,name=con.execute("SELECT original,filename FROM evidence_documents WHERE id=?",(int(sid),)).fetchone()
                st.download_button("⬇ Original workbook",original,name,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",on_click="ignore")
        if not can_edit:
            st.caption("Sign in with an editing role to import revisions.")
            return
        role=st.selectbox("Source format",["auto","production_kpi_section","production_kpi_category"],
                          format_func=lambda v:{"auto":"Detect revised analyst / opening / separate closure / production status", "production_kpi_section":"Production KPI — section plan / actual", "production_kpi_category":"Production KPI — category plan / packing actual"}[v],key="evidence_import_role")
        year=st.number_input("Reporting year for count workbooks without a year cell",min_value=2020,max_value=2100,value=bkk_today().year,key="evidence_import_year")
        month=st.text_input("Matrix month (YYYY-MM; required only for day-number production KPI headers)",bkk_today().strftime("%Y-%m"),key="evidence_matrix_month")
        unit=st.selectbox("Production KPI matrix quantity unit",["work orders","pieces","tonnes"],key="evidence_matrix_unit")
        uploaded=st.file_uploader("Updated workbooks — stored and reused automatically",type=["xlsx","xlsm"],accept_multiple_files=True,key="retained_evidence_uploads")
        if uploaded and st.button("💾 Import selected revisions",type="primary",key="retained_evidence_save"):
            failed=False
            for f in uploaded:
                try:
                    result=store.import_workbook(path,f.getvalue(),f.name,user,role,
                        dict(year=int(year),month=month,unit=unit,forming_unit="g",report_basis="Production plan"))
                    st.success(f"{f.name}: {result['status']} · revision {result['revision']}")
                except Exception as exc:
                    failed=True
                    st.error(f"{f.name}: {exc}")
            if not failed:st.rerun()


def safe_csv(frame):
    return frame.map(lambda v:"'"+v if isinstance(v,str) and v.startswith(("=","+","-","@")) else v).to_csv(index=False).encode("utf-8-sig")


def show_table(st, title, df):
    st.subheader(title)
    if df.empty:
        st.info("No source-backed records for these filters. Missing evidence is not zero output.")
        return
    st.dataframe(df,hide_index=True,use_container_width=True,height=min(530,90+len(df)*30))
    st.download_button("⬇ CSV — "+title,safe_csv(df),title.replace("/","_")+".csv","text/csv",key="export_"+title)


def chart(st, data, x, y, color=None, title="", horizontal=False):
    if data.empty or y not in data or not data[y].notna().any(): return
    fig=px.bar(data,x=y if horizontal else x,y=x if horizontal else y,
               color=color,barmode="stack",orientation="h" if horizontal else "v",
               title=title,color_discrete_sequence=COLORS)
    fig.update_layout(legend_title_text="",margin=dict(l=10,r=10,t=45,b=10))
    st.plotly_chart(fig,use_container_width=True)


def render_department(st, db_path, *, can_edit=False,user="Unknown",**_):
    path=evidence_path(db_path)
    st.header("🎯 Department KPI / KPI แผนกวางแผน")
    st.caption("Department and manager are the same KPI scheme. Maximum marks: accuracy 15, packing plan/actual 10, closed/opened 15. HR awarded marks remain separate.")
    source_controls(st,path,can_edit,user)
    values=store.automatic_values(path)
    periods=sorted(set(values.period)) if not values.empty else []
    sources=store.source_list(path)
    df=retained_frame(str(path),production_revision(sources))
    if not df.empty and "date" in df:
        periods=sorted(set(periods)|set(df.loc[df.valid.eq(True),"date"].dropna().dt.strftime("%Y-%m")))
    period=st.selectbox("Reporting month",periods or [bkk_today().strftime("%Y-%m")],index=periods.index(max(values.period)) if not values.empty and max(values.period) in periods else len(periods)-1 if periods else 0,key="department_reporting_month")
    results=store.department_results(path,period,frame=df)
    for col,(_,row) in zip(st.columns(3),results.iterrows()):
        col.metric(row.KPI,"Not recorded" if pd.isna(row.Achievement_percent) else f"{row.Achievement_percent:.2f}%")
        col.caption(f"Maximum {row.Maximum_marks} marks")
    show_table(st,"Automatic department calculation and evidence",results)
    st.caption("Packing is final actual output. Do not add section outputs or combine section/category workbooks as additional production. Repeated daily WO counts need source-level review; missing denominators stay unrecorded.")
    if not df.empty and "valid" in df:
        packing=df[df.valid.eq(True) & df.sheet.eq("Pack จ่าย") & df.quantity.gt(0)].copy()
        packing=packing[packing.date.dt.strftime("%Y-%m").eq(period)]
        granularity=st.selectbox("Final packing category chart period",["week","month"],key="department_packing_chart_period")
        category=store.aggregate(packing,[granularity,"category"])
        show_table(st,"Final packed output by category",category)
        for measure in ("distinct_WOs","pieces","weight_tonnes"):
            chart(st,category,granularity,measure,"category",f"Packing only — {measure} by category")
    if not values.empty:
        matrices=values[values.role.isin(["production_kpi_section","production_kpi_category"])].copy()
        matrices=matrices[matrices.period.eq(period)]
        for role,title in [("production_kpi_section","Section KPI evidence"),("production_kpi_category","Category KPI evidence — packing source")]:
            subset=matrices[matrices.role.eq(role)]
            show_table(st,title,subset.drop(columns=["cells"],errors="ignore"))
            for unit in subset.unit.unique() if not subset.empty else []:
                data=subset[subset.unit.eq(unit)]
                chart(st,data,"grouping","value","measure",title+" · "+unit)
    if not values.empty:
        with st.expander("Retained automatic KPI history and staff evidence"):
            view=values.drop(columns=["cells"],errors="ignore")
            show_table(st,"KPI source values",view)
    history=store.department_history(path)
    if not history.empty:
        with st.expander("Department KPI trend and retained calculations"):
            latest=history.drop_duplicates(["Period","Code"])
            st.line_chart(latest.pivot(index="Period",columns="KPI",values="Achievement_percent"))
            show_table(st,"Department calculation history",history)
    if st.checkbox("Enter manual evidence / corrections (separate audit trail)",key="show_department_manual"):
        from .manager_kpi import render
        render(st,db_path,can_edit=can_edit,user=user)
    if Path(db_path).exists():
        from .manager_kpi import VERSION as current_definition
        with sqlite3.connect(db_path,timeout=15) as con:
            exists=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='manager_kpi_events'").fetchone()
            archive=pd.read_sql_query("SELECT * FROM manager_kpi_events WHERE definition_version<>? ORDER BY id DESC",con,params=(current_definition,)) if exists else pd.DataFrame()
        if not archive.empty:
            with st.expander("Earlier manual KPI definitions — preserved historical evidence"):
                st.caption("Old codes retain their original definition/version. They are not silently rescored or mixed with the new KPI 2/3 order.")
                show_table(st,"Historical manual KPI records",archive)


def render(st, db_path, *, can_edit=False,user="Unknown"):
    path=evidence_path(db_path)
    st.header("🏭 วิเคราะห์สถานะการผลิต 2026-4 88 / Production Evidence Analysis")
    st.caption("Detailed English analysis · approved production plans vs section handovers · all normalised weights in metric tonnes. Plans, actual outputs, kiln loads, WIP and QC are separate evidence bases.")
    from .kpi_workspace import upload_center
    upload_center(st,db_path,can_edit,user,key='production60',groups=('production',))
    sources=store.source_list(path)
    # Cache the parsed DataFrame by persisted source revision, not by UI navigation.
    df=retained_frame(str(path),production_revision(sources))
    if df.empty:
        st.info("Import the Production status workbook once. It will remain available on future visits and restarts.")
        return
    view=st.selectbox("Analysis view",["Overview","Plans vs actual","Sections","Product categories","Weeks and months","Customers","Part sizes","QC and WIP","Data quality","Source audit"],key="production_analysis_view")
    transactions=df[df.basis.ne("Reference / QC / WIP")].copy()
    valid=transactions[transactions.valid.fillna(False).astype(bool)].copy()
    if valid.empty:
        st.warning("No valid dated transaction records.");return
    low,high=valid.date.min().date(),valid.date.max().date()
    a,b=st.columns(2)
    period=a.date_input("Transaction period",(max(low,date(high.year,1,1)),high),min_value=low,max_value=high,key="production_period")
    if not isinstance(period,(tuple,list)) or len(period)!=2:return
    sections=b.multiselect("Sections",sorted(valid.section.unique()),default=[],key="production_sections")
    valid=valid[valid.date.between(pd.Timestamp(period[0]),pd.Timestamp(period[1]))]
    if sections:valid=valid[valid.section.isin(sections)]
    if st.button("Prepare detailed English report (all sections, selected dates)",key="prepare_english_production_report"):
        from .production_report import english_report
        with st.spinner("Building tables and offline charts…"):
            html=english_report(df,sources,period[0],period[1])
        st.download_button("⬇ Detailed English analysis — offline HTML",html,
                           f"Production_Analysis_{period[0]}_{period[1]}.html","text/html",on_click="ignore")
    basis=st.selectbox("Evidence basis",["Output","Production plan","Kiln loaded","Activity report"],key="production_basis")
    x=valid[valid.basis.eq(basis)].copy()
    if view=="Product categories":
        # Department actual by category means final packing, not the sum of
        # the same material as it passes through multiple departments.
        x=x[x.sheet.eq("Pack จ่าย" if basis=="Output" else "Report Pack")]
    st.caption("Output counts are section handovers. Only Pack จ่าย is final actual. A WO can appear in several sections and periods; distinct counts must not be summed across buckets. Plan piece/weight sums are source allocations and may repeat across operators; they are not certified unique material quantities. Source duplicates are retained and flagged.")
    if not x.empty:
        x["size"]=x.apply(lambda r:" × ".join("?" if pd.isna(r[k]) else f"{r[k]:g}" for k in ("D","T","H")),axis=1)
    if view=="Overview":
        overview=store.aggregate(x,["section"])
        show_table(st,"Section totals — "+basis,overview)
        chart(st,overview,"section","weight_tonnes",title="Section weight — metric tonnes; do not sum repeated process stages")
        packing=valid[(valid.sheet=="Pack จ่าย") & (valid.quantity>0)]
        cards=st.columns(3)
        cards[0].metric("Final packed WOs",packing.wo_key.nunique())
        cards[1].metric("Reported packed pieces",f"{packing.quantity.sum():,.0f}" if not packing.empty else "No records")
        cards[2].metric("Final packed tonnes",f"{packing.weight_tonnes.sum(min_count=1):,.3f}" if packing.weight_tonnes.notna().any() else "Unknown")
        show_table(st,"Final actual packing by category",store.aggregate(packing,["category"]))
    elif view=="Plans vs actual":
        p=valid[valid.basis.eq("Production plan")].copy();a=valid[valid.basis.eq("Output")].copy()
        if p.empty:st.info("No approved plan records in this period. Preparation has no เตรียมReport sheet in this workbook.")
        comparisons=[]
        for sec in sorted(set(valid.section)):
            plan=p[p.section.eq(sec)];actual=a[a.section.eq(sec)]
            ps=set(plan.loc[plan.quantity>0,"wo_key"]);ac=set(actual.loc[actual.quantity>0,"wo_key"])
            comparisons.append(dict(Section=sec,Planned_WOs=len(ps) if not plan.empty else None,
                Actual_output_WOs=len(ac) if not actual.empty else None,Matched_WOs=len(ps&ac),
                Planned_not_output=len(ps-ac),Output_outside_plan=len(ac-ps),
                Actual_vs_plan_percent=len(ac)/len(ps)*100 if ps else None))
        show_table(st,"Distinct work-order reconciliation",pd.DataFrame(comparisons))
        combined=pd.concat([store.aggregate(p,["section"]).assign(Basis="Approved plan"),store.aggregate(a,["section"]).assign(Basis="Section output")])
        chart(st,combined,"section","distinct_WOs","Basis","Plan vs actual WOs (distinct within selected period)")
    elif view in ("Sections","Product categories"):
        dimensions=["section","category"] if view=="Sections" else ["category","section"]
        table=store.aggregate(x,dimensions);show_table(st,view+" — "+basis,table)
        for measure in ("weight_tonnes","pieces","distinct_WOs"):
            chart(st,table,dimensions[0],measure,dimensions[1],f"{basis}: {measure} by {dimensions[0]}")
        packing=valid[(valid.sheet=="Pack จ่าย") & (valid.quantity>0)]
        cat=store.aggregate(packing,["month","category"])
        chart(st,cat,"month","weight_tonnes","category","Final actual packing only — category stacked tonnes")
    elif view=="Weeks and months":
        # Final-actual category charts always use packing, regardless of selected section basis.
        packing=valid[(valid.sheet=="Pack จ่าย") & (valid.quantity>0)]
        for period_col in ("week","month"):
            table=store.aggregate(x,[period_col,"section","category"])
            show_table(st,period_col.title()+" — "+basis,table)
            final=store.aggregate(packing,[period_col,"category"])
            for measure in ("weight_tonnes","pieces","distinct_WOs"):
                chart(st,final,period_col,measure,"category",f"Final packing only — {period_col} category {measure}")
    elif view=="Customers":
        table=store.aggregate(x,["section","customer"])
        show_table(st,"Customer and section totals — "+basis,table)
        top=store.aggregate(x,["customer"]).sort_values("weight_tonnes",ascending=False).head(20)
        chart(st,top,"customer","weight_tonnes",title="Top 20 customers by tonnes",horizontal=True)
    elif view=="Part sizes":
        table=store.aggregate(x,["section","category","size","dimension_basis"])
        show_table(st,"Source-backed part sizes — D × T × H",table)
        if not table.empty:
            chart(st,table.sort_values("pieces",ascending=False).head(20),"size","pieces","section","Top sizes by pieces; dimensions are source-backed")
    elif view=="QC and WIP":
        wip,qc=store.reference_views(df)
        if sections and not wip.empty:wip=wip[wip.section.isin(sections)]
        if not wip.empty:
            totals=wip.groupby(["section","category"],dropna=False).agg(
                WOs=("wo","nunique"),Source_balance_pieces=("source_balance_pieces",lambda s:s.sum(min_count=1)),
                Source_balance_tonnes=("source_balance_tonnes",lambda s:s.sum(min_count=1)),
                Review_rows=("needs_review","sum")).reset_index()
            show_table(st,"WIP snapshot — section and category",totals)
            chart(st,totals,"section","Source_balance_tonnes","category","Source WIP snapshot tonnes — negative balances retained")
            show_table(st,"WIP detail in English",wip)
        if not qc.empty:
            qc["date"]=pd.to_datetime(qc.date,errors="coerce")
            qc=qc[qc.date.between(pd.Timestamp(period[0]),pd.Timestamp(period[1]))]
            show_table(st,"QC detail in English",qc)
            if not qc.empty:
                q=qc.groupby(["cause_section","category"]).agg(WOs=("wo","nunique"),Rejected_pieces=("rejected_pieces",lambda s:s.sum(min_count=1)),Rejected_tonnes=("rejected_tonnes",lambda s:s.sum(min_count=1))).reset_index()
                show_table(st,"QC rejection by section and category",q)
                chart(st,q,"cause_section","Rejected_tonnes","category","QC rejected tonnes — independent from handover output")
        refs=df[df.basis.eq("Reference / QC / WIP")]
        for sh in ("QC Reject","สรุป WIP","สถานะผลิต"):
            records=refs[refs.sheet.eq(sh)]
            rows=[dict(Sheet=r.sheet,Excel_row=r.excel_row,**(r.raw if isinstance(r.raw,dict) else {})) for _,r in records.iterrows()]
            show_table(st,sh+" — retained source cells",pd.DataFrame(rows))
        st.warning("WIP is a snapshot, not period production. Negative WIP and QC source quantities are retained for review, not clamped or subtracted again from handovers. No unsupported stock balance is inferred.")
    elif view=="Data quality":
        flags=[]
        for _,r in transactions.iterrows():
            for issue in r.issues if isinstance(r.issues,list) else []:
                flags.append(dict(Sheet=r.sheet,Row=r.excel_row,WO=r.wo,Date=r.date,Issue=issue,Raw_weight=r.weight_raw,Raw_unit=r.weight_unit,Normalised_tonnes=r.weight_tonnes))
        quality=pd.DataFrame(flags)
        show_table(st,"Data quality flags",quality)
        if not quality.empty:chart(st,quality.groupby("Issue").size().reset_index(name="Rows"),"Issue","Rows",title="Source quality flags")
        st.caption("Confirmed forming Report grams are converted to tonnes. Suspected mixed-scale weights elsewhere are withheld from weight sums; piece/WO evidence remains visible. Owner-confirmed short year 69 maps to 2569/2026; explicit four-digit future years remain flagged.")
        daily=valid.groupby(["date","section","basis"]).agg(Known_weight_tonnes=("weight_tonnes",lambda s:s.sum(min_count=1))).reset_index()
        show_table(st,"Days above the owner's usual 5-tonne reference — review, not a hard capacity limit",daily[daily.Known_weight_tonnes.gt(5)])
    else:
        audit=transactions.drop(columns=["raw","weight_kg"],errors="ignore").copy()
        for col in ("issues",):
            if col in audit:audit[col]=audit[col].map(lambda x:"; ".join(x) if isinstance(x,list) else x)
        show_table(st,"Source transaction audit — all periods",audit)
        inventories=[]
        for _,src in sources[sources.role.eq("production_status")].head(1).iterrows():
            inventories=json.loads(src.inventory)
        show_table(st,"Workbook sheet coverage",pd.DataFrame(inventories))
        with st.expander("Inspect exact original source row"):
            src=sources[sources.role.eq("production_status")].iloc[0]
            sheet=st.selectbox("Worksheet",[i["sheet"] for i in inventories],key="source_row_sheet")
            row=st.number_input("Excel row",min_value=1,step=1,value=3,key="source_row_number")
            if st.button("Read source row",key="read_production_source_row"):
                with store.connect(path) as con:
                    r=con.execute("SELECT data FROM production_evidence_rows WHERE source_id=? AND sheet=? AND excel_row=?",(int(src.id),sheet,int(row))).fetchone()
                if r:
                    cells=json.loads(r[0]).get("raw",{})
                    st.dataframe(pd.DataFrame([dict(Cell=f"{c}{row}",Raw_value=str(v)) for c,v in cells.items()]),hide_index=True)
                else:st.info("No retained nonempty row at this coordinate.")
