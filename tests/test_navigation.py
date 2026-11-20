"""Verify that users see a focused welcome view and can navigate all tools."""
import html.parser
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ScriptCollector(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.active = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_four_focused_views_and_beginner_first_default(self):
        html = self.html
        self.assertIn('role="tablist"', html)
        for section in ("overview", "explore", "compare", "roadmap"):
            with self.subTest(view=section):
                self.assertEqual(html.count('id="tab-' + section + '"'), 1)
                self.assertEqual(html.count('id="view-' + section + '"'), 1)
                self.assertIn('aria-controls="view-' + section + '"', html)
        self.assertIn('id="tab-overview" class="view-tab" role="tab" type="button" aria-controls="view-overview" aria-selected="true"', html)
        self.assertIn('id="view-overview" role="tabpanel" aria-labelledby="tab-overview">', html)
        for section in ("explore", "compare", "roadmap"):
            self.assertIn('id="view-' + section + '" role="tabpanel" aria-labelledby="tab-' + section + '" hidden>', html)
        self.assertLess(html.index('id="view-overview"'), html.index('id="view-explore"'))
        self.assertIn('id="welcomeExperience"', html)
        self.assertIn('id="welcomeSkills"', html)
        self.assertIn('id="welcomeJobs"', html)
        self.assertIn('data-start="compare"', html)
        self.assertIn('data-start="roadmap"', html)
        self.assertIn('class="advanced-filter"', html)
        self.assertIn('class="chart-details"', html)
        self.assertIn(".view-panel[hidden]{display:none!important}", html)
        self.assertIn('event.key==="ArrowRight"', html)
        self.assertIn('event.key==="Home"', html)
        self.assertIn('function showView(name)', html)
        self.assertIn('function openNextStep(name)', html)
        # Comparisons must not be influenced by filters hidden on Explore.
        self.assertIn('function comparisonBaseJobs(){return all}', html)
        self.assertIn('So sánh kỹ năng theo kinh nghiệm', html)
        self.assertIn('My Skill Gap', html)
        self.assertIn('id="records"', html)
        self.assertNotIn('id="csv"', html)

    def test_navigation_and_onboarding_actions_execute_in_javascript(self):
        collector = ScriptCollector()
        collector.feed(self.html)
        script = "\n".join(collector.parts)
        marker = '\npopulate();render();$("#dataStatus").textContent="Đang tải dữ liệu Google Sheet…";\nasync function loadPublishedJobs()'
        self.assertIn(marker, script)
        script = script.split(marker, 1)[0]
        harness = r"""
const vm = require("node:vm");
class Element {
 constructor(tag="div"){
  this.tagName=tag;this.children=[];this.dataset={};this.style={};
  this.listeners={};this.attributes={};this.value="";this.textContent="";
  this.hidden=false;this.focused=false;
 }
 append(...children){this.children.push(...children)}
 replaceChildren(...children){this.children=[...children]}
 addEventListener(name,fn){this.listeners[name]=fn}
 setAttribute(name,val){this.attributes[name]=val}
 focus(){this.focused=true}
 blur(){}
}
const nodes={};const el=id=>nodes[id]||(nodes[id]=new Element());
const tabs=["overview","explore","compare","roadmap"].map(id=>el("#tab-"+id));
const starters=["explore","explore","compare","roadmap"].map(name=>{
 const button=new Element("button");button.dataset.start=name;return button;
});
const findButtons=node=>(!node?[]:[node,...node.children.flatMap(findButtons)]).filter(x=>x.className==="bar-choice");
const document={
 querySelector:el,
 querySelectorAll:s=>s===".view-tab"?tabs:s==="[data-start]"?starters:
   findButtons(el(s.split(" ")[0])),
 createElement:t=>new Element(t)
};
const localStorage={getItem:()=>null,setItem:()=>{}};
const ctx=vm.createContext({document,Date,Intl,Option:class{},console,URL,Blob,localStorage});
vm.runInContext(process.argv[1],ctx);
const steps=[
 'function assert(cond,msg){if(!cond)throw Error(msg)};',
 'assert(activeView==="overview","Default welcome view");',
 'assert($("#view-explore").hidden&&$("#view-compare").hidden&&$("#view-roadmap").hidden,"Other panels initially hidden");',
 'assert($("#tab-overview").attributes["aria-selected"]==="true","Welcome tab active");',
 'all=[',
 ' {title:"QA",experience_text:"3 năm",skills:["API test"],role:"Manual QA",company:"A",source:"TopCV",location:"Hà Nội",market_region:"Vietnam",url:""},',
 ' {title:"QA",experience_text:"5 năm",skills:["SQL","Playwright"],role:"Manual QA",company:"B",source:"ITviec",location:"Hà Nội",market_region:"Vietnam",url:""},',
 ' {title:"QA",experience_text:"5 năm",skills:["SQL"],role:"Automation QA",company:"C",source:"TopCV",location:"Hà Nội",market_region:"Vietnam",url:""}',
 '];',
 '$("#role").value="";$("#location").value="";$("#region").value="";$("#age").value="0";$("#experience").value="";',
 '$("#welcomeExperience").value="5";render();',
 'assert($("#welcomeJobs").textContent===2,"Welcome cohort count");',
 'assert($("#welcomeSkills").children.length===2,"Short list of top skills");',
 'assert($("#welcomeSkills").children[0].textContent==="SQL · 2/2 JD","Top skill is sourced from JD");',
 'starters[0].listeners.click();',
 'assert(activeView==="explore"&&$("#experience").value==="5","Start from cohort into JD Explorer");',
 'assert(!$("#view-explore").hidden&&$("#view-overview").hidden,"One view at a time");',
 '$("#role").value="Manual QA";',
 '$("#welcomeExperience").value="3";',
 'starters[2].listeners.click();',
 'assert(activeView==="compare"&&$("#compareA").value==="5"&&$("#compareB").value==="3","Go from welcome to comparisons");',
 'assert(comparisonBaseJobs().length===3,"Hidden Explore role filters do not affect comparison");',
 'starters[3].listeners.click();',
 'assert(activeView==="roadmap"&&$("#targetExperience").value==="3","Learning target updated");',
 'tabs[1].listeners.click();',
 'assert(activeView==="explore"&&$("#tab-explore").attributes["aria-selected"]==="true","Tab click works");',
 'const event={key:"ArrowRight",preventDefault(){this.prevented=true}};',
 'tabs[1].listeners.keydown(event);',
 'assert(event.prevented&&activeView==="compare"&&tabs[2].focused,"Arrow navigates and focuses");',
 'tabs[2].listeners.keydown({key:"Home",preventDefault(){}});',
 'assert(activeView==="overview","Home returns to first tab");',
 '$("#welcomeExperience").value="6";renderWelcome();',
 'assert($("#welcomeJobs").textContent===0,"Empty cohort count");',
 'assert($("#welcomeSampleNote").textContent.includes("Chưa có JD"),"No-data explanation");'
].join("\n");
vm.runInContext(steps,ctx);
"""
        result = subprocess.run(["node", "-e", harness, script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
