# Performance measurements (cloud VM, synthetic data)

**These are not factory validation.** They were taken on a 4-vCPU cloud VM with a throw-away database of synthetic records, headless Chrome at a phone viewport (390x844 @2x), Chrome DevTools throttling, and one uvicorn process. No real phone, no real camera, no factory Wi-Fi. Re-run on site with `scripts/cloud/perf_user_facing.py` (raw numbers: `docs/PERFORMANCE_RESULTS.json`, measured 2026-10-05 01:16 Asia/Bangkok, 5 runs per page, medians).

## User-facing (what a person waits for)
| Action | No throttle (VM loopback) | Emulated 4 Mbps down / 2 Mbps up / 80 ms RTT, CPU x4 | Emulated 1 Mbps / 0.5 Mbps up / 200 ms RTT, CPU x6 |
|---|---|---|---|
| Mobile home: first contentful paint / load | 24 ms / 11 ms | 276 ms / 391 ms | 716 ms / 1127 ms |
| Scan page: FCP / load | 20 / 11 ms | 272 / 390 ms | 744 / 1149 ms |
| Find page: FCP / load | 24 / 11 ms | 256 / 379 ms | 680 / 1084 ms |
| Audit form: FCP / load | 28 / 15 ms | 308 / 415 ms | 800 / 1204 ms |
| Part register: FCP / load | 28 / 16 ms | 292 / 512 ms | 712 / 1865 ms |
| **Audit submit with one 3.7 MB (12 MP) JPEG: tap to "saved"** | **0.26 s** | **15.2 s** | **60.1 s** |

Reading the table:
* Pages are small (55-160 KB) and render quickly even under throttling. The emulated profile did not visibly delay the first HTML request (TTFB stays ~3-6 ms), so page-load numbers under throttling are probably optimistic for the HTML request itself; the **upload** throttling clearly was applied (see last row).
* **The dominant user-facing cost is the photo upload.** The browser sends the phone's full-size photo; there is no client-side resize. On a 2 Mbps uplink one photo takes about 15 s, and each additional photo in the same submission adds the same again. This is a design observation, not a bug fix made here: shrinking photos would change the stored evidence image, so it is left as an owner decision (see "Recommendation").
* The app tells the user the record is not saved until the server confirms, and a retry with the same submission id is safe (tested), so a slow or dropped upload cannot create duplicates.

## Server-side (in-process, no network)
Measured 2026-10-05 with `scripts/cloud/bench_register.py`, 5,000 synthetic work orders / 20,000 audit rows, 15 runs each, Python 3.12.3:

| Path | Median | p95 |
|---|---|---|
| Part register page 1 (50 rows) | 85.5 ms | 90.0 ms |
| Register API limit 50 / filter by WO / page 100 | 83.7 / 82.4 / 96.0 ms | 93.0 / 83.9 / 97.6 ms |
| Register text search | 56.9 ms | 59.1 ms |
| Resolve a scanned code (exact) | 3.5 ms | 4.0 ms |
| Search box (LIKE) | 5.0 ms | 5.8 ms |
| Mobile home | 5.0 ms | 6.0 ms |
| Audit POST with photo (server wait, no throttle) | ~200 ms | n/a (3 runs) |
| QR decode of a 12 MP photo, label found | ~195 ms | n/a (5 runs) |
| QR decode of a 12 MP photo with no QR (all fallback passes fail) | ~1.1 s | n/a (5 runs) |

The register filtered by WO costs about the same as the unfiltered page because the "latest observation per WO / location / batch" view is computed before the filter is applied, so the cost grows with the total number of audit rows, not with the size of the result. It is under 100 ms at 20,000 rows; larger volumes were not tested and the growth is not yet bounded.

## Recommendation (needs your decision)
Add a client-side "send a smaller copy" option (for example longest side 2048 px, JPEG quality 80, about 0.4-0.8 MB) while keeping the original on the phone, or accept the current behaviour and keep one photo per audit on slow Wi-Fi. Until decided, the current behaviour is unchanged.
