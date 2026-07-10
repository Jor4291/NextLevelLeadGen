# Phase 1 Deployment Guide

Deploy the Next Level Studio Lead Generator for your team: one central API + database, dashboard accessible from any location.

## Architecture

| Component | Host | URL |
|-----------|------|-----|
| React dashboard | Vercel | `https://your-app.vercel.app` |
| FastAPI + Playwright | Railway, Render, or Docker VPS | `https://api.yourdomain.com` |
| PostgreSQL | Railway Postgres, Render, or Docker | internal connection string |

## Option A — Docker (fastest local/staging test)

1. Copy environment file:
   ```powershell
   copy .env.example .env
   ```
2. Set `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `JWT_SECRET` in `.env`.
3. Start stack:
   ```powershell
   docker compose up --build
   ```
4. API: http://localhost:8000/api/health  
5. Run frontend locally pointing at API:
   ```powershell
   cd frontend
   $env:VITE_API_URL="http://localhost:8000"
   npm run dev
   ```

## Option B — Production (Vercel + Railway)

### 1. Deploy API (Railway recommended)

1. Create a new Railway project.
2. Add **PostgreSQL** plugin — copy `DATABASE_URL`.
3. Deploy from this repo using the `Dockerfile` (Railway detects it).
4. Set environment variables:

   | Variable | Value |
   |----------|--------|
   | `DATABASE_URL` | from Railway Postgres |
   | `AUTH_REQUIRED` | `true` |
   | `JWT_SECRET` | long random string |
   | `ADMIN_EMAIL` | your admin email |
   | `ADMIN_PASSWORD` | strong password |
   | `ALLOW_REGISTRATION` | `false` (or `true` to let BDRs self-register) |
   | `CORS_ORIGINS` | your Vercel URL |

5. Mount or upload Google Sheets credentials if using export.
6. Note your public API URL, e.g. `https://nextlevel-leads-api.up.railway.app`.

### 2. Deploy frontend (Vercel)

1. Import the repo in Vercel.
2. Set **Root Directory** to `frontend`.
3. Add environment variables:
   - `VITE_API_URL` = `https://your-api-url` (no trailing slash)
   - `VITE_ENTITY_ID` = `nextlevel`
4. Deploy.

### 3. First login

1. Open your Vercel URL.
2. Sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from Railway env.
3. Optional: set `ALLOW_REGISTRATION=true` so BDRs can create accounts.

## Team workflow

- **Shared inbox** — all authenticated users see all leads by default.
- **My leads** — inbox preset filters to leads assigned to you.
- **Auto-assignment** — leads from a scrape job are assigned to whoever started the job.
- **Manual assignment** — change assignee on Lead Detail or filter by rep in the inbox.

## Local development (no auth)

Default `.env` uses SQLite and `AUTH_REQUIRED=false` so existing `run_dev.ps1` keeps working without login.

To test auth locally:

```env
AUTH_REQUIRED=true
ADMIN_EMAIL=admin@nextlevelstudio.com
ADMIN_PASSWORD=yourpassword
JWT_SECRET=local-dev-secret
```

## Security checklist

- [ ] Change `JWT_SECRET` and `ADMIN_PASSWORD` before going live
- [ ] Set `ALLOW_REGISTRATION=false` unless you want open signups
- [ ] Restrict `CORS_ORIGINS` to your Vercel domain only
- [ ] Use HTTPS on API (Railway/Render provide this automatically)
- [ ] Store Google credentials as platform secrets, not in git

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Login fails | Check `ADMIN_EMAIL`/`ADMIN_PASSWORD` on API; restart after env change |
| CORS error | Add Vercel URL to `CORS_ORIGINS` on API |
| `scrape_ready: false` | Playwright Chromium must be installed in container (Dockerfile handles this) |
| Blank dashboard | Set `VITE_API_URL` on Vercel to your API base URL |

## Next (Phase 2)

- Scrape job queue for multiple concurrent BDRs
- Per-territory metro presets
- Usage quotas and audit log
