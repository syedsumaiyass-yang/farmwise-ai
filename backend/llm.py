import os
import json
import re

import groq
from groq import Groq
from dotenv import load_dotenv

from backend.data_loader import load_data

load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

# llama-3.1-8b-instant: swapped from llama-3.3-70b-versatile. Both support
# tool calling (the assessment brief lists 70B only as an example, not a
# requirement). The 8B model has a much higher free-tier daily request cap
# on Groq, which matters a lot for a chatbot that can make 2-4 API calls
# per user turn (tool-call round trips). If tool-call accuracy noticeably
# drops for tricky multi-filter questions, switch back to the 70B model -
# but test this first since the token/rate savings are significant.
MODEL = "llama-3.1-8b-instant"

_df = load_data()

COUNTRIES = sorted(_df["Area"].dropna().unique().tolist())
CROPS = sorted(_df["Item"].dropna().unique().tolist())
MIN_YEAR = int(_df["Year"].min())
MAX_YEAR = int(_df["Year"].max())


# ==========================================================
# SYSTEM PROMPT
# ==========================================================
# The model is grounded with the ACTUAL crop names in this
# dataset (only 10, so it's cheap and keeps chart titles/wording
# using the dataset's own spelling e.g. "Rice, paddy"), and is
# given the reasoning rules for follow-up questions - there is
# no fixed list of "intents" here, the model decides every
# parameter of every tool call itself.
#
# NOTE: the full 101-country list used to be inlined here too.
# It added ~270 tokens to EVERY single Groq API call (and
# run_agent can make 2-4 calls per user turn), which was the
# main driver of burning through Groq's rate limits after just
# one or two messages. Country-name matching is handled
# entirely downstream by the fuzzy resolver in
# tools.py::_resolve_names, so the model doesn't need the list
# memorized - it just passes the country through as typed, and
# a "no matching data" tool result is itself the signal that a
# country isn't in the dataset.
# ==========================================================

SYSTEM_PROMPT = f"""
You are FarmWise AI, an agricultural data analyst assistant working with a
global crop yield dataset ({MIN_YEAR}-{MAX_YEAR}, {len(COUNTRIES)} countries,
{len(CROPS)} crops).

Crops in this dataset (use EXACT spelling in tool calls):
{", ".join(CROPS)}

Country names are matched fuzzily downstream (typos, casing, and partial
names like "usa" are all resolved automatically), so pass countries through
as the user wrote them - you do NOT need to memorize a country list.

You have two tools:

- analyze_yield: get a numeric answer OR a chart (line/bar/scatter) about
  yield, rainfall, temperature, or pesticide use, with any combination of
  country/crop/year filters and optional grouping.
- dataset_overview: general facts about the dataset itself (rows, years
  covered, how many countries/crops exist).

Guidelines for analyze_yield:
- chart_type="none" for a plain numeric answer about the FILTERED records as
  a whole - overall average, or the single highest/lowest INDIVIDUAL RECORD
  (e.g. "what's the average yield", "highest yield ever recorded", "what
  was the lowest yield"). This does NOT group or rank by category - it's
  one number (or one record) across everything matched by the filters.
- chart_type="bar" with top_n=1 for "WHICH country/crop has the highest/
  lowest (average) ___" questions - anything asking to compare or rank
  categories against each other, not just report one filtered number. Set
  x_axis="crop" or "country" to match what's being asked, and sort_order
  ("desc" for highest, "asc" for lowest). This is REQUIRED whenever the
  question starts with or implies "which" - chart_type="none" has no
  per-category breakdown and cannot correctly answer a "which ___" question.
  - "highest yield ever recorded" -> chart_type="none" (one record, not a
    category ranking).
  - "which crop has the highest yield in India" -> chart_type="bar",
    x_axis="crop", top_n=1, sort_order="desc", countries=["India"] (ranks
    crops by their average yield, since "which crop" needs a per-crop
    comparison, not a single row).
- chart_type="line" for trends over time -> x_axis="year".
- chart_type="bar" (without top_n=1) for open-ended rankings or comparisons
  the user wants to see laid out -> x_axis="country" or "crop".
- chart_type="pie" ONLY when the user explicitly says "pie chart" (or
  clearly asks for a proportion/percentage/share breakdown) - never choose
  it just because a question could also be answered with a bar chart. Use
  x_axis="crop" or "country" the same way as bar. Example: "pie chart for
  yield in India" -> chart_type="pie", x_axis="crop", countries=["India"].
- chart_type="scatter" for relationships between two factors and yield.
  metric is ALWAYS "yield" (it is always the Y-axis for scatter plots -
  yield is what's being explained/predicted). x_axis must be the OTHER
  factor: "rainfall", "temperature", or "pesticides" - NEVER "yield".
  Example: "rainfall vs yield" -> chart_type="scatter", metric="yield",
  x_axis="rainfall". Do NOT reverse these two fields.
- Use series_by to break ONE chart into multiple lines/bars - e.g. "break
  that down by crop" on a country's yield trend means x_axis="year",
  series_by="crop", countries=[that country].
- Use top_n to limit rankings (e.g. "top 10 crops" -> top_n=10). For
  "lowest"/"worst"/"bottom N" rankings, also set sort_order="asc" - without
  it, rankings default to highest-first, which would return the opposite
  of what was asked.
- Use countries/crops arrays to filter or compare specific ones.
- Use year_start/year_end for date ranges, including relative ones like
  "last five years" (resolve against {MAX_YEAR}, the latest year available)
  or "past decade".

For plain numeric answers (chart_type="none"), the tool result includes
minimum/maximum values ALREADY paired with the exact country/crop/year of
that single record (minimum_country, minimum_crop, minimum_year, and the
maximum_* equivalents). Always use those fields when naming which country/
crop that single record belongs to - never guess or recall a country from
your own general knowledge, since only the tool result reflects this
dataset. For "which ___ has the highest/lowest" ranking questions, use the
chart_type="bar" + top_n=1 result instead (see above) - its category label
and value are the actual answer; do not mix it with the chart_type="none"
fields, which describe a single record, not a per-category ranking.

For chart_type="bar" results, use the "breakdown" field (a list of
{{"category": ..., "value": ...}} pairs, in the same order as the chart) as
the ONLY source for category names and their values - it reflects exactly
what's plotted. Do NOT use "mean_value" to describe a specific category:
"mean_value" is the blended average across the ENTIRE filtered set (e.g.
all crops in a country combined), not any single bar's value, and will be
wrong if quoted as one category's number. A "breakdown" value is itself
already an average across all matching years - it is NOT tied to any one
year, so never attach a specific year to it (e.g. never say "yield of X in
year Y" for a breakdown value; just report the category and its value).

This is a MULTI-TURN conversation - reason over the full message history:
- Base each tool call PRIMARILY on the CURRENT question's own wording.
- Only reuse countries/crops/years from EARLIER turns when the current
  question doesn't specify its own AND clearly depends on them - e.g. it
  uses words like "that", "it", "them", "instead", "also", "now just",
  "only", or is otherwise incomplete alone ("just the last five years",
  "break that down by crop", "now compare them", "what about rainfall
  instead").
- If the current question is a self-contained, unrelated request (a new
  metric, new country/crop, or a general question like "top crops by
  yield"), do NOT carry over old filters - treat it as fresh, even if a
  chart was just shown.
- When genuinely unsure whether something is a follow-up or a new topic,
  prefer treating it as NEW (ignore old filters) - a wrong fresh answer is
  easier for the user to correct than a silently mis-filtered one.

If a crop the user mentions is NOT in the crop list above, tell them clearly
it isn't in this dataset instead of guessing or calling a tool with a made-up
name. For countries, you don't have a memorized list - always call the tool
with the country name as given (fuzzy matching handles typos/casing/partial
names downstream). Only tell the user a country "isn't in the dataset" if
the tool result actually comes back empty/no-matching-data for it - never
claim this up front without having called the tool and seen that result.

Past assistant turns may include a trailing note like "[Filters used for
this answer: {{...}}]". That note is the GROUND TRUTH of what was actually
filtered/charted last turn - trust it completely and use it as-is when a
follow-up depends on earlier turns. Do not re-derive filters from your own
prior prose, and never contradict it (e.g. never say a country "isn't in
the dataset" if that same country appears in a filters note from a turn
that already succeeded).

Your final text answer must always be consistent with the tool call you
actually just made in this turn. Never describe a filter or chart as
missing/unavailable/failed if your own tool call this turn succeeded with
that filter applied.

Keep your final text answers concise and conversational - 1 to 3 sentences.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_yield",
            "description": (
                "Get a numeric answer or a chart (line/bar/scatter) about "
                "crop yield or related factors (rainfall, temperature, "
                "pesticides), with optional country/crop/year filters and "
                "grouping."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "enum": ["yield", "rainfall", "temperature", "pesticides"],
                        "description": "The value being measured (y-axis). Defaults to yield."
                    },
                    "chart_type": {
                        "type": "string",
                        "enum": ["none", "line", "bar", "pie", "scatter"],
                        "description": (
                            "'none' for a plain numeric/stat answer, 'line' for "
                            "trends over time, 'bar' for rankings/comparisons, "
                            "'pie' for a part-to-whole breakdown (e.g. each "
                            "crop's share of total/average yield in a country) "
                            "- ONLY when the user explicitly asks for a pie "
                            "chart, since bar is clearer for most comparisons, "
                            "'scatter' for relationships between two factors."
                        )
                    },
                    "x_axis": {
                        "type": "string",
                        "enum": ["year", "country", "crop", "rainfall", "temperature", "pesticides"],
                        "description": (
                            "What varies along the x-axis. 'year' for trends, "
                            "'country' or 'crop' for rankings/comparisons, or "
                            "'rainfall'/'temperature'/'pesticides' for scatter "
                            "plots (the factor being compared against yield). "
                            "Never set this to 'yield' - yield always goes in "
                            "the separate 'metric' field instead."
                        )
                    },
                    "series_by": {
                        "type": "string",
                        "enum": ["none", "country", "crop"],
                        "description": (
                            "'none' (default) for no grouping. Only set to "
                            "'country' or 'crop' to split ONE chart into "
                            "multiple lines/bars - e.g. for requests like "
                            "'break that down by crop'."
                        )
                    },
                    "countries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Country name(s) to filter to, using exact dataset spelling."
                    },
                    "crops": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Crop name(s) to filter to, using exact dataset spelling."
                    },
                    "year_start": {
                        "type": "integer",
                        "description": "Earliest year to include (inclusive)."
                    },
                    "year_end": {
                        "type": "integer",
                        "description": "Latest year to include (inclusive)."
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Limit a ranking chart to the top (or, with sort_order='asc', bottom) N results."
                    },
                    "sort_order": {
                        "type": "string",
                        "enum": ["asc", "desc"],
                        "description": (
                            "Sort direction for bar-chart rankings. 'desc' (default) "
                            "for highest-first/top-N. Use 'asc' whenever the question "
                            "asks for the lowest/worst/smallest/bottom N - e.g. "
                            "'lowest yield', 'worst 5 countries'."
                        )
                    },
                    "title": {
                        "type": "string",
                        "description": "A short, human-readable chart title."
                    },
                },
                "required": ["chart_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dataset_overview",
            "description": (
                "Get general facts about the dataset itself - number of rows, "
                "years covered, how many countries and crops exist."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# The model is shown "[Filters used for this answer: {...}]" notes inside
# PAST assistant turns (see the loop in run_agent) so it can read back the
# real filters on follow-ups. It sometimes imitates that pattern and tacks
# the same note onto its OWN new answer too - which is meant purely as
# internal/history bookkeeping, not something the user should see in the
# chat bubble. Strip it out of whatever text we're about to return.
_FILTERS_NOTE_RE = re.compile(
    r"\s*\[Filters used for this answer:.*\]\s*\Z", re.DOTALL | re.IGNORECASE
)


def _strip_filters_note(text):

    if not text:
        return text

    return _FILTERS_NOTE_RE.sub("", text).strip()


def _extract_rate_limit_info(exc):
    """
    Groq (like the OpenAI SDK it's modeled on) attaches the raw HTTP
    response to rate-limit exceptions, which carries headers like:
      x-ratelimit-remaining-requests, x-ratelimit-remaining-tokens
      x-ratelimit-reset-requests, x-ratelimit-reset-tokens (e.g. "7.66s")
    These tell you exactly which limit was hit (RPM/TPM/RPD) and when
    it resets, instead of guessing. Falls back gracefully if the SDK
    version/exception shape doesn't expose them.
    """

    headers = getattr(getattr(exc, "response", None), "headers", None)

    if not headers:
        return None

    remaining_requests = headers.get("x-ratelimit-remaining-requests")
    remaining_tokens = headers.get("x-ratelimit-remaining-tokens")
    reset_requests = headers.get("x-ratelimit-reset-requests")
    reset_tokens = headers.get("x-ratelimit-reset-tokens")

    return {
        "remaining_requests": remaining_requests,
        "remaining_tokens": remaining_tokens,
        "reset_requests": reset_requests,
        "reset_tokens": reset_tokens,
    }


def _friendly_groq_error(exc):
    """
    Turn a Groq API exception into a short, user-facing chat message
    instead of letting it bubble up as an unhandled 500 (which the
    frontend then shows as a generic, misleading "Unable to connect
    to backend").

    The real exception is ALWAYS printed to server logs (Render's log
    tab) below, and now also included inline in the message itself
    while this is being debugged - a purely generic message made it
    impossible to tell a bad key apart from a bad request apart from
    a genuine outage. Trim the inline detail back out once everything
    is confirmed working end-to-end.
    """

    print(f"[FarmWise AI] Groq error: {type(exc).__name__}: {exc}")

    detail = getattr(exc, "message", None) or str(exc)
    status = getattr(exc, "status_code", None)

    if isinstance(exc, groq.RateLimitError):

        info = _extract_rate_limit_info(exc)

        if info:
            print(f"[Groq rate limit] {info}")

            reset_hint = info.get("reset_tokens") or info.get("reset_requests")

            if reset_hint:
                return (
                    f"⚠️ I've hit Groq's rate limit right now. It should reset "
                    f"in about {reset_hint} - please try again shortly."
                )

        return (
            "⚠️ I've hit the daily usage limit for the AI model right now. "
            "Please try again in a little while (check console.groq.com/settings/limits "
            "for exact reset time)."
        )

    if isinstance(exc, groq.AuthenticationError):
        return f"⚠️ Authentication with the AI service failed. Detail: {detail}"

    if isinstance(exc, groq.APIConnectionError):
        return f"⚠️ Couldn't reach the AI service. Detail: {detail}"

    if isinstance(exc, groq.APIStatusError):
        return f"⚠️ The AI service returned an error (status {status}). Detail: {detail}"

    return f"⚠️ Something went wrong while generating a response. Detail: {type(exc).__name__}: {exc}"


# Cap how many past turns (user+assistant messages, not tool-call
# round trips within a turn) get sent to the model. Without this,
# `history` grows forever across a long chat and every single API
# call - including the extra ones inside a turn's tool-call loop -
# resends the whole thing, which eats into the rate limit fast.
# 12 messages = last ~6 user/assistant exchanges, which is plenty
# of context for the "is this a follow-up" reasoning the prompt
# asks for.
MAX_HISTORY_MESSAGES = 12


def run_agent(history, tool_executor, max_tool_rounds=3):
    """
    history: list of {"role", "content", "filters"} - the full prior
             conversation, sent fresh every call. "filters" (assistant
             turns only) holds the exact analyze_yield args used to
             produce that turn's answer - this IS the session memory
             for follow-ups, not the prose in "content".
    tool_executor: callable(name, args_dict) -> dict result

    Returns: (answer_text, chart_json_or_None, chart_summary_or_None,
              applied_filters_or_None)
    """

    # Build the message list for the model. For any past assistant turn
    # that has recorded filters, append them to that turn's content as
    # an explicit, machine-readable note. Without this the model has to
    # infer "which country/metric/chart type did I just use" purely
    # from its own short prose answer, which is exactly what caused
    # follow-ups like "now break that down by crop" to silently drop or
    # guess the wrong filters.
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    trimmed_history = history[-MAX_HISTORY_MESSAGES:]

    for h in trimmed_history:

        content = h.get("content") or ""
        filters = h.get("filters")

        if h["role"] == "assistant" and filters:
            content += f"\n\n[Filters used for this answer: {json.dumps(filters, default=str)}]"

        messages.append({"role": h["role"], "content": content})

    chart_json = None
    chart_summary = None
    applied_filters = None

    for _ in range(max_tool_rounds):

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,
            )
        except groq.APIError as exc:
            return _friendly_groq_error(exc), chart_json, chart_summary, applied_filters

        msg = response.choices[0].message

        if not msg.tool_calls:
            return _strip_filters_note(msg.content), chart_json, chart_summary, applied_filters

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        for tool_call in msg.tool_calls:

            name = tool_call.function.name

            try:
                args = json.loads(tool_call.function.arguments)
            except Exception:
                args = {}

            result = tool_executor(name, args)

            if name == "analyze_yield":
                applied_filters = args

            if result.get("chart_json"):
                chart_json = result["chart_json"]
                chart_summary = result.get("summary")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": name,
                "content": json.dumps(result.get("summary", {}), default=str),
            })

    # Safety net: if we somehow exhausted max_tool_rounds without a final
    # text answer, ask once more without forcing further tool use.
    try:
        final = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.2,
        )
    except groq.APIError as exc:
        return _friendly_groq_error(exc), chart_json, chart_summary, applied_filters

    return _strip_filters_note(final.choices[0].message.content), chart_json, chart_summary, applied_filters