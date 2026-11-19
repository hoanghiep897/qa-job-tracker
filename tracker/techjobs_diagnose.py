"""Read-only availability checks for documented TechJobs feed endpoints.

No retries, bypass, browser, secrets, persistent storage or job data output.
"""
from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tracker.techjobs_probe import USER_AGENT

CHECK_URLS = [
    "https://techjobs.vn/feeds/jobs.json",
    "https://techjobs.vn/feeds/jobs.json?page=1&per_page=5",
    "https://techjobs.vn/feeds/jobs.json?page=1&per_page=5&q=qa",
    "https://techjobs.vn/feeds/openapi.json",
]

def diagnose(*, fetch=urlopen, sleep=time.sleep):
    rows = []
    for i, url in enumerate(CHECK_URLS):
        if i:
            sleep(2.0)
        request = Request(url, headers={
            "User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with fetch(request, timeout=20) as r:
                row = {"endpoint": url, "status": r.status,
                       "final_url": r.url, "type": r.headers.get("Content-Type")}
        except HTTPError as exc:
            row = {"endpoint": url, "status": exc.code,
                   "error": "HTTP error; no alternate identity or retry attempted"}
        except URLError as exc:
            row = {"endpoint": url, "status": None,
                   "error": "network error"}
        rows.append(row)
    return rows

if __name__ == "__main__":
    print(json.dumps({"techjobs_feed_checks": diagnose()},
                     ensure_ascii=False, indent=2))
