# Cloud / development environment (reproducible)

* `.cursor/environment.json`: `install` = `bash scripts/cloud/install.sh`, `start` = `bash scripts/cloud/start.sh`.
* `install.sh` installs (if missing) `python3-venv`, `tesseract-ocr` + `tesseract-ocr-tha` + `tesseract-ocr-eng`, `poppler-utils`; creates `.venv`; installs `requirements-cloud.txt` (= `requirements-runtime.txt` + `requirements-dev.txt`, all exact); then **fails if any installed package differs from `requirements-cloud.lock.txt`** (full transitive freeze, 74 packages) so drift is visible instead of silent.
* `start.sh` creates synthetic data in `.cloud-test-data/` and starts hub 8510, daily 8511, firing 8512, analysis 8513 and mobile 8000 in tmux sessions.
* `validate.sh` runs: compileall, `pytest suite tests/release`, the undefined-name self-test (scope fixed to skip `.venv`, caches and test data; 7 known star-import notes remain), `pytest apps/mobile/tests`, both `VERIFY_RELEASE.py`, the manifest report, four headless renders, and the mobile API check when the server is up.
* Browser checks (`scripts/cloud/browser_check.py`, `perf_user_facing.py`) use Playwright with the system Chrome at `/usr/local/bin/google-chrome` (override with `CHROME=`); no Playwright browser download is needed.
* Knowledge extraction: `python knowledge/extract_documents.py` (needs Tesseract `tha`+`eng` and Poppler).
* Cloud tests never use production data. They do not verify a real phone camera, GPS, factory Wi-Fi or Windows startup.
