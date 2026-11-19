"""Smoke-check the zero-cost static dashboard for Vercel deployment."""
import html.parser
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ScriptParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.script = []
        self.has_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.inside = True
        if tag == "title":
            self.has_title = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.script.append(data)

class StaticDashboardTests(unittest.TestCase):
    def test_source_label_links_to_original_job(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        # Both Nguồn and Link JD open the *same original* j.url safely.
        self.assertIn('sourceLink.href=j.url', html)
        self.assertIn('sourceLink.textContent=j.source||"Mở nguồn"', html)
        self.assertIn('sourceLink.target="_blank"', html)
        self.assertIn('sourceLink.rel="noopener noreferrer"', html)
        self.assertIn('link.href=j.url', html)
        self.assertIn('sourceTd.textContent=j.source||"—"', html)

    def test_html_and_javascript_syntax(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        parser = ScriptParser()
        parser.feed(html)
        self.assertTrue(parser.has_title)
        self.assertTrue(parser.script, "No dashboard script found")
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp) / "dashboard.js"
            filename.write_text("\n".join(parser.script), encoding="utf-8")
            result = subprocess.run(["node", "--check", str(filename)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == "__main__":
    unittest.main()
