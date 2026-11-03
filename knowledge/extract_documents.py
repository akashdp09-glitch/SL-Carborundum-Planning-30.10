"""Extract the supplied training documents (PDF + PPTX) into an auditable, page/slide-referenced register.

Nothing here claims the documents are *understood*. Every unit records how its text was obtained
(embedded text, table cell, OCR) and OCR output is flagged for human review when confidence is low.
Output (committed, small):
  knowledge/DOCUMENT_EXTRACTION.json      - sources + units (source, sha256, locator, kind, text, method, confidence, review)
  knowledge/DOCUMENT_EXTRACTION_REVIEW.csv - the subset that needs a person to look at the original page/slide
Run:  python knowledge/extract_documents.py [source_dir]      (needs tesseract with 'tha' + 'eng', and pdftoppm/pdftotext)
Rendering and OCR images are temporary and not stored.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "knowledge" / "DOCUMENT_EXTRACTION.json"
OUT_CSV = ROOT / "knowledge" / "DOCUMENT_EXTRACTION_REVIEW.csv"
OCR_LANGS = "tha+eng"
OCR_DPI = 220
LOW_CONF = 70.0          # mean word confidence below this -> review
MIN_WORDS = 6            # fewer recognised words than this -> review
SPARSE_WORDS = 40        # text layer with fewer words than this AND pictures -> also OCR the page
IMAGE_ONLY_CHARS = 20    # embedded text shorter than this -> treat page as image-only


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def tool_versions() -> dict:
    def v(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            return (r.stdout or r.stderr).strip().splitlines()[0]
        except Exception as e:  # noqa: BLE001
            return f"unavailable ({e})"
    langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout.split() if shutil.which("tesseract") else []
    return {"tesseract": v(["tesseract", "--version"]), "tesseract_langs": [x for x in langs if x in ("tha", "eng")],
            "pdftotext": v(["pdftotext", "-v"]), "pdftoppm": v(["pdftoppm", "-v"])}


def ocr_image(png: Path, psm: int = 3) -> tuple[str, float | None, int, list[dict]]:
    """Return (text, mean word confidence, word count, words with boxes)."""
    base = png.with_suffix("")
    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}  # parallel pages x OpenMP threads otherwise oversubscribe the CPU and stall
    subprocess.run(["tesseract", str(png), str(base), "-l", OCR_LANGS, "--psm", str(psm), "-c", "preserve_interword_spaces=1", "txt", "tsv"],
                   capture_output=True, check=True, timeout=300, env=env)
    text = Path(str(base) + ".txt").read_text(encoding="utf8", errors="replace").strip()
    words, confs = [], []
    with open(str(base) + ".tsv", encoding="utf8", errors="replace") as f:
        rows = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    for r in rows[1:]:
        if len(r) < 12 or not r[11].strip():
            continue
        try:
            c = float(r[10])
        except ValueError:
            continue
        if c < 0:
            continue
        confs.append(c)
        words.append({"x": int(r[6]), "y": int(r[7]), "w": int(r[8]), "h": int(r[9]), "conf": c, "text": r[11]})
    return text, (round(sum(confs) / len(confs), 1) if confs else None), len(confs), words


def review_for_ocr(conf, nwords) -> tuple[bool, str]:
    if conf is None or nwords < MIN_WORDS:
        return True, "OCR produced almost no text; page is probably a pure diagram/photo whose meaning is NOT extracted"
    if conf < LOW_CONF:
        return True, f"low OCR confidence ({conf} < {LOW_CONF}); check against the original page"
    return False, "OCR confidence acceptable but OCR output is still unverified against the original"


def pdf_text_pages(pdf: Path, n: int) -> list[str]:
    out = []
    for p in range(1, n + 1):
        r = subprocess.run(["pdftotext", "-f", str(p), "-l", str(p), "-layout", str(pdf), "-"], capture_output=True, text=True, timeout=60)
        out.append(re.sub(r"\f", "", r.stdout).strip())
    return out


def pdf_image_counts(pdf: Path, n: int) -> dict[int, int]:
    from pypdf import PdfReader
    rd = PdfReader(str(pdf))
    res = {}
    for i, pg in enumerate(rd.pages, 1):
        try:
            res[i] = len(list(pg.images))
        except Exception:  # noqa: BLE001
            res[i] = -1
    return res


def extract_pdf(pdf: Path, tmp: Path) -> tuple[dict, list[dict]]:
    from pypdf import PdfReader
    n = len(PdfReader(str(pdf)).pages)
    texts = pdf_text_pages(pdf, n)
    imgs = pdf_image_counts(pdf, n)
    units: list[dict] = []
    image_only = [i for i, t in enumerate(texts, 1) if len(t.strip()) < IMAGE_ONLY_CHARS]
    # pages with a little embedded text plus pictures are mostly diagrams: OCR them too and keep both texts
    sparse = [i for i, t in enumerate(texts, 1) if i not in image_only and len(t.split()) < SPARSE_WORDS and imgs.get(i, 0) > 0]

    def do_ocr(p):
        d = tmp / f"{pdf.stem[:12]}_{abs(hash(pdf.name)) % 9999}_{p}"
        d.mkdir(parents=True, exist_ok=True)
        pref = d / "pg"
        subprocess.run(["pdftoppm", "-r", str(OCR_DPI), "-f", str(p), "-l", str(p), "-png", str(pdf), str(pref)], check=True, capture_output=True, timeout=300)
        png = next(d.glob("pg*.png"))
        return p, ocr_image(png)

    with ThreadPoolExecutor(max_workers=4) as ex:
        ocr = dict(ex.map(do_ocr, image_only + sparse))
    for p in range(1, n + 1):
        t = texts[p - 1]
        if p in ocr:
            text, conf, nw, _ = ocr[p]
            rev, why = review_for_ocr(conf, nw)
            if p in sparse:
                text = (t + "\n--- OCR of page image ---\n" + text).strip()
                kind = "embedded_text+ocr"
            else:
                kind = "ocr"
            units.append({"locator": f"p.{p}", "kind": kind, "method": f"tesseract {OCR_LANGS} @{OCR_DPI}dpi" + (" + pdftotext" if p in sparse else ""), "confidence": conf, "words": nw,
                          "text": text, "review_required": rev or p in sparse,
                          "review_reason": why if rev else ("sparse text layer plus picture: diagram content only partly captured by OCR" if p in sparse else why),
                          "images_on_page": imgs.get(p)})
        else:
            has_img = imgs.get(p, 0) > 0
            units.append({"locator": f"p.{p}", "kind": "embedded_text", "method": "pdftotext -layout", "confidence": None, "words": len(t.split()),
                          "text": t, "review_required": False,
                          "review_reason": (f"page carries {imgs.get(p)} image(s) alongside a full text layer; picture content is not extracted" if has_img else ""),
                          "images_on_page": imgs.get(p)})
    meta = {"pages": n, "image_only_pages": image_only, "sparse_text_pages_also_ocred": sparse, "pages_with_embedded_text": n - len(image_only)}
    return meta, units


def _shape_images(sh):
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    try:
        if sh.shape_type == MSO_SHAPE_TYPE.PICTURE or hasattr(sh, "image"):
            return sh.image
    except Exception:  # noqa: BLE001
        return None
    return None


def extract_pptx(pptx: Path, tmp: Path, skip_ocr: bool = False) -> tuple[dict, list[dict]]:
    from pptx import Presentation
    prs = Presentation(str(pptx))
    units: list[dict] = []
    nslides = len(prs.slides)
    interpreted_callouts = 0
    for si, slide in enumerate(prs.slides, 1):
        loc = f"slide {si}"
        title = ""
        texts, tables, callouts, pics = [], [], [], []
        for sh in slide.shapes:
            if sh.has_text_frame and sh.text_frame.text.strip():
                tx = sh.text_frame.text.strip()
                if re.fullmatch(r"\d{1,2}", tx) and sh.shape_type is not None and "AUTO_SHAPE" in str(sh.shape_type):
                    callouts.append({"n": int(tx), "left": sh.left, "top": sh.top, "w": sh.width, "h": sh.height})
                elif not title and "PLACEHOLDER" in str(sh.shape_type) and sh.top < 700000:
                    title = tx
                else:
                    texts.append(tx)
            if getattr(sh, "has_table", False) and sh.has_table:
                rows = [[c.text.strip().replace("\n", " / ") for c in r.cells] for r in sh.table.rows]
                tables.append(rows)
            img = _shape_images(sh)
            if img is not None:
                pics.append((sh, img))
        if title:
            units.append({"locator": loc, "kind": "title", "method": "pptx text", "confidence": None, "text": title, "review_required": False, "review_reason": ""})
        if texts:
            units.append({"locator": loc, "kind": "slide_text", "method": "pptx text", "confidence": None, "text": "\n".join(texts), "review_required": False, "review_reason": ""})
        for ti, rows in enumerate(tables, 1):
            units.append({"locator": f"{loc} table {ti}", "kind": "table", "method": "pptx table cells", "confidence": None,
                          "text": "\n".join(" | ".join(r) for r in rows), "rows": rows, "review_required": False, "review_reason": ""})
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            units.append({"locator": f"{loc} notes", "kind": "notes", "method": "pptx notes", "confidence": None,
                          "text": slide.notes_slide.notes_text_frame.text.strip(), "review_required": False, "review_reason": ""})
        # numbered call-outs: link number -> definition row of the slide's table (same number in column 1)
        if callouts:
            defs = {}
            for rows in tables:
                for r in rows[1:]:
                    if r and re.fullmatch(r"\d{1,2}", r[0] or ""):
                        defs[int(r[0])] = " - ".join(x for x in r[1:] if x)
            for c in sorted(callouts, key=lambda c: c["n"]):
                d = defs.get(c["n"])
                interpreted_callouts += 1 if d else 0
                units.append({"locator": f"{loc} call-out {c['n']}", "kind": "callout", "method": "pptx shape number + table row with the same number",
                              "confidence": None,
                              "position_pct": {"x": round(100 * c["left"] / prs.slide_width, 1), "y": round(100 * c["top"] / prs.slide_height, 1)},
                              "text": d or "", "review_required": d is None or not d.strip(),
                              "review_reason": ("" if d else f"call-out {c['n']} has no matching numbered row in this slide's table; meaning not extracted"),
                              })
        # pictures: OCR them (form graphics) and place call-outs on them by position
        if skip_ocr:
            if pics:
                units.append({"locator": loc, "kind": "diagram_note", "method": "structural",
                              "confidence": None, "text": f"{len(pics)} embedded picture(s) present; OCR skipped on this pass.",
                              "review_required": True, "review_reason": "picture OCR was not run; compare with the original slide"})
            continue
        for pi, (sh, img) in enumerate(pics, 1):
            png = tmp / f"s{si}_{pi}.{img.ext if img.ext in ('png', 'jpg', 'jpeg') else 'png'}"
            png.write_bytes(img.blob)
            try:
                text, conf, nw, words = ocr_image(png, psm=11)
            except Exception as e:  # noqa: BLE001
                units.append({"locator": f"{loc} picture {pi}", "kind": "diagram_ocr", "method": "tesseract failed", "confidence": None, "text": "",
                              "review_required": True, "review_reason": f"OCR failed: {e}"})
                continue
            rev = True
            reason = "form picture OCR is unverified; the call-out placement on the picture is positional only"
            if conf is not None and nw >= MIN_WORDS and conf >= LOW_CONF:
                reason = "OCR confidence acceptable but a person must still compare it with the slide"
            else:
                reason = review_for_ocr(conf, nw)[1]
            near = []
            if callouts and words:
                from PIL import Image
                W, H = Image.open(png).size
                for c in sorted(callouts, key=lambda c: c["n"]):
                    cx = (c["left"] + c["w"] / 2 - sh.left) / max(sh.width, 1) * W
                    cy = (c["top"] + c["h"] / 2 - sh.top) / max(sh.height, 1) * H
                    if not (0 <= cx <= W and 0 <= cy <= H):
                        continue
                    cand = sorted(words, key=lambda w: (w["x"] + w["w"] / 2 - cx) ** 2 + (w["y"] + w["h"] / 2 - cy) ** 2)[:3]
                    near.append({"callout": c["n"], "nearest_ocr_words": [w["text"] for w in cand], "note": "nearest-word guess, not a verified label"})
            units.append({"locator": f"{loc} picture {pi}", "kind": "diagram_ocr", "method": f"tesseract {OCR_LANGS} psm11 on embedded image", "confidence": conf,
                          "words": nw, "text": text, "callout_nearest_words": near, "review_required": rev, "review_reason": reason})
        if callouts and not pics:
            units.append({"locator": f"{loc} form graphic", "kind": "diagram_note", "method": "structural",
                          "confidence": None, "text": "Call-out numbers sit over the slide's own form layout (no embedded picture to OCR); their meaning is taken only from the numbered table.",
                          "review_required": True,
                          "review_reason": "positions of call-outs relative to the form fields were not interpreted; compare with the original slide"})
    meta = {"slides": nslides, "callouts_matched_to_table_rows": interpreted_callouts,
            "slides_with_pictures": sorted({int(u["locator"].split()[1]) for u in units if u["kind"] == "diagram_ocr"})}
    return meta, units


def main(src_dir: Path):
    tz = ZoneInfo("Asia/Bangkok")
    files = sorted([p for p in src_dir.iterdir() if p.suffix.lower() in (".pdf", ".pptx", ".pptm")])
    reg = {"generated": dt.datetime.now(tz).isoformat(timespec="seconds"), "tools": tool_versions(),
           "understanding_statement": "Text extraction and OCR only. NO document is claimed to be fully understood; units with review_required=true need a person to compare them with the original page/slide.",
           "missing_sources": [{"name": "ตัวอย่างการกรอกข้อมูล.xlsx", "referenced_by": "การอ่านใบสั่งงานการผลิต.pptx slide 21",
                                "status": "NOT SUPPLIED - contents are not known and were not inferred"}],
           "sources": [], "units": []}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for f in files:
            meta, units = (extract_pdf if f.suffix.lower() == ".pdf" else extract_pptx)(f, tmp)
            sid = len(reg["sources"]) + 1
            nrev = sum(1 for u in units if u["review_required"])
            reg["sources"].append({"source_id": sid, "file": f.name, "sha256": sha256(f), "size_bytes": f.stat().st_size, "type": f.suffix.lower()[1:],
                                   **meta, "units": len(units), "units_needing_review": nrev, "understanding": "TEXT_EXTRACTED_NOT_VERIFIED"})
            for u in units:
                u["source_id"] = sid
                u["source"] = f.name
            reg["units"].extend(units)
            print(f"{f.name}: {len(units)} units, {nrev} need review", file=sys.stderr)
    OUT_JSON.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf8")
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["source", "locator", "kind", "ocr_confidence", "reason_for_review", "text_preview"])
        for u in reg["units"]:
            if u["review_required"]:
                w.writerow([u["source"], u["locator"], u["kind"], u.get("confidence"), u["review_reason"], (u["text"] or "")[:160].replace("\n", " ")])
    print(f"wrote {OUT_JSON.name} ({len(reg['units'])} units) and {OUT_CSV.name}", file=sys.stderr)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT)
