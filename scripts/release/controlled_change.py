"""Record a controlled change to a release-baselined file.

  python scripts/release/controlled_change.py apps/daily firing_engine_desktop_v2.py \
      --reason "..." --evidence "tests/path.py::test_name" [--reviewed]
  python scripts/release/controlled_change.py apps/daily --migrate     # convert the legacy name list (hash pinned, reviewed=false)

Refuses entries without a reason and evidence that resolves to an existing file. The accepted hash is computed from the file as it is
now, so run it AFTER the last edit and after the evidence test passes. Hashes are never typed by hand.
"""
import argparse, datetime as dt, hashlib, json, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('folder'); ap.add_argument('file', nargs='?')
ap.add_argument('--reason'); ap.add_argument('--evidence'); ap.add_argument('--reviewed', action='store_true'); ap.add_argument('--migrate', action='store_true')
a = ap.parse_args()
d = Path(a.folder)
sha = lambda n: hashlib.sha256((d / n).read_bytes()).hexdigest()
base = {i['file']: i['sha256'] for i in json.loads((d / 'BASELINE_MANIFEST.json').read_text(encoding='utf-8'))}
cc_path = d / 'CONTROLLED_CHANGES.json'
cc = json.loads(cc_path.read_text(encoding='utf-8')) if cc_path.exists() else {}
today = dt.date.today().isoformat()
if a.migrate:
    if isinstance(cc, list):
        cc = {n: {'baseline_sha256': base[n], 'accepted_sha256': sha(n), 'reason': 'Declared in the legacy CONTROLLED_CHANGES.json name list; per-file reason not recorded in the supplied documents.',
                  'evidence': 'legacy declaration (V16.x release notes)', 'reviewed': False, 'recorded': today} for n in cc if n in base}
elif a.file:
    if not a.reason or not a.evidence:
        sys.exit('refused: --reason and --evidence are mandatory')
    ev_file = a.evidence.split('::')[0]
    if not (Path(ev_file).exists() or (d / ev_file).exists()):
        sys.exit(f'refused: evidence file {ev_file} does not exist')
    if a.file not in base:
        sys.exit(f'{a.file} is not in BASELINE_MANIFEST.json')
    cc[a.file] = {'baseline_sha256': base[a.file], 'accepted_sha256': sha(a.file), 'reason': a.reason, 'evidence': a.evidence, 'reviewed': bool(a.reviewed), 'recorded': today}
else:
    sys.exit('nothing to do')
cc_path.write_text(json.dumps(cc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('written', cc_path, len(cc), 'entries')
