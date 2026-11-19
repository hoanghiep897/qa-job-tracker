import unittest
from unittest.mock import patch
from tracker.licensed_html import (
    canonical_url, discover_links, parse_job, collect_licensed, schema_jobs,
    parse_page,
)

BASE = "https://www.topcv.vn/tim-viec-lam-tester"
TOPCV_JOB = "https://www.topcv.vn/viec-lam/automation-tester/2120933.html"
HTML_LIST = """
<html><a href="/viec-lam/automation-tester/2120933.html?utm_source=test">Apply</a>
<a href="https://evil.example/viec-lam/abc/1.html">Malicious link</a></html>
"""
HTML_JOB = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting",
"title":"Automation Tester (Playwright)","description":"<p>Test API with Playwright</p>",
"hiringOrganization":{"@type":"Organization","name":"Example Software"},
"jobLocation":{"@type":"Place","address":{"addressLocality":"Hà Nội","addressCountry":"VN"}},
"datePosted":"2026-11-15","validThrough":"2026-12-15",
"baseSalary":{"@type":"MonetaryAmount","currency":"VND",
"value":{"@type":"QuantitativeValue","minValue":18000000,"maxValue":30000000,"unitText":"MONTH"}}}
</script></head><body><h1>Automation Tester</h1></body></html>
"""

class LicensedHTMLTests(unittest.TestCase):
    def test_validate_urls(self):
        self.assertEqual(canonical_url(TOPCV_JOB+"?utm_source=test", "topcv"), TOPCV_JOB)
        for url in ["http://www.topcv.vn/viec-lam/a/1.html",
                    "https://another.com/viec-lam/a/1.html"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                canonical_url(url,"topcv")

    def test_discovery_and_dedupe(self):
        links = discover_links(HTML_LIST, BASE, "topcv")
        self.assertEqual(links,[TOPCV_JOB])

    def test_structured_data_extraction(self):
        job=parse_job(HTML_JOB,TOPCV_JOB,"topcv")
        self.assertEqual(job["title"], "Automation Tester (Playwright)")
        self.assertEqual(job["company"], "Example Software")
        self.assertIn("Hà Nội", job["location"])
        self.assertEqual(job["posted_at"], "2026-11-15")
        self.assertEqual(job["application_deadline"], "2026-12-15")
        self.assertEqual(job["salary"]["min"], 18000000)
        self.assertEqual(job["salary"]["currency"], "VND")
        self.assertNotIn("<p>",job["description"])

    def test_missing_schema_type_does_not_crash(self):
        page=parse_page('<script type="application/ld+json">{"@type":null}</script>')
        self.assertEqual(list(schema_jobs(page)), [])

    def test_disabled_or_unconfirmed_sources_rejected(self):
        config={"provider":"topcv","board":"licensed-search","enabled":True,
                "search_urls":[BASE]}
        with self.assertRaises(ValueError):
            collect_licensed(config, fetch=lambda *a,**k:HTML_LIST)
        config["permission_confirmed"]=True
        config["enabled"]=False
        with self.assertRaises(ValueError):
            collect_licensed(config,fetch=lambda *a,**k:HTML_LIST)

    def test_crawl_is_bounded(self):
        urls=[]
        def fake_fetch(url, *, platform):
            urls.append(url)
            return HTML_LIST if "tim-viec-lam" in url else HTML_JOB
        config={"provider":"topcv","board":"licensed-search","enabled":True,
                "permission_confirmed":True,"search_urls":[BASE],
                "max_job_details":1,"delay_seconds":1}
        found=collect_licensed(config,fetch=fake_fetch,
                check_robots=lambda url,platform:True, sleep=lambda n:None)
        self.assertEqual(len(found),1)
        self.assertEqual(len(urls),2)
        self.assertEqual(found[0]["salary"]["max"],30000000)

    def test_anti_bot_stops_source(self):
        def fetch(url, *, platform):
            return HTML_LIST if "tim-viec-lam" in url else (_ for _ in ()).throw(
                RuntimeError("Access verification or anti-bot page detected; stop collection"))
        config={"provider":"topcv","board":"licensed-search","enabled":True,
                "permission_confirmed":True,"search_urls":[BASE]}
        with self.assertRaises(RuntimeError):
            collect_licensed(config,fetch=fetch,
                check_robots=lambda url,platform:True,sleep=lambda n:None)

if __name__ == "__main__":
    unittest.main()
