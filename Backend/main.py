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
    """Step 1: understand the request and autonomously draft a task plan."""
    try:
        result = generate_plan(payload.request)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Planning failed: {e}")

    plan_id = str(uuid.uuid4())[:8]
    tasks = [TaskItem(**t) for t in result["tasks"]]
    PLAN_STORE[plan_id] = {"title": result["title"], "tasks": tasks}

    return AgentResponse(
        plan_id=plan_id,
        title=result["title"],
        tasks=tasks,
        message="Here's a draft plan. Let me know if you'd like anything changed, or confirm to generate the document.",
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
    PLAN_STORE[payload.plan_id] = {"title": result["title"], "tasks": tasks}

    return RefineResponse(
        plan_id=payload.plan_id,
        title=result["title"],
        tasks=tasks,
        message="Updated the plan based on your feedback. Anything else, or shall I generate the document?",
    )


@app.post("/generate-doc", response_model=GenerateDocResponse)
def generate_doc(payload: GenerateDocRequest):
    """Step 3: only now do we write the actual .docx file, once the user is happy."""
    plan = PLAN_STORE.get(payload.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found. It may have expired — try creating a new one.")

    tasks_as_dicts = [t.model_dump() for t in plan["tasks"]]
    filename = build_document(payload.plan_id, plan["title"], tasks_as_dicts)

    return GenerateDocResponse(
        doc_filename=filename,
        download_url=f"/output/{filename}",
        message="Document generated successfully.",
    )


# Serve generated .docx files for download
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}