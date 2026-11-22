"""Handlers for the CreatorPlaybooks plugin. Each returns a JSON string and never raises.

Network: read-only HTTPS GETs to creatorplaybooks.netlify.app (same-host redirects only,
10 s timeout, 4 MB cap). Files: only creatorplaybooks_goal_plan with export_ics=true writes,
and only under <HERMES_HOME>/plugin-data/creatorplaybooks/plans/.
"""

import datetime as _dt
import difflib
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

VERSION = "0.1.0"
SITE = "https://creatorplaybooks.netlify.app"
TIMEOUT = 10.0
MAX_BYTES = 4 * 1024 * 1024
CACHE_TTL = 600.0
MAX_CHUNKS = 15
PRESET_DAYS = (7, 14, 30, 60, 90)
USER_AGENT = f"hermes-creatorplaybooks/{VERSION} (+unofficial community plugin)"
DISCLAIMER = "Unofficial community plugin. Data comes from the public CreatorPlaybooks API; check each sourceUrl."

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_cache: dict = {}
_cache_lock = threading.Lock()


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            raise urllib.error.URLError(f"refusing cross-host redirect to {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SameHostRedirect)


class FetchError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _err(code, message, **extra):
    return json.dumps({"ok": False, "error": {"code": code, "message": message, **extra}}, ensure_ascii=False)


def _ok(payload):
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _get(path: str) -> str:
    """GET SITE+path. Only paths starting with '/' on the fixed site are allowed."""
    if not path.startswith("/") or path.startswith("//"):
        raise FetchError("bad_argument", f"bad path {path!r}")
    url = SITE + path
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(url)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/html, */*"})
    try:
        with _opener.open(req, timeout=TIMEOUT) as r:
            body = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise FetchError("http_error", f"{url} returned HTTP {e.code}")
    except (TimeoutError, OSError) as e:
        if "timed out" in str(e).lower() or isinstance(e, TimeoutError):
            raise FetchError("timeout", f"{url} timed out after {TIMEOUT:g}s")
        raise FetchError("network_error", f"{url}: {e}")
    if len(body) > MAX_BYTES:
        raise FetchError("too_large", f"{url} is larger than {MAX_BYTES} bytes")
    text = body.decode("utf-8", errors="replace")
    with _cache_lock:
        _cache[url] = (now, text)
    return text


def _get_json(path: str):
    text = _get(path)
    try:
        return json.loads(text)
    except ValueError:
        raise FetchError("bad_response", f"{path} did not return JSON")


def _creators() -> list:
    data = _get_json("/api/creators")
    rows = data.get("creators") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise FetchError("bad_response", "/api/creators has no creators list")
    return [c for c in rows if isinstance(c, dict) and c.get("id")]


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _resolve(raw):
    """Map an id, @handle or display name to a creator row. The API silently falls back to its
    first creator for unknown ids, so every id is checked against /api/creators first."""
    raw = str(raw or "").strip()
    if not raw:
        return None, _err("bad_argument", "creator is required; use creatorplaybooks_mentors to find ids")
    rows = _creators()
    key = _norm(raw)
    for c in rows:
        if raw == c["id"] or raw.lower() == str(c.get("handle", "")).lower() or "@" + raw.lower() == str(c.get("handle", "")).lower():
            return c, None
    for c in rows:
        if key and key in {_norm(c["id"]), _norm(c.get("handle")), _norm(c.get("name"))}:
            return c, None
    names = {}
    for c in rows:
        for v in (c["id"], c.get("handle", ""), c.get("name", "")):
            names[_norm(v)] = c["id"]
    close = difflib.get_close_matches(key, list(names), n=5, cutoff=0.6)
    did = []
    for k in close:
        if names[k] not in did:
            did.append(names[k])
    return None, _err("unknown_creator", f"no mentor matches {raw!r}; use creatorplaybooks_mentors", did_you_mean=did)


def _int_arg(args, name, default, lo, hi):
    v = args.get(name, default)
    if v is None or v == "":
        return default, None
    if isinstance(v, bool):
        return None, _err("bad_argument", f"{name} must be an integer")
    try:
        f = float(v)
        if f != int(f):
            raise ValueError
        n = int(f)
    except (TypeError, ValueError):
        return None, _err("bad_argument", f"{name} must be an integer")
    return max(lo, min(hi, n)), None


def _guard(fn):
    def wrapper(args=None, **kwargs):
        try:
            return fn(args if isinstance(args, dict) else {}, **kwargs)
        except FetchError as e:
            return _err(e.code, str(e))
        except Exception as e:  # never raise into the agent loop
            return _err("internal", f"{type(e).__name__}: {e}")
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


@_guard
def mentors(args, **kwargs):
    limit, bad = _int_arg(args, "limit", 50, 1, 100)
    if bad:
        return bad
    rows = _creators()
    words = [w for w in re.split(r"\s+", str(args.get("query") or "").lower().strip()) if w]
    scored = []
    for i, c in enumerate(rows):
        hay_id = " ".join(str(c.get(k, "")).lower() for k in ("id", "handle", "name"))
        hay_bio = str(c.get("bio", "")).lower()
        score = 0
        for w in words:
            if w in hay_id:
                score += 3
            elif w in hay_bio:
                score += 1
            else:
                score = -1
                break
        if words and score <= 0:
            continue
        scored.append((-score, i, c))
    scored.sort(key=lambda t: (t[0], t[1]))
    out = [{
        "id": c["id"], "handle": c.get("handle"), "name": c.get("name"), "status": c.get("status"),
        "followers": c.get("followersStr"), "plays": c.get("playsCount"), "products": c.get("productsCount"),
        "bio": c.get("bio"), "page": f"{SITE}/?mentor={urllib.parse.quote(c['id'])}",
    } for _, _, c in scored[:limit]]
    return _ok({"total_mentors": len(rows), "count": len(out), "results": out, "source": f"{SITE}/api/creators"})


@_guard
def mentor(args, **kwargs):
    c, bad = _resolve(args.get("creator"))
    if bad:
        return bad
    data = _get_json(f"/api/creator?id={urllib.parse.quote(c['id'])}&expand=all")
    prof = data.get("profile") or {}
    if prof.get("id") != c["id"]:
        return _err("bad_response", f"API returned {prof.get('id')!r} for {c['id']!r}")
    for k in ("recentTweets", "media"):
        prof.pop(k, None)
    for k in ("avatar", "banner"):
        if isinstance(prof.get(k), str) and prof[k].startswith("/"):
            prof[k] = SITE + prof[k]
    out = {"profile": prof}
    for k in ("category", "tags", "hooks", "angles", "resources"):
        if k in data:
            out[k] = data[k]
    pb = data.get("playbook") or {}
    out["plays_count"] = pb.get("count", len(pb.get("plays") or []))
    out["note"] = "Use creatorplaybooks_playbook for the plays."
    return _ok(out)


@_guard
def playbook(args, **kwargs):
    c, bad = _resolve(args.get("creator"))
    if bad:
        return bad
    data = _get_json(f"/api/playbook?creator={urllib.parse.quote(c['id'])}")
    if data.get("creator") != c.get("name"):
        return _err("bad_response", f"API returned {data.get('creator')!r} for {c['id']!r}")
    plays = data.get("plays") or []
    return _ok({"creator": c["id"], "name": c.get("name"), "status": data.get("status"),
                "count": len(plays), "plays": plays,
                "source": f"{SITE}/api/playbook?creator={c['id']}", "disclaimer": DISCLAIMER})


@_guard
def ideas(args, **kwargs):
    c, bad = _resolve(args.get("creator"))
    if bad:
        return bad
    count, bad = _int_arg(args, "count", 6, 1, 20)
    if bad:
        return bad
    data = _get_json(f"/api/ideas?creator={urllib.parse.quote(c['id'])}&count={count}")
    if data.get("creator") != c.get("name"):
        return _err("bad_response", f"API returned {data.get('creator')!r} for {c['id']!r}")
    items = [{k: i.get(k) for k in ("format", "hook", "angle", "tags")} for i in (data.get("ideas") or [])]
    uniq = len({i["hook"] for i in items})
    out = {"creator": c["id"], "name": c.get("name"), "count": len(items), "ideas": items,
           "source": f"{SITE}/api/ideas?creator={c['id']}&count={count}"}
    if items and uniq < len(items):
        out["note"] = f"Only {uniq} distinct hooks; the site cycles the mentor's hooks and angles."
    return _ok(out)


# ---------------------------------------------------------------- goal plan

def _js_literals(s: str, i: int):
    """Parse a comma-separated run of JS string/number literals starting at s[i] up to ')'.
    Returns (values, end_index) or (None, i) if anything else appears."""
    vals = []
    n = len(s)
    while i < n:
        ch = s[i]
        if ch in "\"'`":
            q, j, buf = ch, i + 1, []
            while j < n and s[j] != q:
                if q == "`" and s.startswith("${", j):
                    return None, i
                if s[j] == "\\" and j + 1 < n:
                    e = s[j + 1]
                    if e == "n":
                        buf.append("\n"); j += 2
                    elif e == "t":
                        buf.append("\t"); j += 2
                    elif e == "u" and s[j + 2:j + 3] == "{":
                        k = s.index("}", j)
                        buf.append(chr(int(s[j + 3:k], 16))); j = k + 1
                    elif e == "u":
                        buf.append(chr(int(s[j + 2:j + 6], 16))); j += 6
                    elif e == "x":
                        buf.append(chr(int(s[j + 2:j + 4], 16))); j += 4
                    elif e == "\n":
                        j += 2
                    else:
                        buf.append(e); j += 2
                else:
                    buf.append(s[j]); j += 1
            if j >= n:
                return None, i
            vals.append("".join(buf))
            i = j + 1
        else:
            m = re.match(r"-?\d+(?:\.\d+)?", s[i:])
            if not m:
                return None, i
            vals.append(float(m.group()) if "." in m.group() else int(m.group()))
            i += m.end()
        if i < n and s[i] == ",":
            i += 1
            continue
        if i < n and s[i] == ")":
            return vals, i + 1
        return None, i
    return None, i


_STEP_CALL = re.compile(r"[A-Za-z_$][\w$]*\(\"")
_CREATOR_KEY = re.compile(r"(?:[{,])([A-Za-z_$][\w$]*|\"[^\"]+\"):\{why:")


def parse_goal_bundle(js: str) -> dict:
    """Extract {creator_id: {why, mistakes, steps}} from the site's PlaybookGoal bundle.
    A step is a call with 9 or 10 literal args: id, phase, title, detail, deliverable,
    checkpoint, minutes, minDays, basis ('source'|'suggestion'), [sourceUrl]."""
    keys = [(m.start(), m.group(1).strip('"'), m.end()) for m in _CREATOR_KEY.finditer(js)]
    out = {}
    for idx, (start, cid, body) in enumerate(keys):
        end = keys[idx + 1][0] if idx + 1 < len(keys) else len(js)
        seg = js[body:end]
        why = _one_string(seg, 0)
        mistakes = []
        mm = re.search(r",mistakes:\[", seg)
        if mm:
            j = mm.end()
            while j < len(seg) and seg[j] in "\"'`":
                k = _find_str_end(seg, j)
                v = _one_string(seg[:k], j)
                if v is None:
                    break
                mistakes.append(v)
                j = k + 1 if k < len(seg) and seg[k] == "," else k
        steps = []
        for m in _STEP_CALL.finditer(seg):
            vals, _ = _js_literals(seg, m.end() - 1)
            if not vals or len(vals) not in (9, 10):
                continue
            if not all(isinstance(v, str) for v in vals[:6]) or not all(isinstance(v, int) for v in vals[6:8]):
                continue
            if vals[8] not in ("source", "suggestion"):
                continue
            steps.append({
                "id": vals[0], "phase": vals[1], "title": vals[2], "detail": vals[3],
                "deliverable": vals[4], "checkpoint": vals[5], "minutes": vals[6], "min_days": vals[7],
                "basis": vals[8], "source_url": vals[9] if len(vals) == 10 else None,
            })
        if steps:
            out[cid] = {"why": why, "mistakes": mistakes, "steps": steps}
    return out


def _one_string(seg: str, j: int):
    """Decode the JS string literal that starts at seg[j], or None."""
    if j >= len(seg) or seg[j] not in "\"'`":
        return None
    vals, _ = _js_literals(seg[j:_find_str_end(seg, j)] + ")", 0)
    return vals[0] if vals and isinstance(vals[0], str) else None


def _find_str_end(seg: str, j: int) -> int:
    q, k = seg[j], j + 1
    while k < len(seg) and seg[k] != q:
        k += 2 if seg[k] == "\\" else 1
    return k + 1


def _site_goal_plans() -> dict:
    html = _get("/")
    m = re.search(r'src="(/assets/index-[\w-]+\.js)"', html)
    if not m:
        raise FetchError("site_changed", "main bundle not found in index.html")
    main = _get(m.group(1))
    goal_re = re.compile(r"(?:assets/|\./)(PlaybookGoal-[\w-]+\.js)")
    g = goal_re.search(main)
    if not g:
        # Vite lazy chunks: the goal chunk is imported from another chunk (today CreatorModal).
        chunks = sorted(set(re.findall(r"assets/([\w-]+\.js)", main)),
                        key=lambda n: (not re.search(r"Creator|Goal|Modal", n), n))
        for name in chunks[:MAX_CHUNKS]:
            g = goal_re.search(_get("/assets/" + name))
            if g:
                break
    if not g:
        raise FetchError("site_changed", "PlaybookGoal bundle not found")
    plans = parse_goal_bundle(_get("/assets/" + g.group(1)))
    if not plans:
        raise FetchError("site_changed", "no goal-plan steps parsed from the site bundle")
    return plans


def _spread_dates(n: int, start: _dt.date, days: int) -> list:
    """Same spacing as the site: step i lands on round(i*(days-1)/(n-1)) days after start."""
    days = max(1, days)
    return [(start + _dt.timedelta(days=0 if n <= 1 else math.floor(i * (days - 1) / (n - 1) + 0.5))).isoformat()
            for i in range(n)]


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
    except ImportError:
        raw = os.environ.get("HERMES_HOME", "").strip()
        if raw:
            return Path(os.path.expanduser(os.path.expandvars(raw)))
        if sys.platform == "win32":
            local = os.environ.get("LOCALAPPDATA", "").strip()
            return (Path(local) if local else Path.home() / "AppData" / "Local") / "hermes"
        return Path.home() / ".hermes"
    return Path(get_hermes_home()).expanduser()


def data_root() -> Path:
    """The only tree this plugin writes: <HERMES_HOME>/plugin-data/creatorplaybooks."""
    return (_hermes_home() / "plugin-data" / "creatorplaybooks").resolve()


def _ics_escape(t: str) -> str:
    return t.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _ics(creator_id: str, name: str, steps: list) -> str:
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//hermes-creatorplaybooks//unofficial community plugin//EN", "CALSCALE:GREGORIAN"]
    for s in steps:
        desc = [s.get("detail") or ""]
        if s.get("deliverable"):
            desc += ["", f"Deliverable: {s['deliverable']}"]
        if s.get("checkpoint"):
            desc.append(f"Checkpoint: {s['checkpoint']}")
        if s.get("basis") == "suggestion":
            desc.append("This step is a suggestion, not the mentor's claim.")
        if s.get("source_url"):
            desc.append(s["source_url"])
        lines += ["BEGIN:VEVENT", f"UID:{creator_id}-{s['id']}@creatorplaybooks", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{s['date'].replace('-', '')}",
                  f"SUMMARY:{_ics_escape(name + ': ' + s['title'])}",
                  f"DESCRIPTION:{_ics_escape(chr(10).join(desc))}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _write_ics(creator_id: str, start: str, days: int, text: str) -> Path:
    if not _ID_RE.match(creator_id) or not _DATE_RE.match(start):
        raise FetchError("bad_argument", "refusing to build a file name from unexpected input")
    root = data_root()
    plans = root / "plans"
    target = (plans / f"{creator_id}-{start}-{days}d.ics").resolve()
    if target.parent != plans.resolve() or root not in target.parents:
        raise FetchError("dest_outside_root", f"refusing to write outside {root}")
    plans.mkdir(parents=True, exist_ok=True)
    if plans.resolve() != plans or root not in plans.resolve().parents:
        raise FetchError("dest_outside_root", f"refusing to write outside {root}")
    tmp = target.with_suffix(".ics.tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, target)
    return target


@_guard
def goal_plan(args, **kwargs):
    c, bad = _resolve(args.get("creator"))
    if bad:
        return bad
    days, bad = _int_arg(args, "days", 30, 1, 365)
    if bad:
        return bad
    raw_start = str(args.get("start") or "").strip()
    if raw_start:
        if not _DATE_RE.match(raw_start):
            return _err("bad_argument", "start must be YYYY-MM-DD")
        try:
            start = _dt.date.fromisoformat(raw_start)
        except ValueError:
            return _err("bad_argument", "start is not a real date")
    else:
        start = _dt.date.today()

    plan_source, why, mistakes, fallback_reason = "site_goal_plan", None, [], None
    try:
        site = _site_goal_plans().get(c["id"])
        if not site:
            raise FetchError("not_in_site_plans", f"the site has no goal-plan steps for {c['id']}")
        all_steps = site["steps"]
        steps = [dict(s) for s in all_steps if s["min_days"] <= days]
        why, mistakes = site["why"], site["mistakes"]
    except FetchError as e:
        plan_source, fallback_reason = "api_playbook", f"{e.code}: {e}"
        data = _get_json(f"/api/playbook?creator={urllib.parse.quote(c['id'])}")
        if data.get("creator") != c.get("name"):
            return _err("bad_response", f"API returned {data.get('creator')!r} for {c['id']!r}")
        all_steps = steps = [{
            "id": p.get("id"), "phase": None, "title": p.get("title"), "detail": p.get("action"),
            "deliverable": None, "checkpoint": None, "minutes": None, "min_days": None,
            "frequency": p.get("frequency"), "basis": "playbook", "source_url": p.get("sourceUrl"),
        } for p in (data.get("plays") or [])]
    if not steps:
        return _err("empty_plan", f"no steps for {c['id']} within {days} days")
    for s, d in zip(steps, _spread_dates(len(steps), start, days)):
        s["date"] = d
    end = (start + _dt.timedelta(days=days - 1)).isoformat()
    out = {
        "creator": c["id"], "name": c.get("name"), "days": days, "start": start.isoformat(), "end": end,
        "plan_source": plan_source, "steps_in_plan": len(steps), "steps_available": len(all_steps),
        "why": why, "mistakes": mistakes, "steps": steps,
        "page": f"{SITE}/?mentor={urllib.parse.quote(c['id'])}", "disclaimer": DISCLAIMER,
    }
    if days not in PRESET_DAYS:
        out["note"] = "The site offers 7, 14, 30, 60 and 90 days; custom lengths use the same spacing."
    if fallback_reason:
        out["fallback_reason"] = fallback_reason
        out["note"] = ("Site goal-plan steps were unavailable, so each API play is one step. "
                       "Deliverables and checkpoints are left empty rather than invented.")
    if args.get("export_ics") is True:
        path = _write_ics(c["id"], start.isoformat(), days, _ics(c["id"], c.get("name") or c["id"], steps))
        out["ics_path"] = str(path)
    return _ok(out)
