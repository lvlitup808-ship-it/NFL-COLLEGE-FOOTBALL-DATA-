from app.ingest.cfbd import canonicalize_play, classify_play_family, distance_bucket, field_zone


def base_play() -> dict:
    return {
        "id": "p1",
        "gameId": 123,
        "playNumber": 4,
        "offense": "Georgia",
        "offenseScore": 7,
        "defense": "Clemson",
        "defenseScore": 3,
        "home": "Georgia",
        "away": "Clemson",
        "period": 2,
        "clock": {"minutes": 8, "seconds": 9},
        "yardsToGoal": 32,
        "down": 3,
        "distance": 5,
        "yardsGained": 21,
        "playType": "Pass Reception",
        "playText": "Complete for 21 yards",
        "ppa": 1.2,
    }


def test_play_type_classifier_is_conservative():
    assert classify_play_family("Pass Reception") == "pass"
    assert classify_play_family("Sack") == "pass"
    assert classify_play_family("Rush") == "run"
    assert classify_play_family("Punt") is None


def test_cfbd_keeps_ppa_separate_from_epa():
    play = canonicalize_play(base_play(), 2025, 1, 99)
    assert play is not None
    assert play["epa"] is None
    assert play["ppa"] == 1.2
    assert play["success"] is True
    assert "ppa_native" in play["tags"]
    assert "success_proxy_ppa_positive" in play["tags"]


def test_cfbd_does_not_invent_film_fields():
    play = canonicalize_play(base_play(), 2025, 1, 99)
    assert play is not None
    assert play["coverage"] is None
    assert play["motion"] is None
    assert play["concept"] is None
    assert play["formation"] == "UNKNOWN"
    assert play["personnel_offense"] == "UNKNOWN"


def test_situation_fields_and_clock():
    play = canonicalize_play(base_play(), 2025, 1, 99)
    assert play is not None
    assert play["clock"] == "08:09"
    assert play["distance_bucket"] == "medium"
    assert play["field_zone"] == "plus"
    assert play["score_diff"] == 4
    assert play["explosive"] is True


def test_invalid_and_special_teams_plays_are_skipped():
    row = base_play()
    row["playType"] = "Punt"
    assert canonicalize_play(row, 2025, 1, 1) is None

    row = base_play()
    row["down"] = None
    assert canonicalize_play(row, 2025, 1, 1) is None


def test_buckets_match_fieldmind_contract():
    assert distance_bucket(3) == "short"
    assert distance_bucket(4) == "medium"
    assert distance_bucket(7) == "long"
    assert field_zone(15) == "red_zone"
    assert field_zone(40) == "plus"
    assert field_zone(70) == "open_field"
    assert field_zone(90) == "backed_up"
