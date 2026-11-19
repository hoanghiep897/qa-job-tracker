"""Database contract: only Google Sheet rows are public, all snapshots retained."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tracker.sheet_database import build_rows, sync

SHEET_ID = "1z32LC5lyYNif8tZpT99si1HlsiWHNFbUsfL6WJkNBzg"
AT_7 = datetime.fromisoformat("2026-11-19T07:00:00+07:00")
AT_NEXT = datetime.fromisoformat("2026-11-20T07:00:00+07:00")
HEAD = ["Nguồn", "Vị trí", "Công ty", "Lương / Budget", "Địa điểm",
        "Kinh nghiệm / Level", "Skill yêu cầu (cho CV)",
        "Ngày đăng (tính từ 19/11/2026)", "Link"]
R1 = ["TopCV", "Senior QA Engineer", "TechCo", "18 - 24 triệu", "Hà Nội",
      "3-5 năm", "Playwright, API Testing, Postman", "Đăng 2 ngày trước",
      "https://www.topcv.vn/viec-lam/qa/123?utm_source=owner"]
R2 = ["Upwork", "Data Analyst", "AnalysisCo", "$20/hour", "Remote",
      "Intermediate", "SQL / dashboard skills", "Posted 2 hours ago",
      "https://www.upwork.com/jobs/~42"]
R3 = ["ITviec", "Manual Tester", "Software Co", "Thỏa thuận", "TP.HCM",
      "Fresher", "Manual testing", "Posted 24 days ago",
      "https://itviec.com/it-jobs/manual-qa-123"]


class SheetOnlyDatabaseTests(unittest.TestCase):
    def test_preserves_sheet_fields_and_does_not_filter_non_qa_titles(self):
        jobs, observations, stats = build_rows([HEAD, R1, R2, R3], now=AT_7)
        self.assertEqual(len(jobs), 3)
        self.assertEqual(stats["valid_rows"], 3)
        self.assertEqual(stats["invalid_rows"], 0)
        self.assertEqual(jobs[0]["source"], "TopCV")
        self.assertEqual(jobs[0]["sheet_source"], "TopCV")
        self.assertEqual(jobs[0]["title"], "Senior QA Engineer")
        self.assertEqual(jobs[0]["salary_text"], "18 - 24 triệu")
        self.assertEqual(jobs[0]["experience_text"], "3-5 năm")
        self.assertEqual(jobs[0]["skills_text"], "Playwright, API Testing, Postman")
        self.assertEqual(jobs[0]["posted_at"], "2026-11-17T06:00:00+07:00")
        self.assertEqual(jobs[1]["title"], "Data Analyst")
        self.assertEqual(jobs[1]["posted_at"], "2026-11-19T04:00:00+07:00")
        self.assertEqual(jobs[2]["posted_at"], "2026-10-26T06:00:00+07:00")
        self.assertNotIn("utm_source", jobs[0]["url"])
        self.assertTrue(all(j["ingested_from"] == "google_sheet" for j in jobs))
        self.assertEqual(len(observations), 3)

    def test_sync_migrates_to_sheet_only_snapshot_without_old_ats(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "sheet.json"
            output = root / "jobs.json"
            db_file = root / "jobs.sqlite3"
            config.write_text(json.dumps({"spreadsheet_id": SHEET_ID}), encoding="utf-8")
            output.write_text(json.dumps({
                "jobs": [{"source": "lever:old", "title": "Old ATS QA", "url": "https://ats.test/job"}]
            }), encoding="utf-8")
            result = sync(str(config), str(output), str(db_file),
                          loader=lambda _: [HEAD, R1, R2, R3], now=AT_7)
            self.assertEqual(result["source_mode"], "google_sheet_only")
            self.assertEqual(result["database"], "SQLite")
            self.assertEqual(result["snapshot_id"], 1)
            self.assertEqual(len(result["jobs"]), 3)
            self.assertEqual(result["source_records_read"], 3)
            self.assertNotIn("lever:old", {j["source"] for j in result["jobs"]})
            self.assertEqual([j["title"] for j in result["jobs"]],
                             ["Senior QA Engineer", "Data Analyst", "Manual Tester"])
            self.assertTrue(db_file.exists())
            with sqlite3.connect(db_file) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM snapshots").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT count(*) FROM observations").fetchone()[0], 3)
                self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE current=1").fetchone()[0], 3)
            self.assertNotIn("lever:old", output.read_text(encoding="utf-8"))
            self.assertEqual(result["jobs"][0]["salary_text"], "18 - 24 triệu")

    def test_new_day_drops_old_jobs_from_website_but_retains_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, out, db_path = root/"cfg.json", root/"jobs.json", root/"history.sqlite3"
            cfg.write_text(json.dumps({"spreadsheet_id": SHEET_ID}))
            first = sync(str(cfg), str(out), str(db_path), loader=lambda _: [HEAD, R1, R2, R3], now=AT_7)
            newer = [HEAD, [*R1[:3], "20 - 25 triệu", *R1[4:]], R3]
            second = sync(str(cfg), str(out), str(db_path), loader=lambda _: newer, now=AT_NEXT)
            self.assertEqual(len(second["jobs"]), 2)
            self.assertEqual([j["source"] for j in second["jobs"]], ["TopCV", "ITviec"])
            self.assertEqual(second["jobs"][0]["salary_text"], "20 - 25 triệu")
            self.assertEqual(second["jobs"][0]["first_seen"], first["jobs"][0]["first_seen"])
            self.assertEqual(second["capture_reference_at"], "2026-11-20T06:00:00+07:00")
            self.assertEqual(second["jobs"][0]["posted_at"], "2026-11-18T06:00:00+07:00")
            with sqlite3.connect(db_path) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 2)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 5)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 3)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs WHERE current=1").fetchone()[0], 2)
            self.assertNotIn("Upwork", out.read_text(encoding="utf-8"))

    def test_invalid_or_inaccessible_sheet_does_not_erase_db_or_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, out, db_path = root/"cfg.json", root/"jobs.json", root/"db.sqlite3"
            cfg.write_text(json.dumps({"spreadsheet_id": SHEET_ID}))
            sync(str(cfg), str(out), str(db_path), loader=lambda _: [HEAD, R1], now=AT_7)
            current_json, current_db = out.read_bytes(), db_path.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "no valid job"):
                sync(str(cfg), str(out), str(db_path), loader=lambda _: [HEAD, ["", "", ""]], now=AT_NEXT)
            self.assertEqual(out.read_bytes(), current_json)
            self.assertEqual(db_path.read_bytes(), current_db)
            def broken(_):
                raise RuntimeError("HTTP 401")
            with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
                sync(str(cfg), str(out), str(db_path), loader=broken, now=AT_NEXT)
            self.assertEqual(out.read_bytes(), current_json)

    def test_duplicate_urls_are_one_live_job_but_all_observations_retained(self):
        altered = R1.copy()
        altered[3] = "25 triệu"
        altered[-1] = "https://www.topcv.vn/viec-lam/qa/123?utm_campaign=owner"
        jobs, observations, meta = build_rows([HEAD, R1, altered], now=AT_7)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["salary_text"], "25 triệu")
        self.assertEqual(meta["valid_rows"], 2)
        self.assertEqual(len(observations), 2)


if __name__ == "__main__":
    unittest.main()
