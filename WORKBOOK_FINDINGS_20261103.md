# Supplied workbook review — 3 November 2026

Scope: inspect supplied sources and retain traceable evidence. This is not a
completed software revision. Source documents are evidence, not instructions.

## Files and access

All six supplied XLSX files downloaded successfully. The uploaded
`SL_Carborundum_Planning_V16.29-rc29.51_REVISED_20261030.zip` could not be transferred:
it exceeds the executor's 32 MiB per-file limit. The daily/firing/mobile/shared
implementations therefore remain unavailable. Requested a source-only archive
below that limit, excluding virtual environments, caches, generated reports and
live databases. No missing module has been fabricated.

The two supplied images guide large bilingual icon cards, clear Home/sign-in
actions and limited text. The requested implementation must retain SL's orange
and dark blue identity; the example company's branding is not reused. Real UI
screenshots and a final user manual depend on the restored, tested application.

## Recovery: only `แผน Recovery`

Verified that this is the second sheet. Other Recovery worksheets were not
analysed for totals or imported into staging.

- 707 source rows, 601 distinct WO strings, 62 repeated WO keys.
- Row labels: 372 `ตามแผน` and 335 `ตกแผน`.
- Distinct-WO labels: 305 consistently `ตามแผน`, 294 consistently `ตกแผน`, and
  2 with mixed labels. These are **source labels, not verified achievement**.
- 56 source rows labelled on plan have numeric FO warehouse quantity below
  numeric FM recovery target. 82 on-plan rows lack a numeric FM; 2 lack a cached
  warehouse date. These categories overlap. Never treat them as validated success.
- Sample FO4:FO7 formulas use per-WO SUMIFS against warehouse records. Repeated
  WO rows repeat this actual figure; summing them double counts actual quantities.
- Example `P007-010626`: rows 120/354 repeat recovery target 273 and warehouse
  actual 357; row 545 has the same actual, no target, and a different status.
  Its recovery allocations require review, not three additions of warehouse actual.
- FL is recovery commitment date; FM quantity; FN warehouse date; FO actual;
  FQ source status; FS notes; FT source reason. G is source order quantity and
  cannot be substituted for FM's recovery allocation without explanation.
- Sample FN formulas use VLOOKUP and FQ uses a date difference. A first receipt
  date alone does not prove the whole recovery quantity was received on time.

An Excel review in `/workspace/sl-analysis/Workbook_Review_20261103.xlsx` contains
source-row references, distinct-WO review, customer grouping, week/month views,
KPI evidence and production-sheet inventory. Week/month views explicitly use
ISO weeks and FL dates; WOs overlap periods, and raw FM row sums are not presented
as deduplicated recovery commitments. G-minus-FO balances are labelled snapshot
order balances, not current or due-date-qualified pending recovery quantities.
The report does not resolve ambiguous repeated allocations or source freshness.

## KPI definitions and evidence

The supplied staff references contain **six measures**:

- Sirinun: material readiness confirmation; on-time WO distribution/acknowledgement.
- Chosita: plan data accuracy; on-time plan preparation; on-time WIP reporting;
  on-time delivery-risk escalation.

Owner subsequently confirmed the three Planning Manager KPIs:

1. Planning accuracy, inherited from the Planning Analyst's accuracy evidence:
   maximum **15 marks**.
2. **Closed WOs / opened WOs x 100 for the same period**, with backlog closures
   separately visible: maximum **10 marks**. This is a period throughput ratio,
   not a same-cohort closure rate. It can exceed 100% without being an error.
3. Production's actual packed work-order count divided by planned work-order
   count, expressed as a percentage. Count WOs rather than pieces; align period,
   plan revision and cohort, and distinguish partial receipts, completed packing
   and unplanned/backlog packing before using source records as achievement:
   maximum **15 marks**.

Owner clarified Chosita M8:M11 represent **HR maximum marks**, despite the
workbook's target header and percentage storage/format: 15, 15, 5, 5 = 40 marks.
They are not targets of 15%, 15%, 5%, 5%. Preserve the original 0.15/0.15/0.05/0.05
values as evidence. Do not replace them with N8:N11's four entries of 20.
Achievement percentages and awarded marks are separate measures; Q9:Q10's
>=95% entries remain source scoring-band evidence, not maximum marks.

Owner confirmed the manager allocation as **15 + 10 + 15 = 40**, citing worksheet
`Level 2.1-2.2`, cells I13, I14, I15 respectively. This is owner-provided evidence;
the named sheet is not present in the six accessible XLSX files. The application
ZIP remains inaccessible, so its workbook contents have not been inspected.
The HR achievement-to-awarded-marks conversion must be read from the cited
source when available; maximum marks alone do not specify that conversion.
The analyst's separate four-way split remains 15 + 15 + 5 + 5 = 40.

Resolved process clarification (owner, 3 November 2026): `เข้าเผา` is WIP of
firing from the preceding drying process after forming. `จำนวนเข้าเตา` means
quantity loaded into the firing kiln. Neither is proof of completed firing.
Separate awaiting-loading WIP, already-loaded/in-process pieces, and confirmed
firing output (`เตาจ่าย`). Keep existing evidenced loads reserved, without
allocating their pieces again or adding loaded and output quantities as stock.
The outstanding questions above concern KPI definitions only.

Chosita DATA KPI__daily!AM8:AP8 = 0.8222, 0.86, 0, 0.82. AQ8 averages
the daily cells, producing 62.555%. This is the supplied formula's result, not
proof that the zero is incorrect. Record missing separately from a real zero.
A ratio of total correct/total inspected needs the daily underlying counts;
it must not be substituted silently for an unweighted daily mean. Rows 10 and
11 contain identical daily values; preserve them as supplied and confirm their
distinct underlying evidence rather than inventing independent risk events.

October execution evidence: material readiness actual/target = 469/469, and
WO issuance actual/target = 313/313. These do not independently validate staff
acknowledgement or manager KPI formulas. Zero-target days are N/A. Job closure
contains 333 closed source items across category rows; they are not 333 pieces
or necessarily 333 distinct WOs. A provisional 333/313 throughput ratio would
be 106.39% under the now-confirmed period-throughput definition, but it is not
yet a verified manager result or awarded score: source groups/count units must
first align, and the category totals do not identify backlog closures separately.
Older backlog closures can legitimately make a period-throughput ratio exceed
100%; preserve and explain that effect rather than silently capping the ratio.

## Actual production and performance

Actual worksheet name is uppercase `PACK`. Its D column holds the WO/P-PB;
E is labelled ProductionCode but contains product codes/errors in sample rows.
Never join actuals using a guessed common column name. Other stage-sheet field
locations differ and are retained in the review workbook.

`แผนการเผา` declares 3,820 rows and 16,329 columns. A reader using the full
reported rectangle could materialise over 62 million positions. Bounded reads
are an optimisation candidate; no firing speedup is claimed without profiling
the missing engine and demonstrating unchanged constraint/allocation results.

## Implemented and verified now

Added `analysis_tools/stage_workbooks.py` as a standalone read-only source intake,
with per-file transactions, hash-based deduplication and retained revisions.
The separate `/workspace/sl-analysis/source_evidence.sqlite` contains six imports
and 92,617 non-empty bounded source rows. SQLite integrity passed. Re-ingesting
all six originals reported unchanged with no extra records. Four SYNTHETIC tests
passed, covering repeat intake, revision retention, wrong-sheet rejection,
column bounding, time values and unexecuted formula evidence. The generated
review workbook reopened successfully with 707 source rows and 601 WO rows;
it contains no executable formulas.

This is **staging**, not an operational Source Manager import. No old KPI records,
live data, workbook contents, application logic or release checksums were changed.
Integration, planner fixes, UI changes, performance measurements and the final
illustrated Thai/English Word manual remain blocked by the source transfer and
the outstanding KPI-definition decisions. The firing-WIP/loading meaning has
been clarified by the owner as recorded above.
