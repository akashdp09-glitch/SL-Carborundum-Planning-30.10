"""Start Daily (8511), Firing (8512) and the phone app (8000/8443) on this PC.

The hub on port 8510 is a separate process. Opening a Daily / Firing tab used to
iframe http://127.0.0.1:8511 or :8512 even when nothing was listening, which
Chrome reports as “127.0.0.1 refused to connect.” A phone that opens the hub
also treats 127.0.0.1 as the *phone*, not the factory PC.

This module only starts the existing programs with the same flags as
START_SL_CARBORUNDUM_PLANNING_CENTER.bat. It does not invent planner behaviour.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import ssl
import urllib.request
from pathlib import Path

from .common import REPO_ROOT
from .central_paths import child_environ, write_pointer

ROOT = REPO_ROOT
LOG_DIR = ROOT / "logs"

STREAMLIT_FLAGS = (
    "--server.headless", "true",
    "--server.address", "0.0.0.0",
    "--server.enableCORS", "false",
    "--server.enableXsrfProtection", "false",
    "--browser.gatherUsageStats", "false",
)

SERVICES = {
    "daily": {
        "id": "daily",
        "name": "Daily Planner",
        "name_th": "แผนรายวัน",
        "port": 8511,
        "url": "http://127.0.0.1:8511",
        "health": "http://127.0.0.1:8511/_stcore/health",
        "cwd": ROOT / "apps" / "daily",
        "kind": "streamlit",
        "script": "daily_planner_app.py",
        "log": LOG_DIR / "daily.log",
        "pid": LOG_DIR / "daily.pid",
    },
    "firing": {
        "id": "firing",
        "name": "Firing Planner",
        "name_th": "แผนเตา",
        "port": 8512,
        "url": "http://127.0.0.1:8512",
        "health": "http://127.0.0.1:8512/_stcore/health",
        "cwd": ROOT / "apps" / "firing",
        "kind": "streamlit",
        "script": "firing_tomorrow_fast.py",
        "log": LOG_DIR / "firing.log",
        "pid": LOG_DIR / "firing.pid",
    },
    "mobile": {
        "id": "mobile",
        "name": "Phone shop-floor app",
        "name_th": "แอปมือถือหน้างาน",
        "port": 8000,
        "url": "http://127.0.0.1:8000/health",
        "health": "http://127.0.0.1:8000/health",
        "https_health": "https://127.0.0.1:8443/health",
        "cwd": ROOT,
        "kind": "mobile",
        "script": str(ROOT / "scripts" / "windows" / "start_mobile.py"),
        "log": LOG_DIR / "mobile.log",
        "pid": LOG_DIR / "mobile.pid",
    },
}


def child_env(root: Path | None = None) -> dict:
    """Pass the hub's central folders to child processes (same as SERVER_STORAGE_CONFIG.bat)."""
    root = Path(root or ROOT)
    env = child_environ(root)
    try:
        write_pointer(root, env)
    except Exception:
        pass
    return env


def origin_file(service_id: str) -> Path:
    return LOG_DIR / f"{service_id}.origin"


def write_origin(service_id: str, root: Path | None = None) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    origin_file(service_id).write_text(str(Path(root or ROOT).resolve()), encoding="utf-8")


def recorded_origin(service_id: str) -> Path | None:
    try:
        text = origin_file(service_id).read_text(encoding="utf-8").strip()
    except Exception:
        return None
    return Path(text) if text else None


def pid_on_port(port: int) -> int | None:
    """Process listening on this port, if the OS will tell us."""
    try:
        if os.name == "nt":
            out = subprocess.check_output(["netstat", "-ano", "-p", "TCP"], text=True, timeout=8, errors="replace")
            needle = f":{int(port)}"
            for line in out.splitlines():
                if needle not in line or "LISTENING" not in line.upper():
                    continue
                parts = line.split()
                if parts and parts[-1].isdigit():
                    return int(parts[-1])
            return None
        out = subprocess.check_output(["ss", "-lptn", f"sport = :{int(port)}"], text=True, timeout=5, errors="replace")
        import re
        m = re.search(r"pid=(\d+)", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def is_foreign(service_id: str) -> bool:
    """True when something answers on the port but it is not this program folder."""
    if not probe(service_id):
        return False
    origin = recorded_origin(service_id)
    if origin is not None and origin.resolve() != ROOT.resolve():
        return True
    # Phone app: HTTP helper / uvicorn worker PIDs often differ from the pid we
    # recorded. Killing on that mismatch took down a working /mobile. Only
    # replace mobile when the origin file names another ZIP folder.
    if service_id == "mobile":
        return False
    ours = recorded_pid(service_id)
    listening = pid_on_port(SERVICES[service_id]["port"])
    if ours and listening and int(ours) == int(listening):
        return False
    if origin is not None and origin.resolve() == ROOT.resolve() and ours:
        return False
    # Port is open but this unzip did not start it (leftover Daily from another ZIP).
    return True


def _kill_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15)
        else:
            os.kill(pid, 15)
            time.sleep(0.3)
            try:
                os.kill(pid, 9)
            except OSError:
                pass
    except Exception:
        pass


def stop(service_id: str) -> dict:
    """Stop the leftover process on this service port so this install can start its own."""
    svc = SERVICES[service_id]
    pids = set()
    ours = recorded_pid(service_id)
    if ours:
        pids.add(int(ours))
    listening = pid_on_port(svc["port"])
    if listening:
        pids.add(int(listening))
    for pid in pids:
        _kill_pid(pid)
    deadline = time.time() + 6
    while time.time() < deadline and probe(service_id):
        time.sleep(0.25)
    try:
        svc["pid"].unlink()
    except OSError:
        pass
    try:
        origin_file(service_id).unlink()
    except OSError:
        pass
    return {"ok": not probe(service_id), "killed": sorted(pids)}


def host_from_headers(headers) -> str:
    """Host the *browser* used to open the hub. Phones must not iframe 127.0.0.1."""
    if headers is None:
        return "127.0.0.1"
    if hasattr(headers, "get"):
        raw = headers.get("Host") or headers.get("host") or ""
    else:
        raw = ""
    host = str(raw).split("/")[0].split(":")[0].strip()
    return host or "127.0.0.1"


def is_phone_ua(ua: str) -> bool:
    u = (ua or "").lower()
    if "ipad" in u or "tablet" in u:
        return False
    return any(tok in u for tok in ("iphone", "android", "mobile", "ipod"))


def iframe_url(service_id: str, host: str, extra_query: str = "") -> str:
    svc = SERVICES[service_id]
    h = (host or "127.0.0.1").strip() or "127.0.0.1"
    url = f"http://{h}:{svc['port']}"
    extra = (extra_query or "").strip()
    if extra and not extra.startswith("?"):
        extra = "?" + extra
    return url + extra


def command(service_id: str, python: str | None = None) -> list[str]:
    svc = SERVICES[service_id]
    py = python or sys.executable
    if svc["kind"] == "mobile":
        return [py, str(ROOT / "scripts" / "windows" / "start_mobile.py")]
    return [py, "-m", "streamlit", "run", svc["script"], "--server.port", str(svc["port"]), *STREAMLIT_FLAGS]


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.35) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        s.close()


def http_ok(url: str, timeout: float = 0.8) -> bool:
    try:
        ctx = ssl._create_unverified_context() if str(url).startswith("https") else None
        with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
            return 200 <= int(r.status) < 500
    except Exception:
        return False


def probe(service_id: str) -> bool:
    svc = SERVICES[service_id]
    if http_ok(svc["health"]) or port_open(svc["port"]):
        return True
    if service_id == "mobile" and http_ok(svc.get("https_health") or ""):
        return True
    return False


def mobile_https_up() -> bool:
    return http_ok(SERVICES["mobile"]["https_health"])


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def recorded_pid(service_id: str) -> int | None:
    path = SERVICES[service_id]["pid"]
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return None
    return pid if _pid_alive(pid) else None


def tail_log(service_id: str, n: int = 40) -> str:
    path = SERVICES[service_id]["log"]
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    return "\n".join(lines[-n:])


def _lock_path(service_id: str) -> Path:
    return LOG_DIR / f"{service_id}.start.lock"


def _acquire_lock(service_id: str, stale_s: float = 90) -> bool:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = _lock_path(service_id)
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            age = stale_s + 1
        if age > stale_s:
            try:
                path.unlink()
            except OSError:
                return False
            return _acquire_lock(service_id, stale_s)
        return False


def _release_lock(service_id: str) -> None:
    try:
        _lock_path(service_id).unlink()
    except OSError:
        pass


def start(service_id: str, python: str | None = None) -> dict:
    """Start the named program. Replace a leftover process from another ZIP folder."""
    svc = SERVICES[service_id]
    replaced = False
    if probe(service_id):
        if is_foreign(service_id):
            stop(service_id)
            replaced = True
            if probe(service_id):
                return {"ok": False, "already": False, "started": False, "replaced": True,
                        "pid": recorded_pid(service_id),
                        "error": f"an older {svc['name']} is still using port {svc['port']}; close that window from the other ZIP folder"}
        else:
            return {"ok": True, "already": True, "started": False, "replaced": False,
                    "pid": recorded_pid(service_id), "error": ""}
    if not _acquire_lock(service_id):
        return {"ok": probe(service_id), "already": False, "started": False, "replaced": replaced,
                "pid": recorded_pid(service_id), "error": "another start is in progress"}
    try:
        if probe(service_id):
            return {"ok": True, "already": True, "started": False, "replaced": replaced,
                    "pid": recorded_pid(service_id), "error": ""}
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = svc["log"]
        cmd = command(service_id, python)
        kwargs = {
            "cwd": str(svc["cwd"]),
            "env": child_env(),
            "stdout": open(log, "a", encoding="utf-8", errors="replace"),
            "stderr": subprocess.STDOUT,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)
        try:
            kwargs["stdout"].close()
        except Exception:
            pass
        svc["pid"].write_text(str(proc.pid), encoding="utf-8")
        write_origin(service_id)
        time.sleep(0.4)
        if proc.poll() is not None:
            return {"ok": False, "already": False, "started": False, "replaced": replaced, "pid": proc.pid,
                    "error": f"process exited immediately (code {proc.returncode}). See {log.name}"}
        return {"ok": True, "already": False, "started": True, "replaced": replaced, "pid": proc.pid, "error": ""}
    except Exception as e:
        return {"ok": False, "already": False, "started": False, "replaced": replaced, "pid": None, "error": str(e)}
    finally:
        _release_lock(service_id)


def wait_until_up(service_id: str, seconds: float = 12) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if probe(service_id):
            return True
        time.sleep(0.5)
    return probe(service_id)


def ensure(service_id: str, wait_seconds: float = 0) -> dict:
    info = start(service_id)
    if wait_seconds and not probe(service_id):
        info["ready"] = wait_until_up(service_id, wait_seconds)
    else:
        info["ready"] = probe(service_id)
    return info


def ensure_all(names=("daily", "firing", "mobile"), wait_seconds: float = 0) -> dict:
    return {n: ensure(n, wait_seconds=wait_seconds) for n in names}
