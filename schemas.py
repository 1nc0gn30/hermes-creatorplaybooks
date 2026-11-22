"""Tool schemas for the CreatorPlaybooks plugin."""

_SITE = "CreatorPlaybooks (https://creatorplaybooks.netlify.app)"
_CREATOR = {
    "type": "string",
    "description": "Mentor id from creatorplaybooks_mentors (e.g. 'karpathy'). An @handle or display name also works.",
}

MENTORS = {
    "name": "creatorplaybooks_mentors",
    "description": (
        f"List or search the mentors on {_SITE}, a free site of sourced creator playbooks. "
        "Returns id, handle, name, status, follower string, short bio and how many plays and products "
        "each mentor has. An empty query lists everyone. Use the returned id with the other "
        "creatorplaybooks_* tools. One read-only HTTPS GET to /api/creators."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Words to match against id, handle, name and bio."},
            "limit": {"type": "integer", "description": "Max results (default 50, min 1, max 100)."},
        },
        "required": [],
    },
}

MENTOR = {
    "name": "creatorplaybooks_mentor",
    "description": (
        f"Profile for one mentor on {_SITE}: bio, products, pillars, milestones, dated sources, "
        "hooks, angles, tags and API links. The playbook itself is in creatorplaybooks_playbook. "
        "Unknown ids return unknown_creator with did_you_mean instead of a different mentor. "
        "Read-only HTTPS GET to /api/creator."
    ),
    "parameters": {"type": "object", "properties": {"creator": _CREATOR}, "required": ["creator"]},
}

PLAYBOOK = {
    "name": "creatorplaybooks_playbook",
    "description": (
        f"The plays for one mentor on {_SITE}: title, what they do, the action to copy, how often, "
        "a dated example and the source URL. Use it when the user wants to learn from a specific "
        "creator. Read-only HTTPS GET to /api/playbook?creator=<id>."
    ),
    "parameters": {"type": "object", "properties": {"creator": _CREATOR}, "required": ["creator"]},
}

IDEAS = {
    "name": "creatorplaybooks_ideas",
    "description": (
        f"Post ideas in one mentor's style from {_SITE}: format (post, thread, reply, quote), hook, "
        "angle and tags. The site builds these from the mentor's own hooks and angles, so they repeat "
        "once count exceeds the hooks available. Read-only HTTPS GET to /api/ideas."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "creator": _CREATOR,
            "count": {"type": "integer", "description": "How many ideas (default 6, min 1, max 20)."},
        },
        "required": ["creator"],
    },
}

GOAL_PLAN = {
    "name": "creatorplaybooks_goal_plan",
    "description": (
        f"Turn one mentor's playbook on {_SITE} into a dated goal plan over 7, 14, 30, 60 or 90 days "
        "(or any 1-365). Uses the site's own goal-plan steps (deliverable, checkpoint, minutes, and "
        "basis 'source' vs 'suggestion') with the site's date spacing; if those can't be read it falls "
        "back to the API plays and says so in plan_source. It never invents steps. Optional "
        "export_ics writes an .ics calendar file under <HERMES_HOME>/plugin-data/creatorplaybooks/plans/ "
        "and nowhere else. Read-only HTTPS GETs to the site."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "creator": _CREATOR,
            "days": {"type": "integer", "description": "Plan length in days: 7, 14, 30, 60 or 90 (default 30). Any 1-365 is accepted."},
            "start": {"type": "string", "description": "Start date YYYY-MM-DD (default today, local time)."},
            "export_ics": {"type": "boolean", "description": "Also write an .ics file under the plugin data directory (default false)."},
        },
        "required": ["creator"],
    },
}
