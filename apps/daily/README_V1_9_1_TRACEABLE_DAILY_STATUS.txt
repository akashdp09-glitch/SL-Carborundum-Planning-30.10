V1.9.1 TRACEABLE DAILY STATUS CONTROL

New production-performance architecture:
1. Upload multiple monthly/yearly Daily Status Excel files in input ⑤.
2. Program reads every dated sheet automatically.
3. HARD RULE: blank/invalid Work Order = rejected row. Its qty/category/problem/action never enters a KPI.
4. Source traceability retained: file, sheet, original row, date, department, WO.
5. Three plan layers remain separate:
   PPC Issued Plan → Production Daily Plan → Production Actual.
6. KPIs include pcs and WO counts, by department and P/R/S/T/M/PB category.
7. Problem and Production Action are preserved exactly as source evidence.
8. PPC Recommended Action is a separate field and never overwrites Production Action.
9. Rejected source rows and read errors have separate evidence tables.
10. Updated month files can be re-uploaded; current upload is analyzed without changing the original source workbook.

Important:
- Daily Status files are quantity evidence. Weight is NOT taken from rows without valid WO.
- This version does not claim that low utilization is automatically a pull failure.
- Due-date/capacity/firing validation remains in PLAN ACCURACY / VALIDATION.
