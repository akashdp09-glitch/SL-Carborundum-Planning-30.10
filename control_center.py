from __future__ import annotations
import subprocess, sys, threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def hub_command(python: str | None = None) -> list[str]:
    """Open the Planning Center on all interfaces so a phone on the LAN can reach it.
    The local browser still opens http://127.0.0.1:8510."""
    return [
        python or sys.executable, "-m", "streamlit", "run", str(ROOT / "hub.py"),
        "--server.port", "8510",
        "--server.address", "0.0.0.0",
        "--browser.serverAddress", "127.0.0.1",
        "--server.headless", "false",
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false",
        "--browser.gatherUsageStats", "false",
    ]


def start_sidecars() -> None:
    """Daily / Firing / phone start from their hub tabs, not in front of the hub."""
    return


if __name__ == "__main__":
    print("Opening SL Carborundum Planning Center …", flush=True)
    print("A browser window should appear at http://127.0.0.1:8510", flush=True)
    print("Leave this window open while you use the software.", flush=True)
    try:
        import streamlit  # noqa: F401
    except ImportError:
        print("streamlit is not installed. The Start file will install it on first run.", flush=True)
        raise SystemExit(2)
    threading.Thread(target=start_sidecars, name="sl-sidecars", daemon=True).start()
    raise SystemExit(subprocess.call(hub_command(), cwd=ROOT))
