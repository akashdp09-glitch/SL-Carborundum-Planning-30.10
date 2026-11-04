# RC29.53 — Department KPI and Production Evidence Analysis

Owner confirmations: 4 November 2026 (Asia/Bangkok). This note supersedes earlier
manager-KPI numbering and the historical nine-measure reference.

## Department KPI: same scheme as manager KPI

| Code | Current definition | Maximum HR marks |
| --- | --- | ---: |
| KPI-PL-01 | Planning accuracy from revised analyst evidence | 15 |
| KPI-PL-02 | Actual packed WO count / planned WO count x 100 | 10 |
| KPI-PL-03 | Closed / opened WO count x 100, same period; backlog separate | 15 |

The three maxima sum to 40. Achievement percentages are not awarded HR marks;
no HR conversion is invented. Old manual events remain under their old definition
version; old code numbers are not silently reinterpreted under the new order.

The Department KPI page automatically reuses retained sources. It reads revised
analyst daily ratios using the supplied arithmetic-mean method (actual zeros
retained; blanks excluded), separate opening and closure workbooks, and approved
production plans/final packing handovers. No fictional inspected-record counts
are created from a supplied percentage. For this owner's separate count files,
category totals are labelled source items; their distinct-WO identity and backlog
split cannot be reconstructed from totals alone. This limitation is shown next
to the reported ratio rather than claiming unverified distinct-WO performance.

The revised Production KPI section/category inputs are separate source roles.
Both the validated day-number matrix and revised date/group/plan/actual column
format are supported. Source units must match the upload setting. The section
Packing rows alone can supply department KPI 2; category input is supporting
packing evidence, not an additional quantity to add. Other formats fail explicitly
and require mapping review. This release does not claim to have validated revised
production KPI files that the owner has not supplied.

Retired combined Open Job/Close Job workbooks are rejected for the new import.
The old nine-measure reference and legacy KPI source slots are archive/reference
only, omitted from missing-source upload prompts. Historical records are retained.

## Retained originals, automatic calculation and persistence

SQLite file: `<configured planning DB directory>/production_analytics.sqlite`,
normally `CENTRAL_DATA/DATABASE/production_analytics.sqlite`.

It retains original workbook bytes, original filename, SHA-256, role, reporting
configuration, parser version, uploader, import time, revisions, normalised rows,
source cells and calculated monthly KPI snapshots. Settings have an audit history.
One workbook import commits atomically. Unchanged content under the same parser
configuration returns UNCHANGED without parsing XML or duplicating quantities.
A new parser/rule version can create a traceable reprocessing revision; all older
revisions remain. Only the latest relevant source snapshot contributes, so versions
are not added together. Earlier KPI months remain available after later imports.

The supplied five relevant original files have been imported into this cloud
instance's default shared evidence store. They survive navigation/restarts; the
database is not browser session state. Original uploaded workbooks were not changed.

**Software and private data are separate.** The software ZIP excludes operational
databases/workbooks. A different Windows computer must retain/copy its evidence
database with the shared data folder, or import its locally owned originals once.
It cannot receive the cloud machine's private database merely by downloading code.
See `PRODUCTION_EVIDENCE_IMPORT_GUIDE.md`. No customer-level report or private
database is published to GitHub as part of this release.

## The new English analysis destination

Reports → **Production Evidence Analysis**. This is separate from Planning WIP
and does not require building a Daily/Firing plan or parsing a Plan-2026 workbook.

Views: Overview; Plans vs actual; Sections; Product categories; Weeks and months;
Customers; Part sizes; QC and WIP; Data quality; Source audit.

- Date/section/evidence-basis filters, English tables and CSV exports.
- Tonnes, pieces and distinct WOs in separate measures; no incompatible-unit sum.
- Category actual charts use **Pack จ่าย only**, including stacked week/month
  charts. Section handovers are available separately as process throughput.
- Distinct WOs are computed inside each selected bucket, not by adding daily
  distinct counts. Counts overlap across sections, periods or conflicting categories.
- Customer and D x T x H enrichment uses an unambiguous normalised WO match to
  `สถานะผลิต`, preferring finished dimensions BH:BJ, with M:O labelled as forming
  dimensions when used. Missing values stay Unknown; SPEC dimensions/translations
  are not invented. Source customer proper names remain as supplied.
- English QC and WIP tables retain the independent NCR/rework/accepted/rejected
  fields and negative source WIP balances. No stock correction or second deduction
  from handovers is inferred. WIP is a source snapshot, not monthly production.
- Exact source-row inspection and original-workbook download are available.
- The detailed English report download is a self-contained HTML file containing
  narrative, tables and offline interactive charts, including quality/provenance.

Only the selected analytical view renders. Normalised records are cached by
persisted production-source ID; source changes invalidate the cache. Original
26 MB workbooks and full HTML reports are prepared only when explicitly requested.

## Owner-confirmed production semantics

- `Report ...` worksheets are **approved production plans** (owner confirmation).
- `...จ่าย` worksheets record section outputs/handovers.
- Only `Pack จ่าย` is final actual output for department/category achievement.
  Never add `Report Pack` quantities as extra actual output. Operator allocations
  can repeat planned quantities; raw plan piece/weight sums are labelled source
  allocations rather than certified unique material quantities.
- Kiln-loaded quantities remain in-process and are not completed firing output.
- No `เตรียมReport` sheet exists in this workbook; Preparation plans are not invented.
- `Report เตา` contains many attendance/activity rows without WO quantity evidence;
  those rows are retained but cannot become invented planned WOs/pieces.

The workbook has 21 sheets. Fifteen transaction sheets use validated bounded
column mappings. Changed WO/quantity headers fail before misreading data.
The remaining sheets, QC, WIP, master/reference snapshots and empty tabs are
inventoried; nonempty reference cells are retained in bounded projections. The
complete original remains available. The 16,383-column formatting extent on
`คนชั่ง` is never expanded into a huge analytical rectangle.

## Weight policy: display metric tonnes

- Confirmed Forming Report W/X grams: grams / 1,000,000 = tonnes.
- Kilogram source values: kg / 1,000 = tonnes.
- WIP/QC fields explicitly labelled tonnes remain tonnes.
- Raw total/per-piece values, interpreted units, conversion rationale and source references remain
  available. No manufacturing-capacity constant is inferred from the owner's usual
  daily 1–5 tonne guidance; days above that reference are review flags only.
- Mixed scales in other report sheets are corrected only where a 1000x scale
  agrees with the same WO/section handover median mass-per-piece (2% analytical
  tolerance). The cross-reference and an inferred-correction review flag are kept.
  This is an evidence check, not an approved capacity rule. Ambiguous/extreme
  weights remain unknown and are excluded from weight totals; pieces/WOs remain.
- Every total includes weight coverage; unknown weights are not zero-filled or
  estimated from an unrelated stage. Process stages are never summed as unique
  factory output. Weight examples do not certify a feasible schedule.

## Actual workbook review and checks

The source retains 124,245 nonempty bounded rows, including reference/header
evidence, not 124,245 work orders. Data runs through 3 November 2026; older history
is retained. The owner confirmed short year 69 means Buddhist 2569 (2026). All 28 affected
preparation rows are restored to October 2026 with the original year retained
and the correction rule recorded. Years 25/26 remain 2025/2026; an explicit
four-digit future year such as 2069 is not silently rewritten.

October source review: Packing plans cover 594 distinct WOs and Pack จ่าย contains
518 distinct positive-output WOs: **87.2054%** actual/plan count ratio. The sets
have 484 matches, 34 actual outside the month plan, and 110 planned without output.
The source contains 177,397 packed pieces and 92.477160 known-weight tonnes; some
weights are unavailable, so this is explicitly a partial known-weight total.

Analyst accuracy is 62.555% under its supplied daily arithmetic-mean method.
Separate opening/closure source counts are 313 and 333, giving 106.3898% reported
throughput; item labels and missing backlog identities are disclosed. None of
these percentages is silently converted into an awarded HR mark.

On this Linux CPython 3.12.14 instance, first production parsing took about
32.8 seconds for 124,245 retained rows. Reading normalised rows took about 2.7
seconds before UI caching. The unchanged-file fast path took about 0.037 seconds
after reading the file bytes. These are individual measured runs, not factory-load
or concurrency guarantees. Building the full 20 MB offline report took about
13 seconds in one run and is user-triggered, not a navigation cost.

Current regression outputs are in `RC53_*_TESTS.txt`. Synthetic page tests cover
all ten analytical views, department cards, future-date exclusion and full-hub
routes (including the retired route alias). Actual-workbook inspection verifies
header mappings, a forming gram/tonne example, deduplication and October WO counts.

## Existing limitations carried forward

The uploaded Daily/Firing engine acceptance checks still fail against their
supplied controlled-change hashes; those engine files were not altered or falsely
accepted here. Full firing/daily optimisation, real load geometry, full earlier
UI redesign, source Recovery fixes and the complete illustrated manual remain
separate unfinished work. This is a **review candidate**, not a factory-certified
release. Windows/phone/GPS/factory-Wi-Fi checks remain on-device acceptance.

## Migration and rollback

New tables live in a new evidence SQLite file. Old operational tables and old
KPI evidence are untouched. Back up shared data before deployment. Extract to a
new program folder and retain the configured shared data folder. To roll back,
stop the candidate and use the previous program folder; retain the new evidence
database for reconciliation rather than deleting it. Prior code will simply not
read these new tables. Do not merge/replace a live installation without review.
