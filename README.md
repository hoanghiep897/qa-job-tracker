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

## v0.2 — scheduled public job-feed snapshots

The dashboard first tries to read `data/jobs.json` from the repository's `main` branch on GitHub Raw. If there are no records or the request fails, the page uses three **clearly labeled synthetic examples**. CSV uploads are still processed only in your browser.

The daily GitHub Actions workflow `Collect public QA jobs` runs at **03:15 UTC (10:15 Vietnam time)** and can be started manually from Actions → Collect public QA jobs → Run workflow. A first collection is also triggered by changes to its configuration when pushed to `main`. It publishes a compact JSON containing job title, company, location, URL, source and keyword-derived skills, **not full JD text**.

Initial boards (public ATS job feeds): NAVER VIETNAM, what3words, Backbase, BTSE, Colonist. They were selected because their public careers sites have had Vietnam or Southeast Asia-relevant QA roles; currently available positions and successful API access are **not guaranteed**. Review `config/boards.json` to disable any feed if collection is not authorized. Follow the individual source's terms and respect access restrictions and limits.

Dashboard trends cover **only configured, successfully observed boards**, including remote/region-wide positions; they are not a national labour-market estimate. Data may be outdated when a source is unreachable. A posting's `first_seen` means observation time, not original listing date. Different sites may have duplicate vacancies. `status=not_verified_this_run` means absence from a successfully refreshed feed and is not proof of closure.

The collector intentionally keeps old records across runs and refuses to overwrite the snapshot if every feed fails. GitHub is used as storage within repository size and Actions quotas; no cloud database or LLM API is required. The Vercel project is currently deployed manually because its GitHub integration is not connected. Dataset changes propagate through GitHub Raw automatically when the site is loaded, but **UI code changes still need a deployment** until Vercel Git integration is connected.

Run locally:

```bash
python -m tracker.export --config config/boards.json --output data/jobs.json
python -m unittest discover -s tests -v
```

## v0.3 — Geographic coverage and freshness controls

The browser dashboard now adds filters for Vietnam, Southeast Asia, remote/unspecified and other observed locations, plus a 7-day / 30-day **first observed** filter. Results are exploratory: regional and remote listings **are not assumed eligible for Vietnam candidates**. Country classification is rule-based and may need manual review. The dashboard visualizes source observations, not headcount or a representative national market sample.

The pipeline assigns `market_region` for each job, including historical records, while retaining `first_seen`, `last_seen` and verification status. This still runs on GitHub Actions + JSON with no hosted database. The data pipeline's automated updates do not need Vercel redeploys; changes to `index.html` do.

## v0.4 — Salary and recruitment dates

The **JD Explorer** includes **Mức lương**, **Ngày đăng**, and **Hạn ứng tuyển**, and CSV export includes these fields.

- `posted_at` is used only when the ATS provides an explicit publication timestamp. Greenhouse's `first_published` is an initial publication date. Ashby's `publishedAt` may reflect its latest publication/update, so the browser labels it `(cập nhật)`. Lever's `createdAt` is not a publication date, and is **not displayed** as one.
- `application_deadline` is empty for ATS feeds that do not expose a verified field. **Never** infer the deadline from `first_seen`, `last_seen`, or job age.
- `salary` requires a published numeric range with currency and pay interval. Displayed as reported, without conversion. Multicomponent/ambiguous compensation is omitted. Missing values display `Không công bố`; they do not imply an employer offers no compensation.
- CSV uploads may include `posted_at`, `application_deadline`, `salary_min`, `salary_max`, `salary_currency`, `salary_period`. These must be sourced from actual job advertisements.
- New ATS fields populate on the next successful scheduled collection; historical records without source metadata remain blank. No paid API/database required.

## v0.5 — More Vietnam-relevant company career sources

New configured public ATS boards: **Aperia Solutions (Greenhouse)**, **ShopBack (Lever)**, and **Agility IO (Ashby)**. They join the five existing sources. These are **company-owned recruitment boards**, not ITviec/TopCV/LinkedIn scrapers. Some sources may currently have no QA postings or may change their public endpoints; successful live retrieval is checked by GitHub Actions after merging.

**ITviec, TopCV, VietnamWorks, TopDev and LinkedIn are NOT scraped by this application.** Search pages being public does not by itself authorize systematic copying and republishing. ITviec's terms may require prior written permission for automated collection. Integration with these services requires a license, approved API/feed, or another authorized method. No CAPTCHA evasion, logged-in scraping or rotating proxy systems are included.

Use `config/boards.json` to disable any source if its permissions change. At most one request is made to each public ATS endpoint per collection. Publication on the dashboard is still limited to title, company, location, URL, source, observed timestamps and extracted skills; original full JD text is not republished. The sample remains **non-representative** of Vietnam's QA labor market.

## Licensed Vietnamese job-board crawler (v0.6)

The repository contains a bounded HTML crawler in \`tracker/licensed_html.py\` for ITviec, TopCV and VietnamWorks. The operator confirmed they have permission; each integration additionally requires \`enabled: true\` and \`permission_confirmed: true\` in \`config/boards.json\`. Confirm your agreement covers the **specific domains, automated requests, and metadata publication** before running. Disable any source outside scope.

The configured search pages are starter URLs, **not provider-supported APIs**. HTML parsing uses links and structured \`JobPosting\` JSON-LD when available. It does not automate sign-in, access restricted data, solve CAPTCHA, bypass anti-bot protection, or retry blocked requests with other identities. Search page layouts may be JavaScript-rendered, and provider URLs may change. A source with zero parsable links or blocked access is reported as a failed source and does not cause existing good data to be erased.

Collection behavior: one bounded sequential request per listing/detail page; strict domain validation; \`robots.txt\` check; minimum delay of one second; max three search pages and 30 job details per source, with lower configured defaults; HTTPS only; no full JD text republished. Extracted salary and deadline are included only when source structured data explicitly reports them.

Configured examples:
- ITviec: \`https://itviec.com/it-jobs?query=tester\`
- TopCV: \`https://www.topcv.vn/tim-viec-lam-tester\`
- VietnamWorks: \`https://www.vietnamworks.com/viec-lam?q=tester\`

A live result count can only be claimed after reviewing GitHub Actions logs and the updated \`data/jobs.json\`. Sites may return zero or reject crawling even when permission is granted. In that case obtain official API/feed documentation or a site-specific allowed endpoint rather than evading restrictions.

Run tests: \`python -m unittest discover -s tests -v\`.

### Robots policy and written authorization

The first GitHub Actions run found that all three licensed HTML search URLs were disallowed by their robots policies. They therefore **did not contribute any new job records**; the existing ATS records remain intact.

An optional \`robots_override_authorized: true\` flag allows a source owner to honor **specific written permission that explicitly overrides robots.txt restrictions**. It defaults to **false** for ITviec, TopCV and VietnamWorks. The \`permission_confirmed\` flag does not imply such an override. Enable the additional flag only when your agreement actually covers it; no captcha solving, HTTP 403/429 workaround, or traffic obfuscation is performed.

If an official authenticated or licensed API/feed was supplied, prefer that endpoint rather than public HTML crawling. Even with a robots override, pages with blocking or JS-only content may yield no data; inspect Actions logs and request an authorized feed from the provider.

## v0.7 — Daily Playwright browser collector (pilot: ITviec)

A separate workflow, `.github/workflows/browser-collect.yml`, starts Chromium in a fresh GitHub-hosted Ubuntu runner around **07:00 Vietnam time** (`00:00 UTC`) each day, and supports manual dispatch. It is independent of the existing ATS collector and uses the same concurrency group to protect dataset updates. No laptop needs to be on. GitHub Actions cron may execute later than scheduled.

The initial pilot is **ITviec only** with one search URL, a maximum of five job-detail requests, and at least two seconds between requests. TopCV and VietnamWorks are **not browser-enabled**. It renders JavaScript, extracts JobPosting JSON-LD and reuses existing source filtering/metadata export. The browser has no saved session, login, stealth settings, rotating IPs or CAPTCHA solving.

Only run within the scope of your platform authorization. Both `permission_confirmed` and `browser_enabled` must be true. The crawler honors `robots.txt` unless **separate, explicit contractual authorization** allows overriding it via `robots_override_authorized: true`; the default remains false. Encountering HTTP 401/403/429, an authentication challenge, or verification stops that source. A successful HTTP response alone does not guarantee job links are detectable; site-specific selectors may need maintenance.

If the browser scan fails, the workflow fails and **does not overwrite** the published `data/jobs.json`. On success the dashboard reads the new JSON automatically. The first push of this workflow triggers a real smoke run; subsequent runs follow the daily schedule or a manual run. See the GitHub Actions log for the actual results (do not assume successful collection before verifying).

Run local tests without installing Playwright: `python -m unittest discover -s tests -v`. To run the real browser task locally, install Playwright + Chromium and run `python -m tracker.browser_daily --platform itviec`.

## v0.8 — Alternate daily browser pilots

The scheduled Chromium workflow now tries **TopCV** and **VietnamWorks**, separately, at most five job details per source. ITviec browser crawling is disabled following the observed HTTP 403 from the GitHub runner. Each source retains its independently configured permission confirmation and `robots_override_authorized: false` by default. A failed source cannot overwrite the prior JSON; the workflow summary reports each outcome. If both fail, the scan is marked failed. This is a pilot: successful retrieval of live JD is not guaranteed and must be validated from logs.
