#!/usr/bin/env python3
"""Build data/wc2026.json from the worldcup26.ir API.

Auth: register once (POST /auth/register) to get a JWT (valid ~84 days), then set:
    WC_API_TOKEN   = the JWT
or, to auto-authenticate each run:
    WC_API_EMAIL + WC_API_PASSWORD

In GitHub Actions these come from repository Secrets. The token is NEVER written
to the committed JSON or exposed to the page.

Timestamp handling
------------------
The API returns local_date like "06/11/2026 13:00" with NO timezone. We interpret it
as the match VENUE's local time (each stadium mapped to an IANA zone below) and emit a
proper UTC instant (kickoff_utc). The page then converts UTC -> the viewer's local zone.
ASSUMPTION TO VERIFY on first live run: that local_date == venue-local kickoff. If a
known kickoff looks off by a fixed number of hours, adjust the venue zone mapping or the
assumption here.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # py<3.9 fallback (Actions uses 3.11+, so this is just defensive)
    ZoneInfo = None

BASE = os.environ.get("WC_API_BASE", "https://worldcup26.ir").rstrip("/")
OUT = Path(__file__).resolve().parents[1] / "data" / "wc2026.json"
TIMEOUT = 25

# --- venue -> IANA timezone (WC 2026 hosts: USA / Canada / Mexico) -------------
# Matched by case-insensitive substring against the stadium's city, then name.
CITY_TZ = [
    # Pacific
    ("seattle", "America/Los_Angeles"),
    ("los angeles", "America/Los_Angeles"),
    ("inglewood", "America/Los_Angeles"),
    ("santa clara", "America/Los_Angeles"),
    ("san francisco", "America/Los_Angeles"),
    ("bay area", "America/Los_Angeles"),
    ("vancouver", "America/Vancouver"),
    # Mountain (none hosting in 2026, kept for safety)
    ("denver", "America/Denver"),
    # Central
    ("dallas", "America/Chicago"),
    ("arlington", "America/Chicago"),
    ("houston", "America/Chicago"),
    ("kansas city", "America/Chicago"),
    # Eastern
    ("atlanta", "America/New_York"),
    ("boston", "America/New_York"),
    ("foxborough", "America/New_York"),
    ("miami", "America/New_York"),
    ("new york", "America/New_York"),
    ("east rutherford", "America/New_York"),
    ("new jersey", "America/New_York"),
    ("philadelphia", "America/New_York"),
    ("toronto", "America/Toronto"),
    # Mexico
    ("mexico city", "America/Mexico_City"),
    ("guadalajara", "America/Mexico_City"),
    ("monterrey", "America/Monterrey"),
]
COUNTRY_DEFAULT_TZ = {
    "united states": "America/New_York",
    "usa": "America/New_York",
    "canada": "America/Toronto",
    "mexico": "America/Mexico_City",
}


def resolve_tz(city: str, country: str, name: str) -> str:
    hay = f"{city} {name}".lower()
    for needle, tz in CITY_TZ:
        if needle in hay:
            return tz
    return COUNTRY_DEFAULT_TZ.get((country or "").strip().lower(), "America/New_York")


_TZ_CACHE = {}


def _zone(tz_name: str):
    """Cached ZoneInfo. Raises a clear error if the IANA tz database is missing
    (Windows has none by default -> `pip install tzdata`). We fail loud rather than
    silently null every kickoff time."""
    if ZoneInfo is None:
        raise RuntimeError("zoneinfo unavailable (Python < 3.9).")
    if tz_name not in _TZ_CACHE:
        try:
            _TZ_CACHE[tz_name] = ZoneInfo(tz_name)
        except Exception as e:
            raise RuntimeError(
                f"Time zone '{tz_name}' not found. Install the tz database: pip install tzdata"
            ) from e
    return _TZ_CACHE[tz_name]


def to_utc_iso(local_date: str, tz_name: str):
    """'MM/DD/YYYY HH:MM' in tz_name -> ISO-8601 UTC string, or None if unparseable."""
    if not local_date:
        return None
    zone = _zone(tz_name)  # raises loudly if tz db is missing — do not swallow
    for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S"):
        try:
            naive = datetime.strptime(local_date.strip(), fmt)
        except ValueError:
            continue
        return naive.replace(tzinfo=zone).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return None  # date string present but in an unexpected format


# --- HTTP --------------------------------------------------------------------
RETRIES = 3            # transient blips (SSL EOF, timeouts) from the indie source are common
RETRY_BACKOFF = 4      # seconds: 4, 8, 12 ...


def _request(path: str, method="GET", body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Accept", "application/json")
            if data is not None:
                req.add_header("Content-Type", "application/json")
            if token:
                req.add_header("Authorization", "Bearer " + token)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError:
            raise  # 4xx/5xx are not transient — surface immediately (e.g. 401 bad token)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"[fetch] {path} attempt {attempt}/{RETRIES} failed ({e}); retry in {wait}s")
                time.sleep(wait)
    raise last_err


def get_token() -> str:
    token = os.environ.get("WC_API_TOKEN", "").strip()
    if token:
        return token
    email = os.environ.get("WC_API_EMAIL", "").strip()
    password = os.environ.get("WC_API_PASSWORD", "").strip()
    if email and password:
        resp = _request("/auth/authenticate", "POST", {"email": email, "password": password})
        tok = resp.get("token") or resp.get("accessToken") or (resp.get("data") or {}).get("token")
        if not tok:
            sys.exit("Authenticated but no token field found in response: " + json.dumps(resp)[:300])
        return tok
    sys.exit("No credentials. Set WC_API_TOKEN, or WC_API_EMAIL + WC_API_PASSWORD.")


def as_list(resp):
    """API endpoints may wrap results; normalise to a list of records."""
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for key in ("data", "teams", "games", "groups", "stadiums", "results"):
            if isinstance(resp.get(key), list):
                return resp[key]
        # single-object wrapper like {"game": {...}}
        for v in resp.values():
            if isinstance(v, list):
                return v
    return []


# --- normalisation -----------------------------------------------------------
def norm_team(t):
    return {
        "id": str(t.get("id", "")),
        "code": t.get("fifa_code") or t.get("code") or "",
        "name": t.get("name_en") or t.get("name") or "",
        "group": (t.get("groups") or t.get("group") or "").strip(),
        "flag": t.get("flag") or "",
    }


def norm_stadium(s):
    city = s.get("city_en") or s.get("city") or ""
    country = s.get("country_en") or s.get("country") or ""
    name = s.get("name_en") or s.get("fifa_name") or s.get("name") or ""
    return {
        "id": str(s.get("id", "")),
        "name": name,
        "city": city,
        "country": country,
        "capacity": s.get("capacity"),
        "tz": resolve_tz(city, country, name),
    }


def truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes", "ft", "finished")


def parse_score(v):
    try:
        s = str(v).strip()
        if s in ("", "null", "none", "-"):
            return None
        return int(s)
    except (TypeError, ValueError):
        return None


def build_team_ref(team_id, teams_by_id):
    t = teams_by_id.get(str(team_id))
    if not t or t["id"] in ("", "0"):
        return None
    return {"id": t["id"], "code": t["code"], "name": t["name"], "flag": t["flag"]}


def norm_match(g, teams_by_id, stad_by_id):
    g = g.get("game", g) if isinstance(g, dict) and "game" in g else g
    sid = str(g.get("stadium_id", ""))
    st = stad_by_id.get(sid)
    finished = truthy(g.get("finished"))
    elapsed = (g.get("time_elapsed") or "").strip()
    live = (not finished) and elapsed not in ("", "notstarted")
    home = build_team_ref(g.get("home_team_id"), teams_by_id)
    away = build_team_ref(g.get("away_team_id"), teams_by_id)
    return {
        "id": str(g.get("id", "")),
        "group": (g.get("group") or "").strip(),
        "matchday": (str(g.get("matchday")) if g.get("matchday") not in (None, "") else None),
        "type": (g.get("type") or "group").strip().lower(),
        "home": home,
        "away": away,
        "home_label": g.get("home_team_label") or (g.get("home_team_name_en") if not home else None),
        "away_label": g.get("away_team_label") or (g.get("away_team_name_en") if not away else None),
        "home_score": parse_score(g.get("home_score")),
        "away_score": parse_score(g.get("away_score")),
        "finished": finished,
        "status": "FT" if finished else ("LIVE" if live else "NS"),
        "time_elapsed": elapsed or "notstarted",
        "stadium": {"id": st["id"], "name": st["name"], "city": st["city"], "country": st["country"]} if st else None,
        "kickoff_utc": to_utc_iso(g.get("local_date", ""), st["tz"]) if st else None,
        "kickoff_local_label": (g.get("local_date") or "").strip() or None,
    }


def compute_standings(matches, teams):
    """Build full P/W/D/L/GF/GA/GD/Pts tables per group from finished group matches."""
    by_group = {}
    for t in teams:
        if t["group"]:
            by_group.setdefault(t["group"], {})[t["id"]] = {
                "team_id": t["id"], "code": t["code"], "name": t["name"], "flag": t["flag"],
                "played": 0, "won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0, "gd": 0, "pts": 0,
            }
    for m in matches:
        if m["type"] != "group" or not m["finished"]:
            continue
        if not m["home"] or not m["away"] or m["home_score"] is None or m["away_score"] is None:
            continue
        grp = m["group"]
        rows = by_group.get(grp)
        if not rows:
            continue
        h, a = rows.get(m["home"]["id"]), rows.get(m["away"]["id"])
        if not h or not a:
            continue
        hs, as_ = m["home_score"], m["away_score"]
        for row, gf, ga in ((h, hs, as_), (a, as_, hs)):
            row["played"] += 1
            row["gf"] += gf
            row["ga"] += ga
            row["gd"] = row["gf"] - row["ga"]
        if hs > as_:
            h["won"] += 1; h["pts"] += 3; a["lost"] += 1
        elif hs < as_:
            a["won"] += 1; a["pts"] += 3; h["lost"] += 1
        else:
            h["drawn"] += 1; a["drawn"] += 1; h["pts"] += 1; a["pts"] += 1

    out = []
    for grp in sorted(by_group):
        rows = sorted(
            by_group[grp].values(),
            key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["name"]),
        )
        out.append({"group": grp, "rows": rows})
    return out


def main():
    token = get_token()
    print(f"[fetch] base={BASE}")

    teams = [norm_team(t) for t in as_list(_request("/get/teams", token=token))]
    teams = [t for t in teams if t["id"] not in ("", "0")]
    stadiums = [norm_stadium(s) for s in as_list(_request("/get/stadiums", token=token))]
    games = as_list(_request("/get/games", token=token))
    print(f"[fetch] teams={len(teams)} stadiums={len(stadiums)} games={len(games)}")

    teams_by_id = {t["id"]: t for t in teams}
    stad_by_id = {s["id"]: s for s in stadiums}

    matches = [norm_match(g, teams_by_id, stad_by_id) for g in games]
    matches = [m for m in matches if m["id"]]
    standings = compute_standings(matches, teams)

    payload = {
        "meta": {
            "tournament": "FIFA World Cup 2026",
            "source": "worldcup26.ir",
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "is_sample": False,
            "counts": {"teams": len(teams), "stadiums": len(stadiums), "matches": len(matches)},
        },
        "teams": sorted(teams, key=lambda t: t["name"]),
        "stadiums": stadiums,
        "matches": matches,
        "standings": standings,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch] wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from API: {e.read().decode(errors='replace')[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"Network error reaching API: {e.reason}")
