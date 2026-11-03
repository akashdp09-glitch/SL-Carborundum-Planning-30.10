# Windows installer: interpreter, wheels, isolated environment

**Label: release candidate.** The installer and launcher were corrected on Linux and their *decision logic* is covered by `suite/test_windows_runtime_env.py`. **They have not been executed on a factory Windows PC in this environment.** A passing cloud test is not a Windows start-up test.

## What failed on the factory PC
```
Could not find C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe
error: metadata-generation-failed
→ pandas
ERROR: Installation did not complete. Internet may be required the first time.
```

That message came from the **old** launcher (`START_SL_CARBORUNDUM_PLANNING_CENTER.bat`): it used whatever `py` or `python` was first on PATH (often **64-bit CPython 3.14**), then `pip install -r requirements-runtime.txt` into that interpreter.

## Why pip chose a source distribution
Pinned line: `pandas==2.2.3` (not upgraded).

PyPI files for that exact version (checked 2026-10-04):

| Tag | Windows wheel? |
|---|---|
| cp39 / cp310 / cp311 / cp312 / cp313 + **win_amd64** | yes (`pandas-2.2.3-cp3X-cp3X-win_amd64.whl`) |
| cp314 + anything | **no** |
| win32 (32-bit) | **no** |
| win_arm64 | **no** |

If the interpreter tag is `cp314-cp314-win_amd64`, pip has no wheel, so it downloads `pandas-2.2.3.tar.gz`. That sdist is built with **Meson** and looks for Visual Studio’s `vswhere.exe`. Visual Studio is not a requirement of this software and installing it would only paper over the wrong Python.

`numpy==2.3.5` *does* have a cp314 wheel, so numpy can succeed and pandas then fails — matching the log.

Combined with `numpy==2.3.5` (Windows wheels from 3.11), the application accepts **64-bit CPython 3.11, 3.12 or 3.13**. Prefer 3.12.

## What the corrected installer does
1. `INSTALL_REQUIREMENTS.bat` starts any Python only as a **bootstrap** to run `scripts\windows\runtime_env.py`.
2. That script **inspects** each interpreter (`py -0p` and PATH): executable path, `sys.version`, implementation, 32/64-bit, machine, PEP 425 tag.
3. If only Python 3.14 is present, it downloads the official CPython 3.12.15 installer and installs a private copy under `RUNTIME\python312` (per-user, no admin rights, no PATH change). It then uses that interpreter. If download is blocked, it stops before pip with the reason and the manual fallback link. It does not invoke Meson.
4. It creates an **isolated** venv in `RUNTIME\venv` beside the program on D: (`SL_VENV` can override this). System/user site-packages are not used. App runtime, cache and install temp files stay with the program. Factory data is stored under the configured D: `CENTRAL_DATA`.
5. `pip install --only-binary=pandas,numpy,pillow,opencv-python-headless,pillow-heif,pyarrow,matplotlib,reportlab -r requirements-runtime.txt` — pandas stays **2.2.3**. If a wheel is missing, pip fails instead of compiling. If that venv already has the packages and the requirements stamp matches, **pip is skipped**.
6. `START_SL_CARBORUNDUM_PLANNING_CENTER.bat` runs **only** that venv’s `python.exe` for the hub (`hub.py` → 8510). Later clicks print **Already installed — starting**. They do not install packages and do not use the system `python`.

The venv is excluded from the ZIP. That is why an old Start file that looked only inside the unzip folder installed again every time a new ZIP was opened.

## What you do
1. Extract the ZIP to a writable folder on D:.
2. Double-click `START_SL_CARBORUNDUM_PLANNING_CENTER.bat`. On first run it installs its private Python if needed, installs the app packages into `RUNTIME\venv`, and starts the program. Allow internet access to python.org and PyPI for this one-time setup. Later launches skip installation.
3. Keep the existing `CENTRAL_DATA` at the configured D: location. Do not move or overwrite it.
4. The local app opens at http://127.0.0.1:8510. Phone access still requires the PC and phone to be on the factory Wi-Fi and the mobile service/firewall route to be available.

To see every interpreter and why each is accepted or refused:

```
py scripts\windows\runtime_env.py probe
```

## Testing status
| Check | Where | Result |
|---|---|---|
| Wheel-tag / support decisions | Linux cloud VM (`suite/test_windows_runtime_env.py`) | automated |
| Creating `.venv`, pip, Streamlit, `.bat` start | Factory Windows PC | **not done in this environment** |

A green cloud test is not proof that Streamlit starts on the factory PC.
