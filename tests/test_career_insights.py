"""Regression tests for experience-based, Sheet-grounded career insights."""
import html.parser
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ScriptExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.on = False
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.on = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.on = False

    def handle_data(self, text):
        if self.on:
            self.chunks.append(text)


class CareerInsightsTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_all_four_features_are_present(self):
        for item in ('id="experience"', 'id="compareA"', 'id="compareB"',
                     'id="compareRows"', 'id="targetExperience"',
                     'id="gapList"', 'id="gapSummary"', 'id="roadmap"'):
            with self.subTest(element=item):
                self.assertIn(item, self.html)
        for marker in ("function experienceGroup(raw)",
                       "function skillLabelsFromSheet(job)",
                       "function renderComparison()",
                       "function renderSkillGapAndRoadmap()",
                       "localStorage.setItem",
                       "ignoreExperience=false",
                       'payload.source_mode!=="google_sheet_only"'):
            self.assertIn(marker, self.html)
        self.assertNotIn('DEMO DATA:', self.html)
        self.assertNotIn('id="csv"', self.html)

    def test_real_js_experience_comparison_gap_roadmap(self):
        extractor = ScriptExtractor()
        extractor.feed(self.html)
        script = "\n".join(extractor.chunks)
        marker = '\npopulate();render();$("#dataStatus").textContent="Đang tải dữ liệu Google Sheet…";\nasync function loadPublishedJobs()'
        self.assertIn(marker, script)
        script = script.split(marker, 1)[0]
        harness = r"""
const vm=require("node:vm");
class FakeElement {
 constructor(tag="div"){
  this.tagName=tag;this.children=[];this.dataset={};this.style={};
  this.listeners={};this.attributes={};this.value="";this.textContent="";
 }
 append(...items){this.children.push(...items)}
 replaceChildren(...items){this.children=[...items]}
 addEventListener(event,callback){this.listeners[event]=callback}
 setAttribute(name,value){this.attributes[name]=value}
 focus(){}
 blur(){}
}
const nodes={};const get=key=>nodes[key]||(nodes[key]=new FakeElement());
const findButtons=node=>(!node?[]:[node,...node.children.flatMap(findButtons)]).filter(x=>x.className==="bar-choice");
const document={
 querySelector:get,
 querySelectorAll:sel=>findButtons(get(sel.split(" ")[0])),
 createElement:tag=>new FakeElement(tag)
};
const stored={};
const localStorage={
 getItem:key=>stored[key]||null,
 setItem:(key,value)=>{stored[key]=value}
};
const ctx=vm.createContext({document,localStorage,Date,Intl,Option:class{},console,Blob,URL});
vm.runInContext(process.argv[1],ctx);
const execute=[
 'function assert(ok,msg){if(!ok)throw Error(msg);}',
 'assert(experienceGroup("3 năm")==="3","Three years");',
 'assert(experienceGroup("6 năm")==="6","Six years");',
 'assert(experienceGroup("Trên 5 năm")==="over5","Over-five is not six");',
 'assert(experienceGroup("Entry Level")==="entry","Entry is not years");',
 'assert(experienceGroup("Intermediate")==="intermediate","Intermediate is not years");',
 'assert(experienceGroup("Expert")==="expert","Expert is not years");',
 'assert(experienceGroup("3-5 năm")==="other","No guessing from range");',
 'assert(experienceGroup("")==="unknown","Unknown stays unknown");',
 'assert(JSON.stringify(skillLabelsFromSheet({skills_text:"Playwright, SQL/Database, Playwright, Postman",skills:["INVENTED"]}))===JSON.stringify(["Playwright","SQL/Database","Postman"]),"Raw skills only, no fabricated skill");',
 'const make=(exp,role,skills,company)=>({title:"QA",company,role,experience_text:exp,skills:skillLabelsFromSheet({skills_text:skills}),location:"Hà Nội",market_region:"Vietnam",source:"TopCV",url:"",first_seen:"2026-11-20T00:00:00+00:00"});',
 'all=[',
 'make("3 năm","Manual QA","Playwright, SQL/Database","A"),',
 'make("3 năm","Automation QA","SQL/Database, API test","B"),',
 'make("5 năm","Manual QA","Playwright, SQL/Database, API test","C"),',
 'make("5 năm","Automation QA","Playwright, CI/CD","D"),',
 'make("6 năm","Automation QA","Appium","E"),',
 'make("Trên 5 năm","Manual QA","Selenium","F"),',
 'make("Entry Level","Manual QA","Postman","G")',
 '];',
 '$("#role").value="";$("#location").value="";$("#region").value="";$("#age").value="0";',
 '$("#experience").value="3";render();assert(selectedJobs().length===2,"Filter 3-year jobs");',
 '$("#experience").value="4";render();assert(selectedJobs().length===0,"Empty 4 years");',
 '$("#experience").value="6";render();assert(selectedJobs().length===1&&selectedJobs()[0].company==="E","Only exact 6 years");',
 '$("#experience").value="over5";render();assert(selectedJobs().length===1&&selectedJobs()[0].company==="F","Over 5 years separate");',
 '$("#experience").value="entry";render();assert(selectedJobs().length===1&&selectedJobs()[0].company==="G","Entry separate");',
 '$("#experience").value="5";$("#compareA").value="3";$("#compareB").value="5";render();',
 'assert(selectedJobs().length===2,"Filter 5-year explorer");',
 'assert($("#compareSummary").textContent.includes("3 năm: 2 JD")&&$("#compareSummary").textContent.includes("5 năm: 2 JD"),"Compare independent from year filter");',
 'const table=$("#compareRows").children;',
 'const playwright=table.find(row=>row.children[0].textContent==="Playwright");',
 'assert(!!playwright,"Playwright in comparison");',
 'assert(playwright.children[1].textContent==="1/2 JD (50%)","Correct denominator A");',
 'assert(playwright.children[2].textContent==="2/2 JD (100%)","Correct denominator B");',
 'assert(playwright.children[3].textContent==="+50 điểm %","Compare percentage points");',
 '$("#compareB").value="6";renderCareerInsights();',
 'assert($("#compareSummary").textContent.includes("dưới 5 JD"),"Small sample warning");',
 '$("#compareB").value="3";renderCareerInsights();',
 'assert($("#compareRows").children[0].children[0].colSpan===4,"Same group cannot be compared");',
 '$("#compareB").value="5";$("#targetExperience").value="5";renderCareerInsights();',
 'assert($("#gapSummary").textContent.includes("5 năm: 2 JD"),"Target cohort visible");',
 'assert($("#gapList").children.length===4,"All 4 target skills shown");',
 'assert($("#roadmap").children.length>0,"Roadmap derived from target skills");',
 'const box=$("#gapList").children[0].children[0];',
 'assert(!box.checked,"Unchecked initial state");',
 'box.checked=true;box.listeners.change();',
 'assert(knownSkills.size===1,"Marked known skill");',
 'assert(JSON.parse(localStorage.getItem(KNOWN_SKILLS_KEY)).length===1,"Stored locally");',
 'assert($("#gapSummary").textContent.includes("1/4"),"Self-assessment updates");',
 'const names=$("#gapList").children.map(el=>el.children[1].textContent);',
 'assert(names.includes("Playwright"),"Raw skill names are shown");',
 '$("#targetExperience").value="4";renderSkillGapAndRoadmap();',
 'assert($("#gapSummary").textContent.includes("0 JD"),"No-data state");',
 'assert($("#roadmap").textContent.includes("Chưa có dữ liệu"),"No invented roadmap for missing sample");'
].join("\n");
vm.runInContext(execute,ctx);
"""
        result = subprocess.run(["node", "-e", harness, script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
