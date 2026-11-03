V1.9.48 controlled UI update — 23 Sep 2026
- Daily MD report summary is fit to ONE printable page; full data remains in separate editable source sheets.
- Reporting > Traceable Data Studio: date/category controls, selectable Plotly graph, matching editable rows, session-only correction, CSV export. Does NOT overwrite Plan2026 or modify scheduling.
- Reporting > Process-sheet evidence: user uploads current Plan2026 and explicitly selects process sheet, WO, actual quantity, actual date. No unverified unit assumptions.
- Plan vs Production WIP side-by-side chart (Plan first, Actual second) added to Daily MD Report.
- Bundled user-provided Packaging and Diamond reference workbooks; existing operational master databases unchanged. Reference sheets may require mapping/validation before automated consumption.
- Firing Planner has separate traceable data studio; reviewed corrections are DISPLAY-ONLY and do not override physical release gates.
- Streamlit plot selection requires a Streamlit version supporting on_select. Older versions fall back to chart + related data table.
- Python compile and standalone unit tests passed. Full factory workbook integration and runtime must still be validated before operational release.
