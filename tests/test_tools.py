import datetime as dt
import importlib.util, json, os, sys, threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("creatorplaybooks_plugin", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
mod = importlib.util.module_from_spec(spec); sys.modules["creatorplaybooks_plugin"] = mod; spec.loader.exec_module(mod)
tools = mod.tools

CREATORS = [
    {"id": "maya", "handle": "@buildwithmaya", "name": "Maya", "status": "verified", "followersStr": "4.2K",
     "bio": "Host of a founder podcast.", "productsCount": 4, "playsCount": 2},
    {"id": "karpathy", "handle": "@karpathy", "name": "Andrej Karpathy", "status": "verified", "followersStr": "4.44M",
     "bio": "Teaching repos.", "productsCount": 3, "playsCount": 2},
    {"id": "ash_wesley_", "handle": "@ash_wesley_", "name": "Ash Wesley", "status": "verified", "followersStr": "1K",
     "bio": "Builder.", "productsCount": 1, "playsCount": 1},
]
PLAYS = {
    "Maya": [{"id": "maya-show", "title": "Interview", "action": "Record one.", "frequency": "Weekly", "sourceUrl": "https://example.com/m"}],
    "Andrej Karpathy": [
        {"id": "karpathy-repo", "title": "Publish the smallest thing that runs", "action": "Ship a repo.", "frequency": "When ready", "sourceUrl": "https://github.com/karpathy/nanochat"},
        {"id": "karpathy-honest", "title": "Archive the course", "action": "Say so.", "frequency": "Until it exists", "sourceUrl": "https://github.com/karpathy/LLM101n"},
    ],
}
# Shape of the site's minified PlaybookGoal chunk.
GOAL_JS = (
    'import{r as c}from"./index-T.js";const e=(n,s,r,h,y,a,l,u,w,p)=>({id:n}),H={maya:{why:"Maya why.",'
    'mistakes:["M one.","M \\u201ctwo\\u201d."],steps:[e("maya-1","Show","Watch one","Detail","Deliv","Check",45,7,"source","https://example.com/m")]},'
    'karpathy:{why:"K why.",mistakes:["A.","B."],steps:['
    'e("ka-1","Bio","Open the profile","On Nov 11 it was empty.","Your date.","You looked.",10,7,"source","https://x.com/karpathy"),'
    'e("ka-2","Repo","Read the README","Line\\nbreak","Two sentences.","Not a startup.",30,7,"source","https://github.com/karpathy/nanochat"),'
    'e("ka-3","Secondary","Read coverage",`Template, literal`,"Label it.","Not a bio line.",25,14,"source","https://example.com/s"),'
    'e("ka-4","Practice","Publish something","Practice only.","A repo.","It runs.",90,30,"suggestion"),'
    'e("ka-5","Quarter","Re-read","Check again.","The date.","You opened it.",15,90,"suggestion","https://example.com/q")]}};'
    'function O(n,s){const r=H[n];return r?{steps:r.steps.filter(h=>h.minDays<=s)}:null}'
)


class Site(BaseHTTPRequestHandler):
    goal = True
    hits = []

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path); q = dict(urllib.parse.parse_qsl(u.query))
        Site.hits.append(self.path)
        if u.path == "/redirect":
            self.send_response(302); self.send_header("Location", "https://evil.example/x"); self.end_headers(); return
        if u.path == "/":
            return self._send('<script type="module" crossorigin src="/assets/index-T.js"></script>', "text/html")
        if u.path == "/assets/index-T.js":
            return self._send('m.f||(m.f=["assets/DocsView-D.js","assets/CreatorModal-C.js"])', "text/javascript")
        if u.path == "/assets/DocsView-D.js":
            return self._send("docs", "text/javascript")
        if u.path == "/assets/CreatorModal-C.js":
            # Real shape: the goal chunk is a lazy import of the modal chunk.
            return self._send('import("./PlaybookGoal-G1.js")' if Site.goal else "no goal here", "text/javascript")
        if u.path == "/assets/PlaybookGoal-G1.js":
            return self._send(GOAL_JS, "text/javascript")
        if u.path == "/api/creators":
            return self._json({"count": len(CREATORS), "creators": CREATORS})
        # The real API falls back to the first creator for unknown ids.
        c = next((c for c in CREATORS if c["id"] == (q.get("creator") or q.get("id"))), CREATORS[0])
        if u.path == "/api/playbook":
            return self._json({"creator": c["name"], "status": "verified", "count": 1, "plays": PLAYS.get(c["name"], [])})
        if u.path == "/api/ideas":
            n = int(q.get("count", 6))
            return self._json({"creator": c["name"], "count": n, "ideas": [
                {"id": str(i), "format": "post", "hook": ["H1", "H2"][i % 2], "angle": "A", "tags": ["t"]} for i in range(n)]})
        if u.path == "/api/creator":
            return self._json({"profile": {"id": c["id"], "name": c["name"], "avatar": f"/creators/{c['id']}/avatar.jpg",
                                           "recentTweets": [1], "media": [1]},
                               "tags": ["x"], "hooks": ["h"], "angles": ["a"], "playbook": {"count": 2, "plays": []}})
        self.send_response(404); self.end_headers()

    def _send(self, body, ctype):
        b = body.encode(); self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _json(self, data):
        self._send(json.dumps(data), "application/json")

    def log_message(self, *a):
        pass


@pytest.fixture
def site(monkeypatch, tmp_path):
    srv = HTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(tools, "SITE", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    tools._cache.clear(); Site.goal = True; Site.hits = []
    yield srv
    srv.shutdown(); tools._cache.clear()


def call(fn, **args):
    return json.loads(fn(args))


class Ctx:
    def __init__(self): self.tools, self.skills = {}, {}
    def register_tool(self, name, toolset, schema, handler): self.tools[name] = (toolset, schema, handler)
    def register_skill(self, name, path): self.skills[name] = path


def test_register_matches_manifest():
    c = Ctx(); mod.register(c)
    manifest = (ROOT / "plugin.yaml").read_text()
    declared = [l.strip()[2:] for l in manifest.splitlines() if l.strip().startswith("- creatorplaybooks_")]
    assert set(c.tools) == set(declared) and len(declared) == 5
    assert "creatorplaybooks" in c.skills
    for name, (toolset, schema, _) in c.tools.items():
        assert toolset == "creatorplaybooks" and schema["name"] == name
    assert "plugin-data/creatorplaybooks" in mod.schemas.GOAL_PLAN["description"]
    assert f"version: {tools.VERSION}" in manifest


def test_mentors_list_and_search(site):
    r = call(tools.mentors)
    assert r["ok"] and r["total_mentors"] == 3 and [m["id"] for m in r["results"]] == ["maya", "karpathy", "ash_wesley_"]
    r = call(tools.mentors, query="karpathy", limit=5)
    assert [m["id"] for m in r["results"]] == ["karpathy"]
    assert call(tools.mentors, query="podcast")["results"][0]["id"] == "maya"
    assert call(tools.mentors, limit=1)["count"] == 1
    assert call(tools.mentors, query="zzzz")["count"] == 0


def test_unknown_creator_never_falls_back(site):
    r = call(tools.playbook, creator="karpathyy")
    assert r["ok"] is False and r["error"]["code"] == "unknown_creator"
    assert r["error"]["did_you_mean"] == ["karpathy"]
    assert not any(h.startswith("/api/playbook") for h in Site.hits)
    assert call(tools.playbook, creator="")["error"]["code"] == "bad_argument"


def test_resolve_by_handle_and_name(site):
    assert call(tools.playbook, creator="@karpathy")["creator"] == "karpathy"
    assert call(tools.playbook, creator="Andrej Karpathy")["creator"] == "karpathy"
    assert call(tools.playbook, creator="ash_wesley_")["creator"] == "ash_wesley_"


def test_playbook_and_ideas(site):
    r = call(tools.playbook, creator="karpathy")
    assert r["ok"] and r["count"] == 2 and r["plays"][0]["id"] == "karpathy-repo"
    r = call(tools.ideas, creator="karpathy", count=50)
    assert r["count"] == 20 and "note" in r
    assert call(tools.ideas, creator="karpathy", count="x")["error"]["code"] == "bad_argument"


def test_mentor_profile(site):
    r = call(tools.mentor, creator="karpathy")
    assert r["ok"] and r["profile"]["id"] == "karpathy"
    assert r["profile"]["avatar"].endswith("/creators/karpathy/avatar.jpg") and r["profile"]["avatar"].startswith("http")
    assert "recentTweets" not in r["profile"] and r["plays_count"] == 2


def test_goal_plan_uses_site_steps_and_dates(site):
    r = call(tools.goal_plan, creator="karpathy", days=7, start="2026-12-01")
    assert r["ok"] and r["plan_source"] == "site_goal_plan"
    assert [s["id"] for s in r["steps"]] == ["ka-1", "ka-2"]
    assert [s["date"] for s in r["steps"]] == ["2026-12-01", "2026-12-07"]
    assert r["steps"][1]["detail"] == "Line\nbreak"
    assert r["mistakes"] == ["A.", "B."] and r["why"] == "K why."
    r = call(tools.goal_plan, creator="karpathy", days=90, start="2026-12-01")
    assert r["steps_in_plan"] == 5 and r["end"] == "2027-02-28"
    # site spacing: round(i*(days-1)/(n-1))
    assert [s["date"] for s in r["steps"]] == ["2026-12-01", "2026-12-23", "2027-01-15", "2027-02-06", "2027-02-28"]
    assert r["steps"][2]["detail"] == "Template, literal"
    assert r["steps"][3]["basis"] == "suggestion" and r["steps"][3]["source_url"] is None
    assert "note" not in r


def test_goal_plan_single_step_and_custom_days(site):
    r = call(tools.goal_plan, creator="maya", days=7, start="2026-12-01")
    assert r["steps"][0]["date"] == "2026-12-01" and r["mistakes"][1] == "M \u201ctwo\u201d."
    r = call(tools.goal_plan, creator="karpathy", days=10, start="2026-12-01")
    assert "note" in r and r["steps_in_plan"] == 2


def test_goal_plan_falls_back_to_api_without_inventing(site):
    Site.goal = False
    r = call(tools.goal_plan, creator="karpathy", days=30, start="2026-12-01")
    assert r["ok"] and r["plan_source"] == "api_playbook" and "fallback_reason" in r
    assert [s["id"] for s in r["steps"]] == ["karpathy-repo", "karpathy-honest"]
    assert all(s["deliverable"] is None and s["checkpoint"] is None for s in r["steps"])
    assert [s["date"] for s in r["steps"]] == ["2026-12-01", "2026-12-30"]


def test_goal_plan_bad_args(site):
    assert call(tools.goal_plan, creator="karpathy", start="12/01/2026")["error"]["code"] == "bad_argument"
    assert call(tools.goal_plan, creator="karpathy", start="2026-02-30")["error"]["code"] == "bad_argument"
    assert call(tools.goal_plan, creator="karpathy", days=True)["error"]["code"] == "bad_argument"
    assert call(tools.goal_plan, creator="karpathy", days=9999, start="2026-12-01")["days"] == 365


def test_ics_export_confined_to_plugin_data(site, tmp_path):
    r = call(tools.goal_plan, creator="karpathy", days=14, start="2026-12-01", export_ics=True)
    p = Path(r["ics_path"])
    root = (tmp_path / "hermes" / "plugin-data" / "creatorplaybooks").resolve()
    assert p.parent == root / "plans" and p.name == "karpathy-2026-12-01-14d.ics"
    text = p.read_bytes().decode()
    assert text.startswith("BEGIN:VCALENDAR") and "DTSTART;VALUE=DATE:20261201" in text and "\r\n" in text
    # nothing else written anywhere under HERMES_HOME
    written = [x for x in (tmp_path / "hermes").rglob("*") if x.is_file()]
    assert written == [p]
    # no export without the flag
    r = call(tools.goal_plan, creator="maya", days=7, start="2026-12-01")
    assert "ics_path" not in r


def test_ics_write_refuses_symlinked_plans_dir(site, tmp_path):
    root = tmp_path / "hermes" / "plugin-data" / "creatorplaybooks"
    root.mkdir(parents=True)
    outside = tmp_path / "outside"; outside.mkdir()
    (root / "plans").symlink_to(outside, target_is_directory=True)
    r = call(tools.goal_plan, creator="karpathy", days=7, start="2026-12-01", export_ics=True)
    assert r["ok"] is False and r["error"]["code"] == "dest_outside_root"
    assert list(outside.iterdir()) == []


def test_cross_host_redirect_refused(site):
    with pytest.raises(tools.FetchError) as e:
        tools._get("/redirect")
    assert "cross-host" in str(e.value)
    with pytest.raises(tools.FetchError):
        tools._get("//evil.example/x")


def test_network_errors_become_json(monkeypatch):
    monkeypatch.setattr(tools, "SITE", "http://127.0.0.1:9")
    tools._cache.clear()
    r = call(tools.mentors)
    assert r["ok"] is False and r["error"]["code"] in {"network_error", "timeout"}


def test_no_personal_info_in_repo():
    banned = ["ne" + "al", "fra" + "zier", "@gm" + "ail"]
    for f in ROOT.rglob("*"):
        if f.is_file() and ".git" not in f.parts and "__pycache__" not in f.parts:
            text = f.read_text(errors="ignore").lower()
            for b in banned:
                assert b not in text, f"{b!r} in {f}"


@pytest.mark.skipif(os.environ.get("CREATORPLAYBOOKS_LIVE") != "1", reason="set CREATORPLAYBOOKS_LIVE=1")
def test_live_site():
    tools._cache.clear()
    r = call(tools.mentors, query="karpathy")
    assert r["ok"] and r["results"][0]["id"] == "karpathy"
    r = call(tools.goal_plan, creator="karpathy", days=30, start="2026-12-01")
    assert r["ok"] and r["plan_source"] == "site_goal_plan" and r["steps_in_plan"] >= 1
    assert call(tools.playbook, creator="definitely-not-a-mentor")["error"]["code"] == "unknown_creator"
