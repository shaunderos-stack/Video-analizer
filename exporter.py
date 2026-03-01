from pathlib import Path

import pandas as pd

from config import OUTPUT_DIR
from models import PlayerStats, GameState


def _stats_to_rows(player_stats: dict[str, PlayerStats]) -> list[dict]:
    """Convert player stats into a list of flat dictionaries for DataFrame creation."""
    rows = []
    for pid, stats in sorted(player_stats.items()):
        rows.append({
            "Team": stats.player.team,
            "Jersey #": stats.player.jersey_number,
            "Name": stats.player.name or "",
            "Sets Played": stats.sets_played_count,
            "Points": stats.points_scored,
            # Attacking
            "Kills": stats.kills,
            "Attack Errors": stats.attack_errors,
            "Attack Attempts": stats.attack_attempts,
            "Hitting %": round(stats.hitting_percentage, 3),
            # Serving
            "Aces": stats.aces,
            "Service Errors": stats.service_errors,
            "Total Serves": stats.total_serves,
            # Passing
            "Receptions": stats.receptions,
            "Reception Errors": stats.reception_errors,
            "Perfect Passes": stats.perfect_passes,
            # Defense
            "Digs": stats.digs,
            "Dig Errors": stats.dig_errors,
            # Blocking
            "Solo Blocks": stats.solo_blocks,
            "Block Assists": stats.block_assists,
            "Block Errors": stats.block_errors,
            "Total Blocks": stats.total_blocks,
            # Setting
            "Assists": stats.assists,
            "Ball Handling Errors": stats.ball_handling_errors,
        })
    return rows


def _team_summary(player_stats: dict[str, PlayerStats], game_state: GameState) -> list[dict]:
    """Build a team-level summary."""
    teams: dict[str, dict] = {}

    for stats in player_stats.values():
        team = stats.player.team
        if team not in teams:
            teams[team] = {
                "Team": team,
                "Players": 0, "Points": 0,
                "Kills": 0, "Attack Errors": 0, "Attack Attempts": 0,
                "Aces": 0, "Service Errors": 0, "Total Serves": 0,
                "Digs": 0, "Total Blocks": 0, "Assists": 0,
                "Receptions": 0, "Reception Errors": 0,
            }
        t = teams[team]
        t["Players"] += 1
        t["Points"] += stats.points_scored
        t["Kills"] += stats.kills
        t["Attack Errors"] += stats.attack_errors
        t["Attack Attempts"] += stats.attack_attempts
        t["Aces"] += stats.aces
        t["Service Errors"] += stats.service_errors
        t["Total Serves"] += stats.total_serves
        t["Digs"] += stats.digs
        t["Total Blocks"] += stats.total_blocks
        t["Assists"] += stats.assists
        t["Receptions"] += stats.receptions
        t["Reception Errors"] += stats.reception_errors

    # Add hitting percentage
    for t in teams.values():
        attempts = t["Attack Attempts"]
        if attempts > 0:
            t["Hitting %"] = round((t["Kills"] - t["Attack Errors"]) / attempts, 3)
        else:
            t["Hitting %"] = 0.0

    return list(teams.values())


def export_stats(
    player_stats: dict[str, PlayerStats],
    game_state: GameState,
    filename_prefix: str = "volleyball_stats",
) -> tuple[Path, Path]:
    """Export stats to CSV and Excel files.

    Returns paths to the CSV and Excel files.
    """
    rows = _stats_to_rows(player_stats)

    if not rows:
        print("No player stats to export.")
        csv_path = OUTPUT_DIR / f"{filename_prefix}.csv"
        xlsx_path = OUTPUT_DIR / f"{filename_prefix}.xlsx"
        pd.DataFrame().to_csv(csv_path, index=False)
        pd.DataFrame().to_excel(xlsx_path, index=False)
        return csv_path, xlsx_path

    df_players = pd.DataFrame(rows)

    # --- CSV ---
    csv_path = OUTPUT_DIR / f"{filename_prefix}.csv"
    df_players.to_csv(csv_path, index=False)
    print(f"CSV exported: {csv_path}")

    # --- Excel with multiple sheets ---
    xlsx_path = OUTPUT_DIR / f"{filename_prefix}.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        # Sheet 1: Player stats
        df_players.to_excel(writer, sheet_name="Player Stats", index=False)

        # Sheet 2: Team summary
        team_rows = _team_summary(player_stats, game_state)
        df_teams = pd.DataFrame(team_rows)
        df_teams.to_excel(writer, sheet_name="Team Summary", index=False)

        # Sheet 3: Set-by-set scores
        set_data = []
        for i, (h, a) in enumerate(game_state.set_scores):
            set_data.append({"Set": i + 1, "Home": h, "Away": a})
        # Add current set
        set_data.append({
            "Set": game_state.current_set,
            "Home": game_state.score_home,
            "Away": game_state.score_away,
        })
        df_sets = pd.DataFrame(set_data)
        df_sets.to_excel(writer, sheet_name="Set Scores", index=False)

    print(f"Excel exported: {xlsx_path}")

    # --- Console summary ---
    print("\n=== PLAYER STATS ===")
    print(df_players.to_string(index=False))
    print("\n=== TEAM SUMMARY ===")
    print(pd.DataFrame(team_rows).to_string(index=False))

    return csv_path, xlsx_path
