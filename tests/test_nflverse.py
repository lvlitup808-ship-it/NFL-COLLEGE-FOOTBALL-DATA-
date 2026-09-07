from app.ingest.nflverse import canonicalize_row, distance_bucket, field_zone, source_url


def base_row() -> dict[str, str]:
    return {
        "game_id": "2025_01_DAL_PHI",
        "play_id": "1234",
        "season_type": "REG",
        "week": "1",
        "game_date": "2025-09-04",
        "home_team": "PHI",
        "away_team": "DAL",
        "posteam": "PHI",
        "defteam": "DAL",
        "qtr": "2",
        "time": "08:41",
        "down": "3",
        "ydstogo": "5",
        "yardline_100": "32",
        "score_differential": "3",
        "play_type": "pass",
        "yards_gained": "22",
        "epa": "1.42",
        "success": "1",
        "shotgun": "1",
        "offense_personnel": "11",
        "pass_length": "short",
        "pass_location": "middle",
        "qb_hit": "1",
        "sack": "0",
        "interception": "0",
        "fumble_lost": "0",
    }


def test_source_url_is_official_release_pattern():
    assert source_url(2025).endswith("/pbp/play_by_play_2025.csv")


def test_distance_and_field_buckets():
    assert distance_bucket(3) == "short"
    assert distance_bucket(6) == "medium"
    assert distance_bucket(7) == "long"
    assert field_zone(20) == "red_zone"
    assert field_zone(45) == "plus"
    assert field_zone(65) == "open_field"
    assert field_zone(85) == "backed_up"


def test_pass_normalizes_without_inventing_film_only_fields():
    play = canonicalize_row(base_row(), 2025)
    assert play is not None
    assert play["play_family"] == "pass"
    assert play["distance_bucket"] == "medium"
    assert play["field_zone"] == "plus"
    assert play["formation"] == "Shotgun"
    assert play["concept"] == "short-middle"
    assert play["pressure"] == "hit"
    assert play["explosive"] is True
    assert play["coverage"] is None
    assert play["motion"] is None
    assert play["play_external_id"] == "2025_01_DAL_PHI:1234"


def test_run_explosive_threshold_and_epa_success_fallback():
    row = base_row()
    row.update(
        {
            "play_type": "run",
            "yards_gained": "11",
            "success": "",
            "epa": "0.25",
            "shotgun": "0",
            "run_location": "left",
            "run_gap": "guard",
            "qb_hit": "0",
        }
    )
    play = canonicalize_row(row, 2025)
    assert play is not None
    assert play["play_family"] == "run"
    assert play["explosive"] is True
    assert play["success"] is True
    assert play["formation"] == "Under Center"
    assert play["concept"] == "left-guard"


def test_non_scrimmage_and_bad_context_are_rejected():
    row = base_row()
    row["play_type"] = "punt"
    assert canonicalize_row(row, 2025) is None

    row = base_row()
    row["down"] = ""
    assert canonicalize_row(row, 2025) is None
