# Use the retained evidence on your computer

1. Extract the review ZIP to a **new program folder**. Keep existing CENTRAL_DATA
   and the configured shared-data path; do not overwrite the factory installation.
2. Open **Reports → Department KPI** or **Production Evidence Analysis**.
3. If the evidence store already exists in the shared data folder, its originals,
   revisions and calculations load automatically. Do not upload the files again.
4. For a new computer without that private data store, transfer a private database
   backup with the shared data folder, or select your owned originals **once** in
   “Retained sources and revised KPI uploads”. The software ZIP intentionally does
   not include private factory databases or workbooks.
5. The five supplied files are the Sirinun/Chosita KPI workbooks, the updated opening
   workbook, the **separate** closure workbook, and the Production status workbook.
   Confirm reporting year 2026 for count sheets without a year cell. Auto-detection
   recognises these files. It rejects the retired combined opening/closure format.
6. The two revised Production KPI section/category files can be imported separately
   with their corresponding roles. Confirm month for day-number headers and the
   quantity unit. Do not label pieces as WOs. Both revised column-format and the
   validated Plan/Actual-row matrices are supported. Unmapped formats need review.
7. Click Import. Repeated unchanged content adds no duplicated quantities. Later
   revisions refresh affected views while retaining originals and older months.
8. Select a month to see automatic Department KPIs. The detailed production page
   defaults to the latest source year's available period; adjust date/section/basis.
   All normalised weights display tonnes. Review missing weights and quality flags.
9. Use **Prepare detailed English report** for an offline HTML report containing
   narrative, tables and charts. Individual tables also have CSV exports.

Data file: `CENTRAL_DATA/DATABASE/production_analytics.sqlite` in the default
configuration (otherwise alongside the configured planning DB). Use a proper
SQLite backup or stop the application before a private transfer; do not replace
an existing evidence database blindly. Customer-level data is not published in
the GitHub software ZIP.

Optional batch import, using the same shared root as the app:

```text
python scripts/import_owner_evidence.py --shared-root "D:\YourSharedData" --year 2026 --author "Your name" --files "D:\Inputs\KPI_Chosita_completed.xlsx" "D:\Inputs\October_in out.xlsx" "D:\Inputs\October-2026_job closure.xlsx" "D:\Inputs\สถานะการผลิต 2026-4 88.xlsx"
```

ภาษาไทย: เก็บ CENTRAL_DATA เดิมไว้ หากมีฐานข้อมูลหลักฐานแล้ว ระบบจะอ่านให้อัตโนมัติ
ไม่ต้องอัปโหลดซ้ำ หากเป็นเครื่องใหม่ให้นำฐานข้อมูลส่วนตัวมาด้วย หรือนำเข้าไฟล์ต้นฉบับ
ครั้งเดียวที่ Department KPI ไฟล์เปิดใบงานและปิดใบงานต้องแยกกัน น้ำหนักแสดงเป็นตัน
ชีต Report เป็นแผนที่ฝ่ายผลิตอนุมัติ และ Pack จ่าย เท่านั้นเป็นผลจริงขั้นสุดท้าย
