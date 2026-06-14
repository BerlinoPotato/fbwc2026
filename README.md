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
- **Search** — find a team → their results, fixtures, venues, locations and kick-off times.
- **Highlight teams** — toggle chips (defaults: Netherlands, Curaçao, England, Japan, Germany, Belgium, France). Saved in `localStorage`.

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
| `scripts/fetch_data.py` | Fetches the API, normalises, computes standings, writes the JSON |
| `.github/workflows/fetch.yml` | Scheduled Action that runs the fetcher and commits changes |

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
- **Players info**: not included (the chosen free source provides team-level data only).
- **Data source**: [rezarahiminia/worldcup2026](https://github.com/rezarahiminia/worldcup2026)
  (`worldcup26.ir`). To swap to a different provider (e.g. api-football.com), change the
  `_request` calls and the `norm_*` mappers in `fetch_data.py` — the page and JSON shape stay the same.
