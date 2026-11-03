"""Hash, open and classify reference files added on main; writes knowledge/REFERENCE_INTAKE_2026-10-04.csv.
Read-only on the source files. Classification text is a human decision recorded here, not inferred by code."""
import csv, hashlib, zipfile, re, sys
from pathlib import Path
from pypdf import PdfReader
from pptx import Presentation
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
CLASS = {
 "The Basic Process of Grinding PDF..pdf": ("TECHNICAL_REFERENCE", "Grinding-wheel fundamentals deck (English with some Thai): process, parameters, speeds, drawing tolerances and roughness, wheel shapes, abrasive/bond/grade/structure, SL tracking system, SL-vs-competitor spec conversion."),
 "Vitrified_Bond_Kiln โครงสร้างเตา.pdf": ("TECHNICAL_REFERENCE", "Thai supervisor training on vitrified-bond downdraft kilns: dimensions, structure, burner ports, thermocouples/controllers, dampers, refractory and kiln furniture (plate/leg counts updated 30/7/2026), maintenance and inspection checklists, firing program. 43 pages; the longer of two kiln decks."),
 "Vitrified_Bond_Kiln_and_Firing_Technique_2025_v5_Detailed_Checklist -โครงสร้างเตา Th.pdf": ("TECHNICAL_REFERENCE", "Thai kiln training deck, 40 pages; same first 34 slides as the 43-page deck but without the 30/7/2026 furniture-count update, firing-program and author slides. Treated as an earlier/shorter version; supersession not stated in the file."),
 "ความรู้เบื้องต้นเกี่ยวกับวัตถุดิบ.pdf": ("TECHNICAL_REFERENCE", "Thai R&D raw-material training: abrasive, bond, porosity, material types, reading/writing raw-material codes (A=abrasive, B/C/R=bond, F=filler/additive), status-label standard (WI-QC-02-13, FM-QC-02-03/09/10)."),
 "การอ่านใบสั่งงานการผลิต.pptx": ("TECHNICAL_REFERENCE", "Thai guide to reading the production order: factory-no format PXXX-DDMMYY, spec decoding, Vitrify/Resin order types, the 10 sheets of one order (master, prep, mix, forming, firing, grinding, label/pack, QC)."),
 "Packaging-Standard-LATEST.csv": ("MASTER_DATA_UNDATED", "Registered-product code list (not the packaging-quantity master the app reads): 98 data rows of bare 11-char product code, marking-system name, brand and inner/outer box codes. Has an in-file duplicate flag and a note to append after row 99."),
 "Plan 2026-2-Update-01100926.xlsx": ("DATED_PRODUCTION_DATA", "Plan-2026 workbook (modified 2026-10-01): 3,509 production orders on the firing-plan sheet plus preparation, mixing, forming, firing, grinding, pack, reject, kiln and delivery sheets. Operational plan data, not technical knowledge."),
}

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def describe(p):
    s = p.suffix.lower()
    if s == ".pdf":
        r = PdfReader(str(p)); n = len(r.pages)
        empty = [i + 1 for i, pg in enumerate(r.pages) if len((pg.extract_text() or "").strip()) < 20]
        meta = {k: str(v) for k, v in (r.metadata or {}).items()}
        note = f"{n} pages; {n-len(empty)} with extractable text; image-only/no-text pages {empty} (OCR not run). Embedded title='{meta.get('/Title','')}' author='{meta.get('/Author','')}' created={meta.get('/CreationDate','')}"
        if any("\u0e4d" in (pg.extract_text() or "") for pg in r.pages[:5]): note += "; Thai text extraction shows detached sara-am (e.g. 'ส าหรับ'), normalise before search"
        return "READ_OK" if len(empty) < n else "BLOCKED", f"{n} pages", note
    if s == ".pptx":
        pr = Presentation(str(p)); n = len(pr.slides)
        pics = sum(1 for sl in pr.slides for sh in sl.shapes if sh.shape_type == 13)
        return "READ_OK", f"{n} slides", f"{n} slides; text read; {pics} top-level picture shapes; slides 9-20 are mostly numbered call-outs over form graphics whose content was not interpreted; slide 21 references an external 'ตัวอย่างการกรอกข้อมูล.xlsx' not supplied"
    if s == ".csv":
        rows = list(csv.reader(open(p, encoding="utf-8-sig")))
        data = [r for r in rows[2:] if len(r) > 3 and r[3].strip()]
        return "READ_OK", f"{len(data)} data rows", f"{len(rows)} lines, 17 columns, header on line 2; duplicate flag 'Codeซ้ำ' on {sum(1 for r in data if len(r)>4 and r[4]=='Codeซ้ำ')} rows; code 4MP030V0103 appears twice"
    if s == ".xlsx":
        z = zipfile.ZipFile(p); core = z.read("docProps/core.xml").decode("utf8", "ignore")
        mod = re.search(r"<dcterms:modified[^>]*>([^<]+)", core)
        ext = [n for n in z.namelist() if "externalLinks/externalLink" in n and n.endswith(".xml")]
        wb = load_workbook(p, read_only=True, data_only=True)
        sheets = "; ".join(f"{w.title}[{w.sheet_state},{w.max_row}x{w.max_column}]" for w in wb.worksheets)
        return "READ_OK", f"{len(wb.sheetnames)} sheets", f"workbook-modified={mod.group(1) if mod else ''}; {len(ext)} external-workbook links (cached values used, linked files not supplied); sheets: {sheets}"
    return "UNSUPPORTED", "", ""

def main():
    out = ROOT / "knowledge" / "REFERENCE_INTAKE_2026-10-04.csv"
    cols = ["filename", "repo_path", "size_bytes", "sha256", "read_status", "extent", "classification", "approval_status", "content_summary", "technical_notes"]
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(cols)
        for name, (cls, summ) in CLASS.items():
            p = ROOT / name
            try: status, extent, notes = describe(p)
            except Exception as e: status, extent, notes = "BLOCKED", "", f"{type(e).__name__}: {e}"
            appr = "NOT_STATED_IN_FILE - confirm with owner" 
            w.writerow([name, name, p.stat().st_size, sha(p), status, extent, cls, appr, summ, notes])
    print("wrote", out)

if __name__ == "__main__": main()
