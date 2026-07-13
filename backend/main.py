from typing import List

from fastapi import FastAPI
from pydantic import BaseModel

from backend.data_loader import load_data
from backend.llm import run_agent
from backend.tool_executor import execute_tool
from backend.tools import (
    dataset_overview,
    get_average_yield,
    get_maximum_yield,
    get_country_count,
    get_crop_count,
)

# ==========================================================
# FASTAPI
# ==========================================================

app = FastAPI()

df = load_data()


# ==========================================================
# REQUEST MODELS
# ==========================================================

class ChatMessage(BaseModel):
    role: str
    content: str
    # The exact analyze_yield arguments that produced this assistant
    # message (None for user messages, or for assistant messages that
    # didn't call analyze_yield). Sent back to us by the frontend on
    # every turn so the LLM has the REAL filters it used last turn
    # instead of having to re-guess them from its own prose answer.
    filters: dict | None = None


class ChatRequest(BaseModel):

    question: str

    # Full prior conversation (role/content only). This IS the
    # session memory - sent fresh every turn so the LLM can
    # reason over the whole thread itself, rather than us
    # tracking a fixed set of "last filters" server-side.
    history: List[ChatMessage] = []


# ==========================================================
# HOME
# ==========================================================

@app.get("/")
def home():
    return {"message": "Welcome to FarmWise AI"}


# ==========================================================
# DATASET INFO
# ==========================================================

@app.get("/dataset-info")
def dataset_info():
    return {"rows": int(df.shape[0]), "columns": list(df.columns)}


# ==========================================================
# DASHBOARD (plain summary widget - not part of the chatbot)
# ==========================================================

@app.get("/dashboard")
def dashboard():
    return {
        "rows": int(df.shape[0]),
        "columns": len(df.columns),
        "countries": get_country_count(),
        "crops": get_crop_count(),
        "average_yield": get_average_yield(),
        "highest_yield": get_maximum_yield()["Yield"],
    }


# ==========================================================
# CHAT
# ==========================================================
# No intent classification, no fixed if/elif chart mapping.
# The LLM decides everything (metric, chart type, filters,
# grouping) via real tool calling in run_agent().
# ==========================================================

@app.post("/chat")
def chat(request: ChatRequest):

    history = [
        {"role": m.role, "content": m.content, "filters": m.filters}
        for m in request.history
    ]

    history.append({"role": "user", "content": request.question, "filters": None})

    answer, chart_json, chart_summary, applied_filters = run_agent(
        history=history,
        tool_executor=execute_tool,
    )

    return {
        "answer": answer,
        "chart_json": chart_json,
        "chart_summary": chart_summary,
        # The exact analyze_yield args used THIS turn (or None if no
        # chart/stat tool was called). The frontend stores this on the
        # assistant message and echoes it back as `filters` next turn.
        "applied_filters": applied_filters,
    }








