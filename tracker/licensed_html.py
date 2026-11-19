"""Bounded HTML crawler for job boards with operator-supplied permission.

No authentication, captcha solving, proxy rotation, or browser fingerprinting.
Extract structured JobPosting data where possible. Restrict every request to
the configured host and collect only links matching explicit job URL paths.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

PLATFORMS = {
    "itviec": {
        "hosts": ("itviec.com", "www.itviec.com"),
        "path": re.compile(r"^/it-jobs/[^/?#]+-\d+(?:/)?$"),
    },
    "topcv": {
        "hosts": ("topcv.vn", "www.topcv.vn"),
        "path": re.compile(r"^/viec-lam/[^/?#]+/\d+\.html$"),
    },
    "vietnamworks": {
        "hosts": ("vietnamworks.com", "www.vietnamworks.com"),
        "path": re.compile(r"^/.+(?:-jv|-\d+)(?:/)?$"),
    },
}
USER_AGENT = "QAJobTracker/0.6 (+authorized research; contact: repository maintainer)"
MAX_HTML_BYTES = 2_000_000
TRACKING = ("utm_", "fbclid", "gclid", "ta_source", "u_sr_id")
BLOCKED_MARKERS = (
    "verify you are human", "attention required", "captcha", "cf-turnstile",
    "xác nhận bạn không phải robot", "access denied", "just a moment...",
)

def canonical_url(url: str, platform: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in PLATFORMS[platform]["hosts"]:
        raise ValueError("Cross-domain or non-HTTPS URL blocked")
    path = re.sub(r"/{2,}", "/", parsed.path).rstrip("/") or "/"
    qs = [(k, v) for k, v in parse_qsl(parsed.query)
          if not any(k.lower().startswith(t) for t in TRACKING)]
    return urlunsplit(("https", parsed.hostname.lower(), path, urlencode(qs), ""))

class JobHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.scripts = []
        self.metadata = {}
        self.page_title = ""
        self.heading = ""
        self.text_parts = []
        self._script = False
        self._title = False
        self._h1 = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._script = True
        if tag == "title":
            self._title = True
        if tag == "h1":
            self._h1 = True
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                self.metadata[key] = a["content"]

    def handle_endtag(self, tag):
        if tag == "script":
            self._script = False
        elif tag == "title":
            self._title = False
        elif tag == "h1":
            self._h1 = False

    def handle_data(self, data):
        t = data.strip()
        if not t:
            return
        if self._script:
            self.scripts.append(data)
        elif self._title:
            self.page_title += data
        elif self._h1:
            self.heading += data
        else:
            self.text_parts.append(data)

def parse_page(html: str) -> JobHTML:
    parser = JobHTML()
    parser.feed(html)
    return parser

def schema_jobs(page: JobHTML):
    def nodes(obj):
        if isinstance(obj, list):
            for item in obj:
                yield from nodes(item)
        elif isinstance(obj, dict):
            types = obj.get("@type") or []
            if types == "JobPosting" or (isinstance(types, list) and "JobPosting" in types):
                yield obj
            for k in ("@graph", "mainEntity"):
                if k in obj:
                    yield from nodes(obj[k])
    for script in page.scripts:
        try:
            yield from nodes(json.loads(script))
        except (ValueError, TypeError):
            continue

def _text(value):
    if isinstance(value, dict):
        return _text(value.get("name") or value.get("value"))
    if isinstance(value, list):
        return ", ".join(filter(None, (_text(x) for x in value)))
    return str(value).strip() if value is not None else ""

def _description(value):
    raw = _text(value)
    return unescape(re.sub(r"<[^>]+>", " ", raw))[:18000]

def _salary(payload):
    if not isinstance(payload, dict):
        return None
    value = payload.get("value")
    if not isinstance(value, dict):
        return None
    low, high = value.get("minValue"), value.get("maxValue")
    unit = value.get("unitText")
    currency = payload.get("currency")
    if not currency or not unit or (low is None and high is None):
        return None
    if any(isinstance(x, bool) or not isinstance(x, (int, float, type(None))) for x in (low, high)):
        return None
    return {"min": low, "max": high, "currency": str(currency), "period": str(unit).lower()}

def _location(payload):
    loc = payload.get("jobLocation")
    if isinstance(loc, list):
        return ", ".join(filter(None, (_location({"jobLocation": x}) for x in loc)))
    if isinstance(loc, dict):
        addr = loc.get("address") or {}
        if isinstance(addr, dict):
            return ", ".join(filter(None, (_text(addr.get("addressLocality")),
                                             _text(addr.get("addressRegion")),
                                             _text(addr.get("addressCountry")))))
        return _text(loc)
    return _text(loc)

def parse_job(html: str, url: str, platform: str) -> dict | None:
    page = parse_page(html)
    job = next(schema_jobs(page), {})
    title = _text(job.get("title")) or page.heading.strip() or page.metadata.get("og:title", "")
    if not title:
        return None
    company = _text(job.get("hiringOrganization")) or "Không rõ công ty"
    description = _description(job.get("description"))
    posted_at = job.get("datePosted")
    deadline = job.get("validThrough")
    if isinstance(deadline, str) and deadline.strip() == "":
        deadline = None
    canonical = canonical_url(url, platform)
    return {
        "source": platform,
        "source_id": hashlib.sha256(canonical.encode()).hexdigest()[:24],
        "company": company, "title": title, "location": _location(job),
        "url": canonical, "description": description,
        "posted_at": posted_at if isinstance(posted_at, str) else None,
        "posted_at_kind": "datePosted" if posted_at else None,
        "application_deadline": deadline if isinstance(deadline, str) else None,
        "salary": _salary(job.get("baseSalary")),
    }

def discover_links(html: str, base_url: str, platform: str) -> list[str]:
    page = parse_page(html)
    seen = set()
    output = []
    for raw in page.links:
        try:
            link = canonical_url(urljoin(base_url, raw), platform)
        except ValueError:
            continue
        if not PLATFORMS[platform]["path"].fullmatch(urlsplit(link).path):
            continue
        # Strip query params on detail pages to make stable source IDs.
        link = urlunsplit((*urlsplit(link)[:3], "", ""))
        if link not in seen:
            seen.add(link)
            output.append(link)
    return output

def fetch_html(url: str, *, platform: str) -> str:
    canonical_url(url, platform)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urlopen(request, timeout=20) as response:
            canonical_url(response.url, platform)  # Reject redirects beyond approved host.
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            raw = response.read(MAX_HTML_BYTES + 1)
            if len(raw) > MAX_HTML_BYTES:
                raise RuntimeError("HTML response exceeds size limit")
            html = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    except HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} (stopped, no bypass attempted)") from e
    except URLError as e:
        raise RuntimeError("Site unreachable") from e
    if any(marker in html.lower() for marker in BLOCKED_MARKERS):
        raise RuntimeError("Access verification or anti-bot page detected; stop collection")
    return html

def robots_allowed(url: str, platform: str) -> bool:
    parsed = urlsplit(url)
    robots = RobotFileParser()
    robots.set_url(f"https://{parsed.hostname}/robots.txt")
    try:
        robots.read()
    except Exception as exc:
        raise RuntimeError("Cannot verify robots policy; refuse collection") from exc
    return robots.can_fetch(USER_AGENT, url)

def collect_licensed(board: dict, *, fetch=fetch_html, sleep=time.sleep,
                     check_robots=robots_allowed) -> list[dict]:
    platform = board["provider"]
    if platform not in PLATFORMS:
        raise ValueError("Unknown licensed platform")
    if not board.get("enabled") or not board.get("permission_confirmed"):
        raise ValueError("A confirmed permission flag is required")
    seeds = board.get("search_urls") or []
    if not isinstance(seeds, list) or not seeds:
        raise ValueError("Add permitted search URLs first")
    max_pages = min(max(int(board.get("max_search_pages", 1)), 1), 3)
    max_detail = min(max(int(board.get("max_job_details", 12)), 1), 30)
    delay = min(max(float(board.get("delay_seconds", 1.5)), 1.0), 30.0)
    candidate_urls = []
    for seed in seeds[:max_pages]:
        url = canonical_url(seed, platform)
        if not check_robots(url, platform):
            raise RuntimeError(f"Robots policy disallows search URL: {url}")
        html = fetch(url, platform=platform)
        candidate_urls.extend(discover_links(html, url, platform))
        sleep(delay)
    result, seen = [], set()
    attempted = 0
    for url in candidate_urls:
        if attempted >= max_detail:
            break
        if url in seen:
            continue
        seen.add(url)
        if not check_robots(url, platform):
            continue
        attempted += 1
        try:
            job = parse_job(fetch(url, platform=platform), url, platform)
            if job:
                job["source"] = f"{platform}:{board.get('board', 'licensed')}"
                result.append(job)
        except RuntimeError as exc:
            # Anti-bot protections/403 must stop this source, not be bypassed.
            if "anti-bot" in str(exc) or "HTTP 403" in str(exc) or "HTTP 429" in str(exc):
                raise
        sleep(delay)
    if not candidate_urls:
        raise RuntimeError("No job links found: page structure, permissions or selectors may have changed")
    if not result:
        raise RuntimeError("No readable job details found; do not count as successful crawl")
    return result
