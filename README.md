# World Cup 2026 Tracker ⚽

A personal, static web page that tracks the FIFA World Cup 2026: group standings, full
schedule in **your local timezone**, and search-by-team (results, fixtures, venue, kick-off).
Highlight your favourite teams across every view.

Hosted free on **GitHub Pages**. No backend, no API key in the page — a scheduled GitHub
Action fetches the data and commits a JSON snapshot the page reads.

---

## What it does

- **Groups** — live standings (P/W/D/L/GF/GA/GD/Pts), computed from finished matches; top-2 line marked.
- **Schedule** — upcoming / results / all, grouped by day, times in the viewer's local zone.
- **Teams** — all 48 teams grouped A–L; click a team for its detail.
- **Venues** — 16 stadiums: city, country, capacity, number of matches.
- **Search / Team detail** — find a team → group standing, fixtures, venues, kick-off times, and **squad** (players info, if enabled).
- **Highlight teams** — toggle chips (defaults: Netherlands, Curaçao, England, Japan, Germany, Belgium, France). Saved in `localStorage`.
- **Formats** — dates `dd MMM yyyy` (e.g. `14 Jun 2026`), times 24-hour (e.g. `19:00`), in the viewer's local timezone.

## How it works

```
GitHub Action (every 15 min)
  └─ scripts/fetch_data.py  ── fetches worldcup26.ir ──> data/wc2026.json  (committed)
GitHub Pages serves index.html ── reads ──> data/wc2026.json
```

The page is the customer-facing part; it never sees the API token. "Realtime" = last refresh
(~15 min). If the source API is down at refresh time, the last good snapshot keeps serving.

## File structure

| File | Purpose |
|---|---|
| `index.html` / `styles.css` / `app.js` | The static page |
| `data/wc2026.json` | Data snapshot the page reads (sample data shipped; Action overwrites it) |
| `data/squads.json` | Player squads (optional; sample shipped, the squads Action overwrites it) |
| `scripts/fetch_data.py` | Fetches worldcup26.ir, normalises, computes standings, writes `wc2026.json` |
| `scripts/fetch_squads.py` | Fetches squads from api-football.com → `squads.json` |
| `.github/workflows/fetch.yml` | Scheduled Action (15 min) — scores/standings/schedule |
| `.github/workflows/fetch_squads.yml` | Scheduled Action (daily) — player squads |

---

## Setup (one time)

### 1. Get a free API token
worldcup26.ir uses a JWT (valid ~84 days). Register once:

```bash
curl -X POST https://worldcup26.ir/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Me","email":"you@example.com","password":"a-strong-password"}'
```

Copy the `token` from the response.

### 2. Push to a GitHub repo and add the token as a Secret
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

- `WC_API_TOKEN` = the JWT from step 1

> Alternatively, set `WC_API_EMAIL` + `WC_API_PASSWORD` secrets and the script will
> re-authenticate each run (handy since the token expires every 84 days).

### 3. Enable GitHub Pages
Repo → **Settings → Pages** → Source: **Deploy from a branch** → branch `main`, folder `/ (root)`.
Your page goes live at `https://<you>.github.io/<repo>/`.

### 4. Run the Action once
Repo → **Actions → "Fetch World Cup data" → Run workflow**. It writes a real `data/wc2026.json`
and commits it. After that it runs every 15 minutes on its own.

---

## Players info (optional — api-football.com)

Squads come from a second free source because worldcup26.ir has none.

1. Free key: register at `https://dashboard.api-football.com` → copy your API key.
2. Add as repository secret `API_FOOTBALL_KEY` (Settings → Secrets and variables → Actions).
3. Run **Actions → "Fetch squads" → Run workflow**. Writes `data/squads.json` (~49 API calls, under the 100/day free limit). Then runs daily.

Squads match to teams by FIFA code, then normalised name (alias map in `app.js` handles
cases like *South Korea / Korea Republic*). Until enabled, the team detail shows a "squad not
available" note and everything else works.

## Local preview

`fetch()` can't read a local file via `file://`, so use a tiny server:

```bash
cd fbwc2026
python -m http.server 8000
# open http://localhost:8000
```

The shipped `data/wc2026.json` is **sample data** (a "Sample data" badge shows in the header)
so you can see the UI before wiring the token.

## Run the fetcher locally (optional)

```bash
pip install tzdata                 # Windows has no IANA tz database; Linux/Mac already do
export WC_API_TOKEN="your-jwt"     # PowerShell: $env:WC_API_TOKEN="your-jwt"
python scripts/fetch_data.py       # overwrites data/wc2026.json with live data
```

---

## Notes & assumptions

- **Kick-off times**: the API's `local_date` has no timezone. The fetcher interprets it as the
  **match venue's local time** (each stadium mapped to an IANA zone in `fetch_data.py`) and emits
  a UTC instant. Verify against one known kick-off after the first live fetch; if every match is
  off by a constant number of hours, adjust the venue zone map or that assumption.
- **Players info**: from api-football.com (separate daily Action). worldcup26.ir is team-level only.
- **Data source**: [rezarahiminia/worldcup2026](https://github.com/rezarahiminia/worldcup2026)
  (`worldcup26.ir`). To swap to a different provider (e.g. api-football.com), change the
  `_request` calls and the `norm_*` mappers in `fetch_data.py` — the page and JSON shape stay the same.
