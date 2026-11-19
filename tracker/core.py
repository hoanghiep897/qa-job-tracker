"""SQLite storage, skill tagging and approved public ATS collectors."""
from __future__ import annotations

import json
import re
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

SKILLS = {
    "Playwright": r"\bplaywright\b",
    "Selenium": r"\bselenium\b",
    "Cypress": r"\bcypress\b",
    "Appium": r"\bappium\b",
    "Robot Framework": r"\brobot\s+framework\b",
    "Postman": r"\bpostman\b",
    "API Testing": r"\b(?:api\s+testing|rest\s+assured|api\s+automation)\b",
    "Java": r"\bjava\b(?!script)",
    "Python": r"\bpython\b",
    "JavaScript": r"\b(?:javascript|java\s*script)\b",
    "TypeScript": r"\btypescript\b",
    "SQL": r"\bsql\b",
    "Jenkins": r"\bjenkins\b",
    "GitHub Actions": r"\bgithub\s+actions\b",
    "Docker": r"\bdocker\b",
    "JMeter": r"\bjmeter\b",
    "k6": r"\bk6\b",
    "AI / LLM": r"\b(?:llm|large language model|generative ai|genai|chatgpt)\b",
}
ROLE_RE = [
    ("SDET", r"\bsdet\b|software development engineer in test"),
    ("QA Lead", r"\b(?:qa|test|quality)\s*(?:lead|manager)\b|\bhead of qa\b"),
    ("Automation QA", r"\b(?:automation|automated|test automation)\b"),
    ("Manual QA", r"\b(?:qa|tester|testing|quality assurance|test engineer)\b"),
]

def tags(text: str) -> list[str]:
    return [name for name, pattern in SKILLS.items() if re.search(pattern, text or "", re.I)]

def role(title: str) -> str:
    for name, pattern in ROLE_RE:
        if re.search(pattern, title or "", re.I):
            return name
    return "Other"

def connect(db_path: str = "data/jobs.db") -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY,
        source TEXT NOT NULL,
        source_id TEXT NOT NULL,
        company TEXT NOT NULL,
        title TEXT NOT NULL,
        location TEXT NOT NULL DEFAULT '',
        url TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL,
        skills_json TEXT NOT NULL,
        demo INTEGER NOT NULL DEFAULT 0,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        UNIQUE(source, source_id)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_role ON jobs(role)")
    db.commit()
    return db

def save_job(db: sqlite3.Connection, job: dict, demo: bool = False) -> None:
    source = str(job["source"]).strip()
    source_id = str(job["source_id"]).strip()
    title = str(job["title"]).strip()
    if not source or not source_id or not title:
        raise ValueError("source, source_id and title are required")
    company = str(job.get("company") or "Unknown").strip()
    description = str(job.get("description") or "")
    now = datetime.now(timezone.utc).isoformat()
    db.execute("""INSERT INTO jobs
        (source,source_id,company,title,location,url,description,role,skills_json,demo,first_seen,last_seen)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(source,source_id) DO UPDATE SET
        company=excluded.company,title=excluded.title,location=excluded.location,
        url=excluded.url,description=excluded.description,role=excluded.role,
        skills_json=excluded.skills_json,last_seen=excluded.last_seen
    """, (source, source_id, company, title, str(job.get("location") or ""),
          str(job.get("url") or ""), description, role(title),
          json.dumps(tags(title + " " + description)), int(demo), now, now))
    db.commit()

ALLOWED_HOSTS = {"boards-api.greenhouse.io", "api.lever.co", "api.ashbyhq.com"}

def request_json(url: str) -> object:
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("Only configured public ATS API hosts are supported")
    req = urllib.request.Request(url, headers={"User-Agent": "QAJobTracker/0.1 (+public job boards)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return json.load(response)

def fetch_board(board: dict) -> list[dict]:
    """Fetch publicly listed jobs; board names are explicitly configured by the operator."""
    provider = board["provider"].lower()
    slug = board["board"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", slug):
        raise ValueError("Invalid board identifier")
    company = board.get("company") or slug
    safe = quote(slug, safe="")
    if provider == "greenhouse":
        data = request_json(f"https://boards-api.greenhouse.io/v1/boards/{safe}/jobs?content=true")
        items = data.get("jobs", [])
        return [dict(source=f"greenhouse:{slug}", source_id=str(x["id"]),
                     company=company, title=x.get("title", ""),
                     location=(x.get("location") or {}).get("name", ""),
                     url=x.get("absolute_url", ""),
                     description=x.get("content") or "") for x in items]
    if provider == "lever":
        items = request_json(f"https://api.lever.co/v0/postings/{safe}?mode=json")
        output = []
        for x in items:
            parts = [str(x.get("descriptionPlain") or "")]
            for section in x.get("lists") or []:
                if not isinstance(section, dict):
                    continue
                parts.append(str(section.get("text") or ""))
                content = section.get("content") or []
                # Lever boards may return content as plain text, HTML, or
                # structured list elements; never assume dict-only entries.
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    parts.extend(str(c.get("text") or "") if isinstance(c, dict)
                                 else str(c) for c in content)
            output.append(dict(source=f"lever:{slug}", source_id=str(x["id"]),
                               company=company, title=x.get("text", ""),
                               location=(x.get("categories") or {}).get("location", ""),
                               url=x.get("hostedUrl", ""),
                               description=" ".join(parts)))
        return output
    if provider == "ashby":
        data = request_json(f"https://api.ashbyhq.com/posting-api/job-board/{safe}")
        return [dict(source=f"ashby:{slug}", source_id=str(x.get("id") or x.get("jobUrl") or x.get("title")),
                     company=company, title=x.get("title", ""),
                     location=x.get("location") or "", url=x.get("jobUrl") or x.get("applyUrl") or "",
                     description=x.get("descriptionPlain") or "")
                for x in data.get("jobs", []) if x.get("isListed", True)]
    raise ValueError(f"Unsupported provider: {provider}")

def import_csv(db: sqlite3.Connection, filename: str) -> int:
    import csv
    count = 0
    with open(filename, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            save_job(db, row)
            count += 1
    return count
