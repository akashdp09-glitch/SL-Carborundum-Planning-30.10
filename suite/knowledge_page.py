"""Knowledge page: bilingual Q&A first; raw extraction stays in an advanced expander."""
from __future__ import annotations

import html
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from .help_f1 import knowledge_status, search, topics_for_page
from .knowledge_ingest import ingest_bytes, live_path, merged_register, store_original


def _thai(lang=None) -> bool:
    if lang:
        return lang == "ไทย"
    return st.session_state.get("global_language") == "ไทย" or st.session_state.get("lang") == "ไทย" or st.session_state.get("ui_lang") == "ไทย"


def _card(title: str, body: str, cite: str = ""):
    cite_html = f"<div class='sl-src'>{html.escape(cite)}</div>" if cite else ""
    st.markdown(f"<div class='sl-answer'><h4>{html.escape(title)}</h4><div>{html.escape(body).replace(chr(10), '<br>')}</div>{cite_html}</div>", unsafe_allow_html=True)


def render(root: Path, key="kn", lang=None):
    thai = _thai(lang)
    ks = knowledge_status(root)

    st.markdown("### " + ("ถามความรู้โรงงาน / Factory knowledge" if thai else "Ask factory knowledge"))
    st.caption("คำตอบมาจากกฎที่อนุมัติ เอกสารที่ดึงข้อความแล้ว และฐานแถว Plan/WO ถ้ามีติดตั้ง — ไม่แต่งความหมายที่แหล่งไม่มี"
               if thai else
               "Answers come from approved rules, extracted training files (including the product register 11 / 18 digit codes), and Plan/WO rows when that database is installed. Meanings that are not in a source are not invented. Do not upload the product register on Home or Sources.")

    if ks["records_db_installed"]:
        st.success(("ฐานแถว Plan/WO ติดตั้งแล้ว: " if thai else "Plan/WO records database installed: ")
                   + f"{ks['records_db_rows']} rows · snapshot {ks['records_db_snapshot']}.")
    else:
        st.warning("ฐานแถว Plan/WO (knowledge/knowledge_base.sqlite) ยังไม่มี — ค้นรหัสใบสั่งจากสแนปชอต Excel ใช้ไม่ได้จนกว่าจะกู้จากเครื่องเดิมหรือสร้างด้วย REBUILD_KNOWLEDGE_DATABASE.bat วิธีใช้และข้อความจาก PDF/PPTX ยังถามได้"
                   if thai else
                   "Plan/WO records database (knowledge/knowledge_base.sqlite) is not installed, so Excel-row code search is unavailable until it is restored or rebuilt with REBUILD_KNOWLEDGE_DATABASE.bat. Built-in how-to and PDF/PPTX text can still be asked.")

    q_key = f"{key}_ask"
    topics = topics_for_page("knowledge")
    with st.expander("Suggested questions / คำถามแนะนำ", expanded=False):
        picks = topics[:6]
        cols = st.columns(2)
        for i, e in enumerate(picks):
            label = e["th_title"] if thai else e["en_title"]
            if cols[i % 2].button(label, key=f"{key}_chip_{e['id']}", use_container_width=True):
                st.session_state[q_key] = label

    q = st.text_input(
        "พิมพ์คำถาม ภาษาไทยหรืออังกฤษ / Type a question in Thai or English",
        key=q_key,
        placeholder="เช่น ปิดใบสั่ง, resin 2 วัน, 127.0.0.1 refused, รหัสสินค้า 11 หลัก",
    )
    if q and q.strip():
        hits = search(q.strip(), root, limit=3)
        if not hits:
            st.info("ไม่พบในแหล่งที่ติดตั้ง — ไม่มีการเดาความหมาย" if thai else "No match in the installed sources. Nothing is guessed.")
        for _sc, kind, title, body in hits:
            cite = ""
            text = body
            if "\n\nSource:" in body:
                text, cite = body.split("\n\nSource:", 1)
                cite = "Source: " + cite.strip()
            _card(f"{title} · {kind}", text, cite)

    shared = Path(os.environ.get("SL_SHARED_ROOT", str(root / "CENTRAL_DATA")))
    with st.expander("📤 " + ("อัปโหลดเอกสารความรู้ (ทำงานเมื่อกดเท่านั้น)" if thai else "Upload training files (runs only when you press the button)"), expanded=False):
        st.caption("Only add a file that is not already in F1. Product register and the shipped training PDFs/PPTX are already extracted — do not upload those again."
                   if not thai else
                   "เพิ่มเฉพาะไฟล์ที่ยังไม่อยู่ใน F1 ทะเบียนรหัสสินค้าและเอกสารฝึกอบรมที่มีในชุดแล้วถูกดึงไว้แล้ว ไม่ต้องอัปโหลดซ้ำ")
        ups = st.file_uploader("Files", type=["pdf", "pptx", "pptm", "xlsx", "xlsm", "csv"], accept_multiple_files=True, key=f"{key}_up")
        if ups and st.button("Extract and add to F1 / ดึงข้อความเข้า F1", key=f"{key}_go"):
            dest = live_path(shared)
            for up in ups:
                data = up.getvalue()
                store_original(shared, up.name, data)
                r = ingest_bytes(up.name, data, dest, uploaded_by=st.session_state.get("sl_user", ""), skip_ocr=True)
                (st.success if r["status"] == "INGESTED" else st.info)(f"{up.name}: {r['status']} — {r.get('units', 0)} units")
            st.cache_data.clear()

    with st.expander("🗂 " + ("ตารางข้อความที่ดึงจากไฟล์ (ขั้นสูง)" if thai else "Raw extracted text table (advanced)"), expanded=False):
        reg = merged_register(root, shared)
        if not reg.get("sources"):
            st.warning("Training-document extraction register is missing. Run: python knowledge/extract_documents.py")
            return
        st.caption(reg.get("understanding_statement") or "")
        src_df = pd.DataFrame(reg["sources"])
        show = [c for c in ("file", "type", "pages", "slides", "classification", "units", "units_needing_review", "understanding") if c in src_df.columns]
        st.dataframe(src_df[show], use_container_width=True, hide_index=True)
        for m in reg.get("missing_sources") or []:
            st.warning(f"Missing source: {m['name']} (referenced by {m['referenced_by']}) - {m['status']}")
        fq = st.text_input("Find text in the documents / ค้นในเอกสาร", key=f"{key}_rawq")
        only_review = st.checkbox("Only units needing review", key=f"{key}_rev")
        df = pd.DataFrame([{
            "source": u["source"], "where": u["locator"], "kind": u["kind"],
            "ocr_conf": u.get("confidence"), "review": u.get("review_required"),
            "why": u.get("review_reason", ""), "text": (u.get("text") or "")[:400],
        } for u in reg.get("units") or []])
        if not df.empty:
            if only_review:
                df = df[df.review]
            if fq:
                df = df[df.text.str.contains(fq, case=False, regex=False)]
            st.dataframe(df, use_container_width=True, hide_index=True, height=360)
