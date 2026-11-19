"""Google Sheet-only daily importer backed by an on-disk SQLite database.

Use the user-maintained Google Sheet as the *only* authoritative job source.
SQLite stores all dated observations and a current view; public jobs.json is a
small static projection of current rows, never a second source of truth.

The runner commits both data/jobs.sqlite3 and data/jobs.json to its repo.
No external database, cloud keys, raw unrelated sheet columns or web scrapers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tracker.core import role, tags
from tracker.export import market_region
from tracker.google_sheet_sync import (
    capture_reference_at, find_headers, format_date, norm, read_rows,
    relative_posted_at, safe_job_url, safe_salary_text, source_from_link,
    validate_config,
)

def clean_sheet_cell(value: str, max_chars: int = 2000) -> str:
    """Retain cell text without shortening genuine skill requirements to 180 chars."""
    clean = "".join(ch if (ch in "\\n\\r\\t" or (ord(ch) >= 32 and ord(ch) != 127)) else " " for ch in str(value or ""))
    return clean.strip()[:max_chars]


DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spreadsheet_id TEXT NOT NULL,
    tab_gid INTEGER,
    reference_at TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    source_rows INTEGER NOT NULL,
    valid_rows INTEGER NOT NULL,
    unique_jobs INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    job_key TEXT PRIMARY KEY,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    current INTEGER NOT NULL DEFAULT 1,
    row_order INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    job_key TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_current ON jobs(current, row_order);
CREATE INDEX IF NOT EXISTS idx_obs_snap ON observations(snapshot_id);
"""


def build_rows(rows: list[list[str]], *, now: datetime | None = None) -> tuple[list[dict], list[dict], dict]:
    """Map *all* rows with valid title+URL, preserving original Sheet fields."""
    if not rows:
        raise RuntimeError("Sheet is empty: keep the previously published snapshot")
    header_at, columns = find_headers(rows)
    reference = capture_reference_at(now=now)
    imported_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(
        timespec="seconds")
    unique: dict[str, dict] = {}
    observations = []
    nonempty = invalid = 0
    for row_number, line in enumerate(rows[header_at + 1:], start=header_at + 2):
        if not any(str(v).strip() for v in line):
            continue
        nonempty += 1
        rec = {field: (str(line[index]).strip() if index < len(line) else "")
               for field, index in columns.items()}
        title = rec.get("title", "")
        url = safe_job_url(rec.get("url", ""))
        if not title or not url:
            invalid += 1
            continue
        # Do not filter out non-QA titles or previously advertised jobs. The
        # owner controls the Sheet; the current website mirrors that snapshot.
        posted_raw = rec.get("posted_at", "")
        exact = format_date(posted_raw)
        approx = None if exact else relative_posted_at(posted_raw, reference=reference)
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        skills_text = clean_sheet_cell(rec.get("skills", ""), 3000)
        public = {
            "source": source_from_link(url),
            "sheet_source": clean_sheet_cell(rec.get("source", ""), 100),
            "source_id": key[:24],
            "company": clean_sheet_cell(rec.get("company", ""), 240),
            "title": clean_sheet_cell(title, 380),
            "location": clean_sheet_cell(rec.get("location", ""), 240),
            "url": url,
            "role": role(title),
            "market_region": market_region(rec.get("location") or ""),
            "skills_text": skills_text,
            "skills": tags(title + " " + skills_text),
            "experience_text": clean_sheet_cell(rec.get("experience_text", ""), 400) or None,
            "salary_text": clean_sheet_cell(rec.get("salary_text", ""), 400) or None,
            "posted_at": exact or approx,
            "posted_text": clean_sheet_cell(posted_raw, 400) or None,
            "posted_at_kind": ("datePosted" if exact else
                               "estimated_from_sheet_0600" if approx else None),
            "posted_reference_at": reference.isoformat() if approx else None,
            "application_deadline": format_date(rec.get("deadline", "")),
            "sheet_status": clean_sheet_cell(rec.get("status", ""), 120) or None,
            "ingested_from": "google_sheet",
            "sheet_row": row_number,
            "status": "observed",
        }
        item = {"key": key, "row_number": row_number, "job": public}
        observations.append(item)
        unique[key] = item
    if not unique:
        raise RuntimeError("Sheet has no valid job title + HTTP(S) link; keep last snapshot")
    return (
        [x["job"] for x in sorted(unique.values(), key=lambda x: x["row_number"])],
        observations,
        {"sheet_rows": nonempty, "invalid_rows": invalid, "valid_rows": len(observations),
         "unique_jobs": len(unique), "reference_at": reference.isoformat(),
         "imported_at": imported_at},
    )


def write_database(db_path: str, jobs: list[dict], observations: list[dict],
                   metadata: dict, sheet_config: dict) -> tuple[list[dict], int]:
    """Single transaction: update current jobs and append daily observations."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(DB_SCHEMA)
        with db:
            cur = db.execute(
                """INSERT INTO snapshots
                   (spreadsheet_id, tab_gid, reference_at, imported_at,
                    source_rows, valid_rows, unique_jobs)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sheet_config["spreadsheet_id"], sheet_config.get("gid"),
                 metadata["reference_at"], metadata["imported_at"],
                 metadata["sheet_rows"], metadata["valid_rows"], metadata["unique_jobs"]),
            )
            snapshot_id = cur.lastrowid
            db.execute("UPDATE jobs SET current=0")
            for obs in observations:
                db.execute(
                    """INSERT INTO observations
                       (snapshot_id, job_key, row_number, payload_json) VALUES (?, ?, ?, ?)""",
                    (snapshot_id, obs["key"], obs["row_number"],
                     json.dumps(obs["job"], ensure_ascii=False, sort_keys=True)),
                )
            for job in jobs:
                key = hashlib.sha256(job["url"].encode("utf-8")).hexdigest()
                db.execute(
                    """INSERT INTO jobs
                       (job_key, first_seen, last_seen, current, row_order, payload_json)
                       VALUES (?, ?, ?, 1, ?, ?)
                       ON CONFLICT(job_key) DO UPDATE SET
                         last_seen=excluded.last_seen, current=1,
                         row_order=excluded.row_order, payload_json=excluded.payload_json""",
                    (key, metadata["imported_at"], metadata["imported_at"],
                     job["sheet_row"], json.dumps(job, ensure_ascii=False, sort_keys=True)),
                )
        rows = db.execute(
            "SELECT first_seen, last_seen, payload_json FROM jobs "
            "WHERE current=1 ORDER BY row_order ASC"
        ).fetchall()
    current = []
    for first_seen, last_seen, payload in rows:
        item = json.loads(payload)
        item["first_seen"] = first_seen
        item["last_seen"] = last_seen
        current.append(item)
    return current, snapshot_id


def sync(config_path="config/google_sheet.json", output_path="data/jobs.json",
         database_path="data/jobs.sqlite3", *, loader=read_rows,
         now: datetime | None = None) -> dict:
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    validate_config(cfg)
    rows = loader(cfg)
    items, observations, meta = build_rows(rows, now=now)
    current, snapshot_id = write_database(
        database_path, items, observations, meta, cfg
    )
    result = {
        "schema_version": 2,
        "updated_at": meta["imported_at"],
        "scope": "User-maintained Google Sheet only. Current spreadsheet snapshot.",
        "source_mode": "google_sheet_only",
        "database": "SQLite",
        "snapshot_id": snapshot_id,
        "capture_reference_at": meta["reference_at"],
        "sources_succeeded": ["google_sheet"],
        "sources_failed": [],
        "source_records_read": meta["valid_rows"],
        "google_sheet_sync": {
            "source": "google_sheet",
            "sheet_rows": meta["sheet_rows"],
            "invalid_rows": meta["invalid_rows"],
            "distinct_jobs": meta["unique_jobs"],
        },
        "jobs": current,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".tmp")
    try:
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        temp.replace(output)
    finally:
        if temp.exists():
            temp.unlink()
    print("Sheet-only SQLite snapshot saved:", json.dumps({
        "snapshot": snapshot_id, "valid_rows": meta["valid_rows"],
        "current_jobs": len(current), "invalid_rows": meta["invalid_rows"],
        "reference_at": meta["reference_at"],
    }, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/google_sheet.json")
    parser.add_argument("--output", default="data/jobs.json")
    parser.add_argument("--database", default="data/jobs.sqlite3")
    args = parser.parse_args()
    sync(args.config, args.output, args.database)
