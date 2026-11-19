import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tracker.google_sheet_sync import (
    SOURCE, extract_jobs, find_headers, format_date, norm, safe_job_url,
    safe_salary, safe_salary_text, source_from_link, sync, validate_config, fetch_public_rows,
)

SPREADSHEET_ID = "1vl0slYeHVb_yshR2AhczcVppCtBXRCJCty8rXYvkMGA"
ROWS = [
    ["STT", "Tên công ty", "Vị trí tuyển dụng", "Địa điểm làm việc",
     "Link JD", "Kỹ năng", "Ngày đăng", "Hạn ứng tuyển", "Trạng thái"],
    ["1", "Acme", "Automation QA Tester", "Hà Nội",
     "https://acme.example/jobs/qa-01?utm_source=sheets", "Playwright, Python",
     "18/11/2026", "30/11/2026", "Đang tuyển"],
    ["2", "Acme", "Automation QA Tester", "Hà Nội",
     "https://acme.example/jobs/qa-01?utm_source=new", "Playwright",
     "18/11/2026", "30/11/2026", "Đang tuyển"],
    ["3", "Beta", "Manual Tester", "TP.HCM",
     "https://beta.example/jobs/qa-02", "Postman, SQL",
     "2026-11-19", "", "Đang tuyển"],
    ["4", "Gamma", "Marketing Specialist", "Da Nang",
     "https://gamma.example/jobs/marketing", "", "", "", ""],
    ["5", "Delta", "QA Engineer", "Hanoi",
     "javascript:alert(1)", "", "", "", ""],
    ["6", "Old", "QC Tester", "Hanoi",
     "https://old.example/jobs/123", "", "", "", "Đã đóng"],
]


class GoogleSheetSyncTests(unittest.TestCase):
    def test_header_normalization_and_detection(self):
        self.assertEqual(norm("Địa điểm làm việc"), "dia diem lam viec")
        idx, mapping = find_headers(ROWS)
        self.assertEqual(idx, 0)
        self.assertEqual(mapping["title"], 2)
        self.assertEqual(mapping["url"], 4)

    def test_export_filters_invalid_closed_and_unrelated_jobs(self):
        jobs, counts = extract_jobs(ROWS)
        self.assertEqual(counts["sheet_rows"], 6)
        self.assertEqual(counts["valid_link_rows"], 4)
        self.assertEqual(counts["qa_title_rows"], 3)
        self.assertEqual(counts["distinct_qa_jobs"], 2)
        self.assertEqual({j["source"] for j in jobs}, {"acme.example", "beta.example"})
        self.assertEqual(jobs[0]["posted_at"], "2026-11-18")
        self.assertEqual(jobs[0]["application_deadline"], "2026-11-30")
        self.assertNotIn("utm_source", jobs[0]["url"])

    def test_dates_salary_and_urls(self):
        self.assertEqual(format_date("31/12/2026"), "2026-12-31")
        self.assertIsNone(format_date("tomorrow"))
        self.assertIsNone(safe_job_url("javascript:alert(1)"))
        self.assertEqual(
            safe_salary({"salary_min": "2000", "salary_max": "3000",
                         "salary_currency": "USD", "salary_period": "month"}),
            {"min": 2000, "max": 3000, "currency": "USD", "period": "month"})
        self.assertIsNone(safe_salary({"salary_min": "15 triệu", "salary_currency": "VND"}))

    def test_real_sheet_headers_salary_source_skill_fields(self):
        real = [
            ["Nguồn", "Vị trí", "Công ty", "Lương / Budget", "Địa điểm",
             "Kinh nghiệm / Level", "Skill yêu cầu (cho CV)",
             "Ngày đăng (tính từ 19/11/2026)", "Link"],
            ["TopCV", "QA Tester", "ACME", "18 - 24 triệu", "Hà Nội",
             "2 năm", "Playwright, Postman", "2 ngày trước",
             "https://www.topcv.vn/viec-lam/tester/234.html"],
            ["ITviec", "Automation Tester", "Example", "Thoả thuận", "TP.HCM",
             "Senior", "Selenium", "Hôm nay",
             "https://itviec.com/it-jobs/tester-12345"],
            ["Upwork", "QA Automation Engineer", "RemoteCo", "15–20 USD/giờ",
             "Remote", "Mid", "Python", "2026-11-19",
             "https://www.upwork.com/jobs/~01abcdef"],
        ]
        _, fields = find_headers(real)
        self.assertEqual(fields["salary_text"], 3)
        self.assertEqual(fields["skills"], 6)
        jobs, stats = extract_jobs(real)
        self.assertEqual(stats["distinct_qa_jobs"], 3)
        self.assertEqual({j["source"] for j in jobs}, {"TopCV", "ITviec", "Upwork"})
        self.assertEqual([j["salary_text"] for j in jobs],
                         ["18 - 24 triệu", "Thoả thuận", "15–20 USD/giờ"])
        self.assertIn("Playwright", jobs[0]["description"])
        self.assertIsNone(jobs[0]["posted_at"])  # relative dates must not be invented

    def test_migrate_existing_generic_sheet_source_without_duplication(self):
        import hashlib
        rows = [
            ["Vị trí", "Công ty", "Lương / Budget", "Link"],
            ["QA Engineer", "Acme", "20 - 30 triệu",
             "https://www.topcv.vn/viec-lam/qa/123.html"]
        ]
        with tempfile.TemporaryDirectory() as d:
            config, output = Path(d)/"sheet.json", Path(d)/"jobs.json"
            config.write_text(json.dumps({"spreadsheet_id": SPREADSHEET_ID}))
            source_id = hashlib.sha256(rows[1][3].encode()).hexdigest()[:24]
            old_time = "2026-11-18T00:00:00+00:00"
            output.write_text(json.dumps({"jobs":[{
                "source": SOURCE, "source_id": source_id, "title": "QA Engineer",
                "company": "Acme", "url": rows[1][3], "first_seen":old_time,
                "last_seen":old_time, "status":"observed"}]}))
            result = sync(str(config), str(output), loader=lambda _: rows)
            self.assertEqual(len(result["jobs"]), 1)
            self.assertEqual(result["jobs"][0]["source"], "TopCV")
            self.assertEqual(result["jobs"][0]["salary_text"], "20 - 30 triệu")
            self.assertEqual(result["jobs"][0]["first_seen"], old_time)
            self.assertEqual(result["jobs"][0]["ingested_from"], "google_sheet")

    def test_source_names_and_salary_are_safe(self):
        self.assertEqual(source_from_link("https://www.topcv.vn/viec-lam/123"), "TopCV")
        self.assertEqual(source_from_link("https://itviec.com/it-jobs/abc"), "ITviec")
        self.assertEqual(source_from_link("https://www.upwork.com/jobs/123"), "Upwork")
        self.assertEqual(safe_salary_text("Thoả thuận"), "Thoả thuận")
        self.assertIsNone(safe_salary_text("  "))

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            validate_config({"spreadsheet_id": "bad"})
        with self.assertRaises(ValueError):
            validate_config({"spreadsheet_id": SPREADSHEET_ID, "gid": -1})

    def test_sync_keeps_existing_ats_jobs_and_does_not_publish_full_jd(self):
        with tempfile.TemporaryDirectory() as d:
            config, output = Path(d)/"sheet.json", Path(d)/"jobs.json"
            config.write_text(json.dumps({"spreadsheet_id": SPREADSHEET_ID}))
            old = {
                "jobs": [{"source": "lever:BTSE", "source_id": "old",
                          "title": "QA Engineer", "company": "Existing",
                          "location": "Ho Chi Minh", "url": "https://existing.example/jobs/old",
                          "last_seen": "2026-11-18T00:00:00+00:00",
                          "first_seen": "2026-11-18T00:00:00+00:00",
                          "status": "observed"}]
            }
            output.write_text(json.dumps(old))
            result = sync(str(config), str(output), loader=lambda _: ROWS)
            self.assertEqual(len(result["jobs"]), 3)
            self.assertEqual(result["google_sheet_sync"]["distinct_qa_jobs"], 2)
            self.assertEqual(len([j for j in result["jobs"] if j.get("ingested_from") == "google_sheet"]), 2)
            self.assertIn("lever:BTSE", {j["source"] for j in result["jobs"]})
            self.assertNotIn("description", output.read_text())
            self.assertIn("Playwright", next(j for j in result["jobs"]
                                             if j["title"] == "Automation QA Tester")["skills"])

    def test_empty_sheet_does_not_change_old_json(self):
        with tempfile.TemporaryDirectory() as d:
            config, output = Path(d)/"sheet.json", Path(d)/"jobs.json"
            config.write_text(json.dumps({"spreadsheet_id": SPREADSHEET_ID}))
            original = '{"jobs":[{"source":"old","source_id":"x"}]}'
            output.write_text(original)
            with self.assertRaises(RuntimeError):
                sync(str(config), str(output), loader=lambda _: [])
            self.assertEqual(output.read_text(), original)

    def test_csv_reader_on_public_sheet(self):
        class Response:
            status = 200
            headers = {"Content-Type": "text/csv"}
            def read(self, n):
                return "Vị trí,Link JD\nQA Engineer,https://acme.example/job\n".encode()
            def __enter__(self): return self
            def __exit__(self, *args): return None
        with patch("tracker.google_sheet_sync.urlopen", return_value=Response()) as opener:
            result = fetch_public_rows({"spreadsheet_id": SPREADSHEET_ID})
        self.assertEqual(result[1][0], "QA Engineer")
        self.assertIn("format=csv", opener.call_args[0][0].full_url)

    def test_sheet_without_title_url_headers_fails_safe(self):
        with self.assertRaises(ValueError):
            extract_jobs([["Name", "Phone"], ["Alice", "0123456789"]])


if __name__ == "__main__":
    unittest.main()
