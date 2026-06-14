#!/usr/bin/env python3
"""Build data/squads.json (player rosters) from api-football.com (API-SPORTS).

worldcup26.ir has no squads, so players come from a second source. Squads barely
change, so this runs DAILY (not every 15 min): 1 + 48 = ~49 requests, under the
free tier's 100/day limit.

Auth: free key from https://dashboard.api-football.com (header x-apisports-key).
Set as GitHub Secret API_FOOTBALL_KEY.

Output shape (matched to teams in the frontend by code, then normalised name):
    { "meta": {...}, "squads": [ {"name","code","country","players":[{number,name,position}]} ] }
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("AF_API_BASE", "https://v3.football.api-sports.io").rstrip("/")
KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
LEAGUE = os.environ.get("AF_LEAGUE", "1")     # 1 = FIFA World Cup
SEASON = os.environ.get("AF_SEASON", "2026")
OUT = Path(__file__).resolve().parents[1] / "data" / "squads.json"
TIMEOUT = 25
PAUSE = 0.4   # be polite to the free tier


def _get(path: str):
    req = urllib.request.Request(BASE + path, method="GET")
    req.add_header("x-apisports-key", KEY)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        body = json.loads(r.read().decode())
    # api-sports returns HTTP 200 even on auth/quota errors; the real error is in `errors`
    errs = body.get("errors")
    if errs and (errs if isinstance(errs, list) else list(errs.values())):
        sys.exit(f"API error on {path}: {json.dumps(errs)[:300]}")
    return body.get("response", [])


def main():
    if not KEY:
        sys.exit("No API_FOOTBALL_KEY set.")
    print(f"[squads] base={BASE} league={LEAGUE} season={SEASON}")

    teams = _get(f"/teams?league={LEAGUE}&season={SEASON}")
    print(f"[squads] teams={len(teams)}")
    if not teams:
        sys.exit("No teams returned — check league/season or quota.")

    squads = []
    for i, row in enumerate(teams, 1):
        t = row.get("team", {})
        tid = t.get("id")
        if not tid:
            continue
        resp = _get(f"/players/squads?team={tid}")
        players_raw = (resp[0].get("players") if resp else []) or []
        players = [
            {
                "number": p.get("number"),
                "name": p.get("name") or "",
                "position": p.get("position") or "",
            }
            for p in players_raw
            if p.get("name")
        ]
        squads.append({
            "name": t.get("name") or "",
            "code": t.get("code") or "",
            "country": t.get("country") or "",
            "players": players,
        })
        print(f"[squads] {i}/{len(teams)} {t.get('name')}: {len(players)} players")
        time.sleep(PAUSE)

    payload = {
        "meta": {
            "source": "api-football.com",
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "is_sample": False,
            "teams": len(squads),
        },
        "squads": sorted(squads, key=lambda s: s["name"]),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[squads] wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"Network error: {e.reason}")
