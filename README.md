# Current architecture: Google Sheet only + SQLite (November 2026)

**Authoritative data source:** The owner-maintained spreadsheet in `config/google_sheet.json` (currently spreadsheet ID `1z32LC5lyYNif8tZpT99si1HlsiWHNFbUsfL6WJkNBzg`). External ATS crawlers, Playwright probes, and TechJobs diagnostics are **not scheduled, enabled or called** in the live collection pipeline. Their legacy code/documentation may remain for historical reference only; they are not a dashboard data source.

### How the daily pipeline works

1. Before **06:00 Vietnam time**, update the **same configured spreadsheet/tab** with the day's JD records.
2. Around **06:50 Vietnam time**, GitHub Actions runs `.github/workflows/google-sheet-sync.yml`, reads the Sheet (public CSV or Google Sheets read-only service-account API), and validates its headers and links.
3. The standard-library **SQLite database** `data/jobs.sqlite3` stores an immutable observation row for every valid Sheet row in every import (including repeat jobs and updates), plus a current indexed jobs table. Removed jobs are retained in database history, but marked inactive.
4. `data/jobs.json` is generated **only from the current SQLite jobs view**. The public Vercel site reads this JSON with no backend/database credentials. The initial migration discards old ATS records from the displayed snapshot while leaving earlier Git commits intact.
5. On success GitHub Actions commits **both SQLite and the JSON snapshot**. On invalid, empty or inaccessible input, the job fails without publishing a new JSON or altering the committed DB. The existing Vercel deployment is static and reads fresh JSON from GitHub at page load.

**Current display fields mirror the Sheet:** original title, company, source platform (based on the exact row's job link), salary/budget, location, experience/level, original skill requirements, original posting label (and estimated date from 06:00 ICT), link to original job and optional deadline. Unlike the previous ATS collector, the new importer does **not filter job titles** — all valid rows authored in the Sheet become eligible to appear. A repeated job link counts once in the current view; each row observation is still saved in SQLite history. Charts may compute derived roles and skills for filtering, while the JD table retains the owner's original field text.

**Important limitations:** GitHub repositories are versioned storage, not a hosted SQL server. This is a genuine SQLite database file and works for this small daily dataset with no cloud DB account, but it grows with daily history and is committed to a **public GitHub repository**. Do not place confidential, private or personal data in job columns. For large-scale production data or server-side SQL queries, migrate to hosted PostgreSQL. The website **does not query SQLite directly** — it reads the JSON snapshot built from the database.

**Daily "new Sheet":** Fully automatic operation assumes the owner **updates rows in the same Google spreadsheet/tab** each morning. Creating a completely new spreadsheet ID (or a new tab with a new gid) cannot be auto-discovered from the old link with CSV-only access. If replacing the file or tab daily, update `config/google_sheet.json` with the new ID/gid before 06:50, or keep reusing the fixed Sheet as an intake tab. Stale relative posting labels will otherwise be estimated against the wrong day's 06:00 reference.

To run locally (Python 3.11+, no database service needed):
```bash
python -m tracker.sheet_database --config config/google_sheet.json --output data/jobs.json --database data/jobs.sqlite3
```

To inspect history locally: `sqlite3 data/jobs.sqlite3 'SELECT id, reference_at, unique_jobs FROM snapshots ORDER BY id DESC LIMIT 10;'`.

---

## Canonical location options

The public `Địa điểm` dropdown and `JD Explorer` display use consistent Vietnamese city names. Alias spelling (e.g. `Ha Noi`, `Hanoi`, `Hà Nội`) maps to a single `Hà Nội` option; `Ho Chi Minh`, `Hồ Chí Minh (mới)` and `TP.HCM` map to `Hồ Chí Minh`. Other known cities are normalized similarly. A JD spanning two cities (regardless of order or connector such as `-` / `&`) is listed under **both** corresponding city filters, and its table cell shows the standardized locations. `Remote` stays a separate option. City aliases are also recognized as part of the Vietnam market region, including accented labels.

This is a **frontend presentation and search filter normalization only**. The database and `jobs.json` preserve the exact location text supplied by the daily Google Sheet for auditability. Unrecognized places are not guessed or rewritten. No change to the 06:50 import, snapshot schema, JD links or source data is needed.

---

## New first-visit layout (four task-based views)

The production static dashboard has four client-side tabs to avoid dumping all analysis panels into a single page. **Bắt đầu** is shown by default with a clear short explanation, an experience target selector, a five-item skill preview and three actions. Those actions carry the selected experience target into **Khám phá JD** (exact-year filter), **So sánh kỹ năng** (second comparison cohort), or **Lộ trình upskill** (self-assessment target).

- **Khám phá JD:** Current Google Sheet records, filters, JD Explorer, CSV export, and four KPI counters; the region/age selectors are tucked into a collapsed advanced-filter disclosure, and role/skill/region charts into a collapsed statistics disclosure. Interactive chart filtering still works when expanded.
- **So sánh kỹ năng:** Focuses solely on source skill percentages by two experience levels; independent of hidden Explore filters.
- **Lộ trình upskill:** Personal skill checklist and practice suggestions grouped by 30/60/90 days.

Tabs are accessible buttons (click and keyboard arrow/Home/End) and do not fetch new data or require a database migration. All features continue using only the owner's Sheet-based `jobs.json` and optional browser-local self-assessment. No schema changes or scheduling changes.

---

## Career & Skill Insights — frontend only

The dashboard now helps compare explicit experience requirements for **3, 4, 5, and 6 years**, as well as other exact year values, `Trên 5 năm`, `Entry Level`, `Intermediate`, `Expert`, missing or unrecognized labels. These are **mutually separate buckets**: a range like `3-5 năm` and the phrase `Trên 5 năm` are never invented as a precise year.

The **Yêu cầu kinh nghiệm** selector filters JD Explorer, bar charts, KPIs and downloaded CSV. The **So sánh kỹ năng theo kinh nghiệm** panel compares two independently selected cohorts (default 3 vs 5 years), using original comma-/semicolon-separated values from `Skill yêu cầu (cho CV)`, not inferred job-title tags. Counts are per distinct JD and percentages use *that cohort's* JD count as denominator. A difference in percentage points is descriptive only. For each cohort, the UI shows its JD sample count and warns when either group has fewer than five jobs. Comparisons use the entire current Sheet snapshot independently of all filters in the JD Explorer, so previously selected filters cannot silently alter the compared cohorts.

**My Skill Gap** lets visitors self-report known skills with checkboxes, selected from the most frequent 25 skill labels for their selected experience target. Skills not checked mean **not self-assessed**, not proven missing. Answers are stored only in browser `localStorage` for that site and are never sent to GitHub, Google Sheet or the SQLite database. The **30/60/90-day learning roadmap** chooses up to six frequently mentioned skills not self-marked as known and proposes small practice tasks, clearly labeled as *suggestions*, not job responsibilities extracted from the original postings. No new columns or additional Google Sheet scraping are required.

The role bucket remains a title-based heuristic. It can misclassify some QA/Automation titles, so consider the sample and examine original JD links before drawing strong conclusions. These statistics describe only the owner-maintained Sheet's current snapshot, not the complete market.

---

## Historical implementation notes (superseded for live pipeline)

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

## Live browser pilot result (19 November 2026)

The GitHub-hosted Chromium run [44508413945](https://github.com/hoanghiep897/qa-job-tracker/actions/runs/44508413945) found TopCV HTTP 403; VietnamWorks robots.txt returned HTTP 404, leaving its access policy unverified. No new JD were collected from these sites. ITviec previously returned HTTP 403. The browser workflow has been **paused as a daily scheduled job** after these failures to avoid repeated unsuccessful requests; it remains manually runnable (workflow_dispatch) and on code/configuration changes for diagnostics. The separate working ATS daily collector still runs normally. Re-enable scheduling after approved access or a verified API/feed is available.

## TechJobs public feed proof of concept (read-only)

The experimental `tracker/techjobs_probe.py` inspects **https://techjobs.vn/feeds/jobs.json** to evaluate the number of live QA/Tester/SDET/QC job titles in Vietnam-relevant employer postings. Feed documentation: https://techjobs.vn/feeds/openapi.json. The source's operator describes a feed-specific automated indexing exception in the terms at https://techjobs.vn/terms, with TechJobs credit and the original employer apply link required for redistribution. **This proof of concept deliberately does not redistribute, store, or publish any job details.**

It searches six terms (`qa`, `tester`, `sdet`, `kiểm thử`, `qc`, `automation`), takes at most two 200-record pages per term, waits at least two seconds between requests, and prints only counts to GitHub Actions. Counts deduplicate by feed job ID, but title-based QA/QC matches can also include roles outside software testing. Search result totals and partial pages are not a whole-market estimate.

Run manually from GitHub Actions → **TechJobs feed QA coverage probe (read only)** → Run workflow. A first smoke test triggers when the workflow is merged into main. No key, paid plan, database, browser or deployment required; the workflow has `contents: read` permissions and **never modifies `data/jobs.json`**. The separate ATS collector continues to run daily.

Run locally: `python -m tracker.techjobs_probe --max-pages 2 --per-page 200`.

Next steps after evaluating the live response: review the TechJobs feed terms against the intended public dashboard, retain both source attribution and original employer apply link, add explicit opt-in adapter and cross-source deduplication, and only then enable automatic publishing. If GitHub-hosted runners receive 403/429, stop rather than attempting evasion.

### REST API fallback (19 Nov 2026)

The initial GitHub Actions feed trial returned HTTP 404 for `/feeds/jobs.json`, its unfiltered form, the paginated form, and `/feeds/openapi.json`. A second **read-only** test uses the [official developer REST endpoint](https://techjobs.vn/developers) `/api/v1/jobs` with six QA-related queries, `limit=10`, `page=1`, `response_format=detailed` and 2-second spacing. Anonymous REST search may return truncated results (`notice`); reported totals and returned titles are separately labeled. The REST terms restrict building competing job databases. This test prints summary counts only, does not store jobs, and does not update the dashboard. Do not claim the API is accessible until the live workflow succeeds.

## v0.9 — Google Sheets → QA Job Tracker daily (07:00 Vietnam time)

This deployment uses the owner-maintained spreadsheet:

https://docs.google.com/spreadsheets/d/1vl0slYeHVb_yshR2AhczcVppCtBXRCJCty8rXYvkMGA/edit

The separate workflow `.github/workflows/google-sheet-sync.yml` runs every day at **00:00 UTC = 07:00 Vietnam time (UTC+7)**, can be launched manually, and also runs once when this workflow is merged. GitHub scheduled actions may start later than the exact cron time; make sure spreadsheet edits are saved before 07:00. It does not require a personal computer, database, or Vercel redeployment. The existing 10:15 Vietnam-time ATS collector continues independently; they share a concurrency group.

### Grant read-only access (choose one)

**Option A — simple public CSV:** Google Sheets → Share → General access → **Anyone with the link** → **Viewer**. Then the action uses Google's direct CSV export with the current spreadsheet ID, without a credential. Be aware that anyone with the link can read the spreadsheet, so avoid putting private personal data in it. This only enables reading; the workflow never edits the spreadsheet.

**Option B — retain a private spreadsheet:** Enable the **Google Sheets API** for a Google Cloud project, create a service account and JSON key, and share the *specific Google Sheet* as **Viewer** with the service account's email address (not your own email). In GitHub → repo Settings → Secrets and variables → Actions, set repository secret named **`GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON`** to the **entire service-account JSON**. Never commit the secret, paste it in issues, or share it in chat. If the secret is present, the crawler uses read-only OAuth scope `spreadsheets.readonly` automatically; otherwise it uses public CSV export. See [Google Workspace service account credentials](https://developers.google.com/workspace/guides/create-credentials).

The first tab is selected by default. If the JD data is on a different tab, open that tab in Google Sheets, copy its numeric `gid` from the URL (`#gid=123456`), and replace `gid: null` in `config/google_sheet.json` with that integer.

### Required columns and accepted labels

The importer scans the first 20 rows for a column-header row. Two columns are mandatory: a QA/Tester/SDET **job title** (e.g. `Vị trí tuyển dụng`, `Vị trí`, `Title`) and an **original job URL** (e.g. `Link JD`, `Link`, `URL`). A valid external `http(s)` JD link is required for each published row. Other supported aliases include:

| Field | Example header |
| --- | --- |
| Company | `Tên công ty`, `Công ty`, `Company` |
| Location | `Địa điểm làm việc`, `Địa điểm`, `Location` |
| Skills | `Kỹ năng`, `Skills` |
| Description | `Mô tả công việc`, `Description` |
| Posting date | `Ngày đăng` (YYYY-MM-DD or DD/MM/YYYY) |
| Deadline | `Hạn ứng tuyển` |
| Status | `Trạng thái` — `Đã đóng`, `Hết hạn`, `Ngừng tuyển` rows are excluded |

Salary is published only when numeric `salary_min`, `salary_max`, `salary_currency` and `salary_period` (month, year, hour) are present and valid. Arbitrary salary text is deliberately **not** converted or invented.

The sync keeps source metadata (title, company, location, link, verified source dates and skill labels), **not full descriptions**. It filters QA/Tester/SDET roles, deduplicates identical links (including differences only in `utm_*` parameters), and retains previously observed ATS and Sheet records. Jobs removed from the current Sheet are marked `not_verified_this_run` rather than assumed closed. Empty/malformed/inaccessible Sheet responses make the job fail *before* publishing, preserving the previous `data/jobs.json`. The sync displays only counts and error categories in the log; it never prints service-account keys.

**Important:** This conversation could not read the exact spreadsheet contents, so the column mapping is flexible rather than verified against its actual header row. After granting access, check the first GitHub Actions run at **Actions → Sync owner Google Sheet to QA dashboard**, then refresh your existing Vercel dashboard. Public display rights for third-party job metadata remain the sheet owner's responsibility; collecting a source into a spreadsheet does not automatically grant rights to republish entire external JDs.

Manual local run (CSV-public sheet or configured service-account environment):

```bash
python -m tracker.google_sheet_sync --config config/google_sheet.json --output data/jobs.json
```

### Actual November 19 Sheet columns, salary and board source mapping

The live spreadsheet's first-tab columns are `Nguồn`, `Vị trí`, `Công ty`, `Lương / Budget`, `Địa điểm`, `Kinh nghiệm / Level`, `Skill yêu cầu (cho CV)`, `Ngày đăng (tính từ 19/11/2026)`, and `Link`. The owner-controlled sheet contains TopCV, ITviec, and Upwork links (43, 20 and 9 rows when inspected on 19 November 2026). These counts are observations, not a promise of currently open roles.

The importer now detects `Lương / Budget` and preserves **raw salary text verbatim**, including values such as `18 - 24 triệu` or `Thoả thuận`. No monetary interpretation or invented ranges are made. The browser's `Mức lương` column displays the raw value when available and falls back to structured numeric salary. The `Nguồn` field is derived from each row's validated job link hostname (**TopCV**, **ITviec**, **Upwork**, or the normalized domain for other sources); the adjacent **Link JD** column opens the exact original posting URL. The `Skill yêu cầu (cho CV)` field contributes to keyword skill tags, without republishing the entire original content.

This rollout migrates previously ingested generic `google_sheet:daily` source records to their proper job-board source, keeping the original first-observed time and preventing duplicate JDs from the same URL. Google Sheet provenance remains in `ingested_from`. Relative source posting timestamps (e.g. `2 ngày trước`) are **not converted to calendar dates** without a verified reference point. The 07:00 ICT schedule remains unchanged.

### Ngày đăng và Kinh nghiệm / Level từ Google Sheet (19/11/2026)

The importer recognizes the exact Sheet headers `Ngày đăng (tính từ 19/11/2026)` and `Kinh nghiệm / Level`. Raw relative strings, such as `Posted 24 days ago` or `Posted 2 hours ago`, are published as `posted_text` and displayed in the **Ngày đăng** column without interpreting them as dates relative to the current day. Their reference date belongs to the source Sheet, so review or refresh those relative strings when updating the Sheet. Verified explicit dates continue to be parsed into `posted_at` and formatted for display. Experience values are published as `experience_text` and displayed in a new **Kinh nghiệm / Level** column. Both fields are included in downloaded CSV exports. Missing values remain `Không công bố`; no dates or experience requirements are invented. The 07:00 Vietnam-time sync schedule and source links remain unchanged.

### Chuyển ngày đăng tương đối theo mốc crawl 06:00 (giờ Việt Nam)

The owner refreshes the source Google Sheet at **06:00 ICT (Asia/Ho_Chi_Minh)** each day, and GitHub Actions normally synchronizes around 07:00 ICT. The sync resolves English and Vietnamese relative posting labels against **06:00 on the Vietnam-local calendar date of that synchronization**, not the server's UTC time or the static date embedded in a historical column header. Examples for a 19 Nov 2026 sync: `Posted 2 hours ago` → `2026-11-19T04:00:00+07:00`; `Posted 24 days ago` → `2026-10-26T06:00:00+07:00`; `Đăng 3 tuần trước` → `2026-10-29T06:00:00+07:00`. The dashboard renders the timezone-correct date and time with **(ước tính)** because relative timestamps are approximate. Original wording remains stored in `posted_text`, and the reference point in `posted_reference_at`. Exact source dates remain exact-date values; unparseable wording is preserved rather than guessed.

**Important assumption:** the Sheet must actually be refreshed around 06:00 *each day*. A manual sync of stale relative labels on a later day will reinterpret the same labels against that later day's 06:00 and thus shift estimates. If a day is skipped, update the Sheet before manually re-running or add a separate capture-date column to make the reference explicit. The importer prints counts of populated experience and posted fields to distinguish genuinely blank source cells from parsing errors. Existing ATS records are retained, and ATS entries without confirmed experience/posting dates are not filled with invented values.

### Interactive roles and skills (dashboard)

The `Phân bổ vai trò` and `Kỹ năng xuất hiện trong JD` bars in JD Explorer are **clickable filters**, not just summaries. Click a role or skill to filter the table, its KPIs, and the CSV export. Role and skill filters combine with each other and existing location/market/age selectors; clicking an active bar again clears that selection. A compact visible filter summary provides a **Xóa lọc vai trò / kỹ năng** control, leaving location and other selectors unchanged. Bars are native keyboard-accessible buttons with `aria-pressed` selection state. When no JD matches, an informative table row is shown instead of a blank result.

The production UI no longer includes the **Dữ liệu demo** reset button; data already loaded from the daily Google Sheet/ATS sources remains in place. The manual CSV upload (for optional private local analysis) and CSV export are unchanged. The existing 07:00 Vietnam-time sync remains unchanged.
