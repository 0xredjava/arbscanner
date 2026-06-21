# Arbitrage Scanner

Production v1 for a public-data, pre-match moneyline arbitrage scanner.

- **Frontend:** Next.js in `frontend/`, deployed to Vercel.
- **Backend:** FastAPI on Railway.
- **Database:** Supabase Postgres through the REST API.
- **Markets:** pre-match moneyline only.
- **Platforms:** Stake.com, BC.Game, Shuffle.com, Cloudbet, TG.Casino, Thunderpick, Polymarket.

This project intentionally does **not** support wallets, private keys, logged-in cookies, live betting, or proxy bypassing. If a platform blocks public/no-login access, it is reported as unavailable.

## Backend Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app:app --reload
```

Apply `supabase_schema.sql` in Supabase SQL editor, then set Railway variables:

```env
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
ADMIN_TOKEN=
SCAN_INTERVAL_SECONDS=60
CORS_ORIGINS=https://your-vercel-domain.vercel.app
```

The API starts a background scan loop and exposes:

- `GET /api/health`
- `GET /api/platforms`
- `GET /api/scans/latest`
- `GET /api/opportunities/latest?sport=nba&platform=cloudbet&minProfit=1`
- `POST /api/scans/run` with `X-Admin-Token`

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Set Vercel's project root to `frontend/` or use the root `vercel.json`. Configure:

```env
NEXT_PUBLIC_API_BASE_URL=https://your-railway-api.up.railway.app
```

The dashboard reads public scanner data and prompts for the admin token only when triggering a manual refresh.

## Scanner Rules

- Public APIs or unauthenticated JSON endpoints are preferred.
- Server-side Playwright response interception is allowed as a fallback.
- No account sessions, no cookies, no CAPTCHA bypass, no private keys.
- v1 keeps only pre-match 2-way moneyline and 3-way soccer 1X2 markets.

## Tests

```bash
python -m pytest
```
