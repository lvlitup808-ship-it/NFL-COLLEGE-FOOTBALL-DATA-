import csv
import gzip
import io
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator
from urllib.request import Request, urlopen

SOURCE = "nflverse"
URL_TEMPLATE = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv"


def source_url(season: int) -> str:
    if season < 1999 or season > 2100:
        raise ValueError("nflverse play-by-play seasons must be >= 1999")
    return URL_TEMPLATE.format(season=season)


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "na", "null", "none"}:
        return None
    return text


def _int(value: object) -> int | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _float(value: object) -> float | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _bool(value: object) -> bool | None:
    text = _clean(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in {"1", "true", "t", "yes", "y"}:
        return True
    if lowered in {"0", "false", "f", "no", "n"}:
        return False
    return None


def distance_bucket(distance: int) -> str:
    if distance <= 3:
        return "short"
    if distance <= 6:
        return "medium"
    return "long"


def field_zone(yardline_100: int) -> str:
    if yardline_100 <= 20:
        return "red_zone"
    if yardline_100 <= 50:
        return "plus"
    if yardline_100 >= 80:
        return "backed_up"
    return "open_field"


def _concept(row: dict[str, str], play_type: str) -> str | None:
    if play_type == "pass":
        length = _clean(row.get("pass_length"))
        location = _clean(row.get("pass_location"))
        parts = [part for part in (length, location) if part]
        return "-".join(parts) if parts else None
    location = _clean(row.get("run_location"))
    gap = _clean(row.get("run_gap"))
    parts = [part for part in (location, gap) if part]
    return "-".join(parts) if parts else None


def canonicalize_row(row: dict[str, str], season: int) -> dict[str, object] | None:
    """Normalize one nflverse row. Returns None for non-scrimmage or unusable rows."""
    play_type = (_clean(row.get("play_type")) or "").lower()
    if play_type not in {"pass", "run"}:
        return None

    game_external_id = _clean(row.get("game_id"))
    play_external_id = _clean(row.get("play_id"))
    offense = _clean(row.get("posteam"))
    defense = _clean(row.get("defteam"))
    quarter = _int(row.get("qtr"))
    down = _int(row.get("down"))
    distance = _int(row.get("ydstogo"))
    yardline = _int(row.get("yardline_100"))
    sequence = _int(row.get("play_id"))

    if not game_external_id or not play_external_id or not offense or not defense:
        return None
    if quarter is None or quarter < 1 or quarter > 5:
        return None
    if down is None or down < 1 or down > 4:
        return None
    if distance is None or distance < 0:
        return None
    if yardline is None or yardline < 0 or yardline > 100:
        return None
    if sequence is None:
        return None

    yards = _int(row.get("yards_gained")) or 0
    epa = _float(row.get("epa"))
    success = _bool(row.get("success"))
    if success is None:
        success = bool(epa is not None and epa > 0)

    shotgun = _bool(row.get("shotgun"))
    formation = _clean(row.get("offense_formation"))
    if not formation:
        formation = "Shotgun" if shotgun else "Under Center" if shotgun is False else "UNKNOWN"

    personnel = _clean(row.get("offense_personnel")) or "UNKNOWN"
    qb_hit = _bool(row.get("qb_hit")) is True
    sack = _bool(row.get("sack")) is True
    pressure = "sack" if sack else "hit" if qb_hit else None
    interception = _bool(row.get("interception")) is True
    fumble_lost = _bool(row.get("fumble_lost")) is True
    turnover = interception or fumble_lost
    explosive = yards >= (20 if play_type == "pass" else 10)

    return {
        "source": SOURCE,
        "season": season,
        "game_external_id": game_external_id,
        "play_external_id": f"{game_external_id}:{play_external_id}",
        "play_sequence": sequence,
        "week": _int(row.get("week")),
        "game_date": _clean(row.get("game_date")),
        "season_type": _clean(row.get("season_type")),
        "home_team": _clean(row.get("home_team")),
        "away_team": _clean(row.get("away_team")),
        "quarter": quarter,
        "clock": _clean(row.get("time")) or "00:00",
        "down": down,
        "distance": distance,
        "yard_line": yardline,
        "distance_bucket": distance_bucket(distance),
        "field_zone": field_zone(yardline),
        "score_diff": _int(row.get("score_differential")) or 0,
        "offense_team": offense,
        "defense_team": defense,
        "personnel_offense": personnel,
        "formation": formation,
        "motion": None,
        "play_family": play_type,
        "concept": _concept(row, play_type),
        "coverage": None,
        "pressure": pressure,
        "result_yards": yards,
        "epa": epa,
        "success": success,
        "explosive": explosive,
        "turnover": turnover,
        "tags": ["nflverse", play_type],
    }


@contextmanager
def _binary_stream(uri: str) -> Iterator[BinaryIO]:
    if uri.startswith("http://") or uri.startswith("https://"):
        request = Request(uri, headers={"User-Agent": "FIELDMIND/0.2 data-ingest"})
        with urlopen(request, timeout=90) as response:
            yield response
        return
    with Path(uri).open("rb") as handle:
        yield handle


@contextmanager
def csv_rows(uri: str) -> Iterator[csv.DictReader]:
    """Yield a streaming DictReader without materializing a season in memory."""
    with _binary_stream(uri) as binary:
        if uri.lower().endswith(".gz"):
            wrapped_binary: BinaryIO = gzip.GzipFile(fileobj=binary)
        else:
            wrapped_binary = binary
        text = io.TextIOWrapper(wrapped_binary, encoding="utf-8-sig", newline="")
        try:
            yield csv.DictReader(text)
        finally:
            text.detach()
