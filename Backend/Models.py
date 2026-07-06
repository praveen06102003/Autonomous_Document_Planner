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
    plan_id: str                 # used to reference this plan in /refine and /generate-doc
    title: str                   # short title the LLM derives for the doc, e.g. "RAG Project Plan"
    tasks: list[TaskItem]
    message: str                 # friendly note, e.g. "Here's a draft plan — let me know if you'd like changes."


# ---------- POST /agent/refine ----------

class RefineRequest(BaseModel):
    plan_id: str
    feedback: str = Field(..., min_length=1, description="Free-text feedback on what to change")


class RefineResponse(BaseModel):
    plan_id: str
    title: str
    tasks: list[TaskItem]
    message: str


# ---------- POST /generate-doc ----------

class GenerateDocRequest(BaseModel):
    plan_id: str


class GenerateDocResponse(BaseModel):
    doc_filename: str
    download_url: str
    message: str