"""Bilingual (Thai / English) F1 help.

Sources, in priority order:
  1. APPROVED_RULES   - knowledge/approved_rules.json (factory-approved rules; each names the code that implements it)
  2. ENTRIES          - curated how-to / definition entries; each cites the file (and page/slide) it comes from
  3. DOCUMENTS        - knowledge/DOCUMENT_EXTRACTION.json (text + OCR of the supplied PDFs/PPTX, with page/slide references)
  4. RECORDS          - knowledge/knowledge_base.sqlite (Plan / WO / recipe rows) when that database is installed
  5. CODE             - function names
Answers are returned in the language of the question first and always carry their citation. Text that came from
OCR, or from a page/slide flagged for review, is labelled UNVERIFIED. The absence of the knowledge database or of a
referenced source is reported, never papered over.
"""
from __future__ import annotations

import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

_THAI = re.compile(r"[\u0e00-\u0e7f]")


def is_thai(s: str) -> bool:
    return bool(_THAI.search(str(s or "")))


def _tok(s):
    s = str(s).lower()
    out = [t for t in re.split(r"[^0-9a-z\u0e00-\u0e7f]+", s) if len(t) > 1]
    res = []
    for t in out:
        if is_thai(t) and len(t) > 4:
            try:
                from pythainlp.tokenize import word_tokenize
                res += [w for w in word_tokenize(t, engine="newmm") if len(w) > 1 and w.strip()]
                continue
            except Exception:  # noqa: BLE001
                pass
        res.append(t)
    return res


def _e(id_, en_t, th_t, en, th, cites, rules=()):
    return {"id": id_, "en_title": en_t, "th_title": th_t, "en": en, "th": th, "cites": list(cites), "rules": list(rules)}


ENTRIES = [
    _e("usb_scanner", "USB scanner: OPEN CLOSED, audit and safe retry", "สแกน USB เปิดปิดแผนก ตรวจ WIP และส่งซ้ำอย่างปลอดภัย",
       "Open All functions > Scan section status. USB keyboard scanner is supported as keyboard input: focus Scan WO, scan the full label, then Enter (or Find). SLWO labels and legacy URLs resolve exact identities; ambiguous/partial matches require search and confirmation. Select section and OPEN/CLOSED, enter actual pieces (blank is unknown), then Save. Success appears only after commit. Retry a retained unconfirmed submission with the same ID; never start a duplicate entry. Physical audit and production events have separate buttons/history. Section completion does not close the whole WO or count packed output. No special USB driver integration is claimed; verify keyboard/HID mode and Enter suffix on the factory PC.",
       "เปิดทุกฟังก์ชัน > สแกนสถานะแผนก เครื่อง USB ต่อ USB ใช้งานแบบแป้นพิมพ์ คลิกช่องสแกน สแกนป้ายเต็ม แล้วกด Enter หรือค้นหา ระบบไม่เลือกผลลัพธ์คลุมเครือเอง เลือกแผนก เปิด/ปิด ระบุจำนวนจริง เว้นว่างเมื่อไม่ทราบ แล้วบันทึก แสดงสำเร็จหลังฐานข้อมูลยืนยันเท่านั้น หากยังไม่ยืนยันให้ส่งรายการเดิมอีกครั้ง ไม่สร้างรายการซ้ำ การตรวจนับและเหตุการณ์ผลิตแยกกัน การปิดแผนกไม่ปิดใบสั่งทั้งใบ ต้องทดสอบโหมดแป้นพิมพ์และ Enter บนเครื่องโรงงาน",
       ["suite/scanner_lookup.py", "suite/floor_open_close.py", "apps/mobile/static/scan.js", "docs/RC29_54_SCANNER_AND_PLANNING.md"], ["DATA-1", "CLOSE-2"]),
    _e("drying_readiness", "Drying curing readiness before firing", "ยืนยันการอบแห้งก่อนเผา",
       "Firing WIP and เข้าเผา do not prove drying is completed. All functions > Confirm drying readiness retains actual completion date, ready pieces, source, reason and user. It is a quantity snapshot, not new production. Daily and Firing reuse it; a revised imported WO requires reconfirmation. Current capacity workbook Lead Time cells govern category route offsets; the exact-WO Q26-009 calendar exception stays scoped to that WO. Working-day interpretation of unspecified source days is explicit and provisional. Missing oven capacity/staffing is not invented, and unresolved loads are downloadable for review.",
       "WIP เผาและเข้าเผาไม่ได้ยืนยันว่าอบเสร็จ เปิดทุกฟังก์ชัน > ยืนยันการอบแห้ง ระบุวันที่เสร็จจริง จำนวนพร้อม หลักฐาน เหตุผล และผู้บันทึก เป็นยอดสถานะ ไม่ใช่ยอดผลิตเพิ่ม แผนรายวันและแผนเผาใช้ร่วมกัน เมื่อใบสั่งต้นทางเปลี่ยนต้องยืนยันใหม่ ใช้ Lead Time จากไฟล์กำลังผลิตปัจจุบัน กฎเฉพาะ Q26-009 ใช้เฉพาะใบสั่งนั้น วันในต้นทางไม่ระบุชนิด จึงแสดงสมมติฐานวันทำงานและสถานะชั่วคราว ไม่สมมติกำลังเตาอบหรือพนักงาน ดาวน์โหลดรายการที่ต้องตรวจสอบได้",
       ["suite/drying_confirmations.py", "suite/drying_gate.py", "suite/lead_time_source.py", "apps/daily/lead_time_control_v1.py"], ["CAP-1", "DATA-1"]),

    _e("closure", "Order closed vs section closed (backorder)", "ใบสั่งปิด กับ ฝ่ายปิด (ค้างส่ง)",
       "A whole order (WO) is CLOSED when Packing Status (column EU) is closed OR the production closure 'ปิดของผลิต' (column FC) is closed/cancelled. "
       "Preparation, Mixing, Forming, Firing and Grinding closures only mean that section finished; they never close the order. "
       "Backorder = order not closed, remaining packed qty > 0, and due date (E, else C) earlier than today (Asia/Bangkok, computed each time). "
       "Blank or #N/A in FC means 'not recorded', not closed.",
       "ใบสั่งผลิต (WO) ถือว่าปิดเมื่อสถานะบรรจุ (คอลัมน์ EU) ปิด หรือ 'ปิดของผลิต' (คอลัมน์ FC) ปิด/ยกเลิก "
       "การปิดฝ่ายเตรียม ผสม ขึ้นรูป เผา เจียร หมายถึงฝ่ายนั้นเสร็จเท่านั้น ไม่ได้ปิดใบสั่ง "
       "ค้างส่ง = ใบสั่งที่ยังไม่ปิด ยังมีจำนวนบรรจุคงเหลือ และกำหนดส่ง (E ถ้าไม่มีใช้ C) เกินวันนี้ (เวลา Asia/Bangkok คำนวณทุกครั้ง) "
       "ค่าว่างหรือ #N/A ใน FC แปลว่ายังไม่บันทึก ไม่ใช่ปิด",
       ["apps/daily/README_V1_9_30_PLAN2026_KPI_VERTICAL_NAV.txt", "suite/closure_rules.py"], ["CLOSE-1", "CLOSE-2", "DATE-1"]),
    _e("capacity", "Capacity: units and time basis", "กำลังการผลิต: หน่วยและฐานเวลา",
       "Capacity is read from CAPACITY_DATABASE.xlsx (sheets CAP ผสม, CAP ขึ้นรูป, Cap เตา, Cap เจีย, Set Up Time, Cap บรรจุ, กำลังคนแผนกผลิต, Lead Time). "
       "Every value keeps its source unit (tonne, pieces, mills, kilns) and time basis, with sheet and cell. Tonnes, pieces and mill counts are never added together. "
       "Mixing capacity is the number of mills per day only (owner decision); a mill count is not converted to batches, kg or tonnes. Tonne->kg uses 1 t = 1,000 kg (metric tonne, confirmed by the owner). Forming: on sheet rows 28, 33, 38, 40-43 the hourly rate is the approved figure; machines in cells D7-12, D15, D19, D25-26, D32 are not working now (editable list with history). Resin firing is for the PB group only (2 days running time; the workbook says 3 days, both are shown). Pieces->weight needs a part-specific weight at the right stage. "
       "If a conversion or cycle time is missing the planner names the gap and gives only a PROVISIONAL scenario; it never says 'feasible'.",
       "อ่านกำลังการผลิตจาก CAPACITY_DATABASE.xlsx (ชีต CAP ผสม, CAP ขึ้นรูป, Cap เตา, Cap เจีย, Set Up Time, Cap บรรจุ, กำลังคนแผนกผลิต, Lead Time) "
       "ทุกค่าเก็บหน่วยและฐานเวลาต้นทาง พร้อมชีตและเซลล์ ห้ามรวมตัน ชิ้น และจำนวนโม่เข้าด้วยกัน จำนวนโม่ไม่ใช่จำนวนแบทช์ต่อวัน "
       "ตัน->กก. ใช้ 1 ตัน = 1,000 กก. (เมตริกตัน เจ้าของยืนยันแล้ว) งานผสมนับเป็นจำนวนโม่ต่อวันเท่านั้น ไม่แปลงเป็นแบทช์ กก. หรือตัน งานขึ้นรูปแถว 28, 33, 38, 40-43 ใช้อัตราต่อชั่วโมง เครื่องที่เซลล์ D7-12, D15, D19, D25-26, D32 ไม่ทำงานตอนนี้ (แก้ไขรายการได้และมีประวัติ) เตาเรซิ่นใช้กับกลุ่ม PB เท่านั้น (เดินเตา 2 วัน ไฟล์ระบุ 3 วัน แสดงทั้งสองค่า) ชิ้น->น้ำหนัก ต้องมีน้ำหนักเฉพาะชิ้นงานในขั้นตอนที่ถูกต้อง "
       "ถ้าขาดค่าแปลงหรือรอบเวลา ระบบจะระบุช่องว่างและให้เฉพาะแผนชั่วคราว ไม่ระบุว่า 'ทำได้'",
       ["apps/daily/CAPACITY_DATABASE.xlsx", "suite/capacity.py", "knowledge/owner_decisions.json"], ["CAP-1", "CAP-2", "CAP-3", "CAP-4", "CAP-5", "CAP-6", "CAP-7", "CAP-8", "CAP-9"]),
    _e("mps_mrp", "New part / MPS-MRP planning", "แผนชิ้นงานใหม่ / MPS-MRP",
       "Planning Suite > New part / MPS-MRP. Start date = today in Asia/Bangkok (never a date copied from an older order). Sunday is non-working and holidays are selected in the calendar box (saved list with user and reason). Route lead times come from the capacity workbook as elapsed days "
       "(optimistic and conservative). Firm demand (work orders / confirmed orders) and forecast are kept apart; forecast is netted by firm orders of the same product and month "
       "(confirmed by the owner; stated in every export). Existing capacity bookings and material reservations are subtracted before a shortage is reported. Statuses are PROVISIONAL / BLOCKED / LATE, never 'feasible'. "
       "Drafts and scenarios are saved in <SL_SHARED_ROOT>/DATA/newpart_scenarios.sqlite (bond/material scenarios stay in DATA/planning_scenarios.sqlite) and exports list their inputs.",
       "Planning Suite > New part / MPS-MRP วันเริ่มต้น = วันนี้ตามเวลา Asia/Bangkok (ไม่คัดลอกวันที่จากใบสั่งเก่า) วันอาทิตย์ไม่ทำงาน และเลือกวันหยุดได้ในกล่องปฏิทิน (รายการที่บันทึกมีผู้ใช้และเหตุผล) ระยะเวลานำของแต่ละขั้นตอนอ่านจากไฟล์กำลังการผลิต (วันปฏิทิน แบบเร็วสุด/ช้าสุด) "
       "แยกความต้องการแน่นอน (ใบสั่ง/ออเดอร์ยืนยัน) ออกจากพยากรณ์ โดยหักพยากรณ์ด้วยออเดอร์จริงของสินค้าและเดือนเดียวกัน (เจ้าของยืนยันแล้ว ระบุในไฟล์ส่งออก) "
       "หักการจองกำลังการผลิตและการจองวัตถุดิบที่มีอยู่ก่อนรายงานของขาด สถานะมี PROVISIONAL / BLOCKED / LATE ไม่มีคำว่า 'ทำได้' "
       "บันทึกฉบับร่างและฉากทัศน์ใน <SL_SHARED_ROOT>/DATA/newpart_scenarios.sqlite (bond/material scenarios stay in DATA/planning_scenarios.sqlite)",
       ["suite/newpart_planner.py", "suite/capacity.py"], ["CAP-6", "CAL-1", "DATA-2", "DATE-1", "DATA-1"]),
    _e("sept", "September analysis: four separate measures", "วิเคราะห์เดือนกันยายน: สี่ตัวชี้วัดแยกกัน",
       "Sales requests received, production orders issued, requests not yet issued as production orders, and production item closures are four different counts "
       "(JOB_REGISTER_REFERENCE_SEP2026.xlsx, sheets Open Job and Close Job). They are never added or netted. Each figure shows its sheet and cell and is re-checked against the sheet's own Total cell.",
       "คำขอจากฝ่ายขาย ใบสั่งผลิตที่ออกแล้ว คำขอที่ยังไม่ออกใบสั่งผลิต และการปิดรายการผลิต เป็นสี่ตัวเลขที่ต่างกัน "
       "(JOB_REGISTER_REFERENCE_SEP2026.xlsx ชีต Open Job และ Close Job) ไม่นำมารวมหรือหักลบกัน ทุกตัวเลขระบุชีตและเซลล์ และตรวจกับเซลล์ Total ของชีต",
       ["apps/daily/JOB_REGISTER_REFERENCE_SEP2026.xlsx", "suite/sept_analysis.py"], ["CLOSE-2"]),
    _e("source_manager", "Where to import files (Source Manager)", "นำเข้าไฟล์ที่ไหน (Source Manager)",
       "Hub > Files & Traceability > Source Manager. Each source is imported once (SHA-256 duplicate check), the original and every revision are kept, and every module reads the same active copy. "
       "For current KPI evidence use Reports → Department KPI. It retains revised analyst, opening, separate closure, production section/category KPI and production-status originals in the evidence database. The old nine-measure form and combined opening/closure format are retired. Department and manager use the same three KPIs; only packing is final actual. "
       "There is one Daily Status workbook per section. The panel shows active file, timestamp and affected modules. "
       "The Plan workbook's sheet roles are found from headers, not from sheet order. Home asks for Plan-2026 first. Firing accepts either the complete workbook or only the issued Operator Print sheet when it contains Work Order, Kiln, Loading Date, planned quantity and Firing Complete/finish date. Firing, stock, forecast, capacity, job register, one Daily Status per section, Production WIP, the two KPI workbooks, packaging, recipe and costing files are offered only in the page that needs them. Update a source there; it immediately becomes the shared active revision, while history is kept.",
       "Hub > Files & Traceability > Source Manager นำเข้าแต่ละไฟล์ครั้งเดียว (ตรวจซ้ำด้วย SHA-256) เก็บไฟล์ต้นฉบับและทุกฉบับแก้ไข และทุกโมดูลอ่านไฟล์ที่ใช้งานอยู่ชุดเดียวกัน "
       "หลักฐาน KPI ปัจจุบันอยู่ที่ Reports → Department KPI เก็บไฟล์นักวิเคราะห์ ไฟล์เปิดใบงานและปิดใบงานแยกกัน รวมถึง KPI ฝ่ายผลิตและสถานะผลิตในฐานข้อมูล แบบเก่า 9 รายการและไฟล์เปิด/ปิดรวมถูกเลิกใช้ แผนกกับผู้จัดการใช้ KPI เดียวกัน 3 รายการ โดยใช้ผลแพ็คเป็นผลผลิตจริงขั้นสุดท้าย "
       "มี Daily Status หนึ่งไฟล์ต่อฝ่าย แผงแสดงไฟล์ เวลา และโมดูลที่เกี่ยวข้อง บทบาทชีตของไฟล์ Plan ดูจากหัวตาราง ไม่ใช่ลำดับชีต "
       "หน้า Home ขอ Plan-2026 เป็นไฟล์แรก ไฟล์แผนเตารับได้ทั้งสมุดงานฉบับเต็มหรือเฉพาะชีต Operator Print ที่ออกให้ฝ่ายผลิต หากมี Work Order, Kiln, Loading Date, จำนวนแผน และ Firing Complete/วันเผาเสร็จ ส่วนแผนเตา สต็อก พยากรณ์ กำลังผลิต ทะเบียนงาน Daily Status รายฝ่าย Production WIP ไฟล์ KPI สองชุด บรรจุภัณฑ์ สูตร และต้นทุน จะแสดงให้อัปโหลดเฉพาะหน้าที่ต้องใช้ อัปเดตที่หน้านั้นแล้วไฟล์ฉบับใหม่จะเป็นแหล่งข้อมูลกลางทันที และยังเก็บประวัติฉบับเดิมไว้",
       ["suite/source_manager.py", "suite/sheet_roles.py", "suite/central_paths.py"], ["SRC-1", "DATA-1"]),
    _e("planning_kpi", "Planning KPI scorecard and evidence", "KPI ฝ่ายวางแผนและหลักฐาน",
       "Reports → Department KPI automatically reuses retained evidence. KPI 1 analyst planning accuracy has 15 maximum marks; KPI 2 planned versus actual packed WOs has 10; KPI 3 closed/opened WOs for the same period has 15. Total maximum 40. Achievement percentages are not HR awarded marks. Opening and closure are separate revised files. Production section/category workbooks remain separate sources and are not added together. In Production Evidence Analysis, Report sheets are approved plans; only Pack จ่าย is final actual output. All normalised weights are metric tonnes; forming Report grams are divided by 1,000,000. Raw values, corrections, missing weights and source rows remain visible. Download the detailed offline English report from that page.",
       "Reports → Department KPI คำนวณจากหลักฐานที่เก็บไว้ KPI 1 ความถูกต้องของแผนจากนักวิเคราะห์เต็ม 15 คะแนน KPI 2 แผนเทียบใบงานแพ็คจริงเต็ม 10 คะแนน KPI 3 ใบงานปิดหารใบงานเปิดในช่วงเดียวกันเต็ม 15 คะแนน รวม 40 เปอร์เซ็นต์ผลงานไม่ใช่คะแนน HR ใช้ไฟล์เปิดและปิดใบงานแยกกัน ไฟล์ KPI ฝ่ายผลิตสองแบบเป็นคนละแหล่งห้ามบวกรวม ใน Production Evidence Analysis ชีต Report คือแผนที่ฝ่ายผลิตอนุมัติ และ Pack จ่าย เท่านั้นเป็นผลจริงขั้นสุดท้าย น้ำหนักแสดงเป็นตัน ชีต Report ขึ้นรูปที่เป็นกรัมหาร 1,000,000 เก็บค่าดิบ เหตุผลแปลงหน่วยและแถวต้นทางไว้ และดาวน์โหลดรายงานภาษาอังกฤษได้",
       ["suite/production_evidence.py", "suite/production_analysis_page.py", "docs/RC29_53_PRODUCTION_ANALYSIS.md"], ["SRC-1", "DATA-1"]),
    _e("daily_status", "Daily Status upload", "อัปโหลด Daily Status",
       "Upload each section workbook once in the compact Daily Status source panel on the Daily Open / Closed or Daily Status analysis page. Other pages reuse the active copy; the Daily Planner does not ask for a second upload. The sheet tab name is the production date. "
       "A WO-section is closed when cumulative actual >= required qty or balance <= 0 - that is SECTION completion, not order closure.",
       "อัปโหลดสมุดงานแต่ละฝ่ายเพียงครั้งเดียวในแผงแหล่งข้อมูล Daily Status บนหน้า Daily Open / Closed หรือ Daily Status Analysis ทุกหน้าจะใช้ไฟล์เดียวกันและ Daily Planner จะไม่ขออัปโหลดซ้ำ ชื่อแท็บชีต = วันที่ผลิต "
       "ฝ่ายของ WO ปิดเมื่อยอดสะสมจริง >= จำนวนที่ต้องการ หรือคงเหลือ <= 0 ซึ่งเป็นการเสร็จของฝ่าย ไม่ใช่การปิดใบสั่ง",
       ["apps/daily/daily_planner_app.py"], ["CLOSE-2", "SRC-1"]),
    _e("plan_columns", "Plan-2026 master sheet columns", "คอลัมน์ชีตหลักของ Plan-2026",
       "Master sheet 'แผนการเผา' (header row 3, data from row 4; found by header content). A=ProductionCode(WO), C=warehouse due, E=new due, P=BondType, BE=bond grams, BY=mills, CP=cuts per block, CQ=piece weight (g), "
       "FB=status text, FC=ปิดของผลิต, IA=ปิดของ Akash, IB=sales delivery date. Section closed flags: CY Preparation, DH Mixing, DR Forming, EC Firing, EL Grinding/Cutting, EU Packing (informational except EU).",
       "ชีตหลัก 'แผนการเผา' (หัวตารางแถว 3 ข้อมูลเริ่มแถว 4 ตรวจจากหัวตาราง) A=รหัสผลิต(WO) C=กำหนดเข้าคลัง E=กำหนดส่งใหม่ P=ชนิด Bond BE=กรัม Bond BY=จำนวนโม่ CP=ตัด/ก้อน CQ=น้ำหนักชิ้น(กรัม) "
       "FB=สถานะ FC=ปิดของผลิต IA=ปิดของ Akash IB=กำหนดส่งฝ่ายขาย แฟลกปิดรายฝ่าย CY เตรียม DH ผสม DR ขึ้นรูป EC เผา EL เจียร EU บรรจุ (เป็นข้อมูลประกอบ ยกเว้น EU)",
       ["suite/plan_reader.py"], ["CLOSE-1"]),
    _e("bond_plan", "Bond / material plan", "แผน Bond / วัตถุดิบ",
       "Planning Suite > Generate bond / material plans. Demand rows need code, need date, kg, a WO/project/forecast reference and basis. Inventory = confirmed available kg only (dated stock is evidence as of its date). "
       "Receipts: dated confirmed kg only. LAB-hold material is not available stock. Bond recipe components need an approved, source-linked formula; nothing is guessed.",
       "Planning Suite > Generate bond / material plans แถวความต้องการต้องมีรหัส วันที่ต้องใช้ กก. อ้างอิง WO/โครงการ/พยากรณ์ และเหตุผล สต็อก = ยอดพร้อมใช้ที่ยืนยันแล้วเท่านั้น (สต็อกคือหลักฐาน ณ วันที่ระบุ) "
       "ของรับเข้า: เฉพาะที่ยืนยันพร้อมวันที่ วัสดุรอผล LAB ไม่ใช่ของพร้อมใช้ ส่วนประกอบสูตร Bond ต้องมีสูตรที่อนุมัติและอ้างอิงแหล่งได้ ห้ามเดา",
       ["suite/requirements_engine.py"], ["CAP-6", "DATA-1"]),
    _e("material_status", "Find material status from Stock on Hand", "ค้นหาสถานะวัตถุดิบจาก Stock on Hand",
       "Fastest route: Home → Quick access → Material status, or Planning → Stock-on-Hand Material Status. This page reads the active shared Stock on Hand workbook directly and does not require running or rebuilding the Daily Plan. It shows status counts and a searchable all-material table with source sheet, Excel row, and balance column, plus a downloadable CSV carrying workbook revision/import time/SHA. Upload a revised stock workbook once from this page's source panel when needed; navigation reuses the active copy. Stock balance is not the same as a released work-order material-feasibility decision; BOM/recipe, required date, receipts and reservations also matter.",
       "เส้นทางเร็วที่สุด: Home → Quick access → Material status หรือ Planning → Stock-on-Hand Material Status หน้านี้อ่านไฟล์ Stock on Hand ฉบับที่ใช้งานร่วมกันโดยตรง ไม่ต้องสร้างหรือคำนวณ Daily Plan ใหม่ มีสรุปสถานะและตารางค้นหาวัตถุดิบทั้งหมด พร้อมชีตต้นทาง แถว Excel และคอลัมน์ยอดคงเหลือ รวมถึงดาวน์โหลด CSV ที่ระบุชื่อไฟล์ รุ่น เวลานำเข้า และ SHA หากต้องเปลี่ยนไฟล์ ให้อัปโหลดครั้งเดียวจากแผงไฟล์ของหน้านี้ ทุกหน้าจะใช้ฉบับเดียวกัน ยอดสต็อกยังไม่เท่ากับการยืนยันความพร้อมของ WO เพราะต้องตรวจ BOM/สูตร วันที่ต้องใช้ ของรับเข้า และการจองด้วย",
       ["apps/daily/daily_planner_app.py", "suite/source_manager.py", "Stock-on-Hand-LATEST.xlsx"], ["SRC-1", "DATA-1"]),
    _e("daily_by_section", "Daily plan by section", "แผนรายวันตามฝ่าย",
       "Queue = WOs whose current section is the chosen section, overdue first then due date. Capacity must come from the capacity registry or be typed in with its unit; the working calendar is explicit "
       "(no day is assumed to be a day off unless you list it). If capacity or a calendar is missing the table says so instead of inventing a rate.",
       "คิว = WO ที่อยู่ฝ่ายนั้น เรียงเกินกำหนดก่อน แล้วตามกำหนดส่ง กำลังการผลิตต้องมาจากทะเบียนกำลังการผลิตหรือกรอกพร้อมหน่วย ปฏิทินทำงานกำหนดชัดเจน "
       "(ไม่สมมติวันหยุดเอง นอกจากที่ระบุ) ถ้าไม่มีกำลังการผลิตหรือปฏิทิน ตารางจะแจ้งแทนการสร้างค่าเอง",
       ["suite/planners.py"], ["CAP-1", "CAP-6"]),
    _e("wo_number", "Work order (Factory no.) format", "รูปแบบเลขที่ผลิต (Factory no.)",
       "Factory no. = prefix + 3-digit sequence + '-' + DDMMYY (the date the order was OPENED, not a due date). Documented prefixes: P Vitrify made-to-order; PM Vitrify monthly continuous; PS Vitrify monthly made-to-order; "
       "PB Resin made-to-order; PBM Resin monthly continuous; PBS Resin monthly made-to-order. Resin cures at 170-185 C, Vitrify fires at 1180-1260 C. "
       "Example P005-150118 = Vitrify made-to-order, 5th order, opened 15 Jan 2018. Other prefixes/forms found in the Plan (e.g. PM007A010125) are NOT defined in the deck and are reported as undocumented.",
       "เลขที่ผลิต = อักษรนำ + ลำดับ 3 หลัก + '-' + ววดดปป (วันที่เปิดใบสั่ง ไม่ใช่กำหนดส่ง) อักษรนำที่มีในเอกสาร: P Vitrify สั่งทำ; PM Vitrify แผนรายเดือนต่อเนื่อง; PS Vitrify แผนรายเดือนสั่งทำ; "
       "PB Resin สั่งทำ; PBM Resin แผนรายเดือนต่อเนื่อง; PBS Resin แผนรายเดือนสั่งทำ Resin อบ 170-185 องศาเซลเซียส Vitrify เผา 1180-1260 องศาเซลเซียส "
       "ตัวอย่าง P005-150118 = Vitrify สั่งทำ ใบที่ 5 เปิด 15 ม.ค. 2018 รูปแบบอื่นที่พบใน Plan (เช่น PM007A010125) เอกสารไม่ได้กำหนดไว้ จึงรายงานว่าไม่มีคำนิยาม",
       ["การอ่านใบสั่งงานการผลิต.pptx slides 3-5", "suite/wo_codes.py"], ["DATE-1"]),
    _e("spec", "Reading a SPEC string", "อ่านค่า SPEC สินค้า",
       "Deck example WA60L8VB21351A152.4X3.17X31.75 = Abrasive WA, Grain 60, Structures L, Structures No. 8, Product/Type V, Bond/Type B21, M/Sec. 35, Shape 1A, Diameter 152.4, Thickness 3.17, Hold 31.75 (slide 6). "
       "Caution: the decoder is fitted to that single example; it matched only a small fraction of the SPEC values in the real Plan, so it is for reading help only and is not used in any calculation.",
       "ตัวอย่างในเอกสาร WA60L8VB21351A152.4X3.17X31.75 = Abrasive WA, Grain 60, Structures L, Structures No. 8, Product/Type V, Bond/Type B21, M/Sec. 35, Shape 1A, Diameter 152.4, Thickness 3.17, Hold 31.75 (สไลด์ 6) "
       "ข้อควรระวัง: ตัวถอดรหัสสร้างจากตัวอย่างเดียว ตรงกับ SPEC จริงใน Plan เพียงส่วนน้อย จึงใช้เพื่ออ่านประกอบเท่านั้น ไม่ใช้ในการคำนวณ",
       ["การอ่านใบสั่งงานการผลิต.pptx slide 6", "suite/wo_codes.py"], ["KNOW-1"]),
    _e("order_sheets", "The 10 parts of one production order", "ส่วนประกอบของใบสั่งผลิต 1 ใบ (10 ส่วน)",
       "Master sheet (ใบแม่), preparation, mixing, forming, firing/curing, grinding, label/packing, QC (grinding/screening and packaging), product QC, in-process control (slide 7). "
       "Slides 8-20 number each field on the forms and define it in a table; the call-out numbers are linked to those table rows, but their exact position on the form graphics was not interpreted (marked for review). "
       "The filled-in example 'ตัวอย่างการกรอกข้อมูล.xlsx' (slide 21) was NOT supplied.",
       "ใบแม่ ใบเตรียม ใบผสม ใบขึ้นรูป ใบอบ-เผา ใบเจียร ใบฉลาก/บรรจุ ใบตรวจสอบควบคุณภาพ (เจียร/คัดกรอง และบรรจุภัณฑ์) ใบตรวจสอบสินค้า QC ใบควบคุมสินค้าระหว่างผลิต (สไลด์ 7) "
       "สไลด์ 8-20 ใส่หมายเลขแต่ละช่องในแบบฟอร์มและอธิบายในตาราง ระบบเชื่อมหมายเลขกับแถวในตารางแล้ว แต่ตำแหน่งบนภาพแบบฟอร์มยังไม่ได้ตีความ (ต้องทบทวน) "
       "ไฟล์ตัวอย่างการกรอก 'ตัวอย่างการกรอกข้อมูล.xlsx' (สไลด์ 21) ไม่ได้ส่งมา",
       ["การอ่านใบสั่งงานการผลิต.pptx slides 7-21", "knowledge/DOCUMENT_EXTRACTION_REVIEW.csv"], ["KNOW-1"]),
    _e("mobile", "Mobile: WIP audit and part status", "มือถือ: ตรวจนับ WIP และสถานะชิ้นงาน",
       "Scan or search a WO, take photos, enter quantity and physical location, submit. A part with no WO or QR gets a temporary tracking ID (UNID-YYYYMMDD-XXXXX) which planning/supervisor can later link to the real part. "
       "Audit observations are stored separately from production transactions; retries with the same submission id are safe; reconciliation history is kept. Desktop shows the same register, photos, locations and history.",
       "สแกนหรือค้นหา WO ถ่ายรูป กรอกจำนวนและตำแหน่งจริง แล้วส่ง ชิ้นงานที่ไม่มี WO หรือ QR จะได้รหัสติดตามชั่วคราว (UNID-YYYYMMDD-XXXXX) ซึ่งฝ่ายวางแผน/หัวหน้างานเชื่อมกับชิ้นงานจริงภายหลังได้ "
       "ข้อสังเกตจากการตรวจนับเก็บแยกจากรายการผลิต ส่งซ้ำด้วยรหัสการส่งเดิมได้อย่างปลอดภัย เก็บประวัติการกระทบยอด เดสก์ท็อปเห็นทะเบียน รูป ตำแหน่ง และประวัติชุดเดียวกัน",
       ["apps/mobile/audit_v2.py", "docs/PERMISSION_MATRIX.md"], ["MOB-1", "PERM-1"]),
    _e("permissions", "Who can scan and submit audits", "ใครสแกนและส่งผลตรวจได้",
       "Every signed-in role may search, scan and submit part tracking across sections. Login is required and user/time are recorded. Submitted observations are immutable; submit a new observation and explain corrections in Notes. Anonymous users cannot submit.",
       "ทุกบทบาทที่ล็อกอินสามารถค้นหา สแกน และส่งข้อมูลติดตามชิ้นงานข้ามแผนกได้ ต้องล็อกอินและระบบเก็บชื่อผู้ใช้/เวลา รายการที่ส่งแล้วแก้ไขไม่ได้ หากต้องแก้ให้ส่งรายการใหม่พร้อมอธิบายใน Notes ผู้ใช้ที่ไม่ล็อกอินส่งข้อมูลไม่ได้",
       ["docs/PERMISSION_MATRIX.md"], ["PERM-1"]),
    _e("qr", "QR labels", "ป้าย QR",
       "Default QR content is SLWO:<WO ID> (not tied to an IP address). Existing printed QR labels are not rewritten or invalidated by a software update; the app accepts the established code and older URL QR codes. Scan photos are stored under <SL_PHOTO_ROOT>/QR_SCANS/YYYY/MM/DD on the app-server PC.",
       "เนื้อหา QR มาตรฐานคือ SLWO:<WO ID> (ไม่ผูกกับ IP) การอัปเดตโปรแกรมไม่เขียนทับหรือยกเลิกป้าย QR ที่พิมพ์แล้ว แอปรองรับรหัสเดิมและ QR แบบ URL รุ่นก่อน รูปสแกนเก็บที่ <SL_PHOTO_ROOT>/QR_SCANS/ปปปป/ดด/วว บนเครื่องเซิร์ฟเวอร์ของแอป",
       ["apps/mobile/app.py"], []),
    _e("dated_evidence", "Dated stock, WIP, plans and forecasts", "สต็อก WIP แผน และพยากรณ์ เป็นข้อมูลลงวันที่",
       "These are dated operational evidence, not permanent constants. Every import is stamped with its timestamp and SHA-256; every export states its as-of date and sources. "
       "'Today' is the current Thailand local date for Phan Thong, Chonburi, computed at the moment of use.",
       "ข้อมูลเหล่านี้เป็นหลักฐานเชิงปฏิบัติการลงวันที่ ไม่ใช่ค่าคงที่ ทุกการนำเข้ามีเวลาและ SHA-256 ทุกไฟล์ส่งออกระบุวันที่ ณ เวลานั้นและแหล่งข้อมูล 'วันนี้' คือวันที่ท้องถิ่นของโรงงานที่พานทอง ชลบุรี คำนวณตอนใช้งาน",
       ["knowledge/approved_rules.json"], ["DATA-1", "DATE-1"]),
    _e("production_wip_source", "Production WIP source and checks", "แหล่งข้อมูลและการตรวจสอบ Production WIP",
       "Production WIP is read from the second worksheet of each active section workbook. The summary's reported open count (ยังไม่ปิด) and GW (Kg) drive the WIP charts and totals. Total WO minus Closed WO is a separate consistency check; if it disagrees, the reported open count is retained and the row is flagged. Category F is displayed as P. Each row shows workbook, sheet and cell references.",
       "Production WIP อ่านจากแผ่นงานที่ 2 ของไฟล์แผนกฉบับใช้งาน จำนวนเปิดที่รายงาน (ยังไม่ปิด) และ GW (Kg) จากตารางสรุปเป็นค่าที่ใช้ในกราฟและยอดรวม Total WO ลบ Closed WO ใช้ตรวจสอบแยกต่างหาก หากไม่ตรง ระบบคงจำนวนเปิดตามรายงานและแจ้งให้ตรวจสอบ หมวด F แสดงเป็น P แต่ละแถวแสดงชื่อไฟล์ ชีต และเซลล์ต้นทาง",
       ["suite/production_wip_data.py", "apps/daily/production_wip_control.py"], ["DATA-1"]),
    _e("conflicts", "When approved sources disagree", "เมื่อแหล่งข้อมูลที่อนุมัติขัดแย้งกัน",
       "The system lists the exact conflicting entries (file / sheet / cell) and asks only for the decision it needs. It does not pick one silently. See the Capacity tab, 'Conflicts in the approved source'.",
       "ระบบแสดงรายการที่ขัดแย้งกันอย่างชัดเจน (ไฟล์ / ชีต / เซลล์) และถามเฉพาะสิ่งที่ต้องตัดสินใจ ไม่เลือกเองเงียบๆ ดูแท็บ Capacity หัวข้อ 'Conflicts in the approved source'",
       ["suite/capacity.py"], ["CONFLICT-1"]),
    _e("knowledge_db", "Knowledge database status", "สถานะฐานข้อมูลความรู้",
       "knowledge/knowledge_base.sqlite holds Plan / WO / recipe rows built from Excel workbooks. It is not in the source package. Restore it from the existing installation, or rebuild it with REBUILD_KNOWLEDGE_DATABASE.bat "
       "from the workbooks in COMPANY_DATA (the rebuild reads Excel only). The PDF/PPTX knowledge is separate: knowledge/DOCUMENT_EXTRACTION.json (text + OCR with page/slide references). OCR text is UNVERIFIED until reviewed.",
       "knowledge/knowledge_base.sqlite เก็บแถวข้อมูล Plan / WO / สูตร สร้างจากไฟล์ Excel ไม่อยู่ในชุดซอร์สโค้ด ให้กู้คืนจากเครื่องที่ติดตั้งอยู่เดิม หรือสร้างใหม่ด้วย REBUILD_KNOWLEDGE_DATABASE.bat "
       "จากไฟล์ใน COMPANY_DATA (การสร้างใหม่อ่านเฉพาะ Excel) ความรู้จาก PDF/PPTX แยกอยู่ที่ knowledge/DOCUMENT_EXTRACTION.json (ข้อความ + OCR พร้อมเลขหน้า/สไลด์) ข้อความ OCR ยังไม่ยืนยันจนกว่าจะทบทวน",
       ["knowledge/build_knowledge_db.py", "knowledge/DOCUMENT_EXTRACTION.json"], ["KNOW-1"]),
    _e("keys", "Keys", "ปุ่มลัด", "F1 = open this help search; ask in Thai or English. Sidebar > Planning Suite = planners and downloads.",
       "F1 = เปิดค้นหาความช่วยเหลือ ถามเป็นไทยหรืออังกฤษได้ แถบข้าง > Planning Suite = ตัววางแผนและดาวน์โหลด", ["hub.py"], []),
    _e("defect_codes", "Defect codes (cracks / chips / slump)", "รหัสของเสีย (ร้าว / บิ่น / ยุบ)",
       "From Defect Code.pptx (text extracted, not independently verified): 126 partial radial crack; 128 full radial (arbor to periphery); "
       "129 blind-radial / 124 chordal; 122 annular near OD / 123 annular near ID; 110 chipped, green bruise or broken; 121 laminated; 140 slumped after firing. "
       "Each slide lists Cause and Correction in English and Thai. Search F1 for the code number to see the extracted table.",
       "จาก Defect Code.pptx (ดึงข้อความแล้ว ยังไม่ได้ทวนสอบอิสระ): 126 ร้าวตามรัศมีบางส่วน; 128 ร้าวตามรัศมีทั้งเส้น (ขอบถึงรู); "
       "129 ร้าวในรัศมี / 124 ร้าวตั้งฉากรัศมี; 122 ร้าวโค้งใกล้ OD / 123 ใกล้ ID; 110 บิ่น ช้ำก่อนเผา หรือแตก; 121 ร้าวลอกชั้น; 140 ยุบหลังเผา "
       "แต่ละสไลด์มีสาเหตุและการแก้ไข ภาษาอังกฤษและไทย ค้นรหัสใน F1 เพื่อดูตารางที่ดึงมา",
       ["Defect Code.pptx slides 1-13"], ["KNOW-1"]),
    _e("resin_bond", "Resin bond types and storage (SD-PL-001)", "เรซิ่นบอนด์ ชนิดและการจัดเก็บ (SD-PL-001)",
       "Deck คุณสมบัติและการจัดเก็บ Resin Bond SD-PL-001: Resin bond is a chemically synthesised plastic/adhesive that holds abrasive; added at mixing. "
       "Powder: SP222 and SP227 are the usual standard (wet and dry); SP8686 is for fine grit, wet grinding only. Liquid: SW436, mixable with every powder. "
       "SP227 flow 37.5±2.5 mm, hexa 9±0.5%, apparent density 365 g/L. SP8686 flow 30±5 mm, hexa 6.5±0.5%. Liquid viscosity 650±150 mPa.s at 20 C. "
       "Liquid reaction in the oven starts 80-110 C; powder from 110 C; cross-link 110-185 C. If humid, liquid can start from 40 C before baking. "
       "Powder store in a dry room 18-20 C (not above 20 C), RH 60-65%, up to 6 months, 20 kg bags. Liquid store below 10 C (up to 3 months) or below 5 C (6-12 months); factory now stores at ≤5 C, 200 L drums, 5 L shop bottles labelled with lot/date.",
       "เอกสาร คุณสมบัติและการจัดเก็บ Resin Bond SD-PL-001: เรซิ่นบอนด์เป็นพลาสติกสังเคราะห์เหนียวเหมือนกาว ยึด abrasive เติมตอนผสม "
       "เรซิ่นผงที่ใช้มากคือ SP222 และ SP227 (เจียรเปียกและแห้ง) SP8686 สำหรับเบอร์ละเอียดเจียรเปียกอย่างเดียว เรซิ่นน้ำ SW436 ผสมกับผงได้ทุกชนิด "
       "SP227 ระยะไหล 37.5±2.5 มม. hexa 9±0.5% ความหนาแน่นปรากฏ 365 กรัม/ลิตร SP8686 ระยะไหล 30±5 มม. hexa 6.5±0.5% เรซิ่นน้ำความหนืด 650±150 mPa.s ที่ 20 องศา "
       "ปฏิกิริยาน้ำยาในเตาเริ่ม 80-110 องศา ผงเริ่ม 110 องศา ครอสลิงก์ 110-185 องศา ถ้าชื้นน้ำยาอาจเริ่มที่ 40 องศาก่อนอบ "
       "เก็บผงในห้องแห้ง 18-20 องศา (ไม่เกิน 20) ความชื้นสัมพัทธ์ 60-65% ได้ถึง 6 เดือน ถุง 20 กก. เก็บน้ำยาต่ำกว่า 10 องศา (3 เดือน) หรือต่ำกว่า 5 องศา (6-12 เดือน) โรงงานเก็บไม่เกิน 5 องศา ถัง 200 ลิตร และถัง 5 ลิตรติดล็อต/วันที่",
       ["คุณสมบัติและการจัดเก็บ Resin  Bond  SD-PL-001.pptx slides 3-11"], ["KNOW-1"]),
    _e("product_code", "Product code 11 vs 18 digits", "รหัสสินค้า 11 หลัก กับ 18 หลัก",
       "Handbook sheet 'คู่มือรหัสสินค้า2559' in the รายการสินค้าส่งขึ้นทะเบียน workbook: an 11-digit product code is finished goods ready to pack; "
       "an 18-digit code is finished goods ready to enter the warehouse. Position 1 (account group) includes 1 New Design, 2 Production, 3 Trading local, 4 New Item, 5 Trading import. "
       "Position 2 (product type): G grinding wheel, H honing, R rice-stone, F food-grind, S knife, T rubber-tapping knife, N snagging. "
       "A note on the register sheets says GC uses B04 when D=305 and T>=100, and when D>=405 and T>=76. That sentence is copied from the file; it is not a calculated rule.",
       "ชีต 'คู่มือรหัสสินค้า2559' ในไฟล์รายการสินค้าส่งขึ้นทะเบียน: รหัส 11 หลัก = สินค้าสำเร็จพร้อมบรรจุ รหัส 18 หลัก = สินค้าสำเร็จพร้อมเข้าคลัง "
       "ตำแหน่ง 1 กลุ่มบัญชี: 1 New Design, 2 Production, 3 Trading ในประเทศ, 4 New Item, 5 Trading นำเข้า "
       "ตำแหน่ง 2 ประเภท: G หินเจียร H หินขัด R หินสีข้าว F หินบดอาหาร S หินลับมีด T หินลับมีดกรีดยาง N Snagging "
       "หมายเหตุบนชีตรายการ: GC ใช้ B04 เมื่อ D=305 และ T>=100 และเมื่อ D>=405 และ T>=76 ประโยคนี้อยู่ในไฟล์ ไม่ได้คำนวณขึ้นเอง",
       ["Copy of รายการสินค้าส่งขึ้นทะเบียน Revice 2556(10-10-2026.xlsx sheet คู่มือรหัสสินค้า2559"], ["KNOW-1"]),
    _e("section_plans", "One plan, every section, no silent contradiction", "แผนเดียว ทุกฝ่าย ไม่ให้ตัวเลขขัดกันเงียบ ๆ",
       "The tracking workbook ไฟล์ติดตามงาน เบื้องต้น.xlsx lists one lot with columns for Preparation, Mixing, Forming and Kiln (date, qty, status) plus the same WO / due / customer / code / spec / qty. "
       "Plan-2026 already stores those section dates, qtys and closed flags on the master row. The software compares them: if a later section is done/closed while an earlier section is still open, or a section plan qty disagrees with the master qty, both figures are shown. Nothing is picked as the winner (CONFLICT-1).",
       "ไฟล์ติดตามงาน เบื้องต้น.xlsx ใส่ล็อตเดียวพร้อมคอลัมน์แผนเตรียม ผสม ขึ้นรูป เตา (วันที่ จำนวน สถานะ) และ WO / กำหนดเข้าคลัง / ลูกค้า / รหัส / สเปค / จำนวน "
       "Plan-2026 เก็บวันที่ จำนวน และแฟลกปิดของแต่ละฝ่ายไว้บนแถวเดียวกัน ระบบเทียบ: ถ้าฝ่ายหลังทำ/ปิดแล้วแต่ฝ่ายก่อนยังเปิด หรือจำนวนแผนฝ่ายไม่ตรงจำนวนแม่ ระบบแสดงทั้งสองค่า ไม่เลือกให้เอง (CONFLICT-1)",
       ["ไฟล์ติดตามงาน เบื้องต้น.xlsx sheet ติดตามแผนผลิต_TEST", "suite/plan_consistency.py"], ["CONFLICT-1", "CLOSE-2"]),
    _e("local_services", "Daily, Firing and the phone app are three programs", "แผนรายวัน แผนเตา และมือถือเป็นสามโปรแกรม",
       "The Planning Center window (port 8510) is only the hub. Daily Planner is a second program on port 8511, Firing on 8512, and the shop-floor phone app on HTTP 8000 (the page that opens). HTTPS 8443 is optional for the live camera. "
       "If a tab says '127.0.0.1 refused to connect', that program is not running on the factory PC — or a phone is opening 127.0.0.1, which means the phone itself, not the PC. "
       "On the factory PC double-click START_SL_CARBORUNDUM_PLANNING_CENTER.bat (first click installs Streamlit once, then it opens the hub). Leave that window open. The .sha256 file is only a download check and is not copied into the program folder. "
       "On a phone open http://FACTORY-PC-IP:8000/mobile (the factory LAN address, never 127.0.0.1). That HTTP page is the shop-floor app and does not need a certificate. Install ca.crt only if you want HTTPS camera access. "
       "QR labels are printed from the Home Plan-2026. The phone finds a work order from that same file and from CENTRAL_DATA\\DATABASE\\sl_planning.db. "
       "If the phone says the work order does not exist, tap Home → Load Plan-2026 into the phone database, and close Daily/Firing/phone windows from an older ZIP folder. "
       "This does not invent a Daily or Firing plan.",
       "หน้า Planning Center (พอร์ต 8510) เป็นหน้าศูนย์เท่านั้น แผนรายวันเป็นโปรแกรมที่สองที่พอร์ต 8511 แผนเตาที่ 8512 และแอปมือถือหน้างานที่ HTTP 8000 (หน้านี้เปิดได้ทันที) HTTPS 8443 เป็นทางเลือกสำหรับกล้อง "
       "ถ้าแท็บขึ้นว่า '127.0.0.1 refused to connect' แปลว่าโปรแกรมนั้นยังไม่ทำงานบนเครื่องโรงงาน หรือมือถือกำลังเปิด 127.0.0.1 ซึ่งหมายถึงตัวมือถือเอง ไม่ใช่เครื่องโรงงาน "
       "บนเครื่องโรงงานดับเบิลคลิก START_SL_CARBORUNDUM_PLANNING_CENTER.bat (ครั้งแรกจะติดตั้ง Streamlit ครั้งเดียว แล้วเปิดหน้าศูนย์) อย่าปิดหน้าต่างนั้น ไฟล์ .sha256 ใช้ตรวจการดาวน์โหลดเท่านั้น ไม่ต้องคัดลอกเข้าโฟลเดอร์โปรแกรม "
       "บนมือถือให้เปิด http://FACTORY-PC-IP:8000/mobile (ที่อยู่ LAN ของโรงงาน ห้ามใช้ 127.0.0.1) หน้า HTTP คือแอปหน้างาน ไม่ต้องติดตั้งใบรับรอง ติดตั้ง ca.crt เฉพาะเมื่อต้องการกล้อง HTTPS "
       "ป้าย QR สร้างจาก Plan-2026 ที่หน้าหลัก มือถือหาใบสั่งจากไฟล์เดียวกันและจาก CENTRAL_DATA\\DATABASE\\sl_planning.db "
       "ถ้ามือถือบอกว่าไม่มีใบสั่งนี้ ให้กดหน้าหลัก → โหลด Plan-2026 เข้าฐานข้อมูลมือถือ และปิดหน้าต่าง Daily/แผนเตา/มือถือจากโฟลเดอร์ ZIP เก่า "
       "ขั้นตอนนี้ไม่ได้สร้างแผนรายวันหรือแผนเตาให้เอง",
       ["START_SL_CARBORUNDUM_PLANNING_CENTER.bat", "control_center.py", "suite/service_launcher.py", "suite/central_paths.py", "sync_mobile_plan.py", "scripts/windows/start_mobile.py"]),
    _e("cost_kpi", "Cost & Planning KPI Analysis", "วิเคราะห์ต้นทุนและ KPI วางแผน",
       "Open Reports → Cost & Planning KPI Analysis. Upload the Resin, Vitifile and Replacement costing workbooks in the page's source expander; each upload is revisioned and reused. Plan-2026 and Stock on Hand reuse their active Home uploads. Material exposure shows open demand, on-hand, inbound and lab-hold separately. Exact material-code joins are used. Replacement source totals are shown as reported; any alternative is a diagnostic until formulas, units and reject mismatches are approved. CSVs retain source workbook, sheet/row and matched Plan row. Current KPI snapshots can be calculated from current files; historic weekly/monthly/quarterly trends require dated snapshots or append-only actual/change events.",
       "เปิด รายงาน → วิเคราะห์ต้นทุนและ KPI วางแผน อัปโหลดไฟล์ต้นทุน Resin, Vitifile และ Replacement ในกล่องแหล่งข้อมูลของหน้านี้ ระบบเก็บทุกฉบับและใช้ซ้ำ ส่วน Plan-2026 และ Stock on Hand ใช้ไฟล์ที่อัปโหลดไว้หน้า Home การวิเคราะห์วัตถุดิบแสดงความต้องการเปิด ยอดคงคลัง ของรอเข้า และของรอผล LAB แยกกัน จับคู่ด้วยรหัสวัตถุดิบตรงกันเท่านั้น แสดงยอด Replacement ตามไฟล์ ส่วนวิธีคำนวณทางเลือกเป็นเพียงการวิเคราะห์จนกว่าจะอนุมัติสูตร หน่วย และจำนวน Reject ที่ไม่ตรงกัน ไฟล์ CSV ระบุแหล่งสมุดงาน ชีต/แถว และแถว Plan ที่จับคู่ได้ คำนวณภาพ KPI ปัจจุบันได้ ส่วนแนวโน้มย้อนหลังต้องมี snapshot ลงวันที่หรือบันทึก actual/การเปลี่ยนแปลงต่อเนื่อง",
       ["suite/cost_kpi.py", "suite/source_manager.py", "Stock on hand_250926(1).xlsx / Abrasive", "ไฟล์ต้นทุน-แบบใหม่-2568_Resin.XLSX / ราคาวัตถุดิบ NEW", "ไฟล์ต้นทุน-แบบใหม่-2568_Vitifile.XLSX / ราคาวัตถุดิบ NEW", "ต้นทุนการผลิตทดแทน.xlsx", "Plan-2026-LATEST.xlsx / แผนการเผ"], ["SRC-1", "DATA-1"]),
]

PAGE_TOPICS = {
    "cost": ("cost_kpi", "source_manager", "capacity"),
    "control": ("source_manager", "knowledge_db", "local_services", "keys"),
    "daily": ("local_services", "daily_by_section", "daily_status", "section_plans", "plan_columns"),
    "firing": ("local_services", "capacity", "resin_bond", "section_plans", "conflicts"),
    "audit": ("wo_number", "qr", "mobile", "local_services", "defect_codes"),
    "src": ("source_manager", "dated_evidence", "knowledge_db"),
    "more": ("mps_mrp", "bond_plan", "sept"),
    "knowledge": ("knowledge_db", "local_services", "resin_bond", "defect_codes", "product_code", "spec"),
    "suite": ("bond_plan", "mps_mrp", "daily_by_section"),
    "pack": ("product_code", "dated_evidence"),
    "mrp": ("bond_plan", "resin_bond", "dated_evidence"),
    "capacity": ("capacity", "conflicts"),
    "newplan": ("mps_mrp", "wo_number", "order_sheets"),
}


@lru_cache(maxsize=4)
def _load_json(path: str, mtime: float):
    return json.loads(Path(path).read_text(encoding="utf8"))


def _json(p: Path):
    try:
        return _load_json(str(p), p.stat().st_mtime)
    except Exception:  # noqa: BLE001
        return None


def approved_rules(root: Path) -> list[dict]:
    d = _json(root / "knowledge" / "approved_rules.json")
    return (d or {}).get("rules", [])


def _document_register(root: Path):
    """Shipped extraction plus factory overlay (CENTRAL_DATA/KNOWLEDGE), if present."""
    import os
    from .knowledge_ingest import merged_register
    shared = os.environ.get("SL_SHARED_ROOT")
    return merged_register(root, shared)


def knowledge_status(root: Path) -> dict:
    """What knowledge is installed. Used by help and by the Knowledge page so a missing database is never silent."""
    kb = root / "knowledge" / "knowledge_base.sqlite"
    shipped = root / "knowledge" / "DOCUMENT_EXTRACTION.json"
    reg = _document_register(root) if shipped.exists() else {"sources": [], "units": [], "missing_sources": []}
    st = {"records_db_installed": kb.exists(), "records_db_path": str(kb), "records_db_rows": None, "records_db_snapshot": None,
          "documents_registered": shipped.exists() or bool(reg.get("sources")),
          "document_sources": len(reg.get("sources") or []), "document_units": len(reg.get("units") or []),
          "document_units_needing_review": sum(1 for u in (reg.get("units") or []) if u.get("review_required")),
          "missing_sources": (reg or {}).get("missing_sources", [])}
    if kb.exists():
        try:
            con = sqlite3.connect(f"file:{kb.as_posix()}?mode=ro", uri=True)
            st["records_db_rows"] = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            st["records_db_snapshot"] = dict(con.execute("SELECT key,value FROM snapshot_info").fetchall()).get("snapshot_time")
            con.close()
        except Exception as e:  # noqa: BLE001
            st["records_db_error"] = str(e)
    return st


def _fmt_entry(e, thai_first: bool) -> str:
    en, th = e["en"], e["th"]
    body = f"TH: {th}\n\nEN: {en}" if thai_first else f"EN: {en}\n\nTH: {th}"
    cite = "Source: " + "; ".join(e["cites"]) + (f"  |  Rules: {', '.join(e['rules'])}" if e["rules"] else "")
    return body + "\n\n" + cite


def _score(text: str, toks: list[str], title: str = "") -> int:
    low, tl = text.lower(), title.lower()
    return sum(low.count(t) * (3 if t in tl else 1) for t in toks)


def search(query: str, root: Path, limit=8):
    """Return [(score, kind, title, body)] best first. Thai/English question -> the same language is shown first."""
    root = Path(root)
    raw = str(query or "").strip().lower()
    thai = is_thai(query)
    # Direct question intents return the matching curated answer only. This avoids
    # unrelated extracted document chunks overwhelming a simple how-to question.
    spec_intent = bool(re.search(r"\b(spec|specification|product\s+spec|read(?:ing)?\s+(?:the\s+)?spec)\b", raw)) or any(x in raw for x in ("อ่านสเปค", "อ่านค่า spec", "อ่านสเปก", "รหัสสเปค"))
    if spec_intent:
        entry = next((e for e in ENTRIES if e["id"] == "spec"), None)
        if entry:
            return [(10000, "Factory knowledge", entry["th_title"] + " / " + entry["en_title"] if thai else entry["en_title"] + " / " + entry["th_title"], _fmt_entry(entry, thai))]
    stop = {"how", "to", "read", "the", "what", "is", "a", "an", "of", "from", "in", "on", "and", "please", "explain", "show", "me", "can", "you", "tell", "about", "วิธี", "การ", "คือ", "อะไร", "ช่วย", "หน่อย", "อ่าน"}
    q = [t for t in _tok(query) if t not in stop]
    res = []
    if not q:
        return res
    for e in ENTRIES:
        title = e["en_title"] + " " + e["th_title"]
        title_hits = sum(1 for t in q if t in title.lower())
        body_hits = sum(1 for t in q if t in (e["en"] + " " + e["th"]).lower())
        sc = _score(title + " " + e["en"] + " " + e["th"], q, title)
        # Specific material/model codes must outrank incidental numeric title
        # matches (e.g. SP227 storage at 18-20 C versus 11/18-digit codes).
        models=[t for t in q if re.fullmatch(r"[a-z]+\d+",t)]
        sc += 500*sum(bool(re.search(r"\b"+re.escape(t)+r"\b",(e["en"]+" "+e["th"]).lower())) for t in models)
        if title_hits or body_hits >= max(1, (len(q) + 1) // 2):
            res.append((sc + title_hits * 40 + 100, "Factory knowledge", (e["th_title"] if thai else e["en_title"]) + (f"  /  {e['en_title'] if thai else e['th_title']}"), _fmt_entry(e, thai)))
    exact_ids = {m.upper() for m in re.findall(r"\b([A-Za-z]{2,8}-\d{1,2})\b", query)}
    for r in approved_rules(root):
        sc = _score(r["id"] + " " + r["en"] + " " + r["th"], q, r["id"])
        if r["id"] in exact_ids:
            sc += 1000
        if sc:
            body = (f"TH: {r['th']}\n\nEN: {r['en']}" if thai else f"EN: {r['en']}\n\nTH: {r['th']}") + f"\n\nImplemented in: {r['implemented_in']}\nTest: {r.get('test', '')}\nApproved by the factory owner (knowledge/approved_rules.json)"
            res.append((sc + 90, "Approved rule", r["id"], body))
    reg = _document_register(root)
    if reg and reg.get("units"):
        need = max(1, (len(q) + 1) // 2)
        for u in reg["units"]:
            if u["kind"] in ("title",):
                continue
            low = (u.get("text") or "").lower()
            hit = sum(1 for t in q if t in low)
            if hit >= need:
                sc = _score(low, q)
                if "ocr" in u["kind"]:
                    flag = f"UNVERIFIED OCR text (mean confidence {u.get('confidence')}); " + (u.get("review_reason") or "")
                elif u.get("review_required"):
                    flag = "UNVERIFIED, flagged for review: " + (u.get("review_reason") or "")
                else:
                    flag = "text extracted from the file, not independently verified"
                res.append((sc + 30, "Training document", f"{u['source']} - {u['locator']}", (u["text"] or "")[:700] + f"\n\nSource: {u['source']} {u['locator']}  |  {flag}"))
    ks = knowledge_status(root)
    if ks["records_db_installed"]:
        try:
            con = sqlite3.connect(f"file:{Path(ks['records_db_path']).as_posix()}?mode=ro", uri=True)
            like = " AND ".join(["normalized LIKE ?"] * min(len(q), 4))
            args = [f"%{t}%" for t in q[:4]]
            for sheet, row, body in con.execute(f"SELECT sheet,row_number,body FROM records WHERE {like} LIMIT 6", args):
                res.append((10, "Records (Plan/WO/recipe)", f"{sheet} row {row}", str(body)[:400] + f"\n\nSource: knowledge_base.sqlite snapshot {ks['records_db_snapshot']}"))
            con.close()
        except Exception:  # noqa: BLE001
            pass
    sym = re.compile(r"^\s*def\s+(\w+)\s*\(", re.M)
    for p in list(root.glob("*.py")) + list((root / "suite").glob("*.py")):
        try:
            t = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        for m in sym.finditer(t):
            if any(x in m.group(1).lower() for x in q if not is_thai(x)):
                res.append((5, "Code", f"{p.name}: {m.group(1)}()", f"Defined in {p.relative_to(root)}"))
    res.sort(key=lambda x: -x[0])
    out = res[:limit]
    if not ks["records_db_installed"] and not (res and res[0][0] >= 1000):
        out.append((0, "Notice", "Knowledge database not installed" if not thai else "ยังไม่ได้ติดตั้งฐานข้อมูลความรู้",
                    "EN: Plan/WO/recipe record search is unavailable until knowledge/knowledge_base.sqlite is restored from the existing installation or rebuilt (REBUILD_KNOWLEDGE_DATABASE.bat). Built-in help and the PDF/PPTX extraction still work.\n"
                    "TH: การค้นหาแถวข้อมูล Plan/WO/สูตรยังใช้ไม่ได้จนกว่าจะกู้คืน knowledge/knowledge_base.sqlite จากเครื่องเดิมหรือสร้างใหม่ (REBUILD_KNOWLEDGE_DATABASE.bat) วิธีใช้ในตัวและข้อมูลที่ดึงจาก PDF/PPTX ยังใช้ได้"))
    return out


def topics_for_page(page: str) -> list[dict]:
    """Curated F1 entries for the open page (same bilingual text as search)."""
    ids = PAGE_TOPICS.get(page) or PAGE_TOPICS.get("control")
    found = {e["id"]: e for e in ENTRIES}
    return [found[i] for i in ids if i in found]
