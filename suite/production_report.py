"""Self-contained English report; original evidence remains in the database."""
from html import escape

import pandas as pd
import plotly.express as px
from plotly.offline import get_plotlyjs

from .production_evidence import aggregate, reference_views


def english_report(frame, sources, start, end):
    x=frame[frame.valid.eq(True)].copy()
    x=x[x.date.between(pd.Timestamp(start),pd.Timestamp(end))]
    output=x[x.basis.eq("Output")].copy()
    plans=x[x.basis.eq("Production plan")].copy()
    packed=output[output.sheet.eq("Pack จ่าย") & output.quantity.gt(0)]
    fragments=["<!doctype html><html lang='en'><meta charset='utf-8'><title>SL Production Evidence Analysis</title><style>body{font:15px Arial,sans-serif;color:#12395b;margin:30px;line-height:1.5}h1,h2{color:#12395b}h2{border-bottom:3px solid #f58220;padding-bottom:6px}table{border-collapse:collapse;font-size:12px;max-width:100%}td,th{border:1px solid #ccd6df;padding:5px;text-align:left}th{background:#12395b;color:white}section{overflow:auto;margin-bottom:28px}.note{background:#fff4e8;padding:14px;border-left:5px solid #f58220}</style><body>",
        f"<h1>SL Carborundum — Production Evidence Analysis</h1><p>Transaction period: {escape(str(start))} to {escape(str(end))}. All normalised weights are metric tonnes (1 tonne = 1,000 kg = 1,000,000 g).</p>",
        "<p class='note'>Report sheets are owner-approved production plans. Section handovers are output; only Pack จ่าย is final actual packing. Do not add material as it passes through several sections. Kiln loads, QC and WIP remain separate. Forming Report grams are converted explicitly. Other 1000× corrections require matching same-section handover mass/pc; ambiguous weights stay unknown. Missing weights make totals partial, not zero. Source duplicates are retained and flagged. Distinct WOs overlap across periods/categories and must not be added blindly.</p>"]
    def table(title,data):
        fragments.append('<section><h2>'+escape(title)+'</h2>'+('No source-backed records.' if data.empty else data.to_html(index=False,escape=True,na_rep="Unknown",float_format=lambda v:f"{v:,.6f}"))+'</section>')
    loaded_js=False
    def chart(data,xcol,ycol,color,title):
        nonlocal loaded_js
        if data.empty or not data[ycol].notna().any():return
        safe=data.copy()
        for col in safe.select_dtypes(include="object"):
            safe[col]=safe[col].map(lambda v:str(v).replace('<','‹').replace('>','›'))
        fig=px.bar(safe,x=xcol,y=ycol,color=color,barmode="stack",title=title,color_discrete_sequence=["#f58220","#12395b","#3977a6","#e5a351","#4d948a","#7e6599"])
        fragments.append(fig.to_html(full_html=False,include_plotlyjs=True if not loaded_js else False))
        loaded_js=True
    fragments.append('<h2>Interpretation and key findings</h2>')
    if not packed.empty:
        coverage=int(packed.weight_tonnes.count())
        ton=packed.weight_tonnes.sum(min_count=1);ton_text="Unknown" if pd.isna(ton) else f"{ton:,.3f}"
        fragments.append(f'<p>The final handover evidence contains <strong>{packed.wo_key.nunique():,} distinct packed WOs</strong> and <strong>{packed.quantity.sum(min_count=1):,.0f} pieces</strong> in the selected period. Known weights total <strong>{ton_text} tonnes</strong>, with usable weights on {coverage:,} of {len(packed):,} source rows. Missing weights are not estimated or replaced with zero.</p>')
        p=set(plans.loc[(plans.section=='Packing')&(plans.quantity>0),'wo_key']);a=set(packed.wo_key)
        if p:
            fragments.append(f'<p>Packing planning covers {len(p):,} distinct WOs. The actual/plan WO-count ratio is {len(a)/len(p)*100:.2f}%; {len(p&a):,} WOs match the plan, {len(a-p):,} packed WOs are outside that period plan, and {len(p-a):,} planned WOs have no packing handover in the selected period. This compares evidence-period sets; it does not prove customer delivery punctuality or whole-order completion.</p>')
        cats=aggregate(packed,['category']).sort_values('weight_tonnes',ascending=False)
        if not cats.empty and cats.weight_tonnes.notna().any():
            top=cats.iloc[0]
            fragments.append(f'<p>The largest final-output category by known weight is <strong>{escape(str(top.category))}</strong>: {top.weight_tonnes:,.3f} tonnes and {top.pieces:,.0f} pieces. Category WO counts are distinct inside each category and may overlap if source classifications conflict.</p>')
    else:
        fragments.append('<p>No valid final packing handover is recorded for this selection. This is missing evidence, not a certified zero-production result.</p>')
    if not packed.empty:
        table('Final actual packing summary',pd.DataFrame([dict(Distinct_WOs=packed.wo_key.nunique(),Pieces=packed.quantity.sum(min_count=1),Known_weight_tonnes=packed.weight_tonnes.sum(min_count=1),Source_rows=len(packed),Weight_known_rows=packed.weight_tonnes.count())]))
    for basis,data in [('Section handover output',output),('Approved production plans',plans)]:
        t=aggregate(data,['section','category']);table(basis+' by section and category',t)
        for measure in ['weight_tonnes','pieces','distinct_WOs']:chart(t,'section',measure,'category',basis+' — '+measure)
        table(basis+' by month and section',aggregate(data,['month','section','category']))
        table(basis+' by ISO week and section',aggregate(data,['week','section','category']))
        table(basis+' by customer and section',aggregate(data,['section','customer']))
        if not data.empty:
            data=data.copy();data['size']=data.apply(lambda r:' × '.join('?' if pd.isna(r[k]) else f'{r[k]:g}' for k in ['D','T','H']),axis=1)
            table(basis+' by source-backed part size',aggregate(data,['section','category','size','dimension_basis']))
    for period in ['week','month']:
        p=aggregate(packed,[period,'category']);table('Final actual packing by '+period+' and category',p)
        for measure in ['weight_tonnes','pieces','distinct_WOs']:chart(p,period,measure,'category','Final packing only — '+period+' '+measure)
    reconciliation=[]
    for section in sorted(set(x.section)):
        p=set(plans.loc[(plans.section==section)&(plans.quantity>0),'wo_key']);a=set(output.loc[(output.section==section)&(output.quantity>0),'wo_key'])
        reconciliation.append(dict(Section=section,Planned_WOs=len(p) if p else None,Output_WOs=len(a) if a else None,Matched=len(p&a),Planned_not_output=len(p-a),Outside_plan=len(a-p),Output_vs_plan_percent=len(a)/len(p)*100 if p else None))
    table('Plan versus output — distinct WO reconciliation',pd.DataFrame(reconciliation))
    wip,qc=reference_views(frame)
    if not wip.empty:
        t=wip.groupby(['section','category']).agg(WOs=('wo','nunique'),Source_balance_pieces=('source_balance_pieces',lambda s:s.sum(min_count=1)),Source_balance_tonnes=('source_balance_tonnes',lambda s:s.sum(min_count=1)),Review_rows=('needs_review','sum')).reset_index()
        table('WIP snapshot — not period production; negatives retained',t)
    if not qc.empty:
        qc['date']=pd.to_datetime(qc.date,errors='coerce');qc=qc[qc.date.between(pd.Timestamp(start),pd.Timestamp(end))]
        table('QC evidence — not deducted again from handovers',qc)
    flags=[]
    for _,row in frame[frame.basis.ne('Reference / QC / WIP')].iterrows():
        for issue in row.issues if isinstance(row.issues,list) else []:
            flags.append(dict(Sheet=row.sheet,Row=row.excel_row,WO=row.wo,Issue=issue,Raw_weight=row.weight_raw,Interpreted_unit=row.weight_unit,Normalised_tonnes=row.weight_tonnes))
    table('Data quality — all source periods, including invalid dates',pd.DataFrame(flags))
    table('Source provenance and revisions',sources.drop(columns=['inventory','config'],errors='ignore'))
    fragments.append('<p>Preparation has no เตรียมReport sheet in this source. Report เตา contains substantial attendance/activity text without WO quantities; no missing plan quantities are invented. Customer and dimensional enrichment uses an unambiguous exact normalised WO match; missing matches remain Unknown. This is source evidence analysis, not scheduling-feasibility or stock certification.</p></body></html>')
    return ''.join(fragments).encode('utf-8')
