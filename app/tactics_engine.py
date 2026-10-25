"""Deterministic, explicitly hypothetical football tactics engine.

This module does not infer real coverage, personnel, or player ability from film.
All positions are yards, x across field (0..53.333), y downfield (0..120).
"""
from __future__ import annotations
from dataclasses import dataclass
from math import hypot, isfinite
from typing import Any

FIELD_WIDTH = 160 / 3
MAX_PLAYERS = 22
MAX_FRAMES = 1200
MAX_SECONDS = 20.0

@dataclass(frozen=True)
class Actor:
    id: str
    team: str
    x: float
    y: float
    route: tuple[tuple[float, float, float], ...]

def validate_play(play: dict[str, Any]) -> list[Actor]:
    players = play.get("players")
    if not isinstance(players, list) or not 1 <= len(players) <= MAX_PLAYERS:
        raise ValueError("players must contain 1 to 22 actors")
    ids = set()
    actors = []
    for p in players:
        if not isinstance(p, dict):
            raise ValueError("invalid actor")
        ident, team = p.get("id"), p.get("team")
        if not isinstance(ident, str) or not 1 <= len(ident) <= 32 or ident in ids:
            raise ValueError("actor ids must be unique strings of 1-32 characters")
        if team not in ("offense", "defense"):
            raise ValueError("team must be offense or defense")
        ids.add(ident)
        x, y = float(p["x"]), float(p["y"])
        if not all(map(isfinite, (x, y))) or not (0 <= x <= FIELD_WIDTH and 0 <= y <= 120):
            raise ValueError("actor outside field")
        raw = p.get("route", [])
        if not isinstance(raw, list) or len(raw) > 64:
            raise ValueError("route must be a list with at most 64 waypoints")
        route = []
        previous_t = 0.0
        for wp in raw:
            t, px, py = float(wp["t"]), float(wp["x"]), float(wp["y"])
            if not all(map(isfinite, (t, px, py))) or not previous_t < t <= MAX_SECONDS:
                raise ValueError("waypoint times must increase within 20 seconds")
            if not (0 <= px <= FIELD_WIDTH and 0 <= py <= 120):
                raise ValueError("waypoint outside field")
            route.append((t, px, py))
            previous_t = t
        actors.append(Actor(ident, team, x, y, tuple(route)))
    return actors

def interpolate(actor: Actor, t: float) -> tuple[float, float]:
    px, py, pt = actor.x, actor.y, 0.0
    for end_t, ex, ey in actor.route:
        if t <= end_t:
            alpha = max(0.0, (t - pt) / (end_t - pt))
            return (round(px + (ex - px) * alpha, 4),
                    round(py + (ey - py) * alpha, 4))
        px, py, pt = ex, ey, end_t
    return px, py

def simulate(play: dict[str, Any], fps: int = 10, duration: float = 6.0) -> dict[str, Any]:
    actors = validate_play(play)
    if not isinstance(fps, int) or not 1 <= fps <= 60:
        raise ValueError("fps must be 1..60")
    if not isfinite(duration) or not 0 < duration <= MAX_SECONDS:
        raise ValueError("duration must be in (0,20]")
    count = round(duration * fps) + 1
    if count > MAX_FRAMES:
        raise ValueError("too many frames")
    frames = []
    for i in range(count):
        t = min(duration, i / fps)
        frames.append({"t": round(t, 4), "players": [
            {"id": a.id, "team": a.team, "x": interpolate(a, t)[0],
             "y": interpolate(a, t)[1]} for a in actors]})
    return {"kind": "hypothetical_simulation", "fps": fps, "frames": frames,
            "limitations": ["Scripted waypoint interpolation, not validated player physics",
                            "No inferred coverage, outcome probability, or football IQ score"]}

def assess(play: dict[str, Any]) -> dict[str, Any]:
    """Explicit geometric checks, not an AI prediction of football success."""
    actors = validate_play(play)
    findings = []
    for a in actors:
        prev = (0.0, a.x, a.y)
        for wp in a.route:
            dt = wp[0] - prev[0]
            speed = hypot(wp[1] - prev[1], wp[2] - prev[2]) / dt
            if speed > 12:
                findings.append({"actor": a.id, "rule": "speed_over_12_yards_per_second",
                                 "speed_yd_s": round(speed, 2)})
            prev = wp
    return {"kind": "geometry_checks_only", "findings": findings,
            "validated_game_outcome": False}
