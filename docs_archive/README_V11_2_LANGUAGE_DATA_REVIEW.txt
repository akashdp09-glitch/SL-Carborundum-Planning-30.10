V11.2 REVIEW
Reviewed Hub tabs: Control, Daily, Firing, QR/Audit, WIP, Backorder, MPS, MRP, Packaging, Sources.
Logical meeting flow recommended: Control/Search -> Daily/Capacity -> WIP -> Backorder -> MPS -> MRP -> Firing -> Packaging -> QR/Audit -> Sources.

Language changes:
- Thai source customer name is preserved.
- English display uses Thai word segmentation + Royal Institute romanization, so long Thai names are separated into readable words.
- Hub language selector now changes native table headers/common statuses, not only menus.
- Search shows Thai and English customer companions for traceability.
- Original Plan-2026 is never overwritten by display translation.

Known boundary:
Daily and Firing are separate legacy Streamlit services embedded in the Hub. Their internal tables/text are not yet all driven by the Hub language selector. V11.2 makes this explicit; it does not falsely label menu-only translation as full translation.
