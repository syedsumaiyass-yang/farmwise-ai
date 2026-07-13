import plotly.express as px

from backend.tools import filter_dataset, METRIC_COLUMN_MAP, X_AXIS_COLUMN_MAP


# ==========================================================
# COMMON LAYOUT
# ==========================================================

def style_chart(fig):

    fig.update_layout(

        template="plotly_white",

        title={
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 22}
        },

        font={
            "family": "Arial",
            "size": 14
        },

        hovermode="x unified",

        margin=dict(l=40, r=40, t=70, b=40),

        height=500,

        legend=dict(orientation="h", y=1.08)
    )

    fig.update_xaxes(showgrid=False, title_font=dict(size=15))

    fig.update_yaxes(gridcolor="#E5E5E5", title_font=dict(size=15))

    return fig


# ==========================================================
# BUILD CHART
# ==========================================================
# One flexible function instead of 8 fixed chart functions.
# The LLM decides chart_type/x_axis/series_by/filters via tool
# calling - this function just executes whatever it decided.
# ==========================================================

def build_chart(
    chart_type,
    metric="yield",
    x_axis=None,
    series_by=None,
    countries=None,
    crops=None,
    year_start=None,
    year_end=None,
    top_n=None,
    sort_order="desc",
    title=None,
):

    filtered = filter_dataset(
        countries=countries,
        crops=crops,
        year_start=year_start,
        year_end=year_end,
    )

    if filtered.empty:
        return {"error": "No matching data found for the given filters."}

    y_col = METRIC_COLUMN_MAP.get(metric, "hg/ha_yield")

    if not x_axis:
        x_axis = "year" if chart_type == "line" else ("country" if chart_type in ("bar", "pie") else "rainfall")

    x_col = X_AXIS_COLUMN_MAP.get(x_axis, "Year")

    series_col = X_AXIS_COLUMN_MAP.get(series_by) if series_by in ("country", "crop") else None

    # Guard: if series_by resolves to the SAME column as x_axis (e.g. both
    # "crop" -> "Item", from something like "break that down by crop" on a
    # chart that's already x_axis="crop"), grouping by [Item, Item] made
    # pandas try to insert a duplicate "Item" column on reset_index() and
    # crash. Splitting the same field across both axes is redundant anyway,
    # so just drop the series grouping and keep the x-axis grouping.
    if series_col == x_col:
        series_col = None

    chart_title = title or f"{metric.title()} by {x_axis.title()}"

    if chart_type == "line":

        group_cols = [x_col] + ([series_col] if series_col else [])

        data = filtered.groupby(group_cols)[y_col].mean().reset_index()

        fig = px.line(
            data, x=x_col, y=y_col, color=series_col,
            markers=True, title=chart_title
        )

    elif chart_type == "bar":

        group_cols = [x_col] + ([series_col] if series_col else [])

        data = filtered.groupby(group_cols)[y_col].mean().reset_index()

        if not series_col:

            # Hardcoding ascending=False here meant "lowest yield"
            # requests (top_n=1 intended as bottom-1) still returned
            # the HIGHEST row, since there was no way to sort the
            # other direction. sort_order lets the caller ask for
            # ascending ("lowest"/"worst"/"bottom N") explicitly.
            ascending = sort_order == "asc"

            data = data.sort_values(y_col, ascending=ascending)

            if top_n:
                data = data.head(int(top_n))

        fig = px.bar(
            data, x=x_col, y=y_col, color=series_col,
            text_auto=".1f", barmode="group", title=chart_title
        )

    elif chart_type == "pie":

        # Pie has no "series" concept (it's already one whole broken into
        # slices), so series_by is ignored here even if the model passed
        # one - just group by the single x_col, same sort/top_n behavior
        # as bar so "pie chart of top 5 crops" still makes sense.
        data = filtered.groupby(x_col)[y_col].mean().reset_index()

        ascending = sort_order == "asc"

        data = data.sort_values(y_col, ascending=ascending)

        if top_n:
            data = data.head(int(top_n))

        fig = px.pie(
            data, names=x_col, values=y_col, title=chart_title, hole=0.35
        )

        fig.update_traces(textinfo="label+percent")

    elif chart_type == "box":

        # Unlike bar/pie/line, a boxplot needs the RAW per-row values (not
        # pre-averaged) since the whole point is showing the distribution
        # (median/quartiles/outliers) within each category, not a single
        # summary number.
        fig = px.box(
            filtered, x=x_col, y=y_col, color=series_col,
            points="outliers", title=chart_title
        )

    elif chart_type == "scatter":

        fig = px.scatter(
            filtered, x=x_col, y=y_col, hover_name="Area",
            opacity=0.7, title=chart_title
        )

    else:

        return {"error": f"Unsupported chart_type: {chart_type}"}

    fig = style_chart(fig)

    result = {
        "fig": fig,
        "rows": int(len(filtered)),
        "mean_value": round(float(filtered[y_col].mean()), 2),
        "metric": metric,
        "chart_type": chart_type,
    }

    # For bar/pie rankings without a series split, `mean_value` above is
    # the BLENDED average across the whole filtered set (e.g. all crops in
    # India combined) - not the value of whichever category the chart
    # actually highlights (e.g. Sorghum specifically). The model had no
    # real number to attach to a "which crop is lowest/highest" answer,
    # so it fabricated one. `breakdown` gives it the real category/value
    # pairs actually plotted, in the same order shown on the chart.
    if chart_type == "pie" or (chart_type == "bar" and not series_col):

        result["breakdown"] = [
            {"category": str(row[x_col]), "value": round(float(row[y_col]), 2)}
            for _, row in data.iterrows()
        ]

    # A boxplot's whole point is the SPREAD per category, not one number -
    # give the model the real median/min/max per category (not the mean,
    # which isn't what a boxplot's center line represents) so it can
    # describe the distribution without guessing.
    if chart_type == "box" and not series_col:

        stats = (
            filtered.groupby(x_col)[y_col]
            .agg(["median", "min", "max"])
            .reset_index()
        )

        result["breakdown"] = [
            {
                "category": str(row[x_col]),
                "median": round(float(row["median"]), 2),
                "min": round(float(row["min"]), 2),
                "max": round(float(row["max"]), 2),
            }
            for _, row in stats.iterrows()
        ]

    return result