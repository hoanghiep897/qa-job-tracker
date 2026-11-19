"""Export observed QA job postings into a small static dashboard dataset.

Collection uses public ATS APIs from explicitly configured boards. No login,
anti-bot bypass, candidate data or paid services. Published JSON holds only
job metadata and extracted skill labels, not full descriptions.
"""
from __future__ import annotations
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from tracker.core import fetch_board, role, tags

QA_TITLE = re.compile(
    r"\b(?:qa|qc|quality assurance|quality engineer|quality analyst|test(?:ing|er|ers)?|sdet|automation engineer|software quality|verification engineer|kiểm thử|kiểm tra phần mềm)\b",
    re.IGNORECASE,
)
MAX_JOBS = 2500

def market_region(location: str) -> str:
    """Conservative geographic label; SEA is not assumed Vietnam."""
    place = (location or "").lower()
    if re.search(r"\b(?:viet\s?nam|ha\s?noi|hanoi|ho chi minh|hcmc|saigon|sai gon|da nang|danang)\b", place):
        return "Vietnam"
    if re.search(r"\b(?:south\s?east asia|southeast asia|asean)\b", place):
        return "Southeast Asia"
    if re.search(r"\b(?:any location|anywhere|worldwide|global|remote)\b", place):
        return "Remote / unspecified"
    return "Other / unspecified"


def relevant(title: str) -> bool:
    return bool(QA_TITLE.search(title or ""))

def public_job(item: dict, observed_at: str) -> dict:
    title = str(item.get("title") or "").strip()
    source = str(item.get("source") or "").strip()
    source_id = str(item.get("source_id") or "").strip()
    return {
        "source": source,
        "source_id": source_id,
        "company": str(item.get("company") or "Unknown").strip(),
        "title": title,
        "location": str(item.get("location") or "").strip(),
        "market_region": market_region(str(item.get("location") or "")),
        "url": str(item.get("url") or "").strip(),
        "role": role(title),
        "skills": tags(title + " " + str(item.get("description") or "")),
        "first_seen": observed_at,
        "last_seen": observed_at,
        "status": "observed",
        "posted_at": item.get("posted_at") or None,
        "posted_text": str(item.get("posted_text") or "").strip()[:180] or None,
        "experience_text": str(item.get("experience_text") or "").strip()[:180] or None,
        "posted_at_kind": item.get("posted_at_kind") or None,
        "application_deadline": item.get("application_deadline") or None,
        "salary": item.get("salary") if isinstance(item.get("salary"), dict) else None,
        "salary_text": str(item.get("salary_text") or "").strip()[:180] or None,
        "ingested_from": item.get("ingested_from") if item.get("ingested_from") == "google_sheet" else None,
    }

def build_dataset(boards: list[dict], previous: dict | None = None, fetch=fetch_board,
                  observed_at: str | None = None) -> dict:
    today = observed_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    old_items = (previous or {}).get("jobs") or []
    existing = {(j.get("source"), str(j.get("source_id"))): j
                for j in old_items if j.get("source") and j.get("source_id")}
    merged = dict(existing)
    succeeded, failures, fetched_count = [], [], 0
    for board in boards:
        if not board.get("enabled", False):
            continue
        provider = str(board.get("provider", ""))
        slug = str(board.get("board", ""))
        name = f"{provider}:{slug}"
        try:
            jobs = fetch(board)
            fetched_count += len(jobs)
            succeeded.append(name)
            for item in jobs:
                if not relevant(str(item.get("title") or "")):
                    continue
                job = public_job(item, today)
                if not job["source"] or not job["source_id"] or not job["title"]:
                    continue
                key = (job["source"], job["source_id"])
                old = existing.get(key)
                if old:
                    job["first_seen"] = old.get("first_seen") or today
                    # Preserve verified source metadata if the source later omits it.
                    for field in ("posted_at", "posted_at_kind", "posted_text", "experience_text", "application_deadline", "salary", "salary_text"):
                        if job[field] is None and old.get(field) is not None:
                            job[field] = old[field]
                merged[key] = job
        except Exception as exc:
            failures.append({"source": name, "error": str(exc)[:180]})
    if not succeeded:
        raise RuntimeError("No configured job sources succeeded; refusing to overwrite dataset")
    # Retain old jobs, clearly marked 'not_verified_this_run' when a board
    # was successfully checked and its listing disappeared; do not assume closed.
    for key, old in existing.items():
        if key not in merged:
            merged[key] = old
    for key, item in list(merged.items()):
        if item.get("last_seen") != today and item.get("source") in succeeded:
            item = dict(item)
            item["status"] = "not_verified_this_run"
            merged[key] = item
    for job in merged.values():
        job["market_region"] = market_region(job.get("location", ""))
    jobs = sorted(merged.values(),
                  key=lambda j: (j.get("last_seen") or "", j.get("source") or ""),
                  reverse=True)[:MAX_JOBS]
    return {
        "schema_version": 1,
        "updated_at": today,
        "scope": "Selected public job boards; not representative of the whole market",
        "sources_succeeded": succeeded,
        "sources_failed": failures,
        "source_records_read": fetched_count,
        "jobs": jobs,
    }

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/boards.json")
    parser.add_argument("--output", default="data/jobs.json")
    args = parser.parse_args()
    boards = json.loads(Path(args.config).read_text(encoding="utf-8"))
    output = Path(args.output)
    previous = json.loads(output.read_text(encoding="utf-8")) if output.is_file() else None
    result = build_dataset(boards, previous)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(result['jobs'])} QA jobs; successful sources: "
          f"{len(result['sources_succeeded'])}; errors: {len(result['sources_failed'])}")

if __name__ == "__main__":
    main()
