"""Windows runtime environment: pick a supported interpreter, isolate it in a venv, never compile pandas.

pandas==2.2.3 (pinned, not upgraded) publishes win_amd64 wheels for CPython 3.9-3.13 only.
There is no cp314 wheel and no win32 / win_arm64 wheel. For those tags pip downloads
pandas-2.2.3.tar.gz (sdist). The sdist is built with Meson and looks for
Microsoft Visual Studio\\Installer\\vswhere.exe — that is a Python/package mismatch,
not a missing compiler. This module refuses that path before pip runs.

On Windows this release keeps the venv and private Python under the stable D: install root\\RUNTIME, shared across version folders when SERVER_STORAGE_CONFIG.bat points to the existing CENTRAL_DATA root.
pip runs only when that environment is missing or requirements changed.

This file is safe to import on Linux (decision tests). Creating the venv and installing
packages is a Windows operator action; it has not been executed on a factory PC here.
"""
from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGACY_VENV = ROOT / ".venv"
REQ = ROOT / "requirements-runtime.txt"
STAMP_NAME = "INSTALL_STAMP.txt"
PINNED_PANDAS = "2.2.3"
# Packages that ship compiled extensions. pip must take a wheel; an sdist means Meson/VS.
BINARY_ONLY = (
    "pandas",
    "numpy",
    "pillow",
    "opencv-python-headless",
    "pillow-heif",
    "pyarrow",
    "matplotlib",
    "reportlab",
)
# Intersection of Windows wheels for the pinned set (pandas 2.2.3 + numpy 2.3.5).
# pandas 2.2.3: cp39-cp313 win_amd64. numpy 2.3.5: cp311+ (no cp310).
SUPPORTED_MINOR = (11, 12, 13)
PREFERRED_MINOR = 12
PYTHON_ORG_312 = "https://www.python.org/ftp/python/3.12.15/python-3.12.15-amd64.exe"
RUNTIME_ROOT = Path(os.environ.get("SL_RUNTIME_ROOT") or (ROOT / "RUNTIME"))
LOCAL_PYTHON_312 = RUNTIME_ROOT / "python312"


def _ensure_local_python312() -> dict | None:
    """Install a private CPython 3.12 beside the app when no compatible runtime exists.

    This makes the one-click Windows setup work for PCs that only have Python 3.14.
    It does not need administrator rights or modify PATH, and all files stay under
    this program's RUNTIME directory. Download/install only happens on first setup.
    """
    exe = LOCAL_PYTHON_312 / "python.exe"
    if exe.is_file():
        try:
            info = inspect(str(exe))
            return info if supported_for_app(info)[0] else None
        except Exception:
            pass
    installer = RUNTIME_ROOT / "python-3.12.15-amd64.exe"
    installer.parent.mkdir(parents=True, exist_ok=True)
    if not installer.is_file():
        print("No compatible Python is installed. Downloading private Python 3.12.15 for this app...")
        try:
            request = urllib.request.Request(
                PYTHON_ORG_312,
                headers={"User-Agent": "SL-Carborundum-Planning-Center/1.0"},
            )
            with urllib.request.urlopen(request, timeout=60) as response, installer.open("wb") as out:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    out.write(block)
        except Exception as exc:
            try:
                installer.unlink(missing_ok=True)
            except OSError:
                pass
            print(f"Automatic Python download failed: {exc}")
            print("Connect this PC to the internet and allow python.org, then run START again.")
            return None
    args = [
        str(installer), "/quiet", "InstallAllUsers=0", "Include_launcher=0",
        "Include_test=0", "Include_doc=0", "Include_tcltk=0", "Include_pip=1",
        "PrependPath=0", f"TargetDir={LOCAL_PYTHON_312}",
    ]
    print("Installing private Python 3.12.15 under RUNTIME (no admin rights; PATH unchanged)...")
    try:
        result = subprocess.run(args, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Private Python setup failed: {exc}")
        return None
    if result.returncode not in (0, 3010) or not exe.is_file():
        print(f"Python installer returned {result.returncode}; expected runtime: {exe}")
        return None
    try:
        info = inspect(str(exe))
    except Exception as exc:
        print(f"Could not start the installed private Python: {exc}")
        return None
    if not supported_for_app(info)[0]:
        print("Private Python install completed, but its architecture/version is unsupported.")
        return None
    return info


def inspect(exe: str) -> dict:
    """Ask one interpreter who it is. Works for any CPython 3.8+."""
    code = r"""
import platform, struct, sys
print("exe", sys.executable)
print("version", sys.version.splitlines()[0])
print("hexversion", hex(sys.hexversion))
print("major", sys.version_info[0])
print("minor", sys.version_info[1])
print("micro", sys.version_info[2])
print("impl", platform.python_implementation())
print("bits", struct.calcsize("P") * 8)
print("machine", platform.machine())
print("platform", sys.platform)
print("maxsize", sys.maxsize)
"""
    r = subprocess.run([exe, "-c", code], capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise RuntimeError(f"cannot inspect {exe}: {r.stderr.strip() or r.stdout.strip()}")
    info = {"argv_exe": exe}
    for line in r.stdout.splitlines():
        if " " in line:
            k, v = line.split(" ", 1)
            info[k] = v
    info["major"] = int(info["major"])
    info["minor"] = int(info["minor"])
    info["micro"] = int(info["micro"])
    info["bits"] = int(info["bits"])
    info["maxsize"] = int(info["maxsize"])
    info["tag"] = pep425_tag(info)
    return info


def pep425_platform(info: dict) -> str:
    if info.get("platform") != "win32":
        return info.get("platform") or "unknown"
    if info["bits"] != 64:
        return "win32"
    mach = (info.get("machine") or "").lower()
    if mach in {"arm64", "aarch64"}:
        return "win_arm64"
    return "win_amd64"


def pep425_tag(info: dict) -> str:
    impl = "cp" if info.get("impl") == "CPython" else info.get("impl", "??").lower()[:2]
    abi = f"{impl}{info['major']}{info['minor']}"
    return f"{abi}-{abi}-{pep425_platform(info)}"


def pandas_2223_wheel_for(info: dict) -> str | None:
    """Exact PyPI filename if one exists for this interpreter; None means pip will take the sdist."""
    if info.get("impl") != "CPython":
        return None
    plat = pep425_platform(info)
    if plat != "win_amd64":
        return None
    if info["major"] != 3 or info["minor"] not in (9, 10, 11, 12, 13):
        return None
    abi = f"cp{info['major']}{info['minor']}"
    return f"pandas-{PINNED_PANDAS}-{abi}-{abi}-win_amd64.whl"


def why_pip_would_use_sdist(info: dict) -> str:
    tag = info["tag"]
    wheel = pandas_2223_wheel_for(info)
    if wheel:
        return (
            f"A compatible wheel exists ({wheel}). pip should install that file and must not compile."
        )
    if info.get("platform") != "win32":
        return (
            f"Tag {tag} is not a Windows install target. "
            f"Windows wheels for pandas {PINNED_PANDAS} are win_amd64 / CPython 3.9-3.13 only."
        )
    return (
        f"PyPI has no pandas-{PINNED_PANDAS} wheel for tag {tag}. "
        f"pip therefore selects pandas-{PINNED_PANDAS}.tar.gz (sdist). "
        f"The sdist is built with Meson and looks for "
        f"Microsoft Visual Studio\\Installer\\vswhere.exe. "
        f"That is a Python / package mismatch. Visual Studio is not the fix. "
        f"pandas {PINNED_PANDAS} Windows wheels exist only for 64-bit CPython 3.9-3.13 (win_amd64)."
    )


def supported_for_app(info: dict) -> tuple[bool, str]:
    """True only when every BINARY_ONLY pin has a known Windows wheel (pandas + numpy intersection)."""
    if info.get("impl") != "CPython":
        return False, f"Need CPython, not {info.get('impl')}."
    if info.get("platform") == "win32":
        if pep425_platform(info) != "win_amd64":
            return False, f"Need 64-bit Intel/AMD Windows (win_amd64), not {pep425_platform(info)}."
        if info["major"] != 3 or info["minor"] not in SUPPORTED_MINOR:
            return False, (
                f"Need 64-bit CPython 3.11, 3.12 or 3.13 (prefer 3.12). "
                f"This interpreter is {info['major']}.{info['minor']}.{info['micro']} ({info['tag']})."
            )
        if pandas_2223_wheel_for(info) is None:
            return False, why_pip_would_use_sdist(info)
        return True, f"OK: {info['tag']} has pandas-{PINNED_PANDAS} and the other pinned Windows wheels."
    # Non-Windows: used only by cloud tests of this helper, not as a factory install path.
    if info["major"] == 3 and info["minor"] in SUPPORTED_MINOR:
        return True, f"Cloud/Linux helper path ({info['tag']}); not a Windows install."
    return False, f"Unsupported on this helper path: {info['tag']}"


def format_probe(info: dict) -> str:
    ok, reason = supported_for_app(info)
    wheel = pandas_2223_wheel_for(info) or "(none — pip would download the sdist)"
    lines = [
        f"Interpreter : {info.get('exe') or info.get('argv_exe')}",
        f"Version     : {info.get('version')}",
        f"Implementation: {info.get('impl')} {info['major']}.{info['minor']}.{info['micro']}",
        f"Architecture: {info['bits']}-bit  machine={info.get('machine')}  platform={info.get('platform')}",
        f"PEP 425 tag : {info['tag']}",
        f"pandas {PINNED_PANDAS} wheel for this tag: {wheel}",
        f"Why pip chooses wheel or sdist: {why_pip_would_use_sdist(info)}",
        f"Supported for this app: {'YES' if ok else 'NO'} — {reason}",
    ]
    return "\n".join(lines)


def _py_launcher_paths() -> list[str]:
    try:
        r = subprocess.run(["py", "-0p"], capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    out = []
    for line in (r.stdout or "").splitlines():
        m = re.search(r"([A-Za-z]:\\.+python(?:w)?\.exe)\s*$", line.strip(), re.I)
        if m:
            out.append(m.group(1))
    return out


def _path_python() -> list[str]:
    found = []
    for name in ("python", "python3"):
        try:
            r = subprocess.run(["where" if os.name == "nt" else "which", name], capture_output=True, text=True, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        for line in (r.stdout or "").splitlines():
            p = line.strip()
            if p and Path(p).is_file():
                found.append(p)
    return found


def discover_interpreters() -> list[dict]:
    seen = set()
    infos = []
    for exe in _py_launcher_paths() + _path_python() + [sys.executable]:
        key = os.path.normcase(os.path.abspath(exe))
        if key in seen:
            continue
        seen.add(key)
        try:
            infos.append(inspect(exe))
        except Exception:
            continue
    return infos


def choose_base() -> dict:
    cands = []
    for info in discover_interpreters():
        ok, _ = supported_for_app(info)
        if ok and info.get("platform") == "win32":
            cands.append(info)
        elif ok and info.get("platform") != "win32" and os.environ.get("SL_ALLOW_NONWINDOWS_VENV") == "1":
            cands.append(info)
    if not cands:
        # Python 3.14 is common on newer PCs, while this release's tested pandas
        # pin requires a 3.11–3.13 wheel. Provision a private 3.12 automatically.
        info = _ensure_local_python312()
        if info is not None:
            cands.append(info)
        else:
            raise SystemExit(_no_supported_message())
    cands.sort(key=lambda i: (0 if i["minor"] == PREFERRED_MINOR else 1, -i["minor"]))
    return cands[0]


def _no_supported_message() -> str:
    probes = []
    for info in discover_interpreters():
        probes.append(format_probe(info))
        probes.append("")
    body = "\n".join(probes) if probes else "(no Python interpreter could be inspected)\n"
    return (
        "=====================================================================\n"
        "UNSUPPORTED PYTHON — install stopped BEFORE pip, so pandas was not compiled.\n"
        "Visual Studio is NOT required and will not fix this.\n"
        "=====================================================================\n"
        f"This package pins pandas=={PINNED_PANDAS}. Windows wheels exist only for\n"
        "64-bit CPython 3.9-3.13 (filename tag win_amd64). Combined with numpy==2.3.5\n"
        "(wheels from 3.11), the application accepts 64-bit CPython 3.11, 3.12 or 3.13.\n"
        "Python 3.14, 32-bit Python, and ARM64 Windows have no pandas 2.2.3 wheel;\n"
        "pip would take the source distribution and Meson would look for vswhere.exe.\n"
        "\n"
        "The installer tried to provision a private 64-bit Python 3.12 beside this app.\n"
        "If it could not download Python, allow access to python.org and run START again.\n"
        "As a manual fallback, install 64-bit Python 3.12 (Add to PATH is not needed):\n"
        f"  {PYTHON_ORG_312}\n"
        "Show every interpreter:  py -0p\n"
        "\n"
        "Interpreters found on this PC:\n"
        f"{body}"
    )


def _is_windows() -> bool:
    return os.name == "nt"


def venv_dir() -> Path:
    """Where application packages live; this release keeps them on D:."""
    override = (os.environ.get("SL_VENV") or "").strip()
    if override:
        return Path(override)
    return RUNTIME_ROOT / "venv"

def venv_python() -> Path:
    if _is_windows():
        return venv_dir() / "Scripts" / "python.exe"
    return venv_dir() / "bin" / "python"


def requirements_hash() -> str:
    return hashlib.sha256(REQ.read_bytes()).hexdigest()


def stamp_path() -> Path:
    return venv_dir() / STAMP_NAME


def stamp_is_current() -> bool:
    p = stamp_path()
    if not p.is_file():
        return False
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return False
    return f"REQUIREMENTS_SHA256={requirements_hash()}" in text


def write_install_stamp() -> Path:
    venv_dir().mkdir(parents=True, exist_ok=True)
    p = stamp_path()
    p.write_text(
        f"REQUIREMENTS_SHA256={requirements_hash()}\n"
        f"REQUIREMENTS_FILE={REQ.name}\n",
        encoding="utf-8",
    )
    return p


def packages_ready(py: Path | None = None) -> bool:
    exe = py or venv_python()
    if not exe.is_file():
        return False
    try:
        r = subprocess.run(
            [
                str(exe),
                "-c",
                "import streamlit,pandas,fastapi,uvicorn,cv2,pillow_heif,openpyxl,qrcode,plotly,xlsxwriter,matplotlib,PIL; "
                "from pptx import Presentation; import pandas as p; "
                f"assert p.__version__=='{PINNED_PANDAS}', p.__version__",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def should_skip_pip(py: Path | None = None) -> bool:
    """True when packages are already present and requirements have not changed."""
    exe = py or venv_python()
    if not exe.is_file() or not packages_ready(exe):
        return False
    return stamp_is_current()


def ensure_venv(base: dict) -> Path:
    py = venv_python()
    if py.is_file():
        try:
            cur = inspect(str(py))
            ok, _ = supported_for_app(cur)
            if ok and (cur["major"], cur["minor"]) == (base["major"], base["minor"]):
                return py
        except Exception:
            pass
    target = venv_dir()
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run([base["exe"], "-m", "venv", str(target)], check=True)
    if not py.is_file():
        raise SystemExit(f"venv created but {py} is missing")
    return py


def install() -> int:
    print("SL Carborundum — isolated runtime (does not touch factory data folders)")
    print(f"Program folder: {ROOT}")
    print(f"Persistent runtime: {RUNTIME_ROOT}")
    print(f"Virtual env   : {venv_dir()}  (not shipped in the ZIP; reused on later starts)")
    print()
    py = venv_python()
    if should_skip_pip(py):
        if not stamp_is_current():
            write_install_stamp()
        print("Already installed — starting")
        print(f"Using {py}")
        return 0
    print("Bootstrap interpreter (this process):")
    print(format_probe(inspect(sys.executable)))
    print()
    base = choose_base()
    print("Selected BASE interpreter for the application venv:")
    print(format_probe(base))
    print()
    ok, reason = supported_for_app(base)
    if not ok:
        print(reason)
        return 1
    py = ensure_venv(base)
    vinfo = inspect(str(py))
    print("Application venv interpreter:")
    print(format_probe(vinfo))
    print()
    only = ",".join(BINARY_ONLY)
    cmd_pip = [str(py), "-m", "pip", "install", "--upgrade", "pip"]
    print("+", " ".join(cmd_pip))
    subprocess.run(cmd_pip, check=True)
    cmd = [
        str(py), "-m", "pip", "install",
        f"--only-binary={only}",
        "-r", str(REQ),
    ]
    print("+", " ".join(cmd))
    print(f"(pandas stays {PINNED_PANDAS}; if no wheel matches, pip fails instead of compiling)")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print()
        print("pip refused the install (no compile was attempted for pandas/numpy/…).")
        print("Nothing in SL_SHARED_ROOT / CENTRAL_DATA was changed.")
        return r.returncode
    check = subprocess.run(
        [str(py), "-c", "import streamlit,pandas,fastapi,uvicorn,cv2,pillow_heif,openpyxl; import pandas as p; "
         f"assert p.__version__=='{PINNED_PANDAS}', p.__version__; print('Dependencies OK', 'pandas', p.__version__)"]
    )
    if check.returncode != 0:
        return check.returncode
    record = venv_dir() / "INSTALL_RECORD.txt"
    record.write_text(
        "isolated application venv\n"
        + format_probe(vinfo)
        + f"\npandas pin: {PINNED_PANDAS}\nrequirements: {REQ.name}\n",
        encoding="utf-8",
    )
    write_install_stamp()
    print()
    print(f"Wrote {record}")
    print("Already installed. Later Start clicks skip this step.")
    print("Next: edit SERVER_STORAGE_CONFIG.bat, then run START_SL_CARBORUNDUM_PLANNING_CENTER.bat")
    return 0


def check() -> int:
    py = venv_python()
    if not py.is_file():
        print(f"Isolated environment not found ({py}).")
        print("Run START_SL_CARBORUNDUM_PLANNING_CENTER.bat once (first start installs). Factory data folders are not created by that step.")
        return 1
    info = inspect(str(py))
    print(format_probe(info))
    ok, reason = supported_for_app(info)
    if not ok:
        print(reason)
        print("The existing venv was built with an unsupported Python. Delete that venv folder")
        print("(only that folder) and run START once more. Do not delete CENTRAL_DATA.")
        return 1
    r = subprocess.run(
        [str(py), "-c", "import streamlit,pandas; import pandas as p; "
         f"assert p.__version__=='{PINNED_PANDAS}', ('pandas was changed to', p.__version__); print('venv OK')"]
    )
    return r.returncode


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "probe"
    if cmd == "probe":
        print(format_probe(inspect(sys.executable)))
        print()
        print("Other interpreters:")
        for info in discover_interpreters():
            print("-" * 60)
            print(format_probe(info))
        return 0
    if cmd == "install":
        return install()
    if cmd == "check":
        return check()
    if cmd in {"ready", "python-path"}:
        py = venv_python()
        if should_skip_pip(py):
            print(py)
            return 0
        print(f"not-ready: {py}", file=sys.stderr)
        return 1
    print("usage: runtime_env.py [probe|install|check|ready]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
