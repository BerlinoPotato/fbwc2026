#!/usr/bin/env python3
"""Build data/squads.json (player rosters) from TheSportsDB (free).

worldcup26.ir has no squads, and api-football's free tier blocks season 2026
("Free plans do not have access to this season, try from 2022 to 2024"), so player
data comes from TheSportsDB — free, no season lock, no paid key required.

Coverage note: TheSportsDB national-team rosters are PARTIAL (often ~10-20 players,
not the full 26). It's the best free source available for 2026; squads show what it has.

Runs DAILY (squads barely change). Reads the committed data/wc2026.json for the team
names/codes, then per team: search the senior national side + fetch its players.

Auth: free public test key "3" (override with SPORTSDB_KEY). No GitHub secret needed.
"""
import json
import os
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

KEY = (os.environ.get("SPORTSDB_KEY") or "3").strip()  # empty/unset secret -> free key "3"
BASE = f"https://www.thesportsdb.com/api/v1/json/{KEY}"
ROOT = Path(__file__).resolve().parents[1]
WC = ROOT / "data" / "wc2026.json"
OUT = ROOT / "data" / "squads.json"
TIMEOUT = 25
PAUSE = float(os.environ.get("SPORTSDB_PAUSE", "1.5"))   # be gentle on the free tier
LIMIT = int(os.environ.get("SQUADS_LIMIT", "0"))         # >0 = only first N teams (local testing)
RETRIES = 3
RETRY_BACKOFF = 4
SENIOR_LEAGUE = "FIFA World Cup"                          # excludes U-17 / U-20 / Women's


def normname(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if c.isalnum())


def _get(path):
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(BASE + path, headers={"User-Agent": "wc2026-squads"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < RETRIES:
                last = e; time.sleep(RETRY_BACKOFF * attempt); continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            if attempt < RETRIES:
                time.sleep(RETRY_BACKOFF * attempt)
    raise last


def pos_category(p):
    """Map TheSportsDB's granular position to GK/Def/Mid/Att for grouping."""
    p = (p or "").lower()
    if "keeper" in p:
        return "Goalkeeper"
    if "back" in p or "defen" in p:
        return "Defender"
    if "midfield" in p:
        return "Midfielder"
    if any(w in p for w in ("wing", "forward", "striker", "attack", "offence")):
        return "Attacker"
    return ""  # unknown -> sorts last, still displayed by number


def resolve_team(name, code):
    """Find the senior national team's TheSportsDB id. Try name, then code (e.g. USA)."""
    for query in (name, code):
        if not query:
            continue
        resp = _get(f"/searchteams.php?t={urllib.parse.quote(query)}")
        teams = resp.get("teams") or []
        senior = [t for t in teams if t.get("strSport") == "Soccer" and t.get("strLeague") == SENIOR_LEAGUE]
        if not senior:
            continue
        # prefer exact normalised name/code match, else first senior result
        exact = next((t for t in senior if normname(t.get("strTeam")) in (normname(name), normname(code))), None)
        return exact or senior[0]
    return None


def get_players(team_id):
    resp = _get(f"/lookup_all_players.php?id={team_id}")
    out = []
    for p in resp.get("player") or []:
        nm = p.get("strPlayer")
        if not nm:
            continue
        num = p.get("strNumber")
        try:
            num = int(num) if num not in (None, "", "0") else None
        except (TypeError, ValueError):
            num = None
        out.append({"number": num, "name": nm, "position": pos_category(p.get("strPosition"))})
    return out


def main():
    if not WC.exists():
        sys.exit(f"Missing {WC} — ensure data/wc2026.json is committed.")
    teams = json.loads(WC.read_text(encoding="utf-8")).get("teams", [])
    if LIMIT:
        teams = teams[:LIMIT]
    print(f"[squads] source=TheSportsDB key={KEY} teams={len(teams)}")

    squads, matched, missing = [], 0, []
    for i, t in enumerate(teams, 1):
        name, code = t.get("name", ""), t.get("code", "")
        tm = None
        try:
            tm = resolve_team(name, code)
            players = get_players(tm["idTeam"]) if tm else []
        except urllib.error.HTTPError as e:
            print(f"[squads] {name}: HTTP {e.code} — skipping"); players = []
        squads.append({"code": code, "name": name, "players": players})
        if players:
            matched += 1
        else:
            missing.append(name)
        print(f"[squads] {i}/{len(teams)} {name}: {len(players)} players{'' if tm else ' (no match)'}")
        time.sleep(PAUSE)

    payload = {
        "meta": {
            "source": "thesportsdb.com",
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "is_sample": False,
            "teams": len(squads),
            "teams_with_players": matched,
            "note": "TheSportsDB national rosters are partial; some teams may have few/no players.",
        },
        "squads": sorted(squads, key=lambda s: s["name"]),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[squads] wrote {OUT} — {matched}/{len(squads)} teams have players"
          f"{'; empty: ' + ', '.join(missing) if missing else ''}")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode(errors='replace')[:200]}")
    except urllib.error.URLError as e:
        sys.exit(f"Network error: {e.reason}")
