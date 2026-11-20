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

    def test_posting_labels_and_experience_are_rendered(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("<th>Kinh nghiệm / Level</th>", html)
        self.assertIn("if(!job.posted_at)return job.posted_text", html)
        self.assertIn('j.experience_text||(j.ingested_from==="google_sheet"?"Chưa có trong Sheet":"Không công bố")', html)
        self.assertIn('ingested_from:String(j.ingested_from||"")', html)
        self.assertIn('posted_text:String(j.posted_text||"")', html)
        self.assertIn('experience_text:String(j.experience_text||"")', html)
        self.assertIn('"experience_text","salary_text","posted_at","posted_text","skills_text"', html)

    def test_relative_dates_render_estimated_ict_timestamps(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('job.posted_at_kind==="estimated_from_sheet_0600"', html)
        self.assertIn('timeZone:"Asia/Ho_Chi_Minh"', html)
        self.assertIn('return fmt.format(dt)+" (ước tính)"', html)
        self.assertIn('posted_reference_at:String(j.posted_reference_at||"")', html)
        self.assertIn('j.experience_text||(j.ingested_from==="google_sheet"?"Chưa có trong Sheet":"Không công bố")', html)


    def test_jd_explorer_fits_wider_desktop_without_hidden_columns(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("main{width:100%;max-width:1800px;", html)
        self.assertIn('<section class="card section jd-explorer">', html)
        self.assertIn(".jd-explorer table{width:100%;table-layout:fixed}", html)
        self.assertIn("@media(max-width:1279px){.jd-explorer table{table-layout:auto;min-width:1080px}", html)
        # Percent widths for all ten columns must sum to 100%.
        import re
        widths = {int(n): int(p) for n, p in
                  re.findall(r"\.jd-explorer th:nth-child\((\d+)\)\{width:(\d+)%\}", html)}
        self.assertEqual(set(widths), set(range(1, 11)))
        self.assertEqual(sum(widths.values()), 100)
        self.assertIn("<th>Link JD</th>", html)
        self.assertIn("<th>Nguồn</th>", html)

    def test_application_deadline_is_not_rendered(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("<th>Hạn ứng tuyển</th>", html)
        self.assertNotIn("formatDate(j.application_deadline)", html)
        self.assertNotIn("application_deadline:j.application_deadline", html)
        self.assertIn(">Ngày đăng</th><th>Kỹ năng</th>", html)
        self.assertIn("cell.colSpan=10", html)

    def test_interactive_role_skill_filters_are_wired(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="chartFilterStatus"', html)
        self.assertIn('id="clearChartFilters"', html)
        self.assertIn('function toggleRole(name)', html)
        self.assertIn('function toggleSkill(name)', html)
        self.assertIn('ignoreRole=false,ignoreSkill=false', html)
        self.assertIn('j.skills.includes(selectedSkill)', html)
        self.assertIn('selectedJobs({ignoreRole:true})', html)
        self.assertIn('selectedJobs({ignoreSkill:true})', html)
        self.assertIn('content.setAttribute("aria-pressed"', html)
        self.assertIn('content.addEventListener("click",()=>onSelect(name))', html)
        self.assertIn('selectedSkill="";$("#role").value="";render()', html)
        self.assertIn('cell.colSpan=10', html)
        self.assertNotIn('id="reset"', html)
        self.assertNotIn('Dữ liệu demo</button>', html)

    def test_chart_filters_click_combine_toggle_and_clear(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        parser = ScriptParser()
        parser.feed(html)
        script = "\n".join(parser.script)
        marker = '\npopulate();render();$("#dataStatus").textContent="Đang tải dữ liệu Google Sheet…";\nasync function loadPublishedJobs()'
        self.assertIn(marker, script)
        script = script.split(marker, 1)[0]
        harness = r"""
const vm = require("node:vm");
class FakeElement {
  constructor(tag="div"){
    this.tagName=tag;this.children=[];this.dataset={};this.style={};
    this.listeners={};this.attributes={};this.value="";this.textContent="";
  }
  append(...children){this.children.push(...children)}
  replaceChildren(...children){this.children=[...children]}
  addEventListener(event,cb){this.listeners[event]=cb}
  setAttribute(key,value){this.attributes[key]=value}
  focus(){}
  blur(){}
}
const nodes={};
const get=(selector)=>nodes[selector]||(nodes[selector]=new FakeElement());
function findButtons(node){
  if(!node)return [];
  return [node,...node.children.flatMap(findButtons)].filter(x=>x.className==="bar-choice");
}
const document={
  querySelector:get,
  createElement:(tag)=>new FakeElement(tag),
  querySelectorAll:(selector)=>findButtons(get(selector.split(" ")[0]))
};
const ctx=vm.createContext({document,Date,Intl,Option:class{},console,URL,Blob});
vm.runInContext(process.argv[1],ctx);
const demoActions = [
 'all=[',
 ' {title:"Manual QA Tester",role:"Manual QA",company:"A",location:"Hà Nội",market_region:"Vietnam",skills:["Postman","SQL"],source:"TopCV",url:""},',
 ' {title:"Automation QA",role:"Automation QA",company:"B",location:"Hà Nội",market_region:"Vietnam",skills:["Playwright","SQL"],source:"ITviec",url:""},',
 ' {title:"SDET",role:"SDET",company:"C",location:"Remote",market_region:"Remote / unspecified",skills:["Playwright"],source:"Upwork",url:""}',
 '];selectedSkill="";$("#role").value="";$("#location").value="";$("#region").value="";$("#age").value="0";render();',
 'const chartButton=(id,name)=>Array.from(document.querySelectorAll(id+" .bar-choice")).find(b=>b.dataset.filterValue===name);',
 'if(!chartButton("#skills","Playwright"))throw Error("No clickable skill");',
 'chartButton("#skills","Playwright").listeners.click();',
 'if(selectedJobs().length!==2||selectedSkill!=="Playwright")throw Error("Skill click failed");',
 'if($("#chartFilterStatus").hidden)throw Error("Filter summary hidden");',
 'if(!chartButton("#roles","SDET"))throw Error("No clickable role");',
 'chartButton("#roles","SDET").listeners.click();',
 'if(selectedJobs().length!==1||$("#role").value!=="SDET")throw Error("Role intersection failed");',
 'if(chartButton("#roles","SDET").attributes["aria-pressed"]!=="true")throw Error("Selected role not accessible");',
 'if($("#records").children.length!==1)throw Error("JD Explorer not filtered");',
 'chartButton("#roles","SDET").listeners.click();',
 'if(selectedJobs().length!==2||$("#role").value!=="")throw Error("Role toggle failed");',
 'chartButton("#skills","Playwright").listeners.click();',
 'if(selectedJobs().length!==3||selectedSkill!=="")throw Error("Skill toggle failed");',
 'chartButton("#skills","SQL").listeners.click();',
 '$("#role").value="SDET";render();',
 'if(selectedJobs().length!==0)throw Error("Expected empty skill/role intersection");',
 'if($("#records").children.length!==1||$("#records").children[0].children[0].colSpan!==10)throw Error("No empty-table state");',
 '$("#clearChartFilters").listeners.click();',
 'if(selectedJobs().length!==3||selectedSkill!==""||$("#role").value!=="")throw Error("Clear button failed");'
].join("\n");
vm.runInContext(demoActions,ctx);
"""
        result = subprocess.run(["node", "-e", harness, script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_public_dashboard_has_only_google_sheet_input(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('id="csv"', html)
        self.assertNotIn('DEMO DATA:', html)
        self.assertNotIn('const demo=', html)
        self.assertNotIn('id="reset"', html)
        self.assertIn('payload.source_mode!=="google_sheet_only"', html)
        self.assertIn('j.skills_text||j.skills.join(", ")', html)
        self.assertIn('Lịch sử SQLite', html)
        self.assertIn('id="export"', html)

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
