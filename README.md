# QA Job Tracker

A lightweight QA/Tester job market dashboard using Python, SQLite and Streamlit. No paid database, hosting or AI API is required to run locally.

## Features

- Collect public job postings from **operator-approved** Greenhouse, Lever and Ashby boards.
- Import JD rows from CSV.
- SQLite upsert by source + source job ID, with first/last observed timestamps.
- Offline rule-based role classification and skill extraction.
- Streamlit role, location, skill charts, JD Explorer and CSV export.
- Optional, clearly marked demo records.
- GitHub Actions syntax and unit-test checks.

## Get started

Requires Python 3.11+.

```bash
git clone https://github.com/hoanghiep897/qa-job-tracker.git
cd qa-job-tracker
git checkout feat/mvp-dashboard
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m tracker.cli seed-demo
streamlit run app.py
```

## Collect real jobs

Copy `config/boards.example.json` to `config/boards.json`, and add public ATS board identifiers **only for sources that you have approved for collection**. Then run:

```bash
python -m tracker.cli collect
streamlit run app.py
```

Do not bypass rate limits, access restrictions or anti-bot measures. Scraping LinkedIn is not included. If the board list is empty, no requests are made.

## Import CSV

Supply headers `source,source_id,company,title,location,url,description` (only `source`, `source_id` and `title` are required):

```bash
python -m tracker.cli import-csv --file jobs.csv
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Scope and limitations

- The dashboard counts **source-specific records**, not fully deduplicated unique vacancies. Cross-source deduplication is future work.
- Skills are detected via keywords; a mention is not necessarily a mandatory hiring requirement.
- `first_seen` means when the tracker first observed the JD, not when it was first posted.
- SQLite lives on your machine; do **not** assume the database persists across free ephemeral cloud deployments.
- Reports and scheduled collection are planned later, after validating real-source data.
- Demo jobs are synthetic and labeled separately.

## Online dashboard (static / Vercel)

The root `index.html` is an additional **static dashboard** that can run on Vercel's free Hobby tier. It uses synthetic example jobs by default; CSV data is parsed and analyzed **in your browser**, never uploaded to a server. The CSV columns are `title,company,location,description,source,source_id,url` (only `title` is necessary for browser analysis). Skills are keyword-based, not AI-generated.

The static dashboard is **not** the Streamlit service, has **no hosted SQLite database**, and does **not** automatically collect jobs or retain uploaded CSV after refresh. The Python/SQLite collector still runs separately on your machine. Do not assume online data persists or auto-refreshes. The two entrypoints are intentionally separate to avoid ongoing cloud costs.

Production publishing is via Vercel Git integration from `main`. Deploying `index.html` needs no framework build and no server-side secrets. For a future live shared dashboard, use an approved persistent source such as a managed database or generated aggregated JSON committed by an authorized scheduled workflow.
