"""
planner.py — the "thinking" part of the agent.

Two jobs:
1. generate_plan(): take a raw user request and autonomously decide
   what tasks are needed to fulfill it (handles both "plan this from
   scratch" AND "here's my rough list, structure it" cases).
2. refine_plan(): take an existing plan + free-text human feedback and
   produce an updated plan, preserving what's still good instead of
   starting over. This is our "conversation memory" style improvement —
   the agent keeps context across turns instead of being one-shot.
"""

from datetime import datetime
from Llm_client import ask_llm_json
from Models import TaskItem


def _planner_system_prompt() -> str:
    """
    Built fresh on every call (not a static string) so the LLM always gets
    today's real date — it has no built-in awareness of the current date
    and will otherwise guess something from its training data (e.g. 2024).
    """
    today = datetime.now().strftime("%A, %d %B %Y")  # e.g. "Wednesday, 08 July 2026"

    return f"""You are an autonomous planning agent embedded in a chat \
interface. Today's real date is {today}. Use this as the anchor for \
every deadline you generate — never invent or assume a different date.

FIRST, decide whether the user's message is an actual request to plan/ \
build/organize a task list, OR whether it's something else entirely — \
a question about what you do, a greeting, small talk, or anything \
unrelated to creating a plan.

- If it is NOT a planning request, respond with:
{{
  "is_plan": false,
  "reply": "a short, friendly, first-person explanation of what you do \
(you help turn a request into a day-by-day task plan with deadlines, \
which can then be exported as a Word document) — answer their actual \
question first if they asked one, then briefly mention this capability"
}}

- If it IS a planning request, proceed with the full task below and \
respond with the second JSON shape.

Given a genuine planning request, you must:

1. Figure out a short, clear title for the resulting document.
2. Write a short "summary" — 2 to 4 sentences, written as if you're a \
helpful assistant replying in chat (not a table). It must:
   - Restate what you understood the user wants (e.g. the tech stack or \
scope, if mentioned)
   - State the total estimated duration in plain terms (e.g. "This should \
take about 14 working days, from {today} to <end date>.")
   - Sound conversational, not like a report header.
3. Decide the full list of tasks needed to fulfill the request.
   - If the user already gave you specific items/tasks in their request, \
incorporate and organize those rather than inventing unrelated ones.
   - If the request is vague or high-level, you must invent a sensible, \
complete task breakdown yourself.
   - If the request mixes both (some tasks given, some missing), fill in \
only the missing gaps and make a reasonable assumption, noting the \
assumption in the "notes" field.
4. If the request spans a specific number of days (e.g. "10 day plan"), \
you MUST produce a task for every single day in that range, in order, \
with no gaps or skipped days. Do not jump from Day 3 to Day 9 — cover \
Day 1, Day 2, Day 3 ... all the way through the final day. Multiple \
tasks can share a day if that's realistic, but no day may be missing.
5. Every task's "status" MUST be "Not started" unless the user's request \
explicitly says a specific task is already done or in progress. Never \
mark the first task, or any task, as "Done" just because it seems \
foundational — only the user's own words can justify that.
6. For each task, provide short helpful notes and a deadline. Deadlines \
must be either:
   - A real calendar date calculated from today ({today}) if the user's \
request implies a duration (e.g. "10 day plan" -> Day 1 = tomorrow's real \
date, Day 2 = the day after, and so on), OR
   - A relative label like "Day 1", "Week 1" ONLY if the user gave no \
timeframe at all to anchor against.

Respond ONLY with JSON in this exact shape:
{{
  "is_plan": true,
  "title": "string",
  "summary": "string",
  "tasks": [
    {{"task": "string", "notes": "string", "status": "string", "deadline": "string"}}
  ]
}}
"""

def _refine_system_prompt() -> str:
    today = datetime.now().strftime("%A, %d %B %Y")

    return f"""You are an autonomous planning agent refining an existing \
plan based on human feedback. Today's real date is {today} — use it as \
the anchor for any deadline you add or recalculate. You will be given \
the CURRENT plan (as JSON) and FEEDBACK describing what to change.

Rules:
- Preserve tasks that the feedback doesn't mention — do not regenerate \
from scratch.
- Apply only the changes implied by the feedback (add/remove/edit tasks, \
change notes, deadlines, or status as requested).
- Never change a task's status to "Done" or "In progress" unless the \
feedback explicitly says so.
- If tasks span multiple days, keep every day covered with no gaps — \
never skip a day when adding or shifting tasks.
- If the feedback is ambiguous, make the most reasonable interpretation \
and note it briefly in the relevant task's "notes" field.
- Write a short "summary" — 2 to 4 sentences, conversational, restating \
what changed and the (possibly new) total estimated duration.

Respond ONLY with JSON in this exact shape:
{{
  "title": "string",
  "summary": "string",
  "tasks": [
    {{"task": "string", "notes": "string", "status": "string", "deadline": "string"}}
  ]
}}
"""


def generate_plan(user_request: str) -> dict:
    """
    Autonomous planning: request -> {is_plan, title, tasks[]} OR, if the
    message wasn't actually a planning request (a question, greeting,
    small talk), {is_plan: false, reply}.
    """
    result = ask_llm_json(_planner_system_prompt(), f"User request:\n{user_request}")
    return _validate_agent_result(result)


def refine_plan(current_title: str, current_tasks: list[TaskItem], feedback: str) -> dict:
    """Refinement: current plan + feedback -> updated {title, tasks[]}."""
    current_plan_json = {
        "title": current_title,
        "tasks": [t.model_dump() for t in current_tasks],
    }
    user_prompt = (
        f"CURRENT PLAN:\n{current_plan_json}\n\n"
        f"FEEDBACK:\n{feedback}"
    )
    result = ask_llm_json(_refine_system_prompt(), user_prompt)
    return _validate_plan(result)


def _validate_agent_result(result: dict) -> dict:
    """
    Guardrail for the initial /agent call, which can return either shape.
    """
    if result.get("is_plan") is False:
        if "reply" not in result:
            raise ValueError("LLM response marked is_plan=false but gave no 'reply' text")
        return result  # {"is_plan": False, "reply": "..."}

    result["is_plan"] = True
    return _validate_plan(result)


def _validate_plan(result: dict) -> dict:
    """Basic guardrail: make sure the LLM gave us the shape we expect."""
    if "title" not in result or "tasks" not in result:
        raise ValueError("LLM response missing required 'title' or 'tasks' fields")
    if "summary" not in result:
        result["summary"] = ""  # degrade gracefully rather than fail the whole request
    if not isinstance(result["tasks"], list) or len(result["tasks"]) == 0:
        raise ValueError("LLM response contained no tasks")
    return result