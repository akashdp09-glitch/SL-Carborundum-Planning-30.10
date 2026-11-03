"""Open the Planning Center in the browser only after the hub answers.

START_SL_CARBORUNDUM_PLANNING_CENTER.bat used to launch http://127.0.0.1:8510
after five seconds while the hub was still waiting. Chrome then showed
“refused to connect” and it looked as if Streamlit never opened.
"""
from __future__ import annotations

import sys
import time
import urllib.request
import webbrowser

HUB = "http://127.0.0.1:8510"


def hub_up(url: str = HUB, timeout: float = 0.8) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= int(r.status) < 500
    except Exception:
        return False


def wait_for_hub(seconds: float = 60, url: str = HUB) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if hub_up(url):
            return True
        time.sleep(0.5)
    return hub_up(url)


def open_hub(url: str = HUB) -> bool:
    if not hub_up(url):
        return False
    webbrowser.open(url, new=2)
    return True


def main(argv=None) -> int:
    seconds = 60
    args = list(argv if argv is not None else sys.argv[1:])
    if args:
        try:
            seconds = float(args[0])
        except ValueError:
            pass
    print(f"Waiting up to {int(seconds)}s for Planning Center at {HUB} ...", flush=True)
    if not wait_for_hub(seconds):
        print("Planning Center did not answer. Leave the START window open and read the text there.", flush=True)
        return 1
    open_hub()
    print(f"Opened {HUB} in the default browser.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
