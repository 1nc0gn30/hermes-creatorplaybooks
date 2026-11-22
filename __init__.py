"""CreatorPlaybooks plugin for Hermes: read-only tools over the public CreatorPlaybooks API."""

from pathlib import Path

from . import schemas, tools

TOOLSET = "creatorplaybooks"


def register(ctx):
    ctx.register_tool(name="creatorplaybooks_mentors", toolset=TOOLSET, schema=schemas.MENTORS, handler=tools.mentors)
    ctx.register_tool(name="creatorplaybooks_mentor", toolset=TOOLSET, schema=schemas.MENTOR, handler=tools.mentor)
    ctx.register_tool(name="creatorplaybooks_playbook", toolset=TOOLSET, schema=schemas.PLAYBOOK, handler=tools.playbook)
    ctx.register_tool(name="creatorplaybooks_ideas", toolset=TOOLSET, schema=schemas.IDEAS, handler=tools.ideas)
    ctx.register_tool(name="creatorplaybooks_goal_plan", toolset=TOOLSET, schema=schemas.GOAL_PLAN, handler=tools.goal_plan)
    skills = Path(__file__).parent / "skills"
    for child in sorted(skills.iterdir()):
        if (child / "SKILL.md").exists():
            ctx.register_skill(child.name, child / "SKILL.md")
