# Design Decisions

## Backend — FastAPI

Lightweight, async-friendly, and integrates cleanly with the Groq client and
Pydantic request/response models. The `/chat` endpoint is the only route the
chatbot depends on; `/dashboard` and `/dataset-info` are simple, separate
summary endpoints unrelated to the natural-language flow.

## Frontend — Streamlit

Chosen for fast dashboard iteration without hand-rolling frontend
infrastructure. The chat UI keeps all state in `st.session_state` (per
browser session, not persisted to disk), and renders whatever Plotly figure
JSON the backend returns.

## Data Processing — Pandas

All filtering, grouping, and aggregation (`tools.py`, `chart_generator.py`)
is done in Pandas, driven entirely by the arguments the LLM supplies through
tool calling.

## Visualization — Plotly

Used for interactive line/bar/scatter charts, sent to the frontend as JSON
(`fig.to_json()`) and re-hydrated with `plotly.io.from_json` on the Streamlit
side.

## LLM — Groq (`llama-3.3-70b-versatile`)

The only Groq model constraint satisfied is tool calling support, which this
model has. `temperature=0.2` is used to keep chart/filter decisions
consistent rather than creative.

---

## How the chatbot decides what to visualize

There is **no hardcoded question → chart mapping**. Instead, the LLM is
given a single tool, `analyze_yield`, with a rich parameter schema
(`chart_type`, `x_axis`, `series_by`, `metric`, `countries`, `crops`,
`year_start`/`year_end`, `top_n`) and a system prompt that explains, in
plain language, *when* each parameter should be used — e.g. `chart_type:
"line"` with `x_axis: "year"` for trends, `"bar"` with `x_axis: "country"`
or `"crop"` for rankings, `"scatter"` for relationships between two
factors, or `"none"` for a plain numeric answer.

The model is also grounded with the dataset's actual country and crop
names (pulled from the data itself at startup) so it uses correct spelling
in its tool calls rather than guessing.

`chart_generator.py`'s `build_chart()` is a single flexible function that
just executes whatever combination of parameters the model chose — there
are no separate hardcoded functions per chart type, and no keyword-based
`if "yield" in query` branching anywhere in the pipeline. The interpretation
step is entirely the model's; the code only executes it.

## How session memory is handled

The frontend sends the **full prior conversation** on every request — there
is no server-side "last known filters" state to get out of sync. The
trickier part is that a short prose answer like *"Wheat yield in India
averaged 28,000 hg/ha"* doesn't tell the model, in a structurally reliable
way, what filters actually produced it.

To fix that, every assistant turn that called `analyze_yield` has its exact
tool arguments recorded (`applied_filters`) and echoed back by the frontend
on the next request. Before sending history to the model, `llm.py` appends a
machine-readable note to that turn's content:

```
[Filters used for this answer: {"countries": ["India"], "crops": ["Wheat"], ...}]
```

The system prompt tells the model to treat this note as ground truth and use
it directly for follow-ups — rather than re-deriving filters from its own
earlier prose, which is what caused follow-ups to silently drop or guess
wrong filters in early testing.

The prompt also gives explicit rules for *when* to carry filters forward vs.
treat a question as fresh: pronouns/incomplete phrasing ("that", "it",
"instead", "just the last five years") signal a follow-up; a self-contained
new request (new metric, new country/crop, or a general question) is treated
as fresh even if a chart was just shown. When genuinely ambiguous, the
prompt biases toward treating it as a new question — an unexpected fresh
answer is easier for a user to notice and correct than a silently
mis-filtered one.

## How questions without a clean answer are handled

A few different failure modes are handled explicitly rather than left to
produce a confusing or wrong-looking answer:

- **Unrecognized country/crop names.** User (or model) phrasing rarely
  matches the dataset's exact spelling (e.g. "rice" vs. "Rice, paddy", "USA"
  vs. "United States of America"). `tools.py`'s `_resolve_names()` matches
  loosely-typed names against the real dataset values (exact
  case-insensitive match → substring match → fuzzy match) *before*
  filtering, so a near-miss spelling doesn't silently filter out to zero
  rows with no explanation. The system prompt separately instructs the
  model to only tell a user something "isn't in the dataset" after checking
  it against the real list — never guessed.

- **Filters that legitimately match nothing.** If a valid combination of
  filters still returns no rows, both the numeric-answer path and the chart
  path return an explicit `{"error": "No matching data found for the given
  filters."}` rather than crashing or returning an empty/misleading chart.

- **LLM/API failures.** Groq-specific exceptions (rate limit, auth failure,
  connection error, generic API error) are caught and translated into a
  short, user-facing chat message instead of surfacing as a raw 500 or the
  frontend's generic "Unable to connect to backend."

- **Redundant grouping.** If a request would group a chart by the same
  field on both axes (e.g. "break that down by crop" on a chart already
  split by crop), the duplicate grouping is dropped rather than raising a
  pandas error, since splitting the same field twice is redundant anyway.