---
name: creatorplaybooks
description: Learn from a creator's sourced playbook on CreatorPlaybooks, get post ideas in their style, and turn the plays into a dated 7/14/30/60/90-day plan.
---

# CreatorPlaybooks

1. If the user names a creator loosely, call `creatorplaybooks_mentors` with their words and pick the matching `id`. Don't guess ids.
2. `creatorplaybooks_playbook` gives the plays: what the creator does, the action to copy, how often, and a `sourceUrl`. Quote the source when you summarise a play.
3. `creatorplaybooks_ideas` gives post hooks and angles in that creator's style. They come from the creator's own hooks, so they repeat; rewrite them for the user's project rather than pasting them.
4. For "give me a plan", call `creatorplaybooks_goal_plan` with `days` (7, 14, 30, 60 or 90) and an optional `start` date. Read `plan_source`:
   - `site_goal_plan`: the site's own steps. Steps with `basis: "suggestion"` are the site's practice suggestions, not something the creator said or did. Say so.
   - `api_playbook`: the fallback, one step per play, with no deliverables or checkpoints. Don't fill those in as if they came from the site.
5. Offer `export_ics: true` if the user wants it in their calendar. The file is written under the Hermes plugin data folder; give them the `ics_path`.

This is an unofficial community plugin. Don't present the creators as endorsing the user, the plan or this plugin, and don't claim results the sources don't show.
