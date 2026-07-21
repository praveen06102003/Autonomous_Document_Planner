"""
Pydantic models — define the exact shape of every request/response
that flows between frontend <-> FastAPI <-> LLM.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ---------- Shared building block ----------

class TaskItem(BaseModel):
    """One row in the task table (task / notes / status / deadline)."""
    task: str
    notes: str = ""
    status: str = "Not started"
    deadline: str = ""


# ---------- POST /agent ----------

class AgentRequest(BaseModel):
    request: str = Field(..., min_length=1, description="Natural language request from the user")


class AgentResponse(BaseModel):
    is_plan: bool = True
    plan_id: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    tasks: list[TaskItem] = []
    diagram: Optional[str] = ""   # NEW — Mermaid syntax, empty string if not applicable
    message: str
    revision: int = 1

# ---------- POST /agent/refine ----------

class RefineRequest(BaseModel):
    plan_id: str
    feedback: str = Field(..., min_length=1, description="Free-text feedback on what to change")


class RefineResponse(BaseModel):
    plan_id: str
    title: str
    summary: str
    tasks: list[TaskItem]
    message: str
    revision: int


# ---------- POST /agent/update-tasks ----------
# No LLM call here — just overwrites stored tasks with whatever the user
# edited directly in the UI (e.g. status dropdowns), so /generate-doc
# reflects the latest state without needing another refine round-trip.

class UpdateTasksRequest(BaseModel):
    plan_id: str
    tasks: list[TaskItem]


class UpdateTasksResponse(BaseModel):
    plan_id: str
    message: str


# ---------- POST /generate-doc ----------

class GenerateDocRequest(BaseModel):
    plan_id: str


class GenerateDocResponse(BaseModel):
    doc_filename: str
    download_url: str
    message: str