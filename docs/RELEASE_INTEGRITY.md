# Release integrity: the four files that failed the daily / firing checks

## What failed
`VERIFY_RELEASE.py` (daily and firing) compares each file with `BASELINE_MANIFEST.json`. Four files differed from the baseline and were **not** declared in `CONTROLLED_CHANGES.json`:

| # | Folder | File | Baseline sha256 (prefix) | Current sha256 (prefix) |
|---|---|---|---|---|
| 1 | apps/daily | `daily_linear_engine_v1_1.py` | `1060bf3a...` | `ed44ac21...` |
| 2 | apps/daily | `sl_ppc_fast_store_v4_6.py` | `ebf03ed5...` | `b3ab79b2...` |
| 3 | apps/daily | `firing_engine_desktop_v2.py` | `dd8dc05e...` | `ffe7e6e8...` |
| 4 | apps/firing | `firing_engine_desktop_v2.py` | `08cf55f1...` | `bdfa7014...` |

Full hashes, reason, evidence and review flag for every entry are in `apps/daily/CONTROLLED_CHANGES.json` and `apps/firing/CONTROLLED_CHANGES.json`; the checker enforces them (a pinned hash that no longer matches the file fails the release again).

## Investigation (baseline vs the V16.23 build vs now)
| # | Baseline -> V16.23 (`V23_BUILD_MANIFEST.json`, `docs_archive/REVISION_TRACEABILITY_V16_23.txt`) | V16.23 -> now | Verdict |
|---|---|---|---|
| 1 | Date parsing: `pd.to_datetime` on Excel serials could produce dates near 1970; replaced by `date_and_wo_rules.parse_date`; layer-identity lookup normalised. | Identical to V16.23 (hash matches the V23 manifest). | **Intentional**, documented in the V16.23 revision notes. Now covered by `test_linear_engine_uses_the_safe_parser`. |
| 2 | Explicit date decoding when the fast store is loaded (no NaT, no 1970 dates). | Identical to V16.23. | **Intentional.** Covered by `test_fast_store_deserialises_dates_without_nat`. |
| 3 | None (the baseline equals V16.23 for this file). | A V16.24 edit replaced the plotly fallback. The old fallback set `go = px = None`, so a missing plotly would crash later with an unclear `AttributeError` on the first chart. | **Intentional but poorly guarded.** I replaced it with a stub that raises `ImportError` with an explicit message the moment a chart is requested, then recorded it. Test: `test_missing_plotly_fails_with_clear_message`. |
| 4 | Same as 3 for the firing copy. | Same. | Same. |

No unintended behavioural change was found in these four files. Nothing was fixed by editing a checksum or by turning a check off: the two engine edits (1, 2) are recorded as reviewed controlled changes with evidence tests, and the plotly guard (3, 4) was corrected in code first.

## How a change is now released
1. Edit the file. 2. Write a test that proves the intended behaviour. 3. Run
   `python scripts/release/controlled_change.py apps/daily <file> --reason "..." --evidence "tests/release/test_x.py::test_name" --reviewed`
   (the tool refuses a missing reason or an evidence path that does not exist, and computes the hash itself). 4. `python scripts/cloud/manifest_report.py` and both `VERIFY_RELEASE.py` must pass.
`VERIFY_RELEASE.py` prints that a pass is **not** a scheduling approval.

## Still open (honest status)
Ten earlier "declared" changes are hash-pinned but **not reviewed**, because the supplied documents give no per-file reason:
* apps/daily: `ppc_desktop_core_v1_9.py`, `traceable_views.py`, `production_wip_control.py`, `daily_job_control.py`, `daily_md_report.py`, `meeting_presentation.py`, `daily_planner_app.py`
* apps/firing: `ppc_desktop_core_v1_9.py`, `traceable_views.py`, `firing_tomorrow_fast.py`

The verifier reports them as `PENDING REVIEW`. They pass because their current content is exactly what shipped in `SL_V16_28_CODE.zip` (the extraction commit `d8a7305`); no manifest in the package records why they differ from `BASELINE_MANIFEST.json`. A reviewer who knows why they changed should add the reason with the tool above.
