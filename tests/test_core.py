import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from tracker.core import connect, role, save_job, tags, fetch_board

class CoreTests(unittest.TestCase):
    def test_tags_are_case_insensitive_and_distinct(self):
        self.assertEqual(tags("Playwright + PLAYWRIGHT and TypeScript"), ["Playwright", "TypeScript"])
        self.assertNotIn("Java", tags("JavaScript"))
    def test_role(self):
        self.assertEqual(role("Senior SDET"), "SDET")
        self.assertEqual(role("QA Automation Engineer"), "Automation QA")
    def test_lever_string_content(self):
        payload = [{
            "id": "lever-1", "text": "Senior QA Engineer",
            "hostedUrl": "https://jobs.lever.co/example/lever-1",
            "categories": {"location": "Vietnam"},
            "descriptionPlain": "Playwright",
            "lists": [{"text": "Requirements", "content": "Postman SQL"},
                      {"text": "More", "content": [{"text": "Selenium"}, "Docker"]}]
        }]
        with patch("tracker.core.request_json", return_value=payload):
            jobs = fetch_board({"provider": "lever", "board": "example", "company": "Example"})
        self.assertEqual(len(jobs), 1)
        self.assertIn("Postman SQL", jobs[0]["description"])
        self.assertIn("Selenium", jobs[0]["description"])


    def test_greenhouse_source_posted_date(self):
        payload = {"jobs": [{"id": 10, "title": "QA Engineer",
            "location": {"name": "Hanoi"}, "first_published": "2026-11-01T08:00:00Z",
            "absolute_url": "https://example.com/jobs/10"}]}
        with patch("tracker.core.request_json", return_value=payload):
            jobs = fetch_board({"provider": "greenhouse", "board": "example"})
        self.assertEqual(jobs[0]["posted_at"], "2026-11-01T08:00:00Z")
        self.assertIsNone(jobs[0]["salary"])
        self.assertIsNone(jobs[0]["application_deadline"])

    def test_ashby_public_compensation(self):
        payload = {"jobs": [{"id":"a1", "title":"SDET", "location":"Remote",
            "publishedAt":"2026-11-12T00:00:00Z",
            "compensation":{"summaryComponents":[{"compensationType":"Salary",
                "minValue":40000,"maxValue":60000,"currencyCode":"USD",
                "interval":"year"}]}}]}
        with patch("tracker.core.request_json", return_value=payload) as fn:
            jobs = fetch_board({"provider":"ashby","board":"example"})
        self.assertIn("includeCompensation=true", fn.call_args.args[0])
        self.assertEqual(jobs[0]["salary"]["max"], 60000)
        self.assertEqual(jobs[0]["posted_at_kind"],"last_published")

    def test_lever_does_not_treat_created_at_as_posted_at(self):
        with patch("tracker.core.request_json", return_value=[{
            "id":"x","text":"QA Engineer","createdAt":1730000000000}]):
            jobs = fetch_board({"provider":"lever","board":"example"})
        self.assertIsNone(jobs[0]["posted_at"])
        self.assertEqual(jobs[0]["source_created_at"],1730000000000)

    def test_upsert_preserves_first_seen(self):
        with tempfile.TemporaryDirectory() as temp:
            db = connect(str(Path(temp) / "jobs.db"))
            job = dict(source="csv", source_id="123", company="Acme",
                       title="Automation Tester", description="Playwright")
            save_job(db, job)
            first = db.execute("SELECT first_seen FROM jobs").fetchone()[0]
            job["description"] = "Selenium"
            save_job(db, job)
            record = db.execute("SELECT * FROM jobs").fetchone()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)
            self.assertEqual(record["first_seen"], first)
            self.assertEqual(record["skills_json"], '["Selenium"]')

if __name__ == "__main__":
    unittest.main()
