# Design Decisions

## Backend — FastAPI

Lightweight, async-friendly, and integrates cleanly with the Groq client and
Pydantic request/response models. `/chat` is the only route the chatbot
depends on; `/dashboard` and `/dataset-info` are simple, separate summary
endpoints unrelated to the natural-language flow.

## Frontend — Streamlit

Chosen for fast UI iteration without hand-rolling frontend infrastructure.
The UI supports multiple named conversations (create/switch/delete) in a
sidebar, similar to a standard chat app, with all state kept in
`st.session_state` — nothing is written to disk, so a full browser reload
starts fresh. Plotly figure JSON returned by the backend is re-hydrated with
`plotly.io.from_json` and rendered inline in the relevant chat bubble.

## Data Processing — Pandas

All filtering, grouping, and aggregation (`tools.py`, `chart_generator.py`)
is done in Pandas, driven entirely by the arguments the LLM supplies through
tool calling. `clean_data.py` is a separate one-off script (not part of the
running app) that drops the stray index column and duplicate rows from the
raw Kaggle CSV to produce `data/cleaned_yield_df.csv`.

## Visualization — Plotly

Used for line, bar, pie, box, and scatter charts, sent to the frontend as
JSON (`fig.to_json()`) and re-hydrated on the Streamlit side. All charts
share a common style pass (`style_chart()`) for consistent fonts, gridlines,
and layout.

## LLM — Groq (`llama-3.1-8b-instant`)

Originally `llama-3.3-70b-versatile`; switched to the 8B model because Groq's
free tier gives it a much higher daily request cap, which matters for a
chatbot that can make 2-4 API calls per user turn (tool-call round trips).
Both models support tool calling, which is the only hard requirement.
`temperature=0.2` is used to keep chart/filter decisions consistent rather
than creative. If tool-call accuracy noticeably drops on tricky multi-filter
questions, the swap back to the 70B model is a one-line change in `llm.py`.

To keep the system prompt cheap, the full country list (101 countries) is
**not** inlined in it — that alone used to add ~270 tokens to every single
Groq call, which burned through rate limits fast given multiple calls per
turn. Only the crop list (10 items) is inlined, since it's small and keeps
chart titles/wording using the dataset's own spelling. Country matching is
left entirely to the fuzzy resolver in `tools.py`; the model just passes
countries through as the user typed them.

---

## How the chatbot decides what to visualize

There is **no hardcoded question → chart mapping**. Instead, the LLM is
given a single tool, `analyze_yield`, with a rich parameter schema
(`chart_type`, `x_axis`, `series_by`, `metric`, `countries`, `crops`,
`year_start`/`year_end`, `top_n`, `sort_order`) and a system prompt that
explains, in plain language, *when* each parameter should be used:

- `chart_type: "none"` for a plain numeric answer about the filtered
  records as a whole (overall average, or a single min/max record) — never
  for a per-category "which one" question.
- `chart_type: "bar"` with `top_n=1` for "which country/crop has the
  highest/lowest ___" ranking questions — required whenever the question
  starts with or implies "which", since `"none"` has no per-category
  breakdown.
- `chart_type: "line"` with `x_axis="year"` for trends.
- `chart_type: "bar"` (without `top_n=1`) for open-ended rankings/
  comparisons.
- `chart_type: "pie"` only when the user explicitly asks for a pie chart or
  a proportion/share breakdown — never chosen just because a bar chart
  could also answer the question.
- `chart_type: "box"` for spread/distribution/variability/outlier
  questions, not plain rankings by average.
- `chart_type: "scatter"` for relationships between two factors, with
  `metric` always fixed to `"yield"` (the Y-axis) and `x_axis` set to the
  other factor.
- `series_by` to split one chart into multiple lines/bars (e.g. "break that
  down by crop").
- `sort_order="asc"` for "lowest"/"worst"/"bottom N" rankings — without it,
  rankings default to highest-first, which silently answers the opposite
  question.

The model is also grounded with the dataset's actual crop names (pulled
from the data at startup) so it uses correct spelling in tool calls;
country names are resolved fuzzily downstream instead (see below), so the
full country list doesn't need to be in the prompt.

`chart_generator.py`'s `build_chart()` is a single flexible function that
executes whatever combination of parameters the model chose — there are no
separate hardcoded functions per chart type, and no keyword-based
`if "yield" in query` branching anywhere in the pipeline. The interpretation
step is entirely the model's; the code only executes it.

### Keeping the model grounded in real numbers, not guesses

Several fields in `tools.py`/`chart_generator.py`'s return values exist
specifically to stop the model from filling gaps with its own (possibly
wrong) general knowledge:

- **`chart_type="none"` results** include the full min/max row
  (`minimum_country`, `minimum_crop`, `minimum_year`, and the `maximum_*`
  equivalents), not just bare numbers — otherwise "what's the lowest
  yield" gives the model a number with no record to attribute it to.
- **`chart_type="bar"`/`"pie"` results** include a `breakdown` list of the
  exact `{category, value}` pairs actually plotted, in chart order. The
  separate `mean_value` field is the *blended* average across the whole
  filtered set (e.g. all crops in a country combined) and is explicitly
  **not** to be quoted as any single category's value — the prompt calls
  this out directly, since early testing showed the model doing exactly
  that.
- **`chart_type="box"` results** include per-category median/min/max
  (not mean, which isn't what a boxplot's center line represents), so the
  model describes spread using real numbers instead of inventing one.

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
wrong filters in early testing. Since the note is meant purely as internal
bookkeeping, `llm.py` also strips it back out (`_strip_filters_note`) if the
model ever imitates the pattern and tacks one onto its own new answer.

The prompt also gives explicit rules for *when* to carry filters forward vs.
treat a question as fresh: pronouns/incomplete phrasing ("that", "it",
"instead", "just the last five years") signal a follow-up; a self-contained
new request (new metric, new country/crop, or a general question) is treated
as fresh even if a chart was just shown. When genuinely ambiguous, the
prompt biases toward treating it as a new question — an unexpected fresh
answer is easier for a user to notice and correct than a silently
mis-filtered one.

To bound cost, only the last `MAX_HISTORY_MESSAGES` (12) messages are sent
to the model per call — without this, `history` grows forever across a long
chat, and every API call within a turn's tool-call loop would resend the
whole thing, eating into Groq's rate limits fast. 12 messages covers roughly
the last 6 user/assistant exchanges, which is enough context for the
follow-up-vs-fresh reasoning the prompt asks for.

On the frontend, session memory is scoped **per chat**, not globally: the
sidebar supports multiple independent conversations (create/switch/delete),
and `submit_question()` only builds the history payload from the currently
active chat's messages, so switching chats doesn't leak filters or context
from a different conversation.

## How questions without a clean answer are handled

A few different failure modes are handled explicitly rather than left to
produce a confusing or wrong-looking answer:

- **Unrecognized country/crop names.** User (or model) phrasing rarely
  matches the dataset's exact spelling (e.g. "rice" vs. "Rice, paddy", "USA"
  vs. "United States of America"). `tools.py`'s `_resolve_names()` matches
  loosely-typed names against the real dataset values (exact
  case-insensitive match → substring match → fuzzy match, in that order)
  *before* filtering, so a near-miss spelling doesn't silently filter out to
  zero rows with no explanation. If nothing matches at all, the original
  value is kept as-is so the downstream filter legitimately returns "no
  data" for it — instead of it being dropped with no trace. The system
  prompt separately instructs the model to only tell a user something
  "isn't in the dataset" after seeing an actual empty tool result — never
  guessed up front.

- **Filters that legitimately match nothing.** If a valid combination of
  filters still returns no rows, both the numeric-answer path and the chart
  path return an explicit `{"error": "No matching data found for the given
  filters."}` rather than crashing or returning an empty/misleading chart.

- **LLM/API failures.** Groq-specific exceptions (rate limit, auth failure,
  connection error, generic API error) are caught in `llm.py` and translated
  into a short, user-facing chat message — including, for rate limits, the
  actual reset time pulled from Groq's response headers when available —
  instead of surfacing as a raw 500 or the frontend's generic "unable to
  connect to backend."

- **Backend unreachable / slow to wake / bad response.** The Streamlit side
  wraps its request to the backend in explicit handlers for timeout,
  connection error, HTTP error, and any other exception, each producing a
  distinct, readable message in the chat (e.g. calling out Render's free-tier
  cold start on timeout) rather than letting Streamlit surface a raw
  traceback.

- **Redundant grouping.** If a request would group a chart by the same
  field on both axes (e.g. "break that down by crop" on a chart already
  split by crop), the duplicate grouping is dropped rather than raising a
  pandas error, since splitting the same field twice is redundant anyway.