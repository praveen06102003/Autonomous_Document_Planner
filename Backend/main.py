"""
main.py — FastAPI app. Three endpoints, matching the plan -> refine ->
finalize flow:

  POST /agent          request -> initial task plan (no doc yet)
  POST /agent/refine    plan + free-text feedback -> updated plan
  POST /generate-doc    approved plan -> final .docx (only now do we write a file)
  GET  /output/{file}   serves the generated doc for download

In-memory PLAN_STORE holds plans by plan_id during a session. For a
resume/portfolio project this is fine — swap for SQLite/Redis if you
want plans to survive a server restart.
"""

import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from Models import (
    AgentRequest, AgentResponse,
    RefineRequest, RefineResponse,
    UpdateTasksRequest, UpdateTasksResponse,
    GenerateDocRequest, GenerateDocResponse,
    TaskItem,
)
from Planner import generate_plan, refine_plan
from Doc_builder import build_document, OUTPUT_DIR

app = FastAPI(
    title="Autonomous AI Agent for Business Document Generation",
    description="Give it a request, it plans the tasks, you refine it, then it generates a polished Word doc.",
    version="1.0.0",
)

# Allow the JS frontend (served separately or via file://) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store: plan_id -> {"title": ..., "tasks": [TaskItem, ...]}
PLAN_STORE: dict[str, dict] = {}


@app.post("/agent", response_model=AgentResponse)
def create_plan(payload: AgentRequest):
    """Step 1: understand the request and autonomously draft a task plan —
    or, if the message wasn't actually a planning request, reply conversationally
    without creating a plan."""
    try:
        result = generate_plan(payload.request)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Planning failed: {e}")

    if not result.get("is_plan", True):
        return AgentResponse(is_plan=False, message=result["reply"])

    plan_id = str(uuid.uuid4())[:8]
    tasks = [TaskItem(**t) for t in result["tasks"]]
    PLAN_STORE[plan_id] = {
    "title": result["title"],
    "tasks": tasks,
    "summary": result["summary"],
    "diagram": result.get("diagram", ""),   # NEW
    "revision": 1
}

    return AgentResponse(
    is_plan=True,
    plan_id=plan_id,
    title=result["title"],
    summary=result["summary"],
    tasks=tasks,
    diagram=result.get("diagram", ""),   # NEW
    message="Let me know if you'd like anything changed, or confirm to generate the document.",
    revision=1,
)


@app.post("/agent/refine", response_model=RefineResponse)
def refine(payload: RefineRequest):
    """Step 2 (optional, repeatable): adjust the plan based on free-text feedback."""
    existing = PLAN_STORE.get(payload.plan_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Plan not found. It may have expired — try creating a new one.")

    try:
        result = refine_plan(existing["title"], existing["tasks"], payload.feedback)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Refinement failed: {e}")

    tasks = [TaskItem(**t) for t in result["tasks"]]

    # Only bump the revision number if something actually changed — a
    # casual message like "ok thanks" that produces an identical plan
    # back from the LLM shouldn't count as a real revision.
    old_snapshot = (existing["title"], tuple((t.task, t.notes, t.status, t.deadline) for t in existing["tasks"]))
    new_snapshot = (result["title"], tuple((t["task"], t["notes"], t["status"], t["deadline"]) for t in result["tasks"]))
    plan_changed = old_snapshot != new_snapshot

    new_revision = existing.get("revision", 1) + 1 if plan_changed else existing.get("revision", 1)
    PLAN_STORE[payload.plan_id] = {
        "title": result["title"], "tasks": tasks, "summary": result["summary"], "revision": new_revision,
    }

    reply_message = (
        "Updated the plan based on your feedback. Anything else, or shall I generate the document?"
        if plan_changed else
        "No changes needed there. Anything else, or shall I generate the document?"
    )

    return RefineResponse(
        plan_id=payload.plan_id,
        title=result["title"],
        summary=result["summary"],
        tasks=tasks,
        message=reply_message,
        revision=new_revision,
    )


@app.post("/agent/update-tasks", response_model=UpdateTasksResponse)
def update_tasks(payload: UpdateTasksRequest):
    """
    No LLM call — just overwrites the stored plan's tasks with whatever
    the user edited directly in the UI (e.g. status dropdowns). Called
    right before /generate-doc so the final document reflects the latest
    edits even if the user never went through a /agent/refine round-trip.
    """
    existing = PLAN_STORE.get(payload.plan_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Plan not found. It may have expired — try creating a new one.")

    existing["tasks"] = payload.tasks
    return UpdateTasksResponse(plan_id=payload.plan_id, message="Tasks updated.")


@app.post("/generate-doc", response_model=GenerateDocResponse)
def generate_doc(payload: GenerateDocRequest):
    """Step 3: only now do we write the actual .docx file, once the user is happy."""
    plan = PLAN_STORE.get(payload.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found. It may have expired — try creating a new one.")

    tasks_as_dicts = [t.model_dump() for t in plan["tasks"]]
    filename = build_document(
        plan_id=payload.plan_id,          # FIXED — was undefined `plan_id`
        title=plan["title"],
        summary=plan.get("summary", ""),
        tasks=tasks_as_dicts,              # FIXED — was `plan["tasks"]` (TaskItem objects, not dicts)
        diagram=plan.get("diagram", "")
    )

    return GenerateDocResponse(
        doc_filename=filename,
        download_url=f"/output/{filename}",
        message="Document generated successfully.",
    )
# Serve generated .docx files for download
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")


@app.get("/api/status")
def status():
    return {"status": "ok", "docs": "/docs"}


# Serve the frontend (index.html, style.css, script.js) from the same
# service, so in production the frontend and backend share one origin —
# which is what script.js's API_BASE logic (window.location.origin) expects.
# Tries a couple of likely folder names/casings since repo structure varies.
import os

_here = os.path.dirname(__file__)
_frontend_candidates = ["Frontend", "frontend", "../Frontend", "../frontend"]
_frontend_dir = next(
    (os.path.join(_here, c) for c in _frontend_candidates if os.path.isdir(os.path.join(_here, c))),
    None,
)

if _frontend_dir:
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
else:
    print("WARNING: frontend folder not found next to main.py — only the API will be served.")