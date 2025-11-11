# River-PayCheckr — Login validation helper

This repository contains a simple Selenium-based script to validate username/password pairs
against the River-Pay login page for authorized internal testing.

Files added by the automation:

- `scripts/check_logins.py` — main script that reads a `user:pass` file and writes a CSV of results.
- `requirements.txt` — Python dependencies (Selenium).

Quick notes and steps

1) Install Chrome/Chromium and matching chromedriver
	- On Ubuntu: install `chromium` and `chromium-chromedriver` from apt or install Google Chrome + chromedriver manually.
	- Make sure the `chromedriver` binary is available on PATH and matches your browser version.

2) Create python environment and install requirements

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```


3) Run the checker

Default input file is the attachment content which was saved as `river-pay(1).txt` in the repo root. Example run:

```bash
python3 scripts/check_logins.py --input /workspaces/River-PayCheckr/river-pay(1).txt --output /workspaces/River-PayCheckr/login_results.csv --headless --screenshots --auto-driver
```

Selectors and detection
- The script now accepts CSS selectors for the username and password fields (defaults: `#LoginForm_login` and `#LoginForm_password`).
- It will also check for one or more "logout/dashboard" CSS selectors to confirm a successful login. Two defaults are included:
	- `.nav-list > li:nth-child(14) > a:nth-child(1)`
	- `.dropdown-menu > li:nth-child(2) > a:nth-child(1)`

You can pass additional logout selectors with `--logout-selector` repeatedly. For example:

```bash
python3 scripts/check_logins.py --logout-selector '.nav-list > li:nth-child(14) > a' --logout-selector '.dropdown-menu > li:nth-child(2) > a' ...
```

Auto-installing chromedriver
- If you don't have chromedriver installed, use `--auto-driver` to have the script install a matching chromedriver automatically using `webdriver-manager` (network access required).


Options
 - `--url` to override the login URL
 - `--user-xpath` and `--pass-xpath` to override the input XPaths
 - `--wait` seconds to wait after submitting before checking for success (default 3s)
 - `--screenshots` will save failure screenshots to `./screenshots/`

Detection heuristic
 - If the page URL changes after submit the script treats it as a success.
 - If the login form XPath is still present after submit the script treats it as a failure.
 - These heuristics are intentionally simple; you can extend detection to look for specific dashboard elements or success messages.

Security & ethics
 - Keep the credential file and result CSV secure. This tool is intended for authorized internal testing by the company only.

Next steps (optional enhancements):
 - Add retries and parallelization for speed.
 - Add more robust success detection (e.g., CSS selector for a logout button).
 - Integrate with an internal test harness or CI job (careful with secret handling).

If you want, I can implement any of the enhancements or run a small sample here (note: Chrome and chromedriver must be available in this environment).
# River-PayCheckr