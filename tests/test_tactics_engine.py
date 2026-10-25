import pytest
from app.tactics_engine import simulate, assess, validate_play

PLAY = {"players": [
    {"id": "WR1", "team": "offense", "x": 12, "y": 40,
     "route": [{"t": 2, "x": 12, "y": 50}]},
    {"id": "CB1", "team": "defense", "x": 12, "y": 45, "route": []},
]}

def test_deterministic_interpolation():
    a = simulate(PLAY, fps=2, duration=2)
    assert a == simulate(PLAY, fps=2, duration=2)
    assert a["frames"][2]["players"][0]["y"] == 45
    assert a["frames"][-1]["players"][0]["y"] == 50

def test_invalid_actor_and_duplicate():
    with pytest.raises(ValueError):
        validate_play({"players": [PLAY["players"][0]] * 2})

def test_out_of_bounds():
    with pytest.raises(ValueError):
        validate_play({"players": [{"id": "X", "team": "offense", "x": 70, "y": 20}]})

def test_speed_flag():
    p = {"players": [{"id": "X", "team": "offense", "x": 10, "y": 20,
                       "route": [{"t": 0.1, "x": 10, "y": 30}]}]}
    assert assess(p)["findings"][0]["rule"] == "speed_over_12_yards_per_second"

def test_frame_cap():
    with pytest.raises(ValueError):
        simulate(PLAY, fps=60, duration=20)
