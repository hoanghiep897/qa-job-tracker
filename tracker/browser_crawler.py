"""Rate-limited, opt-in Playwright rendering of permitted job-listing pages.

A browser is for JavaScript-rendered pages, not for bypassing access controls.
No login, stealth settings, CAPTCHA solving, cookies or proxy rotation.
"""
from __future__ import annotations

import time
from urllib.parse import urlsplit

from tracker.licensed_html import (
    BLOCKED_MARKERS, MAX_HTML_BYTES, PLATFORMS, canonical_url,
    discover_links, parse_job, robots_allowed,
)

def _bounded_settings(board: dict) -> tuple[list[str], int, float, bool]:
    platform = board.get("provider")
    if platform not in PLATFORMS:
        raise ValueError("Unknown job platform")
    if board.get("enabled") is not True or board.get("permission_confirmed") is not True:
        raise ValueError("Confirmed permission and enabled=true are required")
    seeds = board.get("search_urls")
    if not isinstance(seeds, list) or not seeds:
        raise ValueError("Configured permitted search_urls required")
    max_pages = min(max(int(board.get("max_search_pages", 1)), 1), 3)
    max_details = min(max(int(board.get("max_job_details", 5)), 1), 30)
    delay = max(float(board.get("delay_seconds", 2)), 1.0)
    urls = [canonical_url(url, platform) for url in seeds[:max_pages]]
    return urls, max_details, delay, board.get("robots_override_authorized") is True

def _check_access(url: str, platform: str, *, override: bool, check_robots) -> None:
    canonical_url(url, platform)
    if not override and not check_robots(url, platform):
        raise RuntimeError(f"robots.txt does not allow {url}; no override configured")

def _render(page, url: str, platform: str) -> str:
    response = page.goto(url, wait_until="domcontentloaded", timeout=25000)
    # Only inspect the final URL; blocked redirects are never parsed.
    canonical_url(page.url, platform)
    if response is None:
        raise RuntimeError("No HTTP response when opening the page")
    if response.status in (401, 403, 429):
        raise RuntimeError(f"HTTP {response.status}; stop, do not bypass access control")
    if response.status != 200:
        raise RuntimeError(f"HTTP {response.status} opening source")
    # Wait briefly for ordinary JS hydration, not an anti-bot challenge.
    page.wait_for_timeout(1000)
    html = page.content()
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise RuntimeError("Rendered HTML is larger than the configured limit")
    lower = html.lower()
    if any(marker in lower for marker in BLOCKED_MARKERS):
        raise RuntimeError("Verification/CAPTCHA page detected; stop collection")
    return html

def collect_browser(board: dict, *, browser_factory=None, sleep=time.sleep,
                    check_robots=robots_allowed) -> list[dict]:
    """Collect bounded HTML using Chromium with no persistent session state.

    browser_factory, if supplied, returns a context manager with a browser-like
    object implementing new_page() and close() (used by unit tests).
    """
    platform = board["provider"]
    urls, max_details, delay, override = _bounded_settings(board)
    # Check ALL search page permissions *before* opening Chromium.
    for url in urls:
        _check_access(url, platform, override=override, check_robots=check_robots)

    if browser_factory is None:
        from playwright.sync_api import sync_playwright
        def browser_factory():
            manager = sync_playwright()
            class Managed:
                def __enter__(self):
                    self.playwright = manager.__enter__()
                    self.browser = self.playwright.chromium.launch(headless=True)
                    return self.browser
                def __exit__(self, exc_type, exc, tb):
                    self.browser.close()
                    manager.__exit__(exc_type, exc, tb)
            return Managed()

    candidate_urls, seen = [], set()
    with browser_factory() as browser:
        page = browser.new_page()
        try:
            for url in urls:
                html = _render(page, url, platform)
                for link in discover_links(html, page.url, platform):
                    if link not in seen:
                        seen.add(link)
                        candidate_urls.append(link)
                sleep(delay)
            if not candidate_urls:
                raise RuntimeError("No matching JD links on rendered search page; selectors or URLs may differ")

            jobs, attempted = [], 0
            for link in candidate_urls:
                if attempted >= max_details:
                    break
                # Skip URLs disallowed by robots, unless separately authorized.
                if not override and not check_robots(link, platform):
                    continue
                attempted += 1
                html = _render(page, link, platform)
                job = parse_job(html, link, platform)
                if job:
                    job["source"] = f"{platform}:{board.get('board', 'licensed-search')}"
                    jobs.append(job)
                sleep(delay)
            if not jobs:
                raise RuntimeError("No valid JD detail pages could be parsed")
            return jobs
        finally:
            page.close()
