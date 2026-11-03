"""Merge the owner-uploaded decks/CSV that sit in the repo root into DOCUMENT_EXTRACTION.json."""
from __future__ import annotations

from pathlib import Path

from suite.common import REPO_ROOT
from suite.knowledge_ingest import SHIPPED, extract_bytes, load_register, merge_source, save_register

FILES = [
    "Defect Code.pptx",
    "คุณสมบัติและการจัดเก็บ Resin  Bond  SD-PL-001.pptx",
    "การอ่านใบสั่งงานการผลิต.pptm",
    "1. Multi Process.csv",
    "P280526.csv",
]


def main():
    reg = load_register(SHIPPED)
    for name in FILES:
        p = REPO_ROOT / name
        if not p.exists():
            print("missing", name)
            continue
        data = p.read_bytes()
        meta, units = extract_bytes(name, data, skip_ocr=True)
        r = merge_source(reg, name, data, meta, units, uploaded_by="origin/main upload")
        print(name, r["status"], r.get("units"), "review", r.get("units_needing_review"))
    save_register(reg, SHIPPED)
    print("sources", len(reg["sources"]), "units", len(reg["units"]))


if __name__ == "__main__":
    main()
