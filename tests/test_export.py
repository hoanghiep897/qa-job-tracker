import unittest
from tracker.export import build_dataset, relevant, market_region

class ExportTests(unittest.TestCase):
    def test_market_region_never_assumes_southeast_asia_is_vietnam(self):
        self.assertEqual(market_region("Ho Chi Minh, Vietnam"), "Vietnam")
        self.assertEqual(market_region("Hanoi"), "Vietnam")
        self.assertEqual(market_region("Southeast Asia"), "Southeast Asia")
        self.assertEqual(market_region("Remote"), "Remote / unspecified")
        self.assertEqual(market_region("Hong Kong"), "Other / unspecified")

    def test_filter(self):
        self.assertTrue(relevant("Senior SDET"))
        self.assertTrue(relevant("QA Automation Engineer"))
        self.assertFalse(relevant("Account Executive"))
        self.assertFalse(relevant("Marketing"))
    def test_extract_and_preserve_first_seen(self):
        boards = [{"provider":"greenhouse","board":"example","enabled":True}]
        item = dict(source="greenhouse:example",source_id="123",title="QA Automation Engineer",
                    company="Example",location="Hanoi",url="https://example.com/jobs/123",
                    description="Playwright, TypeScript")
        initial = build_dataset(boards, fetch=lambda b:[item], observed_at="2026-11-18T00:00:00+00:00")
        later = build_dataset(boards, previous=initial, fetch=lambda b:[item], observed_at="2026-11-19T00:00:00+00:00")
        self.assertEqual(len(later["jobs"]),1)
        self.assertEqual(later["jobs"][0]["first_seen"],"2026-11-18T00:00:00+00:00")
        self.assertIn("Playwright",later["jobs"][0]["skills"])
        self.assertNotIn("description",later["jobs"][0])
        self.assertEqual(later["jobs"][0]["market_region"], "Vietnam")
    def test_dont_destroy_last_dataset_on_failure(self):
        boards = [{"provider":"ashby","board":"example","enabled":True}]
        def fail(b): raise ConnectionError("unavailable")
        with self.assertRaises(RuntimeError):
            build_dataset(boards,fetch=fail)
    def test_disabled_sources_not_fetched(self):
        boards = [{"provider":"ashby","board":"example","enabled":False}]
        with self.assertRaises(RuntimeError):
            build_dataset(boards,fetch=lambda b:self.fail("should not fetch"))

if __name__ == "__main__":
    unittest.main()
