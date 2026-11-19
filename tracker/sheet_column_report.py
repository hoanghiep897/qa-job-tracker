"""Diagnostic-only summary of owner-managed Google Sheet schema.

Prints labels and up to five salary examples, never descriptions, job links,
personal information, or service-account credentials.
"""
from __future__ import annotations

import json
from collections import Counter
from urllib.parse import urlsplit

from tracker.google_sheet_sync import read_rows, find_headers, norm


def inspect_schema(rows: list[list[str]]) -> dict:
    header_at, mapping = find_headers(rows)
    headers = rows[header_at]
    salary_cols = [(i, str(c)) for i, c in enumerate(headers)
                   if any(x in norm(c) for x in ("luong", "salary", "thu nhap"))]
    samples = {}
    for i, name in salary_cols:
        values = [str(row[i]).strip() for row in rows[header_at+1:]
                  if i < len(row) and str(row[i]).strip()]
        samples[name] = values[:5]
    link_hosts = Counter()
    url_idx = mapping["url"]
    for row in rows[header_at+1:]:
        if len(row) > url_idx:
            host = urlsplit(str(row[url_idx])).hostname
            if host:
                link_hosts[host.lower()] += 1
    return {"header_row": header_at+1, "headers": headers,
            "recognized_fields": mapping,
            "salary_column_examples": samples,
            "job_link_hosts": dict(link_hosts),
            "row_count_excluding_header": len(rows)-header_at-1}

def main() -> None:
    from pathlib import Path
    cfg = json.loads(Path("config/google_sheet.json").read_text())
    print(json.dumps(inspect_schema(read_rows(cfg)), indent=2,
                     ensure_ascii=False))

if __name__ == "__main__":
    main()
