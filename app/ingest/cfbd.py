import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SOURCE = "cfbd"
API_BASE = "https://api.collegefootballdata.com"


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def distance_bucket(distance: int) -> str:
    if distance <= 3:
        return "short"
    if distance <= 6:
        return "medium"
    return "long"


def field_zone(yards_to_goal: int) -> str:
    if yards_to_goal <= 20:
        return "red_zone"
    if yards_to_goal <= 50:
        return "plus"
    if yards_to_goal >= 80:
        return "backed_up"
    return "open_field"


def classify_play_family(play_type: str) -> str | None:
    lowered = play_type.lower()
    if "pass" in lowered or "sack" in lowered or "interception" in lowered:
        return "pass"
    if "rush" in lowered or lowered == "run" or "rushing" in lowered:
        return "run"
    return None


def canonicalize_play(
    row: dict[str, Any],
    season: int,
    week: int,
    fallback_sequence: int,
) -> dict[str, Any] | None:
    play_id = str(row.get("id") or "").strip()
    game_id_raw = row.get("gameId")
    offense = str(row.get("offense") or "").strip()
    defense = str(row.get("defense") or "").strip()
    home = str(row.get("home") or "").strip()
    away = str(row.get("away") or "").strip()
    play_type = str(row.get("playType") or "").strip()
    family = classify_play_family(play_type)
    quarter = _int(row.get("period"))
    down = _int(row.get("down"))
    distance = _int(row.get("distance"))
    yards_to_goal = _int(row.get("yardsToGoal"))

    if not play_id or game_id_raw is None or not offense or not defense or not family:
        return None
    if quarter is None or not 1 <= quarter <= 5:
        return None
    if down is None or not 1 <= down <= 4:
        return None
    if distance is None or distance < 0:
        return None
    if yards_to_goal is None or not 0 <= yards_to_goal <= 100:
        return None

    game_external_id = str(game_id_raw)
    play_external_id = f"{game_external_id}:{play_id}"
    play_number = _int(row.get("playNumber"))
    yards = _int(row.get("yardsGained")) or 0
    ppa = _float(row.get("ppa"))
    clock = row.get("clock") or {}
    minutes = _int(clock.get("minutes")) if isinstance(clock, dict) else None
    seconds = _int(clock.get("seconds")) if isinstance(clock, dict) else None
    clock_text = f"{minutes or 0:02d}:{seconds or 0:02d}"
    offense_score = _int(row.get("offenseScore")) or 0
    defense_score = _int(row.get("defenseScore")) or 0
    lowered_type = play_type.lower()
    turnover = "interception" in lowered_type or (
        "fumble" in lowered_type and "opponent" in lowered_type
    )
    pressure = "sack" if "sack" in lowered_type else None
    explosive = yards >= (20 if family == "pass" else 10)

    tags = ["cfbd", family, "ppa_native"]
    if ppa is not None:
        tags.append("success_proxy_ppa_positive")

    return {
        "source": SOURCE,
        "season": season,
        "week": week,
        "game_external_id": game_external_id,
        "play_external_id": play_external_id,
        "play_sequence": play_number if play_number is not None else fallback_sequence,
        "home_team": home or None,
        "away_team": away or None,
        "quarter": quarter,
        "clock": clock_text,
        "down": down,
        "distance": distance,
        "yard_line": yards_to_goal,
        "distance_bucket": distance_bucket(distance),
        "field_zone": field_zone(yards_to_goal),
        "score_diff": offense_score - defense_score,
        "offense_team": offense,
        "defense_team": defense,
        "personnel_offense": "UNKNOWN",
        "formation": "UNKNOWN",
        "motion": None,
        "play_family": family,
        "concept": None,
        "coverage": None,
        "pressure": pressure,
        "result_yards": yards,
        "epa": None,
        "ppa": ppa,
        "success": bool(ppa is not None and ppa > 0),
        "explosive": explosive,
        "turnover": turnover,
        "source_play_type": play_type,
        "play_text": row.get("playText"),
        "tags": tags,
    }


def fetch_week(
    api_key: str,
    season: int,
    week: int,
    season_type: str = "regular",
) -> list[dict[str, Any]]:
    if not api_key:
        raise ValueError("CFBD_API_KEY is required for live CFBD requests")
    query = urlencode({"year": season, "week": week, "seasonType": season_type})
    request = Request(
        f"{API_BASE}/plays?{query}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "FIELDMIND/0.3 college-data-ingest",
        },
    )
    with urlopen(request, timeout=90) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError("CFBD /plays response was not a JSON array")
    return payload
