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

from Llm_client import ask_llm_json
from Models import TaskItem

PLANNER_SYSTEM_PROMPT = """You are an autonomous planning agent. Given a user's \
natural language request, you must:

1. Figure out a short, clear title for the resulting document.
2. Decide the full list of tasks needed to fulfill the request.
   - If the user already gave you specific items/tasks in their request, \
incorporate and organize those rather than inventing unrelated ones.
   - If the request is vague or high-level, you must invent a sensible, \
complete task breakdown yourself.
   - If the request mixes both (some tasks given, some missing), fill in \
only the missing gaps and make a reasonable assumption, noting the \
assumption in the "notes" field.
3. For each task, provide short helpful notes, a status ("Not started" \
unless the user said otherwise), and a rough deadline label (e.g. "Day 1", \
"Week 1") — deadlines are relative, not calendar dates, unless the user \
gave real ones.

Respond ONLY with JSON in this exact shape:
{
  "title": "string",
  "tasks": [
    {"task": "string", "notes": "string", "status": "string", "deadline": "string"}
  ]
}
"""

REFINE_SYSTEM_PROMPT = """You are an autonomous planning agent refining an \
existing plan based on human feedback. You will be given the CURRENT plan \
(as JSON) and FEEDBACK describing what to change.

Rules:
- Preserve tasks that the feedback doesn't mention — do not regenerate \
from scratch.
- Apply only the changes implied by the feedback (add/remove/edit tasks, \
change notes, deadlines, or status as requested).
- If the feedback is ambiguous, make the most reasonable interpretation \
and note it briefly in the relevant task's "notes" field.

Respond ONLY with JSON in this exact shape:
{
  "title": "string",
  "tasks": [
    {"task": "string", "notes": "string", "status": "string", "deadline": "string"}
  ]
}
"""


def generate_plan(user_request: str) -> dict:
    """Autonomous planning: request -> {title, tasks[]}."""
    result = ask_llm_json(PLANNER_SYSTEM_PROMPT, f"User request:\n{user_request}")
    return _validate_plan(result)


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
    result = ask_llm_json(REFINE_SYSTEM_PROMPT, user_prompt)
    return _validate_plan(result)


def _validate_plan(result: dict) -> dict:
    """Basic guardrail: make sure the LLM gave us the shape we expect."""
    if "title" not in result or "tasks" not in result:
        raise ValueError("LLM response missing required 'title' or 'tasks' fields")
    if not isinstance(result["tasks"], list) or len(result["tasks"]) == 0:
        raise ValueError("LLM response contained no tasks")
    return result