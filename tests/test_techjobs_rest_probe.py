import unittest
from urllib.parse import parse_qs, urlsplit

from tracker.techjobs_rest_probe import build_url, probe_rest, request_jobs


class TechJobsRestProbeTests(unittest.TestCase):
    def test_url_uses_anonymous_api_limits(self):
        url = build_url("kiểm thử")
        self.assertEqual(urlsplit(url).path, "/api/v1/jobs")
        q = parse_qs(urlsplit(url).query)
        self.assertEqual(q["q"], ["kiểm thử"])
        self.assertEqual(q["limit"], ["10"])
        self.assertEqual(q["page"], ["1"])
        with self.assertRaises(ValueError):
            build_url("nonexistent")

    def test_only_counts_and_deduplicates(self):
        waits = []
        def fetch(url):
            query = parse_qs(urlsplit(url).query)["q"][0]
            if query == "qa":
                return {"jobs": [
                    {"id": 8, "title": "Senior QA Engineer", "company": "A"},
                    {"id": 9, "title": "UX Designer", "company": "B"}],
                    "total": 93, "notice": "Only 10 results visible"}
            return {"jobs": [
                {"id": 8, "title": "Senior QA Engineer", "company": "A"},
                {"id": 10, "title": "Manual Tester", "company": "C"}],
                "total": 70}
        result = probe_rest(fetch=fetch, sleep=waits.append,
                            keywords=("qa", "tester"))
        self.assertEqual(result["unique_items_seen"], 3)
        self.assertEqual(result["unique_qa_qc_titles_seen"], 2)
        self.assertEqual(result["searches"][0]["api_reported_total"], 93)
        self.assertEqual(result["searches"][0]["notice"], "Only 10 results visible")
        self.assertFalse(result["published_to_dashboard"])
        self.assertEqual(waits, [2.0])

    def test_outside_endpoint_denied(self):
        with self.assertRaises(ValueError):
            request_jobs("https://evil.example/api/v1/jobs")


if __name__ == "__main__":
    unittest.main()
