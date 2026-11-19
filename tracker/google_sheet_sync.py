"""Sync a user-owned Google Sheet to the existing static QA jobs dashboard.

Only user-supplied job metadata is published, never the sheet itself, entire
descriptions, private credentials, or a direct spreadsheet link. Supports
shareable CSV or a read-only Google Sheets API service-account secret.
"""
from __future__ import annotations

import argparse
import csv
import calendar
import hashlib
import io
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen

from tracker.export import build_dataset, relevant

SOURCE = "google_sheet:daily" # ingestion event, not the displayed job-board source
SOURCE_NAMES = {"topcv.vn": "TopCV", "itviec.com": "ITviec", "upwork.com": "Upwork",
                "vietnamworks.com": "VietnamWorks", "careerbuilder.vn": "CareerViet"}
MAX_CSV_BYTES = 6_000_000
MAX_ROWS = 5000
VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SHEET_CAPTURE_HOUR = 6  # owner manually updates at 06:00 local time
SHEET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,120}$")
HEADERS = {
    "title": ("title", "job title", "ten vi tri", "vi tri", "vi tri tuyen dung",
              "vi tri cong viec", "chuc danh", "ten cong viec", "cong viec",
              "job", "ten job", "vi tri ung tuyen"),
    "company": ("company", "company name", "cong ty", "ten cong ty",
                "nha tuyen dung", "don vi tuyen dung", "doanh nghiep"),
    "location": ("location", "dia diem", "dia diem lam viec", "noi lam viec",
                 "khu vuc", "dia chi", "tinh thanh", "thanh pho", "city"),
    "url": ("url", "link", "link jd", "jd url", "job url", "job link",
            "link job", "link tin", "link tuyen dung", "link ung tuyen",
            "link cong viec", "duong dan", "url cong viec"),
    "description": ("description", "mo ta", "mo ta cong viec",
                    "job description", "jd", "noi dung jd", "mo ta jd"),
    "skills": ("skills", "skill", "ky nang", "ky nang yeu cau",
               "skill yeu cau cho cv", "ky nang yeu cau cho cv",
               "yeu cau", "yeu cau cong viec", "cong nghe"),
    "experience_text": ("kinh nghiem", "kinh nghiem level", "experience",
                        "experience level", "level", "so nam kinh nghiem",
                        "yeu cau kinh nghiem"),
    "posted_at": ("date posted", "posted at", "posted date", "ngay dang",
                  "ngay dang tin", "ngay dang tuyen", "ngay tuyen dung"),
    "deadline": ("deadline", "han ung tuyen", "han nop ho so",
                 "han nop", "ngay het han", "han chot"),
    "status": ("status", "trang thai", "tinh trang"),
    "salary_text": ("luong budget", "luong / budget", "muc luong", "luong",
                    "salary", "salary range", "thu nhap", "budget"),
    "salary_min": ("salary min", "min salary", "luong toi thieu", "luong min"),
    "salary_max": ("salary max", "max salary", "luong toi da", "luong max"),
    "salary_currency": ("salary currency", "currency", "don vi tien", "tien te"),
    "salary_period": ("salary period", "period", "chu ky luong", "ky luong"),
}
NORMALIZED_ALIASES = {k: set() for k in HEADERS}


def norm(value: object) -> str:
    s = unicodedata.normalize("NFKD", str(value or "").strip().lower().replace("đ", "d"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


for _field, _aliases in HEADERS.items():
    NORMALIZED_ALIASES[_field] = {norm(x) for x in _aliases}


def validate_config(config: dict) -> tuple[str, int | None]:
    sheet_id = str(config.get("spreadsheet_id") or "")
    if not SHEET_ID_RE.fullmatch(sheet_id):
        raise ValueError("Invalid Google spreadsheet ID in config/google_sheet.json")
    gid = config.get("gid")
    if gid is not None and (isinstance(gid, bool) or not isinstance(gid, int) or gid < 0):
        raise ValueError("gid must be null or a nonnegative integer")
    return sheet_id, gid


def fetch_public_rows(config: dict) -> list[list[str]]:
    sheet_id, gid = validate_config(config)
    params = {"format": "csv"}
    if gid is not None:
        params["gid"] = gid
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?{urlencode(params)}"
    request = Request(url, headers={
        "User-Agent": "QAJobTracker/1.0 (user-owned Google Sheet metadata sync)",
        "Accept": "text/csv",
    })
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(f"Google Sheets CSV returned HTTP {response.status}")
            raw = response.read(MAX_CSV_BYTES + 1)
            if len(raw) > MAX_CSV_BYTES:
                raise RuntimeError("Sheet CSV is too large (6 MB limit)")
            ctype = response.headers.get("Content-Type", "").lower()
    except HTTPError as exc:
        raise RuntimeError(
            f"Google Sheet CSV HTTP {exc.code}. For an unlisted sheet, enable "
            "'Anyone with the link: Viewer' or use the service-account secret."
        ) from exc
    except URLError as exc:
        raise RuntimeError("Could not reach Google Sheets for CSV export") from exc
    body = raw.decode("utf-8-sig", errors="replace")
    if "text/html" in ctype or body.lstrip().lower().startswith(("<html", "<!doctype html")):
        raise RuntimeError("Sheet returned a login/HTML page, not CSV; access not granted")
    return list(csv.reader(io.StringIO(body)))


def fetch_private_rows(config: dict, credentials_json: str) -> list[list[str]]:
    """Read the first tab, or a configured gid, with Sheets API read-only scope."""
    sheet_id, gid = validate_config(config)
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as exc:
        raise RuntimeError("Install google-auth[requests] for private Sheet access") from exc

    try:
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(credentials_json),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise RuntimeError("Invalid service-account credentials secret") from exc

    session = AuthorizedSession(credentials)
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    meta = session.get(base, params={"fields": "sheets(properties(sheetId,title))"}, timeout=30)
    if meta.status_code != 200:
        raise RuntimeError(f"Google Sheets API metadata HTTP {meta.status_code}; "
                           "share the sheet with the service account as Viewer")
    sheets = meta.json().get("sheets") or []
    if not sheets:
        raise RuntimeError("Spreadsheet has no visible tabs")
    selected = None
    for tab in sheets:
        p = tab.get("properties") or {}
        if gid is None or p.get("sheetId") == gid:
            selected = p
            break
    if selected is None:
        raise RuntimeError(f"No sheet tab with gid={gid}")
    title = str(selected["title"]).replace("'", "''")
    a1_range = quote(f"'{title}'!A1:AZ{MAX_ROWS + 20}", safe="")
    r = session.get(f"{base}/values/{a1_range}",
                    params={"valueRenderOption": "FORMATTED_VALUE"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Google Sheets API values HTTP {r.status_code}")
    if len(r.content) > MAX_CSV_BYTES:
        raise RuntimeError("Sheet API response is too large")
    values = r.json().get("values") or []
    return [[str(x) for x in row] for row in values]


def read_rows(config: dict) -> list[list[str]]:
    # Secret is never committed or printed. If present, private mode wins.
    secret = os.environ.get("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON", "").strip()
    rows = fetch_private_rows(config, secret) if secret else fetch_public_rows(config)
    if len(rows) > MAX_ROWS + 20:
        raise RuntimeError("Google Sheet has too many rows; split it before syncing")
    return rows


def find_headers(rows: list[list[str]]) -> tuple[int, dict[str, int]]:
    for number, row in enumerate(rows[:20]):
        fields = {}
        for idx, label in enumerate(row):
            key = norm(label)
            # Recognize columns with an owner-specified reference date.
            # Example: "Ngày đăng (tính từ 19/11/2026)".
            if key.startswith("ngay dang tinh tu ") and "posted_at" not in fields:
                fields["posted_at"] = idx
                continue
            for field, aliases in NORMALIZED_ALIASES.items():
                if key in aliases and field not in fields:
                    fields[field] = idx
                    break
        if "title" in fields and "url" in fields:
            return number, fields
    raise ValueError(
        "Google Sheet needs header columns for title (e.g. 'Vị trí') "
        "and job URL (e.g. 'Link JD'); cannot safely publish without them"
    )


def safe_job_url(value: str) -> str | None:
    url = str(value or "").strip()
    p = urlsplit(url)
    if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password:
        return None
    if len(url) > 1800:
        return None
    # Strip marketing trackers and fragments so repeated rows stay stable.
    allowed_query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                     if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/",
                       urlencode(allowed_query), ""))


def source_from_link(url: str) -> str:
    """Use the actual JD URL host, never the spreadsheet's generic source name."""
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    if not host:
        raise ValueError("JD source URL needs a host")
    return SOURCE_NAMES.get(host, host)


def safe_salary_text(raw: str) -> str | None:
    """Keep owner's stated compensation verbatim; don't invent ranges or units."""
    value = str(raw or "").strip()
    if not value:
        return None
    # Limit text and remove dangerous control characters. The UI uses textContent.
    return re.sub(r"[\x00-\x1f\x7f]+", " ", value)[:180].strip() or None


def format_date(value: str) -> str | None:
    v = str(value or "").strip()
    if not v:
        return None
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(v[:10], pattern).date().isoformat()
        except ValueError:
            continue
    try:
        # Timestamps are accepted only when they start with ISO date.
        if re.match(r"^\d{4}-\d{2}-\d{2}T", v):
            return datetime.fromisoformat(v.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    return None


def capture_reference_at(*, now: datetime | None = None) -> datetime:
    """The 06:00 ICT snapshot on the local date the sheet is synchronized.

    GitHub cron runs around 07:00 ICT. We intentionally never use the GitHub
    runner's UTC clock hour as the baseline.
    """
    current = now or datetime.now(VIETNAM_TZ)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("capture reference requires a timezone-aware datetime")
    local_date = current.astimezone(VIETNAM_TZ).date()
    return datetime.combine(local_date, time(SHEET_CAPTURE_HOUR, 0),
                            tzinfo=VIETNAM_TZ)


def relative_posted_at(raw: str, *, reference: datetime) -> str | None:
    """Convert English/Vietnamese relative postings to estimated ISO time.

    Output is marked estimated by the importer; preserve raw text as evidence.
    Month/year offsets use calendar arithmetic and are likewise approximate.
    """
    txt = norm(raw)
    if txt in ("dang hom nay", "hom nay", "posted today", "today",
               "posted just now", "just posted", "vua dang"):
        return reference.isoformat()
    if txt in ("dang hom qua", "hom qua", "posted yesterday", "yesterday"):
        return (reference - timedelta(days=1)).isoformat()
    m = re.fullmatch(
        r"(?:posted\s+|dang\s+)?(\d+)\s+"
        r"(minutes?|mins?|phut|hours?|hrs?|gio|days?|ngay|"
        r"weeks?|tuan|months?|thang|years?|nam)"
        r"(?:\s+(?:ago|truoc))?",
        txt,
    )
    if not m:
        return None
    count = int(m.group(1))
    if count > 3650:  # guard against erroneous units or an unbounded offset
        return None
    unit = m.group(2)
    if unit in ("minute", "minutes", "min", "mins", "phut"):
        timestamp = reference - timedelta(minutes=count)
    elif unit in ("hour", "hours", "hr", "hrs", "gio"):
        timestamp = reference - timedelta(hours=count)
    elif unit in ("day", "days", "ngay"):
        timestamp = reference - timedelta(days=count)
    elif unit in ("week", "weeks", "tuan"):
        timestamp = reference - timedelta(weeks=count)
    else:
        months = count * (12 if unit in ("year", "years", "nam") else 1)
        target_month = reference.year * 12 + reference.month - 1 - months
        if target_month < 1:
            return None
        year, month_zero = divmod(target_month, 12)
        month = month_zero + 1
        day = min(reference.day, calendar.monthrange(year, month)[1])
        timestamp = reference.replace(year=year, month=month, day=day)
    return timestamp.isoformat()


def safe_salary(row: dict) -> dict | None:
    def number(v: str):
        v = str(v or "").strip()
        if not re.fullmatch(r"\d+(?:\.\d+)?", v):
            return None
        return float(v) if "." in v else int(v)
    lower, upper = number(row.get("salary_min", "")), number(row.get("salary_max", ""))
    currency = str(row.get("salary_currency") or "").strip().upper()
    period = str(row.get("salary_period") or "").strip().lower()
    if currency not in ("VND", "USD", "EUR") or period not in (
            "month", "monthly", "year", "yearly", "hour", "hourly"):
        return None
    if lower is None and upper is None:
        return None
    if lower is not None and upper is not None and lower > upper:
        return None
    return {"min": lower, "max": upper, "currency": currency,
            "period": {"monthly": "month", "yearly": "year", "hourly": "hour"}.get(period, period)}


def extract_jobs(rows: list[list[str]], *,
                 now: datetime | None = None) -> tuple[list[dict], dict]:
    if not rows:
        raise RuntimeError("Google Sheet is empty; refusing to overwrite current jobs")
    header_at, fields = find_headers(rows)
    reference = capture_reference_at(now=now)
    by_id = {}
    counts = {"sheet_rows": 0, "valid_link_rows": 0, "qa_title_rows": 0}
    for line in rows[header_at + 1:]:
        if not any(str(x).strip() for x in line):
            continue
        counts["sheet_rows"] += 1
        record = {field: (str(line[idx]).strip() if idx < len(line) else "")
                  for field, idx in fields.items()}
        title = record.get("title", "").strip()
        if norm(title) in NORMALIZED_ALIASES["title"]:
            continue
        if norm(record.get("status", "")) in (
                "closed", "expired", "da dong", "ngung tuyen", "het han"):
            continue
        url = safe_job_url(record.get("url", ""))
        if not url or not title:
            continue
        counts["valid_link_rows"] += 1
        if not relevant(title):
            continue
        counts["qa_title_rows"] += 1
        source_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        raw_posted = record.get("posted_at", "")
        explicit_date = format_date(raw_posted)
        relative_date_time = None if explicit_date else relative_posted_at(
            raw_posted, reference=reference)
        by_id[source_id] = {
            "source": source_from_link(url), "source_id": source_id,
            "ingested_from": "google_sheet", "title": title[:280],
            "company": (record.get("company") or "Không rõ công ty")[:160],
            "location": (record.get("location") or "")[:240],
            "url": url,
            "description": (record.get("description", "") + " " +
                            record.get("skills", ""))[:18000],
            "posted_at": explicit_date or relative_date_time,
            "posted_text": safe_salary_text(raw_posted),
            "experience_text": safe_salary_text(record.get("experience_text", "")),
            "posted_at_kind": ("datePosted" if explicit_date else
                               "estimated_from_sheet_0600" if relative_date_time else None),
            "posted_reference_at": reference.isoformat() if relative_date_time else None,
            "application_deadline": format_date(record.get("deadline", "")),
            "salary": safe_salary(record),
            "salary_text": safe_salary_text(record.get("salary_text", "")),
        }
    if not by_id:
        raise RuntimeError(
            "No QA/Tester/SDET rows with valid job links. "
            "Check the Google Sheet headers and data; preserving previous snapshot."
        )
    counts["distinct_qa_jobs"] = len(by_id)
    counts["experience_present"] = sum(bool(j["experience_text"]) for j in by_id.values())
    counts["posted_text_present"] = sum(bool(j["posted_text"]) for j in by_id.values())
    counts["posted_datetime_present"] = sum(bool(j["posted_at"]) for j in by_id.values())
    return list(by_id.values()), counts


def sync(config_path: str = "config/google_sheet.json",
         output_path: str = "data/jobs.json", *, loader=read_rows) -> dict:
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    validate_config(cfg)
    rows = loader(cfg)
    jobs, counts = extract_jobs(rows)
    output = Path(output_path)
    previous = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
    # Re-key previous generic-source records by job URL to avoid duplicate JD
    # after migration and keep original first_seen timestamps.
    if previous:
        for old in previous.get("jobs", []):
            if old.get("source") == SOURCE and old.get("url"):
                old["source"] = source_from_link(old["url"])
                old["ingested_from"] = "google_sheet"
    result = build_dataset(
        [{"provider": "google_sheet", "board": "daily", "enabled": True}],
        previous=previous, fetch=lambda board: jobs)
    active_keys = {(j["source"], j["source_id"]) for j in jobs}
    for item in result["jobs"]:
        if item.get("ingested_from") == "google_sheet" and (
                item.get("source"), item.get("source_id")) not in active_keys:
            item["status"] = "not_verified_this_run"
    result["google_sheet_sync"] = {"source": SOURCE, **counts,
                                   "read_mode": "service_account" if os.getenv(
                                       "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON") else "public_csv"}
    # Use same parent directory for atomic replacement; never truncate old file
    # until all upstream reads, parsing, and validation succeeded.
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".tmp")
    try:
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        temp.replace(output)
    finally:
        if temp.exists():
            temp.unlink()
    print("Google Sheet sync completed:", json.dumps(counts, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/google_sheet.json")
    parser.add_argument("--output", default="data/jobs.json")
    args = parser.parse_args()
    sync(args.config, args.output)
