from models import GameEvent, EventType, Player, PlayerStats, GameState


def aggregate_stats(events: list[GameEvent]) -> tuple[dict[str, PlayerStats], GameState]:
    """Process a chronological list of GameEvents into per-player stats.

    Returns:
        A tuple of (player_stats_dict, game_state).
        player_stats_dict is keyed by player.id (e.g. "white_7").
    """
    player_stats: dict[str, PlayerStats] = {}
    game_state = GameState()

    # Sort events by timestamp
    events.sort(key=lambda e: e.timestamp)

    for event in events:
        # Update game state from scoreboard info
        if event.score_home is not None:
            game_state.score_home = event.score_home
        if event.score_away is not None:
            game_state.score_away = event.score_away
        if event.set_number > game_state.current_set:
            # New set started — record the previous set score
            game_state.set_scores.append((game_state.score_home, game_state.score_away))
            game_state.current_set = event.set_number

        # Skip events without a player
        if event.player is None:
            continue

        # Get or create player stats
        pid = event.player.id
        if pid not in player_stats:
            player_stats[pid] = PlayerStats(player=event.player)
        stats = player_stats[pid]

        # Track which sets the player appeared in
        stats.sets_played.add(event.set_number)

        # Update stats based on event type
        match event.event_type:
            case EventType.SERVE:
                stats.total_serves += 1

            case EventType.ACE:
                stats.aces += 1
                stats.total_serves += 1
                stats.points_scored += 1

            case EventType.KILL:
                stats.kills += 1
                stats.attack_attempts += 1
                stats.points_scored += 1

            case EventType.ATTACK_ERROR:
                stats.attack_errors += 1
                stats.attack_attempts += 1

            case EventType.ATTACK_ATTEMPT:
                stats.attack_attempts += 1

            case EventType.ASSIST:
                stats.assists += 1

            case EventType.SOLO_BLOCK:
                stats.solo_blocks += 1
                stats.points_scored += 1

            case EventType.BLOCK_ASSIST:
                stats.block_assists += 1

            case EventType.BLOCK_ERROR:
                stats.block_errors += 1

            case EventType.DIG:
                stats.digs += 1

            case EventType.DIG_ERROR:
                stats.dig_errors += 1

            case EventType.RECEPTION:
                stats.receptions += 1

            case EventType.RECEPTION_ERROR:
                stats.reception_errors += 1

            case EventType.PERFECT_PASS:
                stats.perfect_passes += 1
                stats.receptions += 1

            case EventType.SERVICE_ERROR:
                stats.service_errors += 1
                stats.total_serves += 1

            case EventType.BALL_HANDLING_ERROR:
                stats.ball_handling_errors += 1

            case EventType.POINT_SCORED:
                stats.points_scored += 1

            case EventType.SUBSTITUTION | EventType.ROTATION:
                pass  # tracked via sets_played

    return player_stats, game_state
