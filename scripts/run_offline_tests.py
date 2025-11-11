"""Quick runner to validate offline detection against provided HTML samples.

Usage:
  python3 scripts/run_offline_tests.py

It will read the three files bundled in the repo and print results and simple assertions.
"""
import sys
from pathlib import Path

from detect_offline import detect_state


def run_one(path: Path, expected: str):
    html = path.read_text(encoding="utf-8", errors="ignore")
    state, reason = detect_state(html)
    ok = state == expected
    print(f"{path.name}: expected={expected:18} detected={state:18} ok={ok} reason={reason}")
    return ok


def main():
    base = Path(__file__).resolve().parent.parent
    samples = [
        (base / "html-logged-in.html", "logged_in"),
        (base / "html-logged-out.html", "logged_out"),
        (base / "html-invalid-error.html", "invalid_credentials"),
    ]

    all_ok = True
    for p, exp in samples:
        if not p.exists():
            print(f"Missing sample file: {p}")
            all_ok = False
            continue
        ok = run_one(p, exp)
        all_ok = all_ok and ok

    if not all_ok:
        print("Some offline detection tests failed.")
        sys.exit(2)
    print("All offline detection tests passed.")


if __name__ == '__main__':
    main()
