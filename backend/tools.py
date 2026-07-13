from difflib import get_close_matches

from backend.data_loader import load_data

# ==========================================================
# LOAD DATASET
# ==========================================================

df = load_data()

METRIC_COLUMN_MAP = {
    "yield": "hg/ha_yield",
    "rainfall": "average_rain_fall_mm_per_year",
    "temperature": "avg_temp",
    "pesticides": "pesticides_tonnes",
}

X_AXIS_COLUMN_MAP = {
    "year": "Year",
    "country": "Area",
    "crop": "Item",
    "yield": "hg/ha_yield",
    "rainfall": "average_rain_fall_mm_per_year",
    "temperature": "avg_temp",
    "pesticides": "pesticides_tonnes",
}


# ==========================================================
# DATASET OVERVIEW (for the "dataset_overview" tool)
# ==========================================================

def dataset_overview():

    return {
        "rows": int(df.shape[0]),
        "columns": list(df.columns),
        "countries": int(df["Area"].nunique()),
        "crops": sorted(df["Item"].unique().tolist()),
        "year_range": [int(df["Year"].min()), int(df["Year"].max())],
    }


# ==========================================================
# NAME RESOLUTION - map loosely-spelled names (e.g. "rice",
# "usa") to the dataset's exact canonical spelling (e.g.
# "Rice, paddy", "United States of America").
# ==========================================================
# The system prompt tells the LLM to use exact dataset spelling,
# but LLMs don't reliably do this for every phrasing a user might
# type ("rice" vs "Rice, paddy"). Previously this caused silent
# zero-row filtering for the mismatched value with NO error - the
# query looked valid but one side of a comparison just vanished.
# This resolves user/LLM-provided names against the real values
# BEFORE filtering, so filtering never depends on exact string
# reproduction.
# ==========================================================

def _resolve_names(values, canonical_values):

    if not values:
        return values

    lower_map = {c.lower(): c for c in canonical_values}
    resolved = []

    for val in values:

        v = str(val).strip().lower()

        # 1. exact case-insensitive match
        if v in lower_map:
            resolved.append(lower_map[v])
            continue

        # 2. substring match either direction (e.g. "rice" in
        #    "rice, paddy", or "united states" in a longer name)
        substr_matches = [
            c for c in canonical_values
            if v in c.lower() or c.lower() in v
        ]
        if substr_matches:
            resolved.append(substr_matches[0])
            continue

        # 3. fuzzy fallback for typos/close spellings
        close = get_close_matches(
            v, [c.lower() for c in canonical_values], n=1, cutoff=0.6
        )
        if close:
            resolved.append(lower_map[close[0]])
            continue

        # 4. no match at all - keep the original value so the
        #    downstream filter legitimately returns "no data" for
        #    it instead of silently dropping it with no trace
        resolved.append(val)

    return resolved


# ==========================================================
# GENERIC FILTERING - shared by stats and charts
# ==========================================================

def filter_dataset(countries=None, crops=None, year_start=None, year_end=None):

    filtered = df.copy()

    if countries:

        countries = _resolve_names(countries, df["Area"].unique().tolist())

        countries_lower = [c.lower() for c in countries]

        filtered = filtered[filtered["Area"].str.lower().isin(countries_lower)]

    if crops:

        crops = _resolve_names(crops, df["Item"].unique().tolist())

        crops_lower = [c.lower() for c in crops]

        filtered = filtered[filtered["Item"].str.lower().isin(crops_lower)]

    if year_start is not None:

        filtered = filtered[filtered["Year"] >= year_start]

    if year_end is not None:

        filtered = filtered[filtered["Year"] <= year_end]

    return filtered


# ==========================================================
# NUMERIC SUMMARY (for the "analyze_yield" tool, chart_type="none")
# ==========================================================

def compute_summary(filtered, metric="yield"):

    col = METRIC_COLUMN_MAP.get(metric, "hg/ha_yield")

    # Bare min/max numbers give the model nothing to attribute them to,
    # so for questions like "what's the lowest yield" it has no real
    # country/crop to point to and ends up guessing one from its own
    # training knowledge instead of the actual dataset (a hallucination
    # risk). Pulling the full row for idxmin/idxmax grounds the answer
    # in the real record.
    min_row = filtered.loc[filtered[col].idxmin()]
    max_row = filtered.loc[filtered[col].idxmax()]

    return {
        "metric": metric,
        "average": round(float(filtered[col].mean()), 2),
        "maximum": round(float(filtered[col].max()), 2),
        "maximum_country": str(max_row["Area"]),
        "maximum_crop": str(max_row["Item"]),
        "maximum_year": int(max_row["Year"]),
        "minimum": round(float(filtered[col].min()), 2),
        "minimum_country": str(min_row["Area"]),
        "minimum_crop": str(min_row["Item"]),
        "minimum_year": int(min_row["Year"]),
        "records": int(len(filtered)),
    }


# ==========================================================
# SIMPLE HELPERS FOR THE REST /dashboard ENDPOINT ONLY
# ==========================================================
# These are NOT part of the chatbot's tool-calling path - the
# /dashboard endpoint is a plain summary widget, unrelated to
# the natural-language chat flow.
# ==========================================================

def get_average_yield():
    return round(float(df["hg/ha_yield"].mean()), 2)


def get_maximum_yield():
    row = df.loc[df["hg/ha_yield"].idxmax()]
    return {
        "Area": row["Area"],
        "Item": row["Item"],
        "Year": int(row["Year"]),
        "Yield": float(row["hg/ha_yield"]),
    }


def get_country_count():
    return int(df["Area"].nunique())


def get_crop_count():
    return int(df["Item"].nunique())