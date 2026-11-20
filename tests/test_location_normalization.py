"""Regression tests: Vietnamese location aliases merge without changing Sheet originals."""
import html.parser
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ScriptExtractor(html.parser.HTMLParser):
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


class LocationNormalizationTests(unittest.TestCase):
    def test_html_uses_canonical_places_without_rewriting_original_sheet(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("function normalizeLocations(raw)", html)
        self.assertIn("function canonicalLocationPart(value)", html)
        self.assertIn('locations:normalizeLocations(j.location||"")', html)
        self.assertIn('(Array.isArray(j.locations)?j.locations:normalizeLocations(j.location)).includes(l)', html)
        self.assertIn('locations.replaceChildren(new Option("Tất cả địa điểm",""))', html)
        self.assertIn('location:String(j.location||"")', html)
        self.assertIn('j.locations:normalizeLocations(j.location)', html)
        self.assertIn('marketRegion(loc)', html)

    def test_real_js_alias_merging_dropdown_multi_location_filter_and_display(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        parser = ScriptExtractor()
        parser.feed(html)
        script = "\n".join(parser.parts)
        marker = '\npopulate();render();$("#dataStatus").textContent="Đang tải dữ liệu Google Sheet…";\nasync function loadPublishedJobs()'
        self.assertIn(marker, script)
        script = script.split(marker, 1)[0]
        harness = r"""
const vm=require("node:vm");
class Element {
 constructor(tag="div"){
  this.tagName=tag;this.children=[];this.listeners={};this.attributes={};
  this.style={};this.dataset={};this.value="";this.textContent="";
 }
 append(...x){this.children.push(...x)}
 replaceChildren(...x){this.children=[...x]}
 add(x){this.children.push(x)}
 addEventListener(name,fn){this.listeners[name]=fn}
 setAttribute(key,val){this.attributes[key]=val}
 focus(){}
 blur(){}
}
const nodes={}, get=s=>nodes[s]||(nodes[s]=new Element());
const findButtons=e=>(!e?[]:[e,...e.children.filter(x=>x instanceof Element).flatMap(findButtons)])
  .filter(x=>x.className==="bar-choice");
const document={
 querySelector:get,createElement:tag=>new Element(tag),
 querySelectorAll:s=>s===".view-tab"||s==="[data-start]"?[]:
   findButtons(get(s.split(" ")[0]))
};
const Option=class{constructor(label,value){this.textContent=label;this.value=value}};
const localStorage={getItem:()=>null,setItem:()=>{}};
const ctx=vm.createContext({document,Option,Date,Intl,console,URL,Blob,localStorage});
vm.runInContext(process.argv[1],ctx);
const checks=[
 'function assert(ok,msg){if(!ok)throw Error(msg)}',
 'assert(normalizeLocations("Ha Noi").join("|")==="Hà Nội","Unaccented Hanoi");',
 'assert(normalizeLocations("Hà Nội").join("|")==="Hà Nội","Accented Hanoi");',
 'assert(normalizeLocations("Hanoi").join("|")==="Hà Nội","Hanoi alias");',
 'assert(normalizeLocations("Ho Chi Minh").join("|")==="Hồ Chí Minh","Unaccented HCMC");',
 'assert(normalizeLocations("Hồ Chí Minh (mới)").join("|")==="Hồ Chí Minh","new HCMC");',
 'assert(normalizeLocations("TP.HCM").join("|")==="Hồ Chí Minh","HCMC abbreviation");',
 'assert(normalizeLocations("Ho Chi Minh - Da Nang").join("|")==="Đà Nẵng|Hồ Chí Minh","two cities");',
 'assert(normalizeLocations("Ha Noi - Ho Chi Minh").join("|")==="Hà Nội|Hồ Chí Minh","two cities second order");',
 'assert(normalizeLocations("Ho Chi Minh - Ha Noi").join("|")==="Hà Nội|Hồ Chí Minh","reversed order merges");',
 'assert(normalizeLocations("Hà Nội & Hồ Chí Minh (mới)").join("|")==="Hà Nội|Hồ Chí Minh","mixed accents");',
 'assert(normalizeLocations("Bà Rịa - Vũng Tàu").join("|")==="Bà Rịa - Vũng Tàu","do not split legitimate province");',
 'assert(normalizeLocations("Hải Phòng (mới)").join("|")==="Hải Phòng","new city");',
 'assert(marketRegion("Hà Nội")==="Vietnam","Unicode location must be Vietnam");',
 'assert(marketRegion("Hồ Chí Minh (mới)")==="Vietnam","Unicode HCMC must be Vietnam");',
 'assert(marketRegion("Remote")==="Remote / unspecified","Remote stays separate");',
 'const input=["Ha Noi","Hà Nội","Ho Chi Minh","Hồ Chí Minh (mới)","Remote",',
 ' "Ha Noi - Ho Chi Minh","Ho Chi Minh - Ha Noi","Hà Nội & Hồ Chí Minh (mới)",',
 ' "Ho Chi Minh - Da Nang","Hải Phòng (mới)","Thái Nguyên (mới)",',
 ' "Quảng Trị (mới)","Lâm Đồng (mới)"];',
 'all=input.map((location,i)=>({title:"QA"+i,company:"C"+i,location,',
 ' locations:normalizeLocations(location),experience_text:"3 năm",role:"Manual QA",',
 ' skills:[],source:"TopCV",url:"",first_seen:"2026-11-20T00:00:00+00:00",market_region:marketRegion(location)}));',
 'populate();',
 'const cities=$("#location").children.slice(1).map(x=>x.value);',
 'assert(cities.length===8,"13 Sheet labels should become 8 unique place options, got "+cities.length);',
 'assert(new Set(cities).size===8,"No duplicate city values");',
 'assert(!cities.includes("Ha Noi")&&!cities.includes("Ho Chi Minh")&&!cities.includes("Hồ Chí Minh (mới)"),"No duplicate aliases in dropdown");',
 '$("#role").value="";$("#region").value="";$("#age").value="0";$("#experience").value="";',
 '$("#location").value="Hà Nội";',
 'assert(selectedJobs().length===5,"Hanoi includes multi-location postings");',
 '$("#location").value="Hồ Chí Minh";',
 'assert(selectedJobs().length===6,"HCMC includes mixed and new HCMC");',
 '$("#location").value="Đà Nẵng";',
 'assert(selectedJobs().length===1,"Da Nang includes combined listing");',
 '$("#location").value="Hà Nội";render();',
 'assert($("#records").children.length===5,"Explorer rows match selection");',
 'const display=$("#records").children.map(r=>r.children[2].textContent);',
 'assert(display.includes("Hà Nội · Hồ Chí Minh"),"Canonical multi-city display");',
 'assert(all.some(j=>j.location==="Ha Noi"),"Do not modify original Sheet location");'
].join("\n");
vm.runInContext(checks,ctx);
"""
        result = subprocess.run(["node", "-e", harness, script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
