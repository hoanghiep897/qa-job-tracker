"""Read-only TechJobs.vn public feed viability probe.

This does NOT write data/jobs.json, upload job records, or publish JD text.
It counts matching job titles from a small number of feed pages, with source
attribution and publisher-mandated 2-second pacing.

Reference: https://techjobs.vn/feeds/openapi.json
"""
from __future__ import annotations

import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from tracker.export import relevant

FEED_HOST = "techjobs.vn"
FEED_PATH = "/feeds/jobs.json"
KEYWORDS = ("qa", "tester", "sdet", "kiểm thử", "qc", "automation")
USER_AGENT = "QAJobTracker/0.8 (read-only feed research; https://github.com/hoanghiep897/qa-job-tracker)"
MAX_RESPONSE_BYTES = 4_000_000


def feed_url(query: str, page: int, per_page: int) -> str:
    if query not in KEYWORDS:
        raise ValueError("Unsupported search keyword")
    if not 1 <= page <= 3 or not 1 <= per_page <= 200:
        raise ValueError("Probe page and page-size limits exceeded")
    return f"https://{FEED_HOST}{FEED_PATH}?" + urlencode({
        "q": query, "page": page, "per_page": per_page})


def fetch_page(url: str) -> dict:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != FEED_HOST or parts.path != FEED_PATH:
        raise ValueError("Refusing non-TechJobs feed URL")
    request = Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=25) as response:
            final = urlsplit(response.url)
            if (final.scheme, final.hostname, final.path) != (
                    "https", FEED_HOST, FEED_PATH):
                raise RuntimeError("Feed redirected outside the permitted endpoint")
            if response.status != 200:
                raise RuntimeError(f"Feed returned HTTP {response.status}")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise RuntimeError("Feed response exceeds size limit")
    except HTTPError as exc:
        raise RuntimeError(f"TechJobs feed HTTP {exc.code}; stop, no access workaround") from exc
    except URLError as exc:
        raise RuntimeError(f"TechJobs feed unavailable: {exc.reason}") from exc

    try:
        obj = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("TechJobs feed did not return valid JSON") from exc
    if not isinstance(obj, dict) or not isinstance(obj.get("jobs"), list):
        raise RuntimeError("TechJobs feed schema changed: jobs[] missing")
    return obj


def probe(*, fetch=fetch_page, sleep=time.sleep, keywords=KEYWORDS,
          max_pages=2, per_page=200, delay_seconds=2.0) -> dict:
    if not 1 <= max_pages <= 3 or not 1 <= per_page <= 200:
        raise ValueError("Unsafe probe pagination settings")
    if delay_seconds < 2.0:
        raise ValueError("Respect TechJobs feed 2-second crawl-delay")

    seen_all = set()
    seen_qa = set()
    seen_companies = set()
    rows = []
    request_count = 0
    for query in keywords:
        if query not in KEYWORDS:
            raise ValueError("Unsupported keyword")
        found = set()
        title_matched = set()
        total = None
        pages_read = 0
        has_next = False
        for page in range(1, max_pages + 1):
            # Sleep between all requests, even when changing search terms.
            if request_count:
                sleep(delay_seconds)
            payload = fetch(feed_url(query, page, per_page))
            request_count += 1
            pages_read += 1
            total = payload.get("total") if total is None else total
            jobs = payload["jobs"]
            for job in jobs:
                if not isinstance(job, dict) or job.get("id") is None:
                    continue
                identifier = str(job["id"]).strip()
                if not identifier:
                    continue
                found.add(identifier)
                seen_all.add(identifier)
                title = job.get("title")
                if isinstance(title, str) and relevant(title):
                    title_matched.add(identifier)
                    seen_qa.add(identifier)
                    company = job.get("company")
                    if isinstance(company, str) and company.strip():
                        seen_companies.add(company.strip().casefold())
            next_url = payload.get("next")
            pages = payload.get("pages")
            has_next = bool(next_url) or (
                isinstance(pages, int) and not isinstance(pages, bool) and page < pages)
            if not has_next:
                break
        rows.append({
            "keyword": query,
            "feed_reported_total": total if isinstance(total, int) else None,
            "pages_read": pages_read,
            "items_read_unique_in_query": len(found),
            "qa_qc_title_matches_in_query": len(title_matched),
            "truncated_by_probe_limit": has_next,
        })
    return {
        "source": "TechJobs.vn public job feed",
        "feed": f"https://{FEED_HOST}{FEED_PATH}",
        "scope": "read-only viability test; search totals may overlap; QA/QC includes non-software quality jobs",
        "http_requests": request_count,
        "unique_jobs_sampled_across_keywords": len(seen_all),
        "unique_qa_qc_title_matches_across_keywords": len(seen_qa),
        "unique_companies_with_qa_qc_titles": len(seen_companies),
        "searches": rows,
        "published_to_dashboard": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--per-page", type=int, default=200)
    args = parser.parse_args()
    stats = probe(max_pages=args.max_pages, per_page=args.per_page)
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
