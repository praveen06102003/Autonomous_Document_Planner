"""
doc_builder.py — turns an approved plan (title + tasks) into a polished
.docx file using python-docx. This only runs ONCE, after the user has
confirmed the plan is final — not on every planning/refine step.
"""

import os
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def build_document(plan_id: str, title: str, tasks: list[dict]) -> str:
    """
    Builds a Word doc with a title, generated-on date, and a task table.
    Returns the filename (not full path) so main.py can build a download URL.
    """
    doc = Document()

    # Title
    heading = doc.add_heading(title, level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Metadata line
    meta = doc.add_paragraph()
    meta_run = meta.add_run(f"Generated on {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    meta_run.italic = True
    meta_run.font.size = Pt(9)

    doc.add_paragraph()  # spacer

    # Task table
    table = doc.add_table(rows=1, cols=4)
    table.style = "Light Grid Accent 1"

    header_cells = table.rows[0].cells
    headers = ["Task", "Notes", "Status", "Deadline"]
    for cell, text in zip(header_cells, headers):
        cell.text = text
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True

    for task in tasks:
        row_cells = table.add_row().cells
        row_cells[0].text = task.get("task", "")
        row_cells[1].text = task.get("notes", "")
        row_cells[2].text = task.get("status", "Not started")
        row_cells[3].text = task.get("deadline", "")

    # Column widths
    widths = [Inches(2.0), Inches(2.8), Inches(1.1), Inches(1.1)]
    for row in table.rows:
        for idx, width in enumerate(widths):
            row.cells[idx].width = width

    filename = f"{plan_id}.docx"
    filepath = os.path.join(OUTPUT_DIR, filename)
    doc.save(filepath)

    return filename