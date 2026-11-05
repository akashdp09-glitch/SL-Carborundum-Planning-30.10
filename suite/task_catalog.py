"""One visible bilingual directory; destinations render only after navigation."""
from __future__ import annotations
import html

TASKS = [
 ('Production / ฝ่ายผลิต','labels','▦','สร้าง QR · พิมพ์ป้าย','QR labels · print','One WO, selected WOs, all WOs and temporary tracking IDs'),
 ('Production / ฝ่ายผลิต','drying','🌬️','ยืนยันการอบแห้ง','Confirm drying readiness','Ready quantity, actual completion date, source and reason; shared by planners'),
 ('Production / ฝ่ายผลิต','floor','🔫','สแกน · เปิด/ปิดแผนก','Scan · section OPEN/CLOSED','USB scanner / keyboard; saved user, time, reason and event ID'),
 ('Production / ฝ่ายผลิต','audit','📸','ตรวจนับ WIP · ถ่ายภาพ','Physical WIP audit','Known / unidentified parts, photos, location; observations remain separate from production'),
 ('Production / ฝ่ายผลิต','audits','📋','ทะเบียนชิ้นงาน · ประวัติ','Part register · history','Filter, review, correct with reasons, link unidentified parts, export'),
 ('Production / ฝ่ายผลิต','report','📊','รายงานตรวจนับ','Audit analysis','Audit quantities, location, discrepancies and evidence'),
 ('Planning / วางแผน','daily','📅','แผนรายวัน · ทุกกระบวนการ','Daily plan · all processes','Preparation, mixing, forming, firing, grinding/cutting, cleaning and packing'),
 ('Planning / วางแผน','firing','🔥','แผนเผา · รูปแบบการวาง','Firing plan · loading views','Kiln programs, capacity, previous issued loads, top/front views, review and download'),
 ('Planning / วางแผน','newplan','🆕','แผนงานใหม่','New-part plan','Route, drying, lead times, resources, gaps and saved scenarios'),
 ('Planning / วางแผน','mps','🗓️','แผนหลัก','Master production plan','Forecast and future demand'),
 ('Planning / วางแผน','material','📦','สต็อกวัตถุดิบ','Material stock','Availability, shortages and source evidence'),
 ('Planning / วางแผน','mrp','🧪','ความต้องการวัตถุดิบ','Material requirements','Demand, stock, receipts, reservations and purchase proposals'),
 ('Planning / วางแผน','pack','📦','แผนบรรจุ','Packaging plan','Packing standards and requirements'),
 ('Planning / วางแผน','capacity','⚖️','มาตรฐานกำลังผลิต','Capacity standards','Native units, source cells, resources and unresolved gaps'),
 ('Planning / วางแผน','capacity_actual','📈','กำลังผลิต · แผน · ผลจริง','Capacity · plan · actual','Comparable units and utilization by section'),
 ('Planning / วางแผน','suite','🧰','เครื่องมือวางแผน','Planning tools','Additional planning, material and export tools'),
 ('Reports / รายงาน','daily_closed','📋','รายงานเปิด/ปิด','Open/closed report','Source workbook and saved section history'),
 ('Reports / รายงาน','wip','🏭','WIP แผนและฝ่ายผลิต','Planning / production WIP','Compare separate planning, production and audit evidence'),
 ('Reports / รายงาน','daily_status','📡','สถานะรายวัน','Daily status analysis','Section workbook analysis'),
 ('Reports / รายงาน','kpi','🎯','KPI แผนก','Department KPI','Accuracy 15; plan vs packed WOs 10; closed/opened WOs 15'),
 ('Reports / รายงาน','production_analysis','📊','วิเคราะห์ข้อมูลฝ่ายผลิต','Production evidence analysis','Section/category/customer/size/week/month; tonnes, pcs and WOs'),
 ('Reports / รายงาน','cost','💰','ต้นทุน','Cost analysis','Material and planning costs'),
 ('Reports / รายงาน','back','🚨','งานค้างส่ง','Backorders','Shared overdue calculation, closure and due-date basis'),
 ('Reports / รายงาน','daily_recovery','🧯','แผนกู้คืนรายสัปดาห์','Weekly recovery','Actions, owners, dates and saved reasons'),
 ('Reports / รายงาน','recovery_review','📄','ติดตามแผน Recovery','Recovery review','Production commitments, source status and WO reconciliation'),
 ('Data / ข้อมูล','src','📥','ไฟล์ต้นทาง · อัปโหลดครั้งเดียว','Sources · upload once','Active originals, revisions, import user/time, source paths and storage'),
 ('Data / ข้อมูล','history','🕘','ประวัติการใช้งาน · แก้ไข','Usage / edit history','Who changed what, when, with source and reason'),
 ('Data / ข้อมูล','knowledge','📚','ความรู้ · วิธีใช้งาน F1','Knowledge · F1 help','Thai/English source-backed help and approved rules'),
 ('Data / ข้อมูล','accounts','👥','บัญชีผู้ใช้ · แผนก','Accounts · sections','Existing shared accounts and section defaults'),
]


def render(st, href, *, compact=False):
    st.subheader('🧭 เลือกงาน / Choose your task')
    if compact:
        chosen=[x for x in TASKS if x[1] in {'floor','audit','daily','firing','production_analysis','src'}]
        groups=[('Tasks',chosen)]
    else:
        query=st.text_input('🔎 ค้นหางาน / Find a function',key='task_catalog_search',placeholder='USB, WIP, history, drying, KPI, ประวัติ…').strip().casefold()
        filtered=[x for x in TASKS if not query or query in ' '.join(x).casefold()]
        groups=[(g,[x for x in filtered if x[0]==g]) for g in dict.fromkeys(x[0] for x in filtered)]
        if not groups:st.info('ไม่พบงาน / No matching function')
    for group,rows in groups:
        if not compact:st.markdown('#### '+group)
        cards=[]
        for _,page,icon,th,en,detail in rows:
            cards.append(f'<a class="sl-task-card" href="{html.escape(href(page),quote=True)}" target="_self"><span aria-hidden="true">{icon}</span><b>{th}</b><strong>{en}</strong>'+('' if compact else f'<small>{html.escape(detail)}</small>')+'</a>')
        st.markdown('<div class="sl-task-grid">'+''.join(cards)+'</div>',unsafe_allow_html=True)
    if compact:st.link_button('🧭 ทุกฟังก์ชัน / All functions',href('more'),use_container_width=True)
