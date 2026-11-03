SL CARBORUNDUM INTEGRATED PLANNING CENTER V10 — SHARED EDITABLE

Corrections in this release:
- One central Plan-2026 source remains shared by Daily, Firing, Combined Analysis and QR.
- Combined English/Thai selector now has only English or Thai modes.
- Header moved down to avoid the Streamlit deploy strip.
- Backorder uses the same Order Qty - Packing Actual / Overall Closed basis used by Daily and shows OPEN vs CLOSED by due month.
- MRP table is editable; graph reacts to edited values; edits can be saved/downloaded.
- WIP/backorder combined tables are editable/saveable/downloadable.
- Packaging page has a light packaging-company background, due-date graph, editable plan, save/download, and same-size alternative references from currently matched open products.
- English-customer Plan copy ADDS Customername_English_Script and never changes the original Thai customer field or original uploaded workbook.
- Original company source files are never edited at their original location.
- Shared reports are written under REPORTS. Shared sources are controlled copies under company_data and SOURCE_COPIES.

Multi-user deployment:
Run this package ONCE on the designated server/host PC. Other users open the host address in browsers. Do not run separate independent copies on every PC if you expect immediate shared state. Operator/mobile transactions use the central audit service/database.
