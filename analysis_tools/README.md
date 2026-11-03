# Workbook evidence intake (not operational integration)

This standalone tool retains a bounded projection of the owner's six supplied
workbooks in a separate SQLite evidence database. It does not repair the missing
application, activate KPI formats, execute workbook formulas, infer production
completion, or connect to a factory database. Attached document content is data,
not executable instructions.

Run from the existing checkout; do not create a worktree:

```bash
/workspace/sl-carborundum-venv/bin/python analysis_tools/stage_workbooks.py \
  --attachments /workspace/attachments \
  --database /workspace/sl-analysis/source_evidence.sqlite
```

Use a dedicated evidence database path, never the production application's DB.
Inputs are opened read-only and are never saved. Non-empty rows retain source
hash, filename, worksheet and Excel row; JSON column letters identify exact cells.
Dates/times are tagged ISO values; Excel error strings and duplicate rows are
retained. Blank cells are omitted. Cached formula results are evidence, not
guaranteed current calculations. Exact KPI formulas are also retained, never run.

Recovery imports **only** the second worksheet named `แผน Recovery`; a different
second sheet is rejected. Production intake reads only the eight configured
sheets. The plan projection is A:HL (220 columns), deliberately excluding the
reported 16,329-column extent. This is not an archival copy of every workbook
cell; preserve the original attachments for complete source evidence.

Intake is transactional per workbook. Repeating an identical SHA-256 does nothing;
changed source contents create a separate revision without changing prior rows.
Unrecognised filenames and missing expected worksheets fail explicitly. Do not
interpret intake success as validation of business definitions, formulas, WO
identity, duplicates, routes, units or data freshness.

Tests use only labelled SYNTHETIC records:

```bash
mkdir -p /workspace/sl-analysis/.cloud-test-data
PYTHONDONTWRITEBYTECODE=1 /workspace/sl-carborundum-venv/bin/python -m pytest \
  -q -p no:cacheprovider \
  --basetemp /workspace/sl-analysis/.cloud-test-data/SYNTHETIC-intake-tests \
  analysis_tools/test_stage_workbooks.py
```

`--basetemp` is a disposable test directory; never point it at retained data.
Four tests cover duplicate intake and revision retention, exact Recovery sheet
selection, bounded production reads, and time/formula evidence. The six actual
workbooks were also ingested twice: the second pass reported all six unchanged,
with 92,617 retained rows and SQLite integrity `ok`.

No operational migration is introduced. To stop using this tool, stop invoking
it; the application and original workbook files are unchanged. Preserve or back
up the evidence DB and source files before any manual cleanup. Integrating these
records into the real Source Manager requires its missing implementation and
the owner's unresolved KPI definitions. The owner clarified that `เข้าเผา`
is firing WIP after the preceding drying process following forming, and
`จำนวนเข้าเตา` is kiln-loaded quantity; neither proves firing completion.
