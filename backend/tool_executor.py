from backend.tools import filter_dataset, compute_summary, dataset_overview
from backend.chart_generator import build_chart


def execute_tool(name, args):
    """
    Executes a tool the LLM chose to call. Returns a dict with:
      - "summary": small JSON-safe result fed back to the LLM as the
        tool result (so it can write a sensible text answer)
      - "chart_json": (optional) full Plotly figure JSON, sent to the
        frontend to render - NOT sent back to the LLM (too large,
        and the LLM doesn't need to see raw chart JSON to describe it)
    """

    if name == "dataset_overview":

        return {"summary": dataset_overview()}

    if name == "analyze_yield":

        chart_type = args.get("chart_type", "none")

        if not chart_type or chart_type == "none":

            filtered = filter_dataset(
                countries=args.get("countries"),
                crops=args.get("crops"),
                year_start=args.get("year_start"),
                year_end=args.get("year_end"),
            )

            if filtered.empty:
                return {"summary": {"error": "No matching data found for the given filters."}}

            return {"summary": compute_summary(filtered, metric=args.get("metric", "yield"))}

        result = build_chart(**args)

        if "error" in result:
            return {"summary": result}

        fig = result.pop("fig")

        return {
            "chart_json": fig.to_json(),
            "summary": result,
        }

    return {"summary": {"error": f"Unknown tool: {name}"}}