import json
import tempfile
import unittest
from pathlib import Path

from tracker.browser_crawler import collect_browser
from tracker.browser_daily import run

SEARCH = "https://itviec.com/it-jobs?query=tester"
DETAIL = "https://itviec.com/it-jobs/senior-qa-tester-12345"
SEARCH_HTML = '<html><a href="/it-jobs/senior-qa-tester-12345">QA</a></html>'
DETAIL_HTML = """<html><head>
<script type="application/ld+json">
{"@type":"JobPosting","title":"QA Automation Tester",
"hiringOrganization":{"name":"Acme Vietnam"},
"jobLocation":{"address":{"addressLocality":"Ho Chi Minh","addressCountry":"VN"}},
"description":"Selenium and Playwright",
"datePosted":"2026-11-19"}
</script></head><body><h1>QA Automation Tester</h1></body></html>"""

class FakeResponse:
    status = 200

class FakePage:
    def __init__(self):
        self.url = ""
        self.opened = []
        self.waits = []
    def goto(self, url, **kwargs):
        self.url = url
        self.opened.append(url)
        return FakeResponse()
    def wait_for_timeout(self, duration):
        self.waits.append(duration)
    def content(self):
        return SEARCH_HTML if "?query=tester" in self.url else DETAIL_HTML
    def close(self):
        pass

class FakeBrowser:
    def __init__(self):
        self.page = FakePage()
    def new_page(self):
        return self.page
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass

class BrowserScanTests(unittest.TestCase):
    def board(self):
        return dict(provider="itviec", board="licensed-search",
                    enabled=True, permission_confirmed=True, browser_enabled=True,
                    search_urls=[SEARCH], max_job_details=5, delay_seconds=2)

    def test_collects_rendered_links_and_job_json_ld(self):
        browser=FakeBrowser()
        result=collect_browser(self.board(), browser_factory=lambda:browser,
                               check_robots=lambda *args:True,
                               sleep=lambda n:None)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["source"],"itviec:licensed-search")
        self.assertIn("Playwright",result[0]["description"])
        self.assertEqual(result[0]["posted_at"],"2026-11-19")
        self.assertEqual(browser.page.opened,[SEARCH,DETAIL])

    def test_robot_denial_does_not_launch_browser(self):
        with self.assertRaisesRegex(RuntimeError,"robots"):
            collect_browser(self.board(),
                            browser_factory=lambda:self.fail("browser should not launch"),
                            check_robots=lambda *args:False)

    def test_no_permission_does_not_launch_browser(self):
        bad=self.board()
        bad["permission_confirmed"]=False
        with self.assertRaises(ValueError):
            collect_browser(bad, browser_factory=lambda:self.fail("no browser"))

    def test_daily_preserves_existing_dataset_if_source_fails(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=Path(d)/"boards.json"
            out=Path(d)/"jobs.json"
            cfg.write_text(json.dumps([self.board()]))
            previous={"jobs":[{"source":"lever:BTSE","source_id":"old","title":"QA Engineer",
                     "company":"Old","location":"Hanoi","last_seen":"2026-11-18"}]}
            out.write_text(json.dumps(previous))
            before=out.read_bytes()
            def broken(board):
                raise RuntimeError("HTTP 403; no bypass")
            with self.assertRaisesRegex(RuntimeError,"HTTP 403"):
                run(str(cfg),str(out),fetch=broken)
            self.assertEqual(out.read_bytes(),before)

    def test_daily_writes_only_after_success(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=Path(d)/"boards.json"
            out=Path(d)/"jobs.json"
            cfg.write_text(json.dumps([self.board()]))
            job={"source":"itviec:licensed-search","source_id":"abc","title":"QA Tester",
                 "company":"Acme","location":"Hanoi","description":"Playwright"}
            result=run(str(cfg),str(out),fetch=lambda b:[job])
            self.assertEqual(len(result["jobs"]),1)
            self.assertEqual(result["jobs"][0]["market_region"],"Vietnam")
            self.assertNotIn("description",result["jobs"][0])

if __name__=="__main__":
    unittest.main()
