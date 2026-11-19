import unittest
from urllib.parse import parse_qs, urlsplit

from tracker.techjobs_probe import (
    FEED_PATH, feed_url, probe, fetch_page,
)


class TechJobsProbeTests(unittest.TestCase):
    def test_feed_url_is_scoped_and_quoted(self):
        url = feed_url("kiểm thử", 1, 200)
        self.assertEqual(urlsplit(url).path, FEED_PATH)
        self.assertEqual(parse_qs(urlsplit(url).query)["q"], ["kiểm thử"])
        for bad in ("../jobs", "https://evil.test/", ""):
            with self.subTest(keyword=bad), self.assertRaises(ValueError):
                feed_url(bad, 1, 200)
        with self.assertRaises(ValueError):
            feed_url("qa", 4, 200)

    def test_unique_counts_across_terms_and_pages(self):
        responses = {
            ("qa", 1): {
                "total": 3, "pages": 2, "next": "page2",
                "jobs": [
                    {"id": 1, "title": "QA Engineer", "company": "Acme"},
                    {"id": 2, "title": "Marketing", "company": "Acme"},
                ],
            },
            ("qa", 2): {
                "total": 3, "pages": 2, "next": None,
                "jobs": [{"id": 3, "title": "Kiểm thử phần mềm", "company": "Beta"}],
            },
            ("tester", 1): {
                "total": 2, "pages": 1, "next": None,
                "jobs": [
                    {"id": 1, "title": "QA Engineer", "company": "Acme"},
                    {"id": 4, "title": "Software Tester", "company": "Gamma"},
                ],
            },
        }
        waits = []
        def fake_fetch(url):
            p = parse_qs(urlsplit(url).query)
            return responses[(p["q"][0], int(p["page"][0]))]

        result = probe(fetch=fake_fetch, sleep=waits.append,
                       keywords=("qa", "tester"), max_pages=2)
        self.assertEqual(result["http_requests"], 3)
        self.assertEqual(result["unique_jobs_sampled_across_keywords"], 4)
        self.assertEqual(result["unique_qa_qc_title_matches_across_keywords"], 3)
        self.assertEqual(result["unique_companies_with_qa_qc_titles"], 3)
        self.assertFalse(result["published_to_dashboard"])
        self.assertEqual(waits, [2.0, 2.0])
        self.assertEqual(result["searches"][0]["qa_qc_title_matches_in_query"], 2)
        self.assertFalse(result["searches"][0]["truncated_by_probe_limit"])

    def test_probing_does_not_invent_complete_coverage(self):
        result = probe(
            fetch=lambda url: {
                "total": 2500, "pages": 13, "next": "/feeds/jobs.json?page=2",
                "jobs": [{"id": 1, "title": "Senior SDET", "company": "VietCo"}],
            },
            sleep=lambda x: None, keywords=("sdet",), max_pages=1)
        self.assertTrue(result["searches"][0]["truncated_by_probe_limit"])
        self.assertEqual(result["unique_qa_qc_title_matches_across_keywords"], 1)

    def test_probe_respects_limits(self):
        with self.assertRaises(ValueError):
            probe(max_pages=4)
        with self.assertRaises(ValueError):
            probe(delay_seconds=0.5)
        with self.assertRaises(ValueError):
            probe(per_page=501)

    def test_unsafe_feed_host_rejected_before_network(self):
        with self.assertRaises(ValueError):
            fetch_page("https://example.com/feeds/jobs.json")


if __name__ == "__main__":
    unittest.main()
