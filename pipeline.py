"""Pipeline wrapper — orchestrates video analysis and stores results in the database.

Wraps existing pipeline modules (downloader, frame_extractor, analyzer, stats_tracker)
for use from the Streamlit UI with progress callbacks.
"""

from pathlib import Path

from config import DOWNLOADS_DIR
from models import EventType


def run_full_pipeline(video_source, game_id, home_team_id, away_team_id, progress_callback=None):
    """Run the full analysis pipeline: download/locate → extract → analyze → store.

    Args:
        video_source: YouTube URL or local file path.
        game_id: ID of the game record in the database.
        home_team_id: DB ID for home team.
        away_team_id: DB ID for away team.
        progress_callback: Optional callable(stage: str, pct: float) for UI updates.

    Returns:
        dict with keys: events_count, players_found, sets_detected
    """
    def _progress(stage, pct):
        if progress_callback:
            progress_callback(stage, pct)

    import db

    # Step 1: Download or locate video
    _progress("Locating video...", 0.0)
    video_path = _download_or_locate(video_source, game_id)
    _progress("Video ready", 0.15)

    # Step 2: Extract frames
    _progress("Extracting frames...", 0.15)
    from frame_extractor import extract_frames
    frames = extract_frames(video_path)
    _progress(f"Extracted {len(frames)} frames", 0.35)

    # Step 3: Analyze with Claude Vision
    _progress("Analyzing frames with Claude Vision...", 0.35)
    from analyzer import analyze_frames
    events = analyze_frames(frames)
    _progress(f"Detected {len(events)} events", 0.75)

    # Step 4: Aggregate stats
    _progress("Aggregating statistics...", 0.75)
    from stats_tracker import aggregate_stats
    player_stats, game_state = aggregate_stats(events)
    _progress("Stats aggregated", 0.85)

    # Step 5: Store results in DB
    _progress("Saving to database...", 0.85)
    result = _store_pipeline_results(game_id, home_team_id, away_team_id,
                                     events, player_stats, game_state)
    db.update_game(game_id, status="completed", video_path=str(video_path))
    _progress("Complete!", 1.0)

    return result


def _download_or_locate(video_source, game_id):
    """Resolve a video source to a local file path.

    If video_source looks like a URL, download via yt-dlp.
    Otherwise treat as a local file path.
    """
    import db

    source = video_source.strip()
    if source.startswith("http://") or source.startswith("https://"):
        from downloader import download_video
        video_path = download_video(source)
        db.update_game(game_id, video_url=source, video_path=str(video_path))
        return video_path

    path = Path(source)
    if path.exists():
        db.update_game(game_id, video_path=str(path))
        return path

    raise FileNotFoundError(f"Video not found: {source}")


def _store_pipeline_results(game_id, home_team_id, away_team_id,
                            events, player_stats, game_state):
    """Convert pipeline output into database records.

    Returns dict with summary counts.
    """
    import db

    # Determine set structure from game_state
    set_scores = list(game_state.set_scores)
    # Add current/final set
    set_scores.append((game_state.score_home, game_state.score_away))

    set_ids = {}
    for i, (home_s, away_s) in enumerate(set_scores, start=1):
        set_id = db.create_set(game_id, i, home_s, away_s)
        set_ids[i] = set_id

    # Ensure at least set 1 exists
    if not set_ids:
        set_ids[1] = db.create_set(game_id, 1, game_state.score_home, game_state.score_away)

    # Store events as rallies (point_scored events)
    rallies_stored = _store_events_as_rallies(game_id, events, home_team_id, away_team_id, set_ids)

    # Store player stats
    players_stored = 0
    for pid, pstats in player_stats.items():
        team_id = _map_team_color_to_id(pstats.player.team, home_team_id, away_team_id)
        player_id = db.get_or_create_player(
            team_id, pstats.player.jersey_number,
            name=pstats.player.name or f"#{pstats.player.jersey_number}",
            position="",
        )
        players_stored += 1

        # Store stats per set the player appeared in
        for set_num in pstats.sets_played:
            set_id = set_ids.get(set_num, set_ids.get(1))
            # For now, store all stats under the set (aggregated per set requires
            # more granular event tracking — store full stats under set 1 if single set)
            db.upsert_player_set_stats(
                player_id, set_id,
                serves=pstats.total_serves,
                aces=pstats.aces,
                service_errors=pstats.service_errors,
                kills=pstats.kills,
                attack_errors=pstats.attack_errors,
                attack_attempts=pstats.attack_attempts,
                solo_blocks=pstats.solo_blocks,
                block_assists=pstats.block_assists,
                block_errors=pstats.block_errors,
                digs=pstats.digs,
                dig_errors=pstats.dig_errors,
                receptions=pstats.receptions,
                reception_errors=pstats.reception_errors,
                perfect_passes=pstats.perfect_passes,
                assists=pstats.assists,
                ball_handling_errors=pstats.ball_handling_errors,
                points=pstats.points_scored,
            )

    return {
        "events_count": len(events),
        "players_found": players_stored,
        "sets_detected": len(set_ids),
    }


def _map_team_color_to_id(color, home_team_id, away_team_id):
    """Map an analyzer color string (e.g. 'white', 'dark') to a team ID.

    Uses simple heuristics — 'home'/'dark' → home, 'away'/'white' → away.
    Falls back to home_team_id if uncertain.
    """
    color_lower = color.lower() if color else ""
    # Direct labels from analyzer
    if "home" in color_lower:
        return home_team_id
    if "away" in color_lower:
        return away_team_id
    # Color-based heuristics (common in volleyball)
    if any(w in color_lower for w in ("white", "light")):
        return away_team_id
    if any(w in color_lower for w in ("dark", "black", "navy", "blue", "red")):
        return home_team_id
    return home_team_id


def _store_events_as_rallies(game_id, events, home_team_id, away_team_id, set_ids):
    """Create rally records from point_scored events."""
    import db

    rally_count = 0
    point_events = [e for e in events if e.event_type == EventType.POINT_SCORED]

    for i, event in enumerate(point_events, start=1):
        set_num = event.set_number
        set_id = set_ids.get(set_num, set_ids.get(1))

        scoring_team = ""
        if event.player:
            tid = _map_team_color_to_id(event.player.team, home_team_id, away_team_id)
            team = db.get_team(tid)
            scoring_team = team["abbreviation"] if team else event.player.team

        score_str = ""
        if event.score_home is not None and event.score_away is not None:
            score_str = f"{event.score_home}-{event.score_away}"

        # Convert timestamp to mm:ss
        mins = int(event.timestamp // 60)
        secs = int(event.timestamp % 60)
        video_time = f"{mins}:{secs:02d}"

        db.upsert_rally(
            set_id, i,
            video_time=video_time,
            score_after=score_str,
            scoring_team=scoring_team,
            play_type=event.details or "Rally",
            key_player=event.player.id if event.player else "",
            confidence="M",
            notes=event.details,
        )
        rally_count += 1

    return rally_count
