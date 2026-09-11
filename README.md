# Souveno Expo Agent — backend

FastAPI + SQLAlchemy API for Souveno AI Solutions' exhibition agent: 29 scored shows, approvals (propose → tap →
pay/book), subsidies, finance / P&L, actuals & calibration, funds & pavilions, voice intents, floor plans, cards.

```
pip install -r requirements.txt
uvicorn backend.main:app --reload            # http://localhost:8000/docs
pytest tests -q                               # 32 tests, no CV stack needed
python scripts/build_dashboard.py ../expo-frontend/dashboard/command_center_template.html ../expo-frontend/dashboard/souveno-expo-command-center.html
```

Live: https://hellomass-pd54.vercel.app (Vercel). Set `EXPO_CORS_ORIGINS` there to the frontend's origin.

Env: `DATABASE_URL` (Postgres; default SQLite), `EXPO_CORS_ORIGINS` (frontend origin, default `*`),
`EXPO_FRONTEND_DIR` (serve the static frontend from this process), `EXPO_PAYMENT_MODE` (automate | manual),
`DUFFEL_ACCESS_TOKEN`, `DUFFEL_PASSENGERS_JSON`, `RAZORPAYX_*`, `ANTHROPIC_API_KEY` (card OCR fallback).

Deploy: `vercel.json` + `api/index.py` (bootstraps this branch's tarball into /tmp), `Dockerfile`, `render.yaml`.
Docs: `docs/EXPO_SCORING.md` (how the stars are computed), `docs/SOUVENO_EXPO_OPERATIONS.md` (sector-by-sector manual).
Data: `data/expo/events.json` (single source of truth for shows), `funds.json`, `pavilions.json`.
