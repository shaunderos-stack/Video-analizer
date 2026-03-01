"""Feature 3: Play type classification — heuristic + optional API mode.

Classifies rallies into: Ace, Service Error, Kill, Attack Error, Block,
Block Error, Ball Handling Error, Rally.

Heuristic mode works locally without an API key by analysing rally duration
and metadata patterns.
"""

import db
from models import PlayType


def classify_by_duration(duration_sec):
    """Quick classification based on rally duration alone.

    <3s  → likely ace or service error
    3-8s → likely a kill or attack play
    >8s  → extended rally
    """
    if duration_sec is None:
        return PlayType.RALLY
    if duration_sec < 3.0:
        return PlayType.ACE  # or SERVICE_ERROR — refined by scoring team
    if duration_sec <= 8.0:
        return PlayType.KILL
    return PlayType.RALLY


def classify_rally_heuristic(rally, prev_rally=None, next_rally=None):
    """Classify a single rally using available metadata.

    Uses: duration between rallies, scoring team vs serving team,
    play_type hints already in the data, and score progression patterns.

    Args:
        rally: Rally dict from DB.
        prev_rally: Previous rally dict (for timing).
        next_rally: Next rally dict (unused, for future expansion).

    Returns:
        dict with 'play_type' (PlayType value string) and 'confidence'.
    """
    scoring_team = rally.get("scoring_team", "")
    serving_team = rally.get("serving_team", "")
    is_sideout = rally.get("is_sideout", 0)

    # Try to estimate duration from consecutive rally timestamps
    duration = _estimate_duration(rally, prev_rally)

    # Existing play_type hint
    existing = (rally.get("play_type") or "").strip()
    if existing and existing not in ("Kill/Rally", "Rally", ""):
        # Already classified — keep it
        return {"play_type": existing, "confidence": "high"}

    # Short rally (< 3s) — ace or service error
    if duration is not None and duration < 3.0:
        if scoring_team == serving_team:
            return {"play_type": PlayType.ACE.value, "confidence": "medium"}
        else:
            return {"play_type": PlayType.SERVICE_ERROR.value, "confidence": "medium"}

    # Sideout context
    if is_sideout:
        # The receiving team scored — likely a kill or attack
        if duration is not None and duration <= 6.0:
            return {"play_type": PlayType.KILL.value, "confidence": "medium"}
        return {"play_type": PlayType.KILL.value, "confidence": "low"}

    # Serving team scored (not sideout)
    if scoring_team == serving_team:
        if duration is not None and duration < 5.0:
            return {"play_type": PlayType.ACE.value, "confidence": "low"}
        if duration is not None and duration <= 8.0:
            return {"play_type": PlayType.KILL.value, "confidence": "low"}
        return {"play_type": PlayType.RALLY.value, "confidence": "low"}

    # Default — medium/long rally
    if duration is not None and duration > 8.0:
        return {"play_type": PlayType.RALLY.value, "confidence": "low"}

    return {"play_type": PlayType.KILL.value, "confidence": "low"}


def _estimate_duration(rally, prev_rally):
    """Estimate rally duration from timestamps of consecutive rallies."""
    if not prev_rally:
        return None

    def _parse_time(vt):
        if not vt:
            return None
        try:
            if ":" in str(vt):
                parts = str(vt).split(":")
                return int(parts[0]) * 60 + float(parts[1])
            return float(vt)
        except (ValueError, IndexError):
            return None

    t_cur = _parse_time(rally.get("video_time"))
    t_prev = _parse_time(prev_rally.get("video_time"))

    if t_cur is not None and t_prev is not None:
        d = t_cur - t_prev
        if 0 < d < 120:  # sanity check
            return d
    return None


def classify_all_rallies(game_id, mode="heuristic"):
    """Batch classify all unclassified rallies for a game.

    Args:
        game_id: Game ID.
        mode: "heuristic" (local, no API) or could be extended to "api".

    Returns:
        Number of rallies classified.
    """
    rallies = db.get_rallies_for_game(game_id)
    if not rallies:
        return 0

    classified = 0
    for i, r in enumerate(rallies):
        prev = rallies[i - 1] if i > 0 else None
        nxt = rallies[i + 1] if i < len(rallies) - 1 else None

        result = classify_rally_heuristic(r, prev, nxt)

        # Only update if we have a better classification than current
        current_type = (r.get("play_type") or "").strip()
        if current_type in ("", "Kill/Rally", "Rally") or result["confidence"] != "low":
            db.update_rally(
                r["id"],
                play_type=result["play_type"],
                confidence=result["confidence"],
            )
            classified += 1

    return classified


def get_play_type_distribution(game_id):
    """Get counts of each play type for a game (for pie charts).

    Returns dict like {"Kill": 15, "Ace": 3, "Rally": 8, ...}.
    """
    rallies = db.get_rallies_for_game(game_id)
    dist = {}
    for r in rallies:
        pt = (r.get("play_type") or "Unknown").strip()
        if not pt:
            pt = "Unknown"
        dist[pt] = dist.get(pt, 0) + 1
    return dist
