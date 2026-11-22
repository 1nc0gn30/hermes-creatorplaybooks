# hermes-creatorplaybooks

**[CreatorPlaybooks](https://creatorplaybooks.netlify.app) for [Hermes Agent](https://github.com/NousResearch/hermes-agent).**

Gives Hermes five read-only tools and a skill for the free CreatorPlaybooks site: list the mentors, read a mentor's sourced playbook, get post ideas in their style, and turn their plays into a dated 7, 14, 30, 60 or 90-day goal plan.

> Unofficial community plugin by 1nc0gn30. Not affiliated with or endorsed by Nous Research or by any creator listed on the site. Mentor data belongs to its sources; every play links to one.

## Install

```bash
hermes plugins install https://github.com/1nc0gn30/hermes-creatorplaybooks
hermes plugins enable creatorplaybooks
hermes plugins list | grep creatorplaybooks   # creatorplaybooks 0.1.0 (5 tools)
```

Or copy the folder to `~/.hermes/plugins/creatorplaybooks/` and run `hermes plugins enable creatorplaybooks`.

Needs Hermes `>=0.21.5`. Free: no API keys, no accounts, no Python dependencies.

## Tools

| Tool | Use it for | API |
| --- | --- | --- |
| `creatorplaybooks_mentors` | List or search mentors (id, handle, name, follower string, bio, play count). | `GET /api/creators` |
| `creatorplaybooks_mentor` | One mentor's profile: products, pillars, milestones, dated sources, hooks, angles. | `GET /api/creator?id=<id>&expand=all` |
| `creatorplaybooks_playbook` | The plays: what they do, the action to copy, cadence, a dated example and `sourceUrl`. | `GET /api/playbook?creator=<id>` |
| `creatorplaybooks_ideas` | Post hooks and angles in the mentor's style (1-20). | `GET /api/ideas?creator=<id>&count=<n>` |
| `creatorplaybooks_goal_plan` | A dated plan over 7/14/30/60/90 days (any 1-365), optionally as an `.ics` file. | the site's goal-plan steps, else `/api/playbook` |

`creator` accepts an id (`karpathy`), an @handle (`@karpathy`) or a display name (`Andrej Karpathy`).

Skill: `skill_view("creatorplaybooks:creatorplaybooks")` walks the agent through picking a mentor, citing sources and building a plan.

### Unknown mentors

The public API answers an unknown id with its first mentor instead of an error. This plugin checks every id against `/api/creators` first, so a typo returns `unknown_creator` with `did_you_mean`, never someone else's playbook.

### How the goal plan is built

The site's "Start goal" panel has its own steps for each mentor: a phase, a deliverable, a checkpoint, minutes, the shortest plan length the step belongs to, and a `basis` of `source` (from a cited page) or `suggestion` (the site's practice idea, not the creator's claim). Those steps aren't in the JSON API, so the plugin reads them from the site's published JavaScript bundle and keeps the steps whose length fits `days`. Dates use the site's own spacing: step *i* of *n* lands `round(i * (days - 1) / (n - 1))` days after `start`.

If the bundle can't be read (the site changed), the plan falls back to one step per API play, `plan_source` says `api_playbook`, `fallback_reason` says why, and deliverables and checkpoints are left `null`. Nothing is made up in either case.

## Examples

```
Who's on CreatorPlaybooks that ships open-source models?
Show me Andrej Karpathy's playbook with sources.
Give me five post ideas in levelsio's style for my side project.
Make me a 30-day plan from Teknium's playbook starting Monday, and put it in my calendar.
```

### What the agent sees

`creatorplaybooks_goal_plan {"creator": "@teknium", "days": 30, "start": "2026-11-23"}` (live, trimmed)

```json
{
 "ok": true,
 "creator": "teknium",
 "days": 30,
 "start": "2026-11-23",
 "end": "2026-12-22",
 "plan_source": "site_goal_plan",
 "steps_in_plan": 4,
 "steps_available": 5,
 "steps": [
  {
   "id": "tk-1",
   "phase": "Three facts",
   "title": "Write role, project, and previous lab",
   "deliverable": "Three lines.",
   "checkpoint": "Previous is labeled previous.",
   "minutes": 10,
   "basis": "source",
   "source_url": "https://x.com/Teknium",
   "date": "2026-11-23"
  },
  "..."
 ]
}
```

`creatorplaybooks_playbook {"creator": "karpathyy"}`

```json
{"ok": false, "error": {"code": "unknown_creator", "message": "no mentor matches 'karpathyy'; use creatorplaybooks_mentors", "did_you_mean": ["karpathy"]}}
```

### Errors

Every tool returns JSON and never raises. Failures look like `{"ok": false, "error": {"code": ..., "message": ...}}`. Codes: `unknown_creator` (with `did_you_mean`), `bad_argument`, `http_error`, `network_error`, `timeout`, `too_large`, `bad_response`, `empty_plan`, `dest_outside_root`, `internal`.

## Disclosures

- **Network:** HTTPS GETs to `creatorplaybooks.netlify.app` only: the JSON API, and for `creatorplaybooks_goal_plan` the site's `index.html` and JavaScript bundles (read as text, never executed). 10 s timeout per request, 4 MB cap, redirects to other hosts refused, responses cached in memory for 10 minutes. No telemetry.
- **Files:** only `creatorplaybooks_goal_plan` with `export_ics: true` writes, and only `<HERMES_HOME>/plugin-data/creatorplaybooks/plans/<id>-<start>-<days>d.ics`. The file name is built from a validated mentor id and date, never from a path the model supplies. If `plans/` resolves outside that directory (a symlink, for example) the write is refused with `dest_outside_root`. Reads nothing outside the plugin directory.
- **Shell:** none. **Credentials:** none. No background processes and no self-updating code.

## Development

```bash
python -m pytest -c tests/pytest.ini --rootdir tests tests                         # offline, local fake site
CREATORPLAYBOOKS_LIVE=1 python -m pytest -c tests/pytest.ini --rootdir tests tests  # adds one live check
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
```

`.github/workflows/ci.yml` runs the tests on GitHub Actions for every push and pull request.

## Changelog

### 0.1.0

- First version: five read-only tools, the `creatorplaybooks` skill, `.ics` export under plugin-data.

## License

MIT © 2026 1nc0gn30
