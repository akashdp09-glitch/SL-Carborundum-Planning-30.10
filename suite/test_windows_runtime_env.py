"""Decision tests for the Windows runtime helper.

These run on Linux in the cloud VM. They do NOT start Streamlit on Windows,
do NOT create a factory venv, and are not a Windows install test.
"""
from pathlib import Path
import sys

import importlib.util
from suite.common import REPO_ROOT

_W = REPO_ROOT / "scripts" / "windows" / "runtime_env.py"
_spec = importlib.util.spec_from_file_location("sl_runtime_env", _W)
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)


def _info(**kw):
    base = dict(impl="CPython", major=3, minor=12, micro=3, bits=64, machine="AMD64",
                platform="win32", version="3.12.3 (tags/v3.12.3:f6650f9)", maxsize=2**63 - 1)
    base.update(kw)
    base["tag"] = W.pep425_tag(base)
    return base


def test_pandas_pin_is_unchanged():
    text = (REPO_ROOT / "requirements-runtime.txt").read_text(encoding="utf-8")
    assert "pandas==2.2.3" in text
    assert W.PINNED_PANDAS == "2.2.3"


def test_win_amd64_312_has_the_known_wheel():
    i = _info()
    assert W.pandas_2223_wheel_for(i) == "pandas-2.2.3-cp312-cp312-win_amd64.whl"
    ok, reason = W.supported_for_app(i)
    assert ok and "cp312-cp312-win_amd64" in reason


def test_python_314_has_no_wheel_and_is_rejected_before_pip():
    i = _info(minor=14, micro=0, version="3.14.0")
    assert W.pandas_2223_wheel_for(i) is None
    ok, reason = W.supported_for_app(i)
    assert not ok
    msg = W.why_pip_would_use_sdist(i)
    assert "pandas-2.2.3.tar.gz" in msg and "vswhere.exe" in msg
    assert "cp314-cp314-win_amd64" in i["tag"]
    probe = W.format_probe(i)
    assert "NO" in probe and "sdist" in probe


def test_choose_base_auto_selects_private_312_when_pc_only_has_314(monkeypatch):
    pc314 = _info(minor=14, micro=7, version="3.14.7")
    private312 = _info(minor=12, micro=15, version="3.12.15")
    monkeypatch.setattr(W, "discover_interpreters", lambda: [pc314])
    provisioned = []

    def provision():
        provisioned.append(True)
        return private312

    monkeypatch.setattr(W, "_ensure_local_python312", provision)
    picked = W.choose_base()
    assert picked["minor"] == 12
    assert provisioned == [True]


def test_win32_and_arm64_are_rejected():
    w32 = _info(bits=32, machine="x86")
    assert W.pep425_platform(w32) == "win32"
    assert W.pandas_2223_wheel_for(w32) is None
    assert W.supported_for_app(w32)[0] is False
    arm = _info(machine="ARM64")
    assert W.pep425_platform(arm) == "win_arm64"
    assert W.supported_for_app(arm)[0] is False


def test_cpython_310_has_a_pandas_wheel_but_not_the_numpy_intersection():
    i = _info(minor=10)
    assert W.pandas_2223_wheel_for(i) == "pandas-2.2.3-cp310-cp310-win_amd64.whl"
    assert W.supported_for_app(i)[0] is False  # numpy==2.3.5 has no cp310 Windows wheel


def test_binary_only_list_includes_pandas_and_does_not_upgrade_it():
    assert "pandas" in W.BINARY_ONLY
    assert W.PINNED_PANDAS == "2.2.3"


def test_linux_cloud_interpreter_is_labelled_as_not_a_windows_install():
    i = _info(platform="linux", machine="x86_64")
    i["tag"] = W.pep425_tag(i)
    ok, reason = W.supported_for_app(i)
    assert ok and "not a Windows install" in reason


def test_inspect_this_process():
    info = W.inspect(sys.executable)
    assert info["major"] == sys.version_info[0] and info["impl"] == "CPython"
    assert "tag" in info


def test_venv_dir_honors_sl_venv(monkeypatch, tmp_path):
    target = tmp_path / "custom-venv"
    monkeypatch.setenv("SL_VENV", str(target))
    assert W.venv_dir() == target


def test_venv_dir_defaults_inside_program_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(W, "_is_windows", lambda: False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("SL_VENV", raising=False)
    monkeypatch.setattr(W, "ROOT", tmp_path / "program")
    assert W.venv_dir() == tmp_path / "program" / "RUNTIME" / "venv"


def test_venv_dir_windows_defaults_inside_program_even_if_localappdata_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(W, "_is_windows", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("SL_VENV", raising=False)
    monkeypatch.setattr(W, "ROOT", tmp_path / "program")
    assert W.venv_dir() == tmp_path / "program" / "RUNTIME" / "venv"


def test_requirements_stamp_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(W, "venv_dir", lambda: tmp_path)
    digest = W.requirements_hash()
    assert len(digest) == 64
    assert not W.stamp_is_current()
    written = W.write_install_stamp()
    assert written == tmp_path / "INSTALL_STAMP.txt"
    assert W.stamp_is_current()
    written.write_text("REQUIREMENTS_SHA256=deadbeef\n", encoding="utf-8")
    assert not W.stamp_is_current()


def test_should_skip_pip_when_stamp_matches(monkeypatch, tmp_path):
    fake = tmp_path / "python"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(W, "venv_dir", lambda: tmp_path)
    monkeypatch.setattr(W, "packages_ready", lambda py=None: True)
    W.write_install_stamp()
    assert W.should_skip_pip(fake) is True


def test_should_not_skip_pip_when_install_stamp_is_missing(monkeypatch, tmp_path):
    fake = tmp_path / "python"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(W, "venv_dir", lambda: tmp_path)
    monkeypatch.setattr(W, "packages_ready", lambda py=None: True)
    assert not (tmp_path / "INSTALL_STAMP.txt").is_file()
    assert W.should_skip_pip(fake) is False


def test_should_not_skip_pip_when_requirements_changed(monkeypatch, tmp_path):
    fake = tmp_path / "python"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(W, "venv_dir", lambda: tmp_path)
    monkeypatch.setattr(W, "packages_ready", lambda py=None: True)
    (tmp_path / "INSTALL_STAMP.txt").write_text(
        "REQUIREMENTS_SHA256=0" * 8 + "\n", encoding="utf-8"
    )
    assert W.should_skip_pip(fake) is False


def test_install_skips_pip_when_already_ready(monkeypatch, tmp_path):
    fake = tmp_path / "python"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(W, "venv_dir", lambda: tmp_path)
    monkeypatch.setattr(W, "venv_python", lambda: fake)
    monkeypatch.setattr(W, "packages_ready", lambda py=None: True)
    W.write_install_stamp()
    pip_calls = []

    def fake_run(cmd, *a, **k):
        if isinstance(cmd, (list, tuple)) and any("pip" in str(part) for part in cmd):
            pip_calls.append(list(cmd))
            raise AssertionError("pip must not run when already installed")
        raise AssertionError(f"unexpected subprocess.run {cmd!r}")

    monkeypatch.setattr(W.subprocess, "run", fake_run)
    assert W.install() == 0
    assert pip_calls == []
    assert W.stamp_is_current()
