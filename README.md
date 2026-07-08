# Next Level Studio B2B Lead Generator

Local lead discovery and qualification dashboard for [Next Level Studio](https://nextlevelstudio.com/). Discovers businesses via public web scraping, scores them against your ICP, and exports qualified leads to Google Sheets for your sales team.

> **Repo:** [NextLevelLeadGen](https://github.com/Jor4291/NextLevelLeadGen) — sibling product: [CaelvonLeadGen](https://github.com/Jor4291/CaelvonLeadGen)

## Features

- **Discovery scraper** — DuckDuckGo public search by industry + location (optional Playwright Google Maps)
- **Website enrichment** — emails, phones, decision-makers, employee estimates, pain keywords
- **Job signal mining** — careers pages and Indeed snippets for hiring/pain indicators
- **ICP scoring (0–100)** — weighted toward Process Optimization and Custom Software practices
- **Lead inbox** — review, notes, status workflow, filters
- **Google Sheets export** — call-team column layout
- **Email canvas (Phase 2)** — Resend API or CSV export for Instantly/GMass

## Deployment

See **[DEPLOY.md](DEPLOY.md)** for Phase 1 multi-user deployment (Docker, Railway + Vercel, auth setup).

## Quick Start (Windows)

### 1. Prerequisites

- Python 3.11+
- Node.js 18+

### 2. Install

```powershell
cd "C:\Users\jor42\Desktop\AI Lead Generator"

# Python backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium

# Frontend
cd frontend
npm install
cd ..
```

### 3. Configure

```powershell
copy .env.example .env
```

Edit `.env` and optionally set `GOOGLE_SHEET_ID` after completing Google Sheets setup below.

### 4. Run

```powershell
.\scripts\run_dev.ps1
```

This opens **two minimized PowerShell windows** (API + dashboard). Close those windows to stop the servers.

- **Dashboard:** http://localhost:5173
- **API:** http://127.0.0.1:8000/api/health

## Scrape Prerequisites

**Required for scraping (nothing in `.env` is required to start a scrape):**

| Requirement | How to verify |
|-------------|---------------|
| Python venv + dependencies | `pip install -r requirements.txt` |
| **Playwright Chromium** | `playwright install chromium` |
| Backend API running from venv | http://127.0.0.1:8000/api/health shows `"scrape_ready": true` |
| City + state (strongly recommended) | e.g. Houston, TX — nationwide-only searches are slower and less accurate |

**NOT required for scraping:**
- Google Sheets credentials
- `GOOGLE_SHEET_ID` in `.env`
- Resend API key
- Any paid data APIs

**Optional `.env` tuning:**
- `SCRAPE_RATE_LIMIT_SECONDS` — delay between requests (default `2`)
- `SCRAPE_USER_AGENT` — bot identification string

**Tips for best results:**
1. Pick an **industry** and a **city/state** (or use Quick Metro Fill on Run Scrape).
2. A full job discovers ~50 companies and can take **15–30+ minutes** (Maps + website enrichment).
3. Watch **Job History** on Run Scrape — status should move `pending` → `running` → `completed`.
4. If a job fails instantly, restart the API from the project venv (see Troubleshooting).

## Google Sheets Setup

1. Create a [Google Cloud project](https://console.cloud.google.com/) and enable **Google Sheets API**.
2. Create a **service account** and download the JSON key.
3. Save the key as `credentials/google-service-account.json`.
4. Create a Google Sheet and share it with the service account email (Editor).
5. Copy the Sheet ID from the URL into Settings in the dashboard or `.env`:

   ```
   GOOGLE_SHEET_ID=your_sheet_id_here
   ```

## Usage Workflow

1. **Run Scrape** — pick industry (manufacturing, distribution, etc.), city/state or use metro quick-fill.
2. **Lead Inbox** — filter by score, review pain signals and evidence on each lead.
3. **Call team** — add notes, update status (Contacted, Qualified, Not a fit).
4. **Export** — push approved leads to Google Sheets.
5. **Email canvas** — mark leads "Approved for email", send via Resend or export CSV to Instantly.

## ICP Configuration

Edit [`config/icp.yaml`](config/icp.yaml) to tune:

- Six target industries and search queries
- Process optimization and custom software pain keywords
- ERP system names, hiring signals, scoring weights
- 50 US metro seed list for nationwide discovery

## Email (Phase 2)

**Built-in (Resend):** Set `RESEND_API_KEY` in `.env`. Configure SPF/DKIM for `engage@caelvon.com`.

**Instantly.ai (recommended for volume):** Export CSV from Email Campaigns page, upload with warmup enabled.

**GMass (small batches):** Export to Sheets, mail merge from Gmail (50–200/week).

## Compliance Notes

- Scrapes **public web data only**; respects rate limits and identifies via User-Agent.
- **CAN-SPAM:** Include physical address and unsubscribe in email templates (default template included).
- **TCPA (calling):** Your team should scrub phone numbers against Do-Not-Call registries before outbound calls. This tool does not automate DNC scrubbing.

## Optional: Playwright Google Maps

Set in `.env`:

```
USE_PLAYWRIGHT_FOR_MAPS=true
```

Then install browsers:

```powershell
playwright install chromium
```

## Project Structure

```
backend/           FastAPI API, scrapers, scoring, integrations
frontend/          React dashboard (Vite)
config/icp.yaml    ICP rules and keywords
data/              SQLite database (created on first run)
credentials/       Google service account JSON (not committed)
scripts/           Dev startup script
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/config` | Industries, metros, ICP config |
| POST | `/api/scrape-jobs` | Start a scrape job |
| GET | `/api/leads` | List/filter leads |
| PATCH | `/api/leads/{id}` | Update notes/status |
| POST | `/api/leads/export` | Export to Google Sheets |
| POST | `/api/email/send` | Send email campaign via Resend |

## Troubleshooting

- **Scrape fails instantly (status `failed` in under 1 second):** Restart the API so it picks up the latest code. Stop all Python windows, then run `.\scripts\run_dev.ps1` again. Check http://127.0.0.1:8000/api/health — `scrape_ready` must be `true`.
- **Scrape stuck on `running`:** Normal for 15–30+ minutes. Refresh Job History every few minutes to see progress messages.
- **`playwright install chromium` not run:** Scrape will fail. Install Chromium and restart the API.
- **No leads found:** Try a specific city/state or keyword override. Google Maps may return few results for broad searches.
- **Sheets export fails:** Verify credentials path, Sheet ID, and that the sheet is shared with the service account.
- **Low email find rate:** Industrial sites often list phone only — prioritize calling; check evidence URLs manually.
