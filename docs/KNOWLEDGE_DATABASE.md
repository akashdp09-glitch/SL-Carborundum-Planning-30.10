# Knowledge database: restore or rebuild?

**Short answer: this release needs the existing `knowledge/knowledge_base.sqlite` restored from the current installation.** A rebuild from the sources supplied in this repository is possible, but it is only partial. Nothing in the release hides this: the Knowledge page and F1 help show a red notice whenever the file is absent.

## What the two knowledge stores are

| Store | Content | Built from | In the ZIP / git? |
|---|---|---|---|
| `knowledge/knowledge_base.sqlite` | Searchable rows (Plan / work order / recipe / capacity / stock) with sheet + row references | Excel workbooks in `COMPANY_DATA`, by `knowledge/build_knowledge_db.py` | **No.** Large, contains live data. |
| `knowledge/DOCUMENT_EXTRACTION.json` (+ `DOCUMENT_EXTRACTION_REVIEW.csv`) | Text and OCR of the training PDFs/PPTX/PPTM (grinding, kiln, raw materials, work-order reading, defect codes, resin bond SD-PL-001) plus CSV previews | The files in the repository root, by `knowledge/extract_documents.py` / `suite/knowledge_ingest.py` | **Yes.** Reproducible, no live data. |
| `CENTRAL_DATA/KNOWLEDGE/DOCUMENT_EXTRACTION_LIVE.json` | Extra files uploaded on the Knowledge page | Factory PC, via the Knowledge upload popup | **No.** Stays on the shared data folder. |

## Why a rebuild from this repository is not enough (measured)
* The shipped snapshot manifest (`knowledge/SOURCE_MANIFEST_V16_15.csv`) lists **25 sources and 283,584 indexed rows**.
* Only three of those workbooks are available in this repository, and two of them are different versions from the ones indexed (Plan `...240926` was indexed, `...01100926` is supplied; the capacity workbook was indexed as the 11 Sep export).
* A trial rebuild on 2026-10-04 from the supplied files (Plan 01100926, `CAPACITY_DATABASE.xlsx`, `JOB_REGISTER_REFERENCE_SEP2026.xlsx`) produced **77,099 rows from 3 files** (plus the built-in 12-row "user taught" note) in 13 s. The trial file was deleted; it is not part of the release.
* Missing from this repository (cannot be rebuilt from here): the monthly section workbooks (prepare, mix, form, kiln, grind, pack), both KPI workbooks, the PS/PBS and PM/PBM work-order books (the two largest, about 160k rows), P280526, Cover S&OP, SOP10, RP, MRP Bond, Stock on hand, material usage, and the new-job review workbooks.

## Options
1. **Restore (recommended, preserves everything).** Copy `knowledge\knowledge_base.sqlite` from the current factory installation into the new installation's `knowledge\` folder before first start. The file is only opened read-only by the apps. Keep the old file as a backup.
2. **Rebuild on the factory PC.** Put every workbook that the manifest lists into `COMPANY_DATA`, then run `REBUILD_KNOWLEDGE_DATABASE.bat`. The script builds into a temporary file and replaces the live one only after success. This gives a *new snapshot of the current workbooks*, not a copy of the old one, and is as complete as the folder.
3. **Do neither.** The app still starts. Records search is disabled with a visible notice; the PDF/PPTX knowledge and all built-in help keep working.

## What is different for the documents
`REBUILD_KNOWLEDGE_DATABASE.bat` reads Excel only. PDF and PPTX content is *not* in `knowledge_base.sqlite`; it lives in `DOCUMENT_EXTRACTION.json` and is re-created with `python knowledge\extract_documents.py` (needs Tesseract with Thai + English data and Poppler; see `docs/ENVIRONMENT.md`). The register is checked against the source file hashes by `suite/test_help_f1.py`.

## What the extraction does and does not claim
* Every unit has its page or slide reference. OCR units carry the mean word confidence; low-confidence, near-empty and picture-heavy units are flagged `review_required` and listed in `DOCUMENT_EXTRACTION_REVIEW.csv`.
* No document is marked understood. Every source is `TEXT_EXTRACTED_NOT_VERIFIED`. Diagrams, photographs and charts are not interpreted; the PPTX call-out numbers are linked only to the numbered table rows on the same slide, and their position on the form graphic is not interpreted.
* `ตัวอย่างการกรอกข้อมูล.xlsx` (PPTX slide 21) was not supplied. Its contents are not known and were not inferred.
* Further files the owner uploaded on 2026-10-05 (Defect Code, resin bond SD-PL-001, work-order .pptm, Multi Process.csv, P280526.csv) are extracted into this register. The product-code handbook (11 / 18 digit) is already in F1 / this extraction register — operators do not upload a product-register slot. Dated Excel books on GitHub `main` (stock, PM/PBM, warehouse receipts, packaging reservation) are operational evidence: import them on **Home** (the orange upload box). They are not treated as permanent rules.
* Extra training files can be added on **Knowledge → Upload** without rebuilding the release. F1 searches the shipped register plus `CENTRAL_DATA/KNOWLEDGE`.
