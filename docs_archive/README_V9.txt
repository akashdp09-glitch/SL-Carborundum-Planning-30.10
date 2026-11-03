SL CARBORUNDUM INTEGRATED PLANNING CENTER V9

Key corrections requested 27-Sep-2026
- ONE visible browser window with persistent tabs. Daily, Firing and QR iframes remain mounted while switching tabs, reducing reset/re-upload behavior.
- Shared Plan-2026: upload in Sources, Daily or Firing -> controlled copy updates company_data/Plan-2026-LATEST.xlsx. Original source file is never edited.
- Shared Firing output: generated firing plan automatically updates company_data/Firing-Plan-LATEST.xlsx; Daily uses it when no local override is supplied.
- Shared Stock, Sales Forecast and Packaging Standard defaults.
- Packaging standard supplied by user is bundled as company_data/Packaging-Standard-LATEST.xlsx and can be replaced from Sources.
- MRP detects the REAL Plan-2026 material layout: columns 1/g, 2/g.1, 3/g.2, 4/g.3, 5/g.4; also supports material1..material5 layouts. Date/time-formatted bad gram cells are rejected as numeric demand rather than becoming huge values.
- QR pack generation for every Work Order in the central mobile database.
- Separate English-customer Plan-2026 copy generator. Original Plan-2026 remains unchanged. Thai names are romanized when pythainlp is available.
- Daily dashboard shows total Stock in Hand and total/open/closed WO values.
- Planning vs Production WIP changed to stacked section x product-category comparison.
- Capacity chart x-axis labels are vertical to reduce overlap.
- More SL product imagery is used in the Control, Daily, Firing and Operator screens.
- English/Thai is primary. The combined control language selector is real; Daily/Firing keep bilingual labels. Operator remains compact.

Storage
- Program may stay on local PC.
- Set SERVER_STORAGE_CONFIG.bat for server paths before production rollout.
- Avoid a sync-folder SQLite database for many concurrent users. Use one central service/server for multi-user operation.
