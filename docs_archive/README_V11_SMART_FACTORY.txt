SL CARBORUNDUM SMART FACTORY CENTER V11

Major revision based on management feedback:
- One authoritative close rule: ยังไม่ปิด=open; ปิดใบสั่ง=closed; ปิด=closed. Any controlled preparation/final close excludes backorder and new material planning.
- Remaining quantity basis retained for open backlog; completed packing quantity is not counted again.
- Multi-session architecture retained: Hub, Daily, Firing, Mobile/QR and Shared Analysis run as separate services against shared data.
- User + section identity added to Hub; editable table saves stamp Edited By / Edited Section / Edited At and write an SQLite audit record.
- Large left-side hierarchy/quick tree added for fast navigation.
- Meeting cockpit adds instant WO/customer/product search and direct capacity-control guidance.
- Firing interface uses the supplied kiln photography; packaging keeps packaging imagery; duplicated photo strip removed from Control.
- Hub graphs show value labels and remain paired with editable/source tables.
- QR/mobile workflow retained for low typing and fast shop-floor audit.
- Original company source files are never overwritten; controlled copies remain inside company_data/SOURCE_COPIES.

IMPORTANT: Capacity remains sourced from the existing controlled Daily Planner capacity engine/database. V11 intentionally does not invent a second capacity calculation.
