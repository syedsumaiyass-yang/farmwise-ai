# FarmWise AI Dashboard

An AI-powered analytics assistant for exploring global crop yield data through
natural language. Ask a question in plain English in the chat UI and get back
the right answer — a plain number, or the right chart type — with nothing
pre-built or keyword-mapped. The LLM decides the metric, chart type, filters,
and grouping itself via tool calling, and reasons over the full conversation
history for follow-up questions.

## Live Demo

- **Frontend (Streamlit):** `<add your deployed Streamlit URL here>`
- **Backend (FastAPI):** `<add your deployed backend URL here>`

## Deployment

Two pieces need to be hosted separately — a deployed Streamlit app can't
reach a backend running on your own machine.

**1. Deploy the backend (FastAPI) — e.g. on [Render](https://render.com) (free tier)**

- New → Web Service → connect your GitHub repo
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Add an environment variable: `GROQ_API_KEY` = your key
- You'll also need `data/cleaned_yield_df.csv` present in the deployed
  repo (commit it, or add a build step to fetch it) since the free tier
  has no separate persistent storage for you to upload it manually
- Once deployed, copy the service's public URL, e.g.
  `https://farmwise-backend.onrender.com`

**2. Deploy the frontend (Streamlit) — [Streamlit Community Cloud](https://streamlit.io/cloud) (free)**

- New app → connect your GitHub repo → main file path: `app.py`
- Under **Advanced settings → Secrets**, add:
  ```toml
  BACKEND_URL = "https://farmwise-backend.onrender.com/chat"
  ```
  (use your actual Render URL, with `/chat` on the end)
- Deploy. `app.py` reads `BACKEND_URL` from `st.secrets` automatically,
  falling back to `http://127.0.0.1:8000/chat` only when no secret is set
  (i.e. local development) — no code changes needed between local and
  deployed.

**3. Update the Live Demo links above** with both URLs once deployed.

> Free-tier note: Render's free web services spin down after inactivity
> and take ~30-60s to wake up on the first request after a while. The
> frontend has a 120s request timeout and shows a friendly "waking up"
> message rather than a raw timeout error, so the chatbot's first message
> after idle time may just look slow, not broken.

## What it does

- A ChatGPT-style chat UI (multiple named conversations, switchable and
  deletable from a sidebar) accepts any natural-language question about the
  dataset — yield, rainfall, temperature, or pesticide use, for any
  country/crop/year combination it contains.
- The LLM (via Groq tool calling) decides *whether* the answer needs a
  chart at all, and if so, which type — line, bar, pie, box, or scatter —
  what goes on which axis, and how to filter/group/sort the data. There is
  no hardcoded question-to-chart mapping.
- The conversation has real session memory: follow-ups like *"now just the
  last five years"* or *"break that down by crop"* build on the previous
  answer instead of starting from scratch, while genuinely new questions
  are treated fresh rather than dragging old filters along.
- Loosely-typed or misspelled country/crop names (e.g. "usa", "rice") are
  resolved against the dataset's real values before filtering, so a
  near-miss spelling doesn't silently return "no data" with no explanation.
- Backend and LLM failures (rate limits, auth errors, connection issues)
  are caught and shown as a short, readable chat message instead of a raw
  500 or a generic "unable to connect."

See [`DECISIONS.md`](./DECISIONS.md) for the reasoning behind how each of
these works.

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI |
| Frontend | Streamlit |
| Data processing | Pandas |
| Visualization | Plotly |
| LLM | Groq — `llama-3.1-8b-instant` (tool calling) |

## Dataset

[Crop Yield Prediction Dataset](https://www.kaggle.com/datasets/patelris/crop-yield-prediction-dataset)
(Kaggle). Download the raw CSV as `data/yield_df.csv`, then run
`clean_data.py` to drop the stray index column and duplicate rows and
produce the file the app actually reads:

```
data/cleaned_yield_df.csv
```

relative to the project root — this is the exact path `backend/data_loader.py`
reads from.

## Setup & Run Locally

**1. Clone the repo and create a virtual environment**

```bash
git clone <your-repo-url>
cd <your-repo-folder>
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Set up your Groq API key**

Get a free key at [console.groq.com](https://console.groq.com) (no credit
card required), then create a `.env` file in the project root:

```
GROQ_API_KEY=your_key_here
```

`.env` is already in `.gitignore` — never commit your real key.

**4. Add the dataset**

Download the dataset (see [Dataset](#dataset) above), place the raw CSV at
`data/yield_df.csv`, and run:

```bash
python clean_data.py
```

This produces `data/cleaned_yield_df.csv`, which the app reads at startup.

**5. Run the backend** (from the project root)

```bash
uvicorn backend.main:app --reload --port 8000
```

**6. Run the frontend** (in a separate terminal)

```bash
streamlit run app.py
```

**7. Open the app**

Streamlit will open automatically at `http://localhost:8501`. Make sure the
backend (step 5) is running first — the chatbot calls it directly.

## Example questions to try

- "What's the average yield for Wheat in India?"
- "Show me India's crop yield trend"
- "Compare India and China"
- "Top 10 crops by yield"
- "Which country has the lowest yield?"
- "Pie chart of crop share in India"
- "How much does yield vary across crops?" (boxplot)
- "Rainfall vs yield"
- "Now just the last five years"
- "Break that down by crop"

## AI tools used

- **Groq** `llama-3.1-8b-instant` for natural-language understanding and
  tool calling (chosen over the larger 70B model for its much higher
  free-tier request cap — see `DECISIONS.md`).
- **Claude (Anthropic)** was used as an AI coding assistant throughout —
  `<add/adjust this line to reflect exactly what you used and how>`.

## Project Structure

```
.
├── backend/
│   ├── main.py            # FastAPI app: /chat, /dashboard, /dataset-info
│   ├── llm.py              # Groq tool-calling agent loop, system prompt
│   ├── tools.py             # Filtering, fuzzy name resolution, dataset overview
│   ├── chart_generator.py   # Builds whatever chart the LLM decided on
│   ├── tool_executor.py     # Dispatches LLM tool calls to the right function
│   └── data_loader.py       # Loads data/cleaned_yield_df.csv
├── data/
│   └── cleaned_yield_df.csv # dataset (see Dataset section)
├── app.py                   # Streamlit frontend / multi-chat UI
├── clean_data.py             # One-off script: raw CSV -> cleaned_yield_df.csv
├── requirements.txt
├── DECISIONS.md
└── README.md
```