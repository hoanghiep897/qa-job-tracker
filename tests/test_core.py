import tempfile
import unittest
from pathlib import Path
from tracker.core import connect, role, save_job, tags

class CoreTests(unittest.TestCase):
    def test_tags_are_case_insensitive_and_distinct(self):
        self.assertEqual(tags("Playwright + PLAYWRIGHT and TypeScript"), ["Playwright", "TypeScript"])
        self.assertNotIn("Java", tags("JavaScript"))
    def test_role(self):
        self.assertEqual(role("Senior SDET"), "SDET")
        self.assertEqual(role("QA Automation Engineer"), "Automation QA")
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
