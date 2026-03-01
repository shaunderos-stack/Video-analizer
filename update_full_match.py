"""Update the database with full match data (all 5 sets) from scoreboard analysis."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import db

# Scoreboard readings from visual analysis of match video
# Each entry: (video_time_str, usta_score, ukc_score)
SET_2_READINGS = [
    ("72:00", 1, 0),
    ("75:00", 5, 3),
    ("78:00", 9, 6),
    ("81:00", 15, 8),
    ("84:00", 19, 12),
    ("86:00", 20, 15),
    ("88:00", 22, 15),
    ("90:00", 25, 15),
]

SET_3_READINGS = [
    ("94:00", 0, 2),
    ("98:00", 6, 5),
    ("102:00", 10, 7),
    ("106:00", 13, 13),
    ("109:00", 18, 15),
    ("111:00", 19, 18),
    ("114:00", 21, 19),
    ("116:00", 23, 19),
    # Set ended ~117:00 with USTA winning 25-19
]

SET_4_READINGS = [
    ("120:00", 0, 0),
    ("123:00", 4, 5),
    ("126:00", 7, 9),
    ("130:00", 7, 14),
    ("134:00", 13, 18),
    ("136:00", 13, 19),
    ("139:00", 17, 19),
    ("141:00", 19, 21),
    ("143:00", 21, 23),
    ("145:00", 21, 25),
]

SET_5_READINGS = [
    ("149:00", 0, 0),
    ("152:00", 4, 2),
    ("155:00", 7, 4),
    ("158:00", 10, 7),
    ("160:00", 12, 7),
    ("163:00", 13, 11),
    ("165:00", 15, 11),
]

# Set final scores: (home/USTA, away/UKC)
SET_SCORES = {
    1: (17, 25),   # already in DB
    2: (25, 15),
    3: (25, 19),
    4: (21, 25),
    5: (15, 11),
}


def generate_rallies_from_readings(readings, final_home, final_away):
    """Generate point-by-point rally entries from scoreboard readings.

    Between consecutive readings, distribute points proportionally.
    Returns list of (rally_num, video_time, score_before, score_after, scoring_team).
    """
    rallies = []
    rally_num = 0
    prev_home = 0
    prev_away = 0

    for time_str, home, away in readings:
        # Skip if no score change from previous
        if home == prev_home and away == prev_away:
            continue

        home_gained = home - prev_home
        away_gained = away - prev_away

        # Generate individual point entries for each point scored
        cur_h = prev_home
        cur_a = prev_away
        total_points = home_gained + away_gained

        if total_points == 0:
            prev_home = home
            prev_away = away
            continue

        # Interleave points proportionally
        for p in range(total_points):
            # Distribute: alternate based on ratio
            h_remaining = home - cur_h
            a_remaining = away - cur_a
            total_remaining = h_remaining + a_remaining

            if total_remaining == 0:
                break

            score_before = f"{cur_h}-{cur_a}"

            if h_remaining > 0 and (a_remaining == 0 or
                    h_remaining / total_remaining >= away_gained / max(total_points, 1)):
                cur_h += 1
                scoring = "USTA"
            else:
                cur_a += 1
                scoring = "UKC"

            score_after = f"{cur_h}-{cur_a}"
            rally_num += 1
            rallies.append((rally_num, time_str, score_before, score_after, scoring))

        prev_home = home
        prev_away = away

    # Add remaining points to reach final score if needed
    if prev_home < final_home or prev_away < final_away:
        remaining_h = final_home - prev_home
        remaining_a = final_away - prev_away
        cur_h = prev_home
        cur_a = prev_away
        for _ in range(remaining_h + remaining_a):
            score_before = f"{cur_h}-{cur_a}"
            h_rem = final_home - cur_h
            a_rem = final_away - cur_a
            if h_rem > 0 and (a_rem == 0 or h_rem >= a_rem):
                cur_h += 1
                scoring = "USTA"
            else:
                cur_a += 1
                scoring = "UKC"
            score_after = f"{cur_h}-{cur_a}"
            rally_num += 1
            rallies.append((rally_num, "~end", score_before, score_after, scoring))

    return rallies


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== Updating Database with Full Match Data ===\n")

    db.init_db()

    # Get existing game (should be game_id=1)
    games = db.get_all_games()
    if not games:
        print("Error: No games found in database")
        sys.exit(1)

    game = games[0]
    game_id = game["id"]
    print(f"Game ID: {game_id} - {game['home_abbr']} vs {game['away_abbr']}")

    # Get existing sets
    existing_sets = db.get_sets_for_game(game_id)
    existing_set_nums = {s["set_number"]: s["id"] for s in existing_sets}
    print(f"Existing sets: {list(existing_set_nums.keys())}")

    # Create missing sets (2-5)
    set_ids = dict(existing_set_nums)
    for set_num, (home_score, away_score) in SET_SCORES.items():
        if set_num in set_ids:
            # Update existing set score if needed
            db.update_set(set_ids[set_num], home_score=home_score, away_score=away_score)
            print(f"  Set {set_num}: Updated score to USTA {home_score} - UKC {away_score}")
        else:
            set_id = db.create_set(game_id, set_num, home_score, away_score)
            set_ids[set_num] = set_id
            print(f"  Set {set_num}: Created (USTA {home_score} - UKC {away_score})")

    # Generate and store rally data for sets 2-5
    set_readings = {
        2: (SET_2_READINGS, 25, 15),
        3: (SET_3_READINGS, 25, 19),
        4: (SET_4_READINGS, 21, 25),
        5: (SET_5_READINGS, 15, 11),
    }

    total_rallies = 0
    for set_num, (readings, final_h, final_a) in set_readings.items():
        set_id = set_ids[set_num]
        rallies = generate_rallies_from_readings(readings, final_h, final_a)
        print(f"\n  Set {set_num}: {len(rallies)} rallies generated")

        for rally_num, time_str, score_before, score_after, scoring in rallies:
            db.upsert_rally(
                set_id, rally_num,
                video_time=time_str,
                score_before=score_before,
                score_after=score_after,
                scoring_team=scoring,
                play_type="Rally",
                key_player="",
                confidence="M",
                notes=f"From scoreboard analysis at {time_str}",
            )
        total_rallies += len(rallies)

    # Update game metadata
    db.update_game(
        game_id,
        date="2026-01-25",
        video_url="https://www.youtube.com/watch?v=_8IpwuW7CdM",
        video_path=r"C:\Users\shaun\Video analizer\downloads\match.mp4",
        notes="Full match analyzed (5 sets). USTA wins 3-2 (17-25, 25-15, 25-19, 21-25, 15-11).",
    )
    print(f"\n  Game record updated with video URL and match notes")

    # Verify
    print("\n=== Verification ===")
    sets = db.get_sets_for_game(game_id)
    for s in sets:
        rallies = db.get_rallies_for_set(s["id"])
        print(f"  Set {s['set_number']}: USTA {s['home_score']} - UKC {s['away_score']}  ({len(rallies)} rallies)")

    game = db.get_game(game_id)
    print(f"\n  Game: {game['home_abbr']} vs {game['away_abbr']}")
    print(f"  Date: {game['date']}")
    print(f"  Video: {game['video_url']}")
    print(f"  Notes: {game['notes']}")
    print(f"\n  Total new rallies stored: {total_rallies}")
    print("\nDone!")


if __name__ == "__main__":
    main()
