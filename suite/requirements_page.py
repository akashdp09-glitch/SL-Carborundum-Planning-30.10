"""Persistent bilingual scenario editor for bond/material plans."""
import datetime as dt, json, sqlite3, uuid
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
import streamlit as st
from .requirements_engine import net_requirements,seed_demands,explode_recipe,DEMAND_COLUMNS,STOCK_COLUMNS,RECEIPT_COLUMNS
from .exporters import to_workbook

def render(plan,plan_path,data,shared):
    th=st.session_state.get('global_language')=='ไทย'
    def T(en,thai): return thai if th else en
    st.subheader(T('Create dated bond / material plans','สร้างแผนบอนด์ / วัตถุดิบตามวันที่'))
    st.caption(T('Generate proposals from demand and confirmed supply. This is planning, not purchase release or a chemistry/formula designer.','คำนวณข้อเสนอจากความต้องการและปริมาณที่ยืนยันแล้ว เป็นแผนเสนอ ไม่ใช่การอนุมัติซื้อหรือออกแบบสูตรเคมี'))
    db=Path(shared)/'DATA'/'planning_scenarios.sqlite';db.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE IF NOT EXISTS scenarios(id TEXT PRIMARY KEY,name TEXT,created TEXT,payload TEXT)')
        saved=con.execute('SELECT id,name,created FROM scenarios ORDER BY created DESC').fetchall()
    st.caption(T('Saved scenarios and their full input snapshot: ','ที่จัดเก็บสถานการณ์และข้อมูลต้นฉบับ: ')+str(db.resolve()))
    labels={a[0]:a[1]+' · '+a[2] for a in saved}
    pick=st.selectbox(T('Saved scenario','สถานการณ์ที่บันทึก'),['New']+list(labels),format_func=lambda v:T('New scenario','สร้างใหม่') if v=='New' else labels[v],key='rpgen_saved')
    if pick!='New' and st.button(T('Restore selected inputs','เรียกคืนข้อมูลที่เลือก'),key='rpgen_restore'):
        with sqlite3.connect(db) as con: payload=json.loads(con.execute('SELECT payload FROM scenarios WHERE id=?',(pick,)).fetchone()[0])
        st.session_state['rpgen_payload']=payload;st.session_state['rpgen_generation']=uuid.uuid4().hex;st.rerun()
    payload=st.session_state.get('rpgen_payload',{})
    kind=st.selectbox(T('Plan type','ประเภทแผน'),['Bond','Material'],index=0 if payload.get('kind','Bond')=='Bond' else 1,key='rpgen_kind')
    if st.button(T('Start with active Plan-2026 demand','เริ่มจากความต้องการใน Plan-2026'),key='rpgen_seed',disabled=plan is None or plan.empty):
        dem=seed_demands(plan,kind,str(Path(plan_path).resolve()))
        codes=sorted(dem.code.unique())
        inv=pd.DataFrame([[c,None,0,None,None,0,''] for c in codes],columns=STOCK_COLUMNS)
        # Seed known stock only, never use pending LAB as available inventory.
        try:
            from .planners import read_bond_mrp,read_material_stock
            path=Path(data)/('Bond-MRP-LATEST.xlsx' if kind=='Bond' else 'Stock-on-Hand-LATEST.xlsx')
            if path.exists():
                stock=read_bond_mrp(path) if kind=='Bond' else read_material_stock(path)
                for i,c in enumerate(codes):
                    q=stock[stock['bond' if kind=='Bond' else 'material'].astype(str).str.strip().str.upper()==c]
                    if len(q)==1:
                        inv.loc[i,'available_kg']=q.iloc[0]['on_hand_kg'] if kind=='Bond' else q.iloc[0]['stock_g']/1000
                        inv.loc[i,'lot_kg']=q.iloc[0]['lot_kg'] if kind=='Bond' and q.iloc[0]['lot_kg']>0 else None
                        inv.loc[i,'source']=str(path.resolve())+' | '+('Bond stock row' if kind=='Bond' else 'Abrasive stock row')
        except Exception as e: st.warning(T('Stock seed unavailable: ','ไม่สามารถดึงข้อมูลสต็อก: ')+str(e))
        st.session_state['rpgen_payload']={'kind':kind,'demand':dem.to_dict('records'),'inventory':inv.where(pd.notna(inv),None).to_dict('records'),'receipts':[]}
        st.session_state['rpgen_generation']=uuid.uuid4().hex;st.rerun()
    gen=st.session_state.setdefault('rpgen_generation',uuid.uuid4().hex)
    def frame(key,cols): return pd.DataFrame(payload.get(key,[]),columns=cols)
    cols=st.columns(3)
    name=cols[0].text_input(T('Scenario name','ชื่อสถานการณ์'),payload.get('name','Requirements plan'),key='rpgen_name_'+gen)
    today=cols[1].date_input(T('Planning date — Phan Thong, Chonburi','วันที่วางแผน'),dt.date.fromisoformat(payload['today']) if payload.get('today') else dt.datetime.now(ZoneInfo('Asia/Bangkok')).date(),key='rpgen_today_'+gen)
    end=cols[2].date_input(T('Horizon end (short / long term)','วันสิ้นสุดแผน (ระยะสั้น / ระยะยาว)'),dt.date.fromisoformat(payload['end']) if payload.get('end') else today+dt.timedelta(days=90),key='rpgen_end_'+gen)
    st.info(T('Edit demand or add new-project/forecast requirements in kg. Enter dates as YYYY-MM-DD or DD/MM/YYYY. Net only confirmed available stock; record incoming quantities separately with confirmed dates. Enter 0 lot size only if unrestricted ordering is approved. Lead time is calendar days.','แก้ไขหรือเพิ่มความต้องการจากโครงการใหม่ / พยากรณ์ในหน่วยกิโลกรัม ใช้วันที่ YYYY-MM-DD หรือ DD/MM/YYYY ใช้เฉพาะสต็อกพร้อมใช้ที่ยืนยันแล้ว แยกรายการรับเข้าพร้อมวันที่ยืนยัน ใส่ขนาดล็อต 0 เฉพาะกรณีอนุญาตให้สั่งได้โดยไม่จำกัดล็อต ระยะเวลาจัดหาใช้วันปฏิทิน'))
    titles={'code':'รหัส','need_date':'วันที่ต้องใช้','gross_kg':'ความต้องการรวม kg','reference':'เอกสารอ้างอิง','source':'แหล่งข้อมูล','basis':'หลักเกณฑ์','available_kg':'สต็อกพร้อมใช้ kg','safety_kg':'สต็อกสำรอง kg','lead_days':'ระยะเวลาจัดหา (วัน)','lot_kg':'ขนาดล็อต kg','minimum_order_kg':'ขั้นต่ำการสั่ง kg','receipt_date':'วันที่รับเข้า','receipt_kg':'ปริมาณรับ kg','confirmed':'ยืนยันแล้ว'}
    with st.form('rpgen_form_'+gen):
        st.markdown('**'+T('Demand: order / forecast / project','ความต้องการ: ใบสั่ง / พยากรณ์ / โครงการ')+'**')
        demand=st.data_editor(frame('demand',DEMAND_COLUMNS),num_rows='dynamic',key='rpgen_demand_'+gen,use_container_width=True,column_config={c:titles.get(c,c) for c in DEMAND_COLUMNS} if th else {})
        st.markdown('**'+T('Inventory and ordering rules','สต็อกและหลักเกณฑ์การสั่ง')+'**')
        inv=st.data_editor(frame('inventory',STOCK_COLUMNS),num_rows='dynamic',key='rpgen_inventory_'+gen,use_container_width=True,column_config={c:titles.get(c,c) for c in STOCK_COLUMNS} if th else {})
        st.markdown('**'+T('Dated confirmed receipts','รายการรับเข้าที่มีวันที่ยืนยัน')+'**')
        receipts=st.data_editor(frame('receipts',RECEIPT_COLUMNS),num_rows='dynamic',key='rpgen_receipts_'+gen,use_container_width=True,column_config={c:titles.get(c,c) for c in RECEIPT_COLUMNS} if th else {})
        recipe_cols=['bond','component','output_kg_per_batch','component_kg_per_batch','approved','source']
        st.markdown('**'+T('Optional approved bond recipes → component material requirements','สูตรบอนด์ที่อนุมัติ (ถ้ามี) → ความต้องการวัตถุดิบส่วนประกอบ')+'**')
        st.caption(T('For Bond scenarios only. Enter one batch output and each component kg per batch; source and approval required. No formula is guessed.','ใช้สำหรับแผนบอนด์ ระบุปริมาณผลิตต่อชุดและวัตถุดิบแต่ละชนิดต่อชุด ต้องมีแหล่งอ้างอิงและการอนุมัติ ไม่คาดเดาสูตร'))
        recipes=st.data_editor(pd.DataFrame(payload.get('recipes',[]),columns=recipe_cols),num_rows='dynamic',key='rpgen_recipes_'+gen,use_container_width=True)
        submit=st.form_submit_button(T('SAVE SNAPSHOT AND CALCULATE','บันทึกข้อมูลและคำนวณ'),type='primary')
    if submit:
        payload={'kind':kind,'name':name,'today':today.isoformat(),'end':end.isoformat(),'demand':json.loads(demand.to_json(orient='records')),'inventory':json.loads(inv.to_json(orient='records')),'receipts':json.loads(receipts.to_json(orient='records')),'recipes':json.loads(recipes.to_json(orient='records'))}
        stamp=dt.datetime.now(ZoneInfo('Asia/Bangkok')).isoformat();sid=uuid.uuid4().hex
        with sqlite3.connect(db) as con:con.execute('INSERT INTO scenarios VALUES(?,?,?,?)',(sid,name,stamp,json.dumps(payload,ensure_ascii=False)))
        st.session_state['rpgen_payload']=payload
        st.success(T('Inputs saved permanently; restore them above after changing pages.','บันทึกข้อมูลถาวรแล้ว สามารถเรียกคืนด้านบนเมื่อเปลี่ยนหน้า'))
    # Calculate only a saved snapshot, not a silently changed/recomputed draft.
    p=st.session_state.get('rpgen_payload')
    if not p or not p.get('today'): return
    try:
        ledger,orders,issues=net_requirements(pd.DataFrame(p['demand'],columns=DEMAND_COLUMNS),pd.DataFrame(p['inventory'],columns=STOCK_COLUMNS),pd.DataFrame(p['receipts'],columns=RECEIPT_COLUMNS),p['today'],p['end'])
        st.caption(T('Results from saved snapshot: ','ผลจากข้อมูลที่บันทึก: ')+p['name']+' | '+p['today']+' → '+p['end'])
        st.markdown('**'+T('Purchase / bond preparation proposals','ข้อเสนอการซื้อ / เตรียมบอนด์')+'**');st.dataframe(orders,use_container_width=True,hide_index=True)
        st.markdown('**'+T('Dated demand / confirmed supply / proposed balances','ความต้องการ / รับเข้าที่ยืนยัน / ยอดคาดการณ์รายวัน')+'**');st.dataframe(ledger,use_container_width=True,hide_index=True)
        if not ledger.empty:st.line_chart(ledger.groupby('date')[['gross_need_kg','confirmed_receipts_kg','proposal_kg']].sum())
        if not issues.empty:st.warning(T('Review diagnostics before releasing any plan.','ตรวจสอบรายการปัญหาก่อนอนุมัติแผน'));st.dataframe(issues,use_container_width=True,hide_index=True)
        notes=pd.DataFrame([['Snapshot',p['name']],['Method','Firm stock excludes proposals; proposed balance includes hypothetical purchases; no substitutions.'],['Demand basis','Seed uses full unconsumed-WO source totals; replace with verified remaining need and Mixing/preparation need date.'],['Availability','Confirmed dated receipts only; LAB/held supply excluded. Same-day receipts precede demand.'],['Lead time','Calendar days; release before today flagged expedite, never assumed feasible.'],['Approval','Proposal only; recipe, supplier, material release and procurement authorization required.']],columns=['Property','Value'])
        sheets={'Proposals':orders,'Dated ledger':ledger,'Diagnostics':issues,'Demand inputs':pd.DataFrame(p['demand']),'Stock rules':pd.DataFrame(p['inventory']),'Receipt inputs':pd.DataFrame(p['receipts']),'Basis':notes}
        if p['kind']=='Bond' and not orders.empty and p.get('recipes'):
            components,recipe_issues=explode_recipe(orders,pd.DataFrame(p['recipes']))
            sheets['Bond recipe inputs']=pd.DataFrame(p['recipes']);sheets['Component demand']=components;sheets['Recipe diagnostics']=recipe_issues
            st.markdown('**'+T('Bond batch component requirements','ความต้องการวัตถุดิบสำหรับผลิตบอนด์')+'**');st.dataframe(components,use_container_width=True,hide_index=True)
            if not recipe_issues.empty:st.dataframe(recipe_issues,use_container_width=True,hide_index=True)
        if not ledger.empty:
            dates=pd.to_datetime(ledger['date'])
            for period,label in [('W-SUN','Weekly'),('M','Monthly'),('Q','Quarterly'),('Y','Yearly')]:
                q=ledger.copy();q['period']=dates.dt.to_period(period).astype(str)
                sheets[label+' requirements']=q.groupby(['code','period'],as_index=False)[['gross_need_kg','confirmed_receipts_kg','proposal_kg']].sum()
            q=ledger.copy();q['period']=dates.dt.year.astype(str)+'-H'+((dates.dt.month-1)//6+1).astype(str)
            sheets['Half-year requirements']=q.groupby(['code','period'],as_index=False)[['gross_need_kg','confirmed_receipts_kg','proposal_kg']].sum()
        st.download_button(T('Download complete plan and analysis','ดาวน์โหลดแผนพร้อมการวิเคราะห์'),to_workbook(sheets),file_name=f'{p["kind"]}_Generated_Plan.xlsx',key='rpgen_download')
    except Exception as e:st.error(T('Planning diagnostic: ','ข้อผิดพลาดในการวางแผน: ')+str(e))
