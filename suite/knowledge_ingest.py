"""Ingest owner-supplied training / reference files into the extraction register.

Text is copied from the file. Nothing is interpreted as an approved rule.
Operational workbooks are indexed (sheet names + header rows) only.
Factory uploads are stored under SL_SHARED_ROOT/KNOWLEDGE and merged into a live overlay
so the shipped register is not overwritten.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

from .common import REPO_ROOT, sha256_bytes, sha256_file

SHIPPED = REPO_ROOT / "knowledge" / "DOCUMENT_EXTRACTION.json"
LIVE_NAME = "DOCUMENT_EXTRACTION_LIVE.json"
TRAINING_SUFFIXES = {".pdf", ".pptx", ".pptm"}
TABLE_SUFFIXES = {".xlsx", ".xlsm", ".csv"}


def live_path(shared_root) -> Path:
    return Path(shared_root) / "KNOWLEDGE" / LIVE_NAME


def load_register(path: Path | None = None) -> dict:
    p = path or SHIPPED
    if not p.exists():
        return {"generated": "", "understanding_statement": "", "missing_sources": [], "sources": [], "units": [], "tools": {}}
    return json.loads(p.read_text(encoding="utf8"))


def save_register(reg: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf8")


def merged_register(root: Path, shared_root=None) -> dict:
    """Shipped register plus factory overlay. Same source sha256 is not duplicated."""
    base = load_register(root / "knowledge" / "DOCUMENT_EXTRACTION.json")
    if shared_root:
        live = live_path(shared_root)
        if live.exists():
            overlay = load_register(live)
            have = {s.get("sha256") for s in base.get("sources", [])}
            sid = max((s.get("source_id") or 0) for s in base.get("sources", [])) if base.get("sources") else 0
            for s in overlay.get("sources", []):
                if s.get("sha256") in have:
                    continue
                sid += 1
                old, s = s.get("source_id"), {**s, "source_id": sid, "overlay": True}
                base["sources"].append(s)
                for u in overlay.get("units", []):
                    if u.get("source_id") == old or u.get("source") == s.get("file"):
                        base["units"].append({**u, "source_id": sid, "source": s["file"]})
            for m in overlay.get("missing_sources", []):
                if m not in base.get("missing_sources", []):
                    base.setdefault("missing_sources", []).append(m)
    return base


def classify(name: str, suffix: str) -> str:
    n = name.lower()
    if suffix in TRAINING_SUFFIXES:
        return "TECHNICAL_REFERENCE"
    if "stock" in n or "คงคลัง" in n:
        return "DATED_STOCK"
    if "plan" in n or "pm_pbm" in n or "ติดตาม" in n:
        return "DATED_PRODUCTION_DATA"
    if "mrp" in n or "bond" in n:
        return "DATED_MATERIAL_PLAN"
    if "ขึ้นทะเบียน" in n or "product" in n:
        return "PRODUCT_REGISTER"
    if "คลัง" in n or "warehouse" in n:
        return "DATED_WAREHOUSE"
    return "UPLOADED_FILE"


def _read_csv_text(data: bytes) -> tuple[str, list[list[str]]]:
    for enc in ("utf-8-sig", "utf-8", "cp874", "tis-620", "latin-1"):
        try:
            text = data.decode(enc)
            rows = list(csv.reader(text.splitlines()))
            sample = "".join("".join(r) for r in rows[:8])
            if enc != "latin-1" and "\ufffd" not in sample:
                return enc, rows
            if enc == "latin-1":
                return enc, rows
        except UnicodeDecodeError:
            continue
    return "undecoded", []


def extract_csv(name: str, data: bytes) -> tuple[dict, list[dict]]:
    enc, rows = _read_csv_text(data)
    units = []
    preview = "\n".join(" | ".join((c or "")[:80] for c in r[:16]) for r in rows[:40])
    garbled = enc in ("latin-1", "undecoded") or any("\ufffd" in (c or "") for r in rows[:8] for c in r)
    units.append({
        "locator": "rows 1-40", "kind": "csv_preview", "method": f"csv decode {enc}",
        "confidence": None, "text": preview, "review_required": True if garbled else False,
        "review_reason": "Thai bytes may be mis-decoded; compare with the original file" if garbled else "",
    })
    meta = {"rows": len(rows), "encoding_tried": enc, "type": "csv"}
    return meta, units


def extract_xlsx(name: str, data: bytes, max_sheets=12, preview_rows=8) -> tuple[dict, list[dict]]:
    import io
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    units, sheets = [], []
    for si, sheet in enumerate(wb.sheetnames[:max_sheets], 1):
        ws = wb[sheet]
        rows = []
        for i, r in enumerate(ws.iter_rows(max_row=preview_rows, max_col=16, values_only=True), 1):
            rows.append(["" if v is None else str(v).replace("\n", " ")[:80] for v in r])
        text = "\n".join(" | ".join(r) for r in rows)
        units.append({
            "locator": f"sheet '{sheet}' header", "kind": "workbook_index", "method": "openpyxl read_only header rows",
            "confidence": None, "text": text, "review_required": True,
            "review_reason": "header/preview only; row values are dated operational evidence and were not interpreted as rules",
        })
        sheets.append(sheet)
    extra = wb.sheetnames[max_sheets:]
    wb.close()
    if extra:
        units.append({
            "locator": "further sheets", "kind": "workbook_index", "method": "sheet-name list",
            "confidence": None, "text": ", ".join(extra), "review_required": True,
            "review_reason": "only sheet names recorded; contents not extracted",
        })
    return {"type": "xlsx", "sheets": sheets, "further_sheets": extra}, units


def extract_deck(name: str, data: bytes, skip_ocr=True) -> tuple[dict, list[dict]]:
    from knowledge.extract_documents import extract_pptx
    suffix = Path(name).suffix.lower() or ".pptx"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / (Path(name).stem + (suffix if suffix in (".pptx", ".pptm") else ".pptx"))
        p.write_bytes(data)
        meta, units = extract_pptx(p, Path(td), skip_ocr=skip_ocr)
    meta["type"] = suffix.lstrip(".")
    return meta, units


def extract_pdf(name: str, data: bytes) -> tuple[dict, list[dict]]:
    from knowledge.extract_documents import extract_pdf as _pdf
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / name
        p.write_bytes(data)
        meta, units = _pdf(p, Path(td))
    meta["type"] = "pdf"
    return meta, units


def extract_bytes(name: str, data: bytes, skip_ocr=True) -> tuple[dict, list[dict]]:
    suf = Path(name).suffix.lower()
    if suf in {".pptx", ".pptm"}:
        return extract_deck(name, data, skip_ocr=skip_ocr)
    if suf == ".pdf":
        return extract_pdf(name, data)
    if suf == ".csv":
        return extract_csv(name, data)
    if suf in {".xlsx", ".xlsm"}:
        return extract_xlsx(name, data)
    raise ValueError(f"Unsupported file type: {suf or name}")


def merge_source(reg: dict, name: str, data: bytes, meta: dict, units: list[dict], uploaded_by="") -> dict:
    digest = sha256_bytes(data)
    existing = next((s for s in reg.get("sources", []) if s.get("sha256") == digest), None)
    if existing:
        return {"status": "DUPLICATE_UNCHANGED", "source_id": existing["source_id"], "file": existing["file"]}
    sid = max((s.get("source_id") or 0) for s in reg.get("sources", [])) + 1 if reg.get("sources") else 1
    nrev = sum(1 for u in units if u.get("review_required"))
    src = {
        "source_id": sid, "file": name, "sha256": digest, "size_bytes": len(data),
        "type": meta.get("type") or Path(name).suffix.lower().lstrip("."),
        "classification": classify(name, Path(name).suffix.lower()),
        "units": len(units), "units_needing_review": nrev,
        "understanding": "TEXT_EXTRACTED_NOT_VERIFIED",
        "uploaded_by": uploaded_by,
        "ingested_at": dt.datetime.now(ZoneInfo("Asia/Bangkok")).isoformat(timespec="seconds"),
        **{k: v for k, v in meta.items() if k not in {"type"}},
    }
    reg.setdefault("sources", []).append(src)
    for u in units:
        u = {**u, "source_id": sid, "source": name}
        reg.setdefault("units", []).append(u)
    return {"status": "INGESTED", "source_id": sid, "file": name, "units": len(units), "units_needing_review": nrev}


def ingest_bytes(name: str, data: bytes, dest: Path, uploaded_by="", skip_ocr=True) -> dict:
    if dest.exists():
        reg = load_register(dest)
    else:
        reg = {
            "generated": dt.datetime.now(ZoneInfo("Asia/Bangkok")).isoformat(timespec="seconds"),
            "understanding_statement": "Text extraction and OCR only. NO document is claimed to be fully understood.",
            "missing_sources": [], "sources": [], "units": [], "overlay": True,
        }
    meta, units = extract_bytes(name, data, skip_ocr=skip_ocr)
    result = merge_source(reg, name, data, meta, units, uploaded_by=uploaded_by)
    if result["status"] == "INGESTED":
        reg["generated"] = dt.datetime.now(ZoneInfo("Asia/Bangkok")).isoformat(timespec="seconds")
        save_register(reg, dest)
    result["path"] = str(dest)
    return result


def store_original(shared_root, name: str, data: bytes) -> Path:
    folder = Path(shared_root) / "KNOWLEDGE" / "DOCS"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / Path(name).name
    if dest.exists() and sha256_file(dest) == sha256_bytes(data):
        return dest
    if dest.exists():
        stamp = dt.datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y%m%d_%H%M%S")
        dest = folder / f"{dest.stem}_{stamp}{dest.suffix}"
    dest.write_bytes(data)
    return dest
