# SignalLens
**Don't just measure whether AI sees your brand. Understand why.**

## Overview
SignalLens checks whether an AI assistant mentions your product when shoppers ask buying questions, which competitors appear instead, and which buyer requirements are not represented in your product profile. Every finding links to stored evidence.

## Problem
Shoppers increasingly ask AI assistants instead of searching. A brand can be absent from those answers without any visible signal. SignalLens makes that absence measurable and inspectable.

## Engineering principle: LLM as witness, code as judge
The LLM only generates candidate prompts and returns a structured observation (brands, positions, attributes). Deterministic Python (`backend/app/analysis.py`) computes inclusion rate, coverage, average position, competitor frequency, attribute matches, severity and findings. Whether the brand was mentioned is recomputed by code from the stored structure. Findings say "potential visibility gap", never "the AI excluded you because...".

## Architecture
React → FastAPI → PostgreSQL → Prompt Engine → LLM (provider abstraction) → Pydantic-validated extraction → Deterministic analysis → Evidence-backed findings

Providers live only in `backend/app/providers.py`: `AIProvider` → `DemoProvider` | `GeminiProvider`, selected by `get_ai_provider(name)`.

## Zero-cost mode
SignalLens includes a Demo AI provider that requires no API key or paid service. Demo output is canned, labelled `DEMO MODE` / `DEMO ANALYSIS`, and is never a live measurement. The demo provider only ever mentions the demo brand (Minimalist).

## Optional live AI mode
SignalLens can optionally use Google Gemini through its available free-tier API access. Provider availability and quotas change; check Google's current API terms and limits. On failure (timeout, 429, empty, malformed output) the scan is marked FAILED, no findings are created, and nothing is substituted.

## Setup
```bash
# PostgreSQL
createdb signallens          # or set DATABASE_URL

# Backend
cd backend && pip install -r requirements.txt
cp .env.example .env         # AI_PROVIDER=demo needs no key
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --reload   # tables + demo data are created on first start

# Frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```
Env vars: `AI_PROVIDER` (demo|gemini), `GEMINI_API_KEY`, `GEMINI_MODEL`, `MAX_PROMPTS_PER_SCAN` (default 10), `DATABASE_URL`, and `VITE_API_URL` for the frontend.

## Database
`brands`, `products` (attributes as JSON), `prompts` (family stored), `scans` (status, provider, pipeline `trace`, `kind` full|single), `ai_responses` (raw + validated structured JSON), `findings` (type, severity, evidence JSON).

## API
`GET /api/health` · `GET /api/config` · `GET|POST /api/products` · `GET /api/products/{id}` · `POST /api/prompts/generate` · `GET|POST /api/products/{id}/prompts` · `POST /api/prompts/{id}/analyze` · `POST /api/scans` · `GET /api/scans/{id}` · `GET /api/products/{id}/scans` · `GET /api/products/{id}/metrics` · `GET /api/products/{id}/findings`

Metric definitions: inclusion = prompts with brand mention / analyzed prompts; average position uses only mentioned responses; visibility gaps = number of ATTRIBUTE_GAP findings; severity for gaps: 1 prompt LOW, 2-3 MEDIUM, 4+ HIGH.

## Testing
```bash
cd backend && python -m pytest -q     # uses in-memory SQLite, no key needed
```

## Limitations
- One live provider (Gemini) plus the demo provider.
- Small prompt samples (max 10 per scan by default).
- AI responses are non-deterministic.
- Findings are potential contributing signals, not proven causation.
- Requirement matching uses a small keyword lexicon (`LEXICON` in `analysis.py`); unrecognized requirements are ignored, not guessed.
- Demo data is separated from live data and labelled.

## Future work
Additional providers, larger prompt libraries, scheduled monitoring, product-page ingestion, historical trends.

## Deployment (free tiers; check current limits)
- **Database:** Neon PostgreSQL. Keep `?sslmode=require` in the URL.
- **Backend:** Render web service, root `backend`, build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Env: `DATABASE_URL`, `AI_PROVIDER=demo`, `CORS_ORIGINS=<your Vercel URL>`.
- **Frontend:** Vercel, root `frontend`, env `VITE_API_URL=<your Render URL>` (no trailing slash).
- `postgres://` and `postgresql://` URLs are rewritten automatically to the `postgresql+psycopg2://` form.
- Public deployments should stay in demo mode unless you accept others using your Gemini quota.
