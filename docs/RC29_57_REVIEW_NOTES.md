# RC29.57 review — 6 November 2026

This is a revised complete code ZIP, not factory acceptance. Extract into its unique new folder and point it at your existing central data. Do not overwrite CENTRAL_DATA. Private workbooks/databases are retained in the existing installation and excluded from this code download.

## Firing transition

- Select first firing date 6 November and retain issued loads through 9 November. Valid supported loads are merged into the SAME main Firing Loads and Operator Print used by the UI and daily anchor, not only a supplementary sheet.
- Reserve retained WO quantities before optimization. Production actuals are unchanged. New optimization begins 10 November when commitments have been retained.
- Protect kiln availability BEFORE candidate allocation; separate measured formed WIP from the future upstream portion of a partially completed WO.
- Reject a whole issued load with explicit reasons if current formed WIP is insufficient, a WO is closed/missing/ambiguous, the kiln calendar overlaps, starts/day are exceeded or known physical limits fail. No silent clipping or date shifting. A missing physical placement/drying confirmation remains HOLD.
- Transition Control and Transition Reconciliation contain source hashes, sheets and rows. No past workbook is bundled or fabricated.

## UI and evidence

Home exposes revised staff/count workbook upload, desktop scan URL/QR and detailed Production Evidence Analysis. Compact white cards have larger icons/Thai and smaller English. Soi=Chosita and Pui=Sirinun. Department maxima 15/10/15; awarded HR scores require the approved conversion. MD daily category open/close counts remain an operational report, distinct from staff KPI. Two missing Production KPI sources are not invented.

Desktop/mobile share central physical audits, append-only process and reasoned whole-WO status histories and Excel reports. Physical observations never add production. Whole-WO changes never fabricate packed output. Recovery reads only แผน Recovery, preserves repeated/conflicting WOs and reconciles row-linked planned/applied/pending/unmatched quantities. MRP separates physical stock, incoming and under-test stock; MPS provides weekly/monthly source-backed demand. Analytical weights are tonnes, unknown conversions remain flagged.

## Validation limits

See RC57 test logs. The actual older FIRING_PLAN_OUTPUT_V1_9_12_Prod_29.10.xlsx mentioned in pasted chat text is NOT present in this workspace: its alleged prior results are not treated as verified evidence. Synthetic transition tests and a real fast-allocator/export test confirm the integration, not the factory's exact quantities or full upstream/resource acceptance. The allocator/export scenario disables hard pull/upstream validation; dedicated regression tests cover upstream/drying logic separately. Top/front physical verification, factory scanner/phone/Wi-Fi and Windows startup still need on-device acceptance. Broader historical failures and three inherited firing integrity mismatches remain reported. Do not treat this review package as an automatically approved production schedule.

## Additive data and rollback

New append-only wo_status_events and tracking_addresses tables; existing audit/status/import originals remain. Existing passwords are not reset. Stop services, back up the existing shared folder, extract the new code folder, configure that SAME shared root and restart. To roll back code, stop services and launch the previous code folder against the retained data; do not restore an empty database. Earlier code does not enforce all current guards.
