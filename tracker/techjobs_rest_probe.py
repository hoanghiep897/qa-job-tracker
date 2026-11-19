"""Read-only viability probe for TechJobs' documented developer REST API.

Use of REST is restricted by the provider's API terms. No job text or record
is persisted, redistributed or exported. Without a key only 10 records per
page and up to 3 pages are allowed; this probe takes only page 1.
"""
from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from tracker.export import relevant
from tracker.techjobs_probe import KEYWORDS, USER_AGENT

REST_URL = "https://techjobs.vn/api/v1/jobs"
MAX_BYTES = 1_000_000


def build_url(query: str) -> str:
    if query not in KEYWORDS:
        raise ValueError("Unknown or unapproved search term")
    return REST_URL + "?" + urlencode({
        "q": query, "limit": 10, "page": 1,
        "response_format": "detailed"})


def request_jobs(url: str) -> dict:
    parsed = urlsplit(url)
    if (parsed.scheme, parsed.hostname, parsed.path) != (
            "https", "techjobs.vn", "/api/v1/jobs"):
        raise ValueError("Not the documented TechJobs REST endpoint")
    req = Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=20) as response:
            final = urlsplit(response.url)
            if (final.scheme, final.hostname, final.path) != (
                    "https", "techjobs.vn", "/api/v1/jobs"):
                raise RuntimeError("Unexpected API redirect")
            if response.status != 200:
                raise RuntimeError(f"API HTTP {response.status}")
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise RuntimeError("API response too large")
    except HTTPError as exc:
        raise RuntimeError(f"TechJobs REST HTTP {exc.code}; no workaround attempted") from exc
    except URLError as exc:
        raise RuntimeError("TechJobs REST connection failed") from exc

    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("REST response was not JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise RuntimeError("REST JSON does not have jobs[]")
    return data


def probe_rest(*, fetch=request_jobs, sleep=time.sleep, keywords=KEYWORDS) -> dict:
    unique_all, unique_qa = set(), set()
    rows = []
    for i, query in enumerate(keywords):
        if query not in KEYWORDS:
            raise ValueError("Unsupported query")
        if i:
            sleep(2.0)
        payload = fetch(build_url(query))
        title_matches = set()
        for item in payload["jobs"]:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            identifier = str(item["id"])
            unique_all.add(identifier)
            if relevant(str(item.get("title") or "")):
                title_matches.add(identifier)
                unique_qa.add(identifier)
        rows.append({
            "keyword": query,
            "api_reported_total": payload.get("total") if isinstance(payload.get("total"), int) else None,
            "items_returned": len(payload["jobs"]),
            "qa_qc_title_matches_in_page_1": len(title_matches),
            "notice": str(payload.get("notice") or "")[:160] or None,
        })
    return {
        "source": "TechJobs REST Developer API (read-only)",
        "url": REST_URL,
        "sample_pages": 1,
        "unique_items_seen": len(unique_all),
        "unique_qa_qc_titles_seen": len(unique_qa),
        "searches": rows,
        "published_to_dashboard": False,
        "scope": "Page-one pilot, not a full market or company coverage estimate",
    }


if __name__ == "__main__":
    print(json.dumps(probe_rest(), indent=2, ensure_ascii=False))
