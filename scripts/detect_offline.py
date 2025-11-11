"""Offline detection helpers using HTML parsing (BeautifulSoup).

These helpers let us validate the same cues the Selenium checker uses but without a browser:
- presence of /office/logout anchor
- text cue 'You logged in as'
- explicit invalid-login messages (e.g. 'Incorrect login or password' inside alert blocks)
"""
from typing import Tuple
from bs4 import BeautifulSoup


def detect_logged_in(html: str) -> Tuple[bool, str]:
    """Return (is_logged_in, reason).

    Scans HTML for reliable logged-in cues.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1) explicit logout anchor href
    logout_link = soup.find("a", href=lambda v: v and "/office/logout" in v)
    if logout_link:
        return True, "logout link (/office/logout) present"

    # 2) header textual cue
    text_nodes = soup.find_all(string=True)
    for t in text_nodes:
        if isinstance(t, str) and "You logged in as" in t:
            return True, "header 'You logged in as' present"

    # 3) presence of known dashboard nav items (nav-list) - heuristic
    if soup.select_one(".nav .nav-list, .nav-list, .nav.pull-right, .navbar-inner"):
        # presence of dashboard nav likely means logged-in (but could be present also on public pages)
        # Only use this as a weak hint
        return True, "dashboard nav present (heuristic)"

    return False, "no logged-in cues found"


def detect_invalid_login(html: str) -> Tuple[bool, str]:
    """Return (is_invalid_login, reason).

    Look for common server-side error messages shown after a failed login.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Common pattern: <div class="alert alert-error"><ul><li>Incorrect login or password</li></ul></div>
    alert = soup.select_one(".alert-error, .alert-danger, .alert")
    if alert:
        text = alert.get_text(separator=" ", strip=True)
        if "incorrect" in text.lower() and ("login" in text.lower() or "password" in text.lower()):
            return True, f"invalid-login message: {text}"

    # Also search for list items with contain 'Incorrect login' etc.
    for li in soup.find_all("li"):
        txt = li.get_text(strip=True).lower()
        if "incorrect login" in txt or "incorrect login or password" in txt or "invalid login" in txt:
            return True, f"invalid-login li: {li.get_text(strip=True)}"

    return False, "no explicit invalid-login message found"


def detect_state(html: str) -> Tuple[str, str]:
    """Return state (one of: 'logged_in','invalid_credentials','logged_out') and reason."""
    logged_in, r1 = detect_logged_in(html)
    if logged_in:
        return "logged_in", r1

    invalid, r2 = detect_invalid_login(html)
    if invalid:
        return "invalid_credentials", r2

    return "logged_out", "no logged-in or invalid-login cues"
