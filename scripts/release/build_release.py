"""Build the versioned Windows ZIP from the committed tree (never from the working directory).

  python scripts/release/build_release.py            # refuses if tracked files have uncommitted changes
  python scripts/release/build_release.py --verify   # also unpacks the ZIP and re-checks it

What goes in: git-tracked files only, minus the exclusion rules below. What never goes in: live/dated data workbooks, databases, photos, uploads,
QR images, logs, caches, virtual environments, cloud-only scripts, secrets. A RELEASE_MANIFEST.json records the exact commit, the version and the sha256 of every file shipped.
Windows line endings (CRLF) are applied to .bat files only; the manifest records the shipped hash.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import py_compile
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]

EXCLUDE_GLOBS = [
    "downloads/*",  # downloadable prior releases must never be nested into the next package
    "knowledge/Planning_KPI_Reference_Q4_2026.xlsx",
    "knowledge/kpi/Planning_KPI_Measurement_Evidence_REVISED.xlsx",
    "docs/RC29_52_Quick_Guide_Thai_English.docx",  # historical guide uses superseded KPI numbering
    "docs/RC29_54_User_Guide_Thai_English.docx", # superseded scanner-specific guide
    "RELEASE_MANIFEST.json",  # generated below; do not archive a stale manifest or hash itself
    "knowledge/kpi/inputs/*", "seed_data/*", "P280526.csv",
    "apps/daily/DIAMOND_AUG2026_ISSUE.xlsx", "apps/daily/DIAMOND_CURRENT_PLAN_160926.xlsx",
    "apps/daily/DIAMOND_HISTORY_DATABASE.xlsx", "apps/daily/JOB_REGISTER_REFERENCE_SEP2026.xlsx",
    ".cursor/*", ".gitignore", "scripts/cloud/*", "requirements-cloud.txt", "requirements-cloud.lock.txt",
    "SL_V16_28_CODE.zip",                              # the previous package, kept in git for provenance only
    "Plan 2026-*.xlsx", "*-LATEST.*",                  # live / dated operational data: imported through the Source Manager on site
    "*.sqlite", "*.sqlite-*", "*.db", "*.db-*", "*.log", "*.pyc", "*/__pycache__/*", "__pycache__/*",
    "apps/mobile/uploads/*", "apps/mobile/qr/*", "apps/mobile/data/*", "CENTRAL_DATA/*", ".cloud-test-data/*", ".venv/*", "dist/*", "releases/*", "logs/*",
    "*.env", ".env", "*secret*", "*.pem", "*.key",
]
FORBIDDEN_IN_ZIP = ["*.sqlite", "*.db", "*.pem", "*.key", ".env", "*.log", "*.pyc", "Plan 2026-*.xlsx"]
SECRET_PATTERNS = [re.compile(rb"SL_APP_SECRET\s*=\s*[\"']?(?!change-this|replace-with|%|\$|\s)[A-Za-z0-9_\-]{8,}"), re.compile(rb"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
                   re.compile(rb"AKIA[0-9A-Z]{16}")]
TEXT_CRLF = (".bat",)


def run(*a):
    return subprocess.run(a, cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def excluded(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(Path(rel).name, g) for g in EXCLUDE_GLOBS)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true", help="build anyway (the manifest will say dirty=true)")
    ap.add_argument("--out", default=str(ROOT / "dist"))
    a = ap.parse_args()

    version = (ROOT / "VERSION").read_text().strip()
    commit = run("git", "rev-parse", "HEAD")
    branch = run("git", "rev-parse", "--abbrev-ref", "HEAD")
    dirty = bool(run("git", "status", "--porcelain", "--untracked-files=no"))
    if dirty and not a.allow_dirty:
        sys.exit("Tracked files have uncommitted changes; commit first so the manifest names a real commit (or --allow-dirty).")
    files = [f for f in run("git", "ls-files", "-z").split("\0") if f]
    shipped, skipped = [], []
    for rel in sorted(files):
        (skipped if excluded(rel) else shipped).append(rel)

    top = f"SL_Carborundum_Planning_{version}"
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    zpath = out_dir / f"{top}_{commit[:8]}.zip"
    entries, problems = [], []
    for rel in shipped:
        data = (ROOT / rel).read_bytes()
        if rel.lower().endswith(TEXT_CRLF):
            data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        for pat in SECRET_PATTERNS:
            if pat.search(data):
                problems.append(f"possible secret in {rel}")
        entries.append((rel, data))
    if problems:
        sys.exit("REFUSING TO BUILD: " + "; ".join(problems))

    manifest = {
        "product": "SL Carborundum Planning Center", "version": version, "base_version": "V16.28",
        "commit": commit, "branch": branch, "dirty": dirty,
        "built_at_bangkok": dt.datetime.now(ZoneInfo("Asia/Bangkok")).isoformat(timespec="seconds"),
        "status": "REVIEW CANDIDATE - synthetic regression checks and supplied-workbook analysis; inherited planner acceptance checks remain unresolved; not factory-validated.",
        "python_tested": "CPython 3.12.14 (Linux). Windows install not exercised in the cloud.",
        "dependencies": "requirements-runtime.txt (exact versions)",
        "knowledge_database": "knowledge/knowledge_base.sqlite is NOT included (live data, large). Restore it from the existing installation, or rebuild; see docs/KNOWLEDGE_DATABASE.md.",
        "live_data_included": False,
        "excluded_categories": ["live/dated workbooks (Plan 2026-*, *-LATEST.*)", "databases and WAL files", "photos / uploads / QR images", "logs and caches", "virtual environments", "cloud-only scripts", "secrets and keys", "previous code ZIP"],
        "files": [{"path": rel, "sha256": sha(d), "bytes": len(d)} for rel, d in entries],
    }
    mbytes = json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel, d in entries:
            zi = zipfile.ZipInfo(f"{top}/{rel}", date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, d)
        z.writestr(f"{top}/RELEASE_MANIFEST.json", mbytes)
    print(f"built {zpath}  ({zpath.stat().st_size/1e6:.1f} MB, {len(entries)} files, {len(skipped)} excluded, commit {commit[:8]}, dirty={dirty})")
    (out_dir / (zpath.name + ".sha256")).write_text(f"{sha(zpath.read_bytes())}  {zpath.name}\n")

    if a.verify:
        verify(zpath, top)


def verify(zpath: Path, top: str):
    bad = []
    with tempfile.TemporaryDirectory() as td, zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        for n in names:
            rel = n[len(top) + 1:]
            if any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(Path(rel).name, g) for g in FORBIDDEN_IN_ZIP):
                bad.append(f"forbidden file in ZIP: {rel}")
        z.extractall(td)
        root = Path(td) / top
        m = json.loads((root / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
        for f in m["files"]:
            p = root / f["path"]
            if not p.exists() or sha(p.read_bytes()) != f["sha256"]:
                bad.append(f"hash mismatch {f['path']}")
            if p.suffix == ".py":
                try:
                    py_compile.compile(str(p), doraise=True, cfile=str(Path(td) / "x.pyc"))
                except py_compile.PyCompileError as e:
                    bad.append(f"does not compile: {f['path']}: {e}")
        for need in ("START_SL_CARBORUNDUM_PLANNING_CENTER.bat", "INSTALL_REQUIREMENTS.bat", "requirements-runtime.txt", "VERSION", "user details.txt", "docs/INSTALL_AND_UPDATE.md",
                     "docs/STORAGE_GUIDE.md", "docs/MIGRATION_BACKUP_ROLLBACK.md", "docs/KNOWLEDGE_DATABASE.md", "docs/TEST_RESULTS.md", "docs/LIMITATIONS.md",
                     "docs/ON_PHONE_CHECKLIST.md", "docs/PERMISSION_MATRIX.md", "docs/WINDOWS_INSTALL.md", "FACTORY_APPROVAL.md", "knowledge/approved_rules.json", "apps/mobile/app.py", "hub.py"):
            if not (root / need).exists():
                bad.append(f"missing {need}")
        for b in root.rglob("*.bat"):
            if b"\r\n" not in b.read_bytes():
                bad.append(f"{b.name} is not CRLF")
    if bad:
        sys.exit("VERIFY FAILED:\n  " + "\n  ".join(bad))
    print(f"verify OK: {len(names)} entries, hashes match manifest, all .py compile, no forbidden files, required files present")


if __name__ == "__main__":
    main()
