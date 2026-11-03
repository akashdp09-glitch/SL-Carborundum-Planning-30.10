"""Release integrity check (identical copy in apps/daily and apps/firing).

* Every file in BASELINE_MANIFEST.json must either match its baseline sha256, or have an entry in CONTROLLED_CHANGES.json whose
  ``accepted_sha256`` equals the CURRENT file hash. Any later edit therefore fails until the change is re-reviewed.
* An entry must carry a ``reason`` and ``evidence`` (test id / document). Entries migrated from the old name-only list are
  marked ``reviewed: false`` and are reported as PENDING REVIEW (they still pin the hash so further drift is detected).
* Add/refresh entries with scripts/release/controlled_change.py; never edit hashes by hand.
Not a scheduling approval.
"""
from pathlib import Path
import ast, json, hashlib, sys

root = Path(__file__).resolve().parent
sha = lambda n: hashlib.sha256((root / n).read_bytes()).hexdigest()
changes = json.loads((root / 'CONTROLLED_CHANGES.json').read_text(encoding='utf-8'))
if isinstance(changes, list):
    sys.exit('FAIL: CONTROLLED_CHANGES.json is a bare list (no hashes/reasons). Run scripts/release/controlled_change.py --migrate.')
for p in root.glob('*.py'):
    ast.parse(p.read_text(encoding='utf-8-sig'))
errors, accepted, pending = [], [], []
for item in json.loads((root / 'BASELINE_MANIFEST.json').read_text(encoding='utf-8')):
    name, cur = item['file'], sha(item['file'])
    if cur == item['sha256']:
        continue
    e = changes.get(name)
    if not e:
        errors.append(f'{name}: differs from baseline and has no controlled-change entry')
    elif e.get('baseline_sha256') != item['sha256']:
        errors.append(f'{name}: entry was written against a different baseline hash')
    elif e.get('accepted_sha256') != cur:
        errors.append(f'{name}: file changed after it was accepted (current {cur[:12]} != accepted {str(e.get("accepted_sha256"))[:12]}); re-review required')
    elif not e.get('reason') or not e.get('evidence'):
        errors.append(f'{name}: entry lacks reason/evidence')
    else:
        (accepted if e.get('reviewed') else pending).append(name)
for name in changes:
    if not (root / name).exists():
        errors.append(f'{name}: controlled-change entry for a missing file')
if errors:
    print('FAIL:'); [print('  -', x) for x in errors]; sys.exit(1)
print(f'PASS: syntax OK; unchanged baseline files match; {len(accepted)} reviewed controlled change(s) pinned; '
      f'{len(pending)} legacy declared change(s) PENDING REVIEW (hash pinned): {", ".join(pending) or "none"}. Not a scheduling approval.')
