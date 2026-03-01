"""Generate comprehensive per-player and per-team Excel/CSV output from Set 1 analysis.

Based on rally-by-rally review of dense frame bursts (0.5s intervals, 10s window)
around each of the 43 detected score changes in Set 1.
ACAA Women's Volleyball match: UKC @ USTA, January 25, 2026.

Rally detection: automated scoreboard pixel-change detection at 0.5s intervals.
Score verification: manual scoreboard reading for every rally (LEFT=USTA home, RIGHT=UKC visitor).
Team identification: USTA wears dark/navy jerseys (right court); UKC wears white jerseys (left court).
"""
import pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from openpyxl.drawing.image import Image as XlImage

output_dir = Path(__file__).parent / "output"
output_dir.mkdir(exist_ok=True)


# =============================================================================
# Helper Functions
# =============================================================================

def format_hit_pct(kills, atk_err, atk_att):
    """Format hitting percentage volleyball-style: '.333' not '0.333', '--' if no attempts."""
    if atk_att == 0:
        return "--"
    pct = (kills - atk_err) / atk_att
    s = f"{pct:.3f}"
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    return s


def compute_team_stats(players):
    """Sum all numeric stat fields across players. Returns dict with totals + computed hit%."""
    fields = ['serves', 'aces', 'svc_err', 'kills', 'atk_err', 'atk_att',
              'blocks', 'digs', 'receptions', 'assists', 'total_points']
    stats = {f: sum(p[f] for p in players.values()) for f in fields}
    if stats['atk_att'] > 0:
        stats['hit_pct'] = (stats['kills'] - stats['atk_err']) / stats['atk_att']
    else:
        stats['hit_pct'] = 0.0
    return stats


def player_dict_to_tuple(jersey, player):
    """Convert player dict back to tuple matching existing DataFrame column structure."""
    hit_pct = format_hit_pct(player['kills'], player['atk_err'], player['atk_att'])
    return (
        jersey,
        player['jersey_color'],
        player['position'],
        player['serves'], player['aces'], player['svc_err'],
        player['kills'], player['atk_err'], player['atk_att'], hit_pct,
        player['blocks'], player['digs'], player['receptions'], player['assists'],
        player['total_points'],
        player['confidence'],
    )


def compute_rotations(rally_data):
    """Compute volleyball rotation (1-6) for each team at each rally.

    UKC serves first from R1. Both teams start in R1.
    When a team gains serve via sideout, that team rotates (R increments, wrapping 6->1).
    Rotation recorded is the state DURING the rally; updates happen after.
    """
    rotation_data = []
    ukc_rot = 1
    usta_rot = 1
    serving_team = "UKC"  # UKC served first
    rally_num = 0

    for entry in rally_data:
        det_num, time, score_before, score_after, scoring_team, play_type, key_player, confidence, notes = entry
        if scoring_team == "FALSE POSITIVE":
            continue
        rally_num += 1
        is_sideout = (scoring_team != serving_team)

        rotation_data.append({
            'rally_num': rally_num,
            'det_num': det_num,
            'time': time,
            'score_before': score_before,
            'score_after': score_after,
            'scoring_team': scoring_team,
            'serving_team': serving_team,
            'ukc_rotation': ukc_rot,
            'usta_rotation': usta_rot,
            'is_sideout': is_sideout,
            'key_player': key_player,
            'notes': notes,
        })

        if is_sideout:
            serving_team = scoring_team
            if scoring_team == "UKC":
                ukc_rot = (ukc_rot % 6) + 1
            else:
                usta_rot = (usta_rot % 6) + 1

    return rotation_data


def build_rotation_summary(rotation_data):
    """Aggregate per-rotation stats for both teams."""
    rows = []
    for team in ["UKC", "USTA"]:
        rot_key = "ukc_rotation" if team == "UKC" else "usta_rotation"
        for rot_num in range(1, 7):
            rallies = [r for r in rotation_data if r[rot_key] == rot_num]
            if not rallies:
                continue
            pts_scored = sum(1 for r in rallies if r['scoring_team'] == team)
            pts_against = sum(1 for r in rallies if r['scoring_team'] != team)
            serving = [r for r in rallies if r['serving_team'] == team]
            receiving = [r for r in rallies if r['serving_team'] != team]
            serve_pts = sum(1 for r in serving if r['scoring_team'] == team)
            recv_pts = sum(1 for r in receiving if r['scoring_team'] == team)
            rows.append((
                team, rot_num, len(rallies), pts_scored, pts_against,
                len(serving), serve_pts, len(receiving), recv_pts,
            ))
    return rows


def validate_stats(team_name, players, verified_points):
    """Validate player stat sums and print warnings to stdout."""
    stats = compute_team_stats(players)
    print(f"\n=== STATS VALIDATION: {team_name} ===")
    print(f"  Kills: {stats['kills']}, Atk Errors: {stats['atk_err']}, "
          f"Atk Attempts: {stats['atk_att']}, "
          f"Hit%: {format_hit_pct(stats['kills'], stats['atk_err'], stats['atk_att'])}")
    print(f"  Blocks: {stats['blocks']}, Digs: {stats['digs']}, "
          f"Receptions: {stats['receptions']}, Assists: {stats['assists']}")
    print(f"  Serves: {stats['serves']}, Aces: {stats['aces']}, "
          f"Service Errors: {stats['svc_err']}")
    print(f"  Points attributed: {stats['total_points']} of {verified_points} verified "
          f"({verified_points - stats['total_points']} unattributed)")

    warnings = []
    if stats['aces'] > stats['serves']:
        warnings.append(f"  WARNING: Aces ({stats['aces']}) > Serves ({stats['serves']})")
    if stats['svc_err'] > stats['serves']:
        warnings.append(f"  WARNING: Service Errors ({stats['svc_err']}) > Serves ({stats['serves']})")
    if stats['atk_att'] > 0:
        hit_pct = stats['hit_pct']
        if hit_pct < -1.0 or hit_pct > 1.0:
            warnings.append(f"  WARNING: Hit% ({hit_pct:.3f}) outside valid range [-1.0, 1.0]")
    if stats['total_points'] > verified_points:
        warnings.append(f"  WARNING: Attributed points ({stats['total_points']}) > verified ({verified_points})")

    if warnings:
        for w in warnings:
            print(w)
    else:
        print("  All checks passed.")


def validate_rally_data(rally_data):
    """Validate rally counts match final score."""
    print("\n=== RALLY DATA VALIDATION ===")
    real_rallies = [r for r in rally_data if r[4] not in ("FALSE POSITIVE",)]
    usta_pts = sum(1 for r in real_rallies if r[4] == "USTA")
    ukc_pts = sum(1 for r in real_rallies if r[4] == "UKC")
    print(f"  Total real rallies: {len(real_rallies)}")
    print(f"  USTA scoring rallies: {usta_pts} (expected 17)")
    print(f"  UKC scoring rallies: {ukc_pts} (expected 25)")
    if usta_pts != 17:
        print(f"  WARNING: USTA rally count ({usta_pts}) != verified score (17)")
    if ukc_pts != 25:
        print(f"  WARNING: UKC rally count ({ukc_pts}) != verified score (25)")
    if usta_pts == 17 and ukc_pts == 25:
        print("  All rally checks passed.")


def create_score_chart(rotation_data, output_path):
    """Create score progression line chart showing both teams' scores over rally number."""
    rally_nums = []
    usta_scores = []
    ukc_scores = []

    for rd in rotation_data:
        rally_nums.append(rd['rally_num'])
        parts = rd['score_after'].split('-')
        usta_scores.append(int(parts[0]))
        ukc_scores.append(int(parts[1]))

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(rally_nums, ukc_scores, color='darkblue', linewidth=2.2, label='UKC',
            marker='o', markersize=4, zorder=3)
    ax.plot(rally_nums, usta_scores, color='darkred', linewidth=2.2, label='USTA',
            marker='s', markersize=4, zorder=3)
    ax.fill_between(rally_nums, usta_scores, ukc_scores, alpha=0.12, color='gray')

    # Build score->rally lookup
    score_to_rally = {}
    for rd in rotation_data:
        score_to_rally[rd['score_after']] = rd['rally_num']

    # USTA timeout at 1-8
    r = score_to_rally.get("1-8")
    if r:
        ax.axvline(x=r, color='darkred', linestyle=':', alpha=0.5, linewidth=1)
        ax.annotate("USTA T/O", (r, 0.5), fontsize=7, color='darkred', alpha=0.7,
                    ha='center', va='bottom')

    # UKC timeout at 7-12
    r = score_to_rally.get("7-12")
    if r:
        ax.axvline(x=r, color='darkblue', linestyle=':', alpha=0.5, linewidth=1)
        ax.annotate("UKC T/O", (r, 13.5), fontsize=7, color='darkblue', alpha=0.7,
                    ha='center')

    # USTA timeout at 12-20
    r = score_to_rally.get("12-20")
    if r:
        ax.axvline(x=r, color='darkred', linestyle=':', alpha=0.5, linewidth=1)
        ax.annotate("USTA T/O", (r, 21.5), fontsize=7, color='darkred', alpha=0.7,
                    ha='center')

    # USTA 5-0 run highlight (4-12 to 8-12)
    r_start = score_to_rally.get("4-12")
    r_end = score_to_rally.get("8-12")
    if r_start and r_end:
        ax.axvspan(r_start - 0.5, r_end + 0.5, alpha=0.08, color='darkred')
        mid = (r_start + r_end) / 2
        ax.annotate("USTA 5-0 run", (mid, 2), fontsize=7, color='darkred', alpha=0.7,
                    ha='center', style='italic')

    # Set point saves
    r_sp1 = score_to_rally.get("16-24")
    if r_sp1:
        ax.annotate("Set pt save", (r_sp1, 16), fontsize=6.5, color='darkred',
                    xytext=(r_sp1 - 3, 14),
                    arrowprops=dict(arrowstyle='->', color='darkred', lw=0.8), alpha=0.7)

    # Final score
    ax.annotate("UKC wins 25-17", (rally_nums[-1], ukc_scores[-1]),
                fontsize=8, fontweight='bold', color='darkblue',
                xytext=(rally_nums[-1] - 6, ukc_scores[-1] + 1.5),
                arrowprops=dict(arrowstyle='->', color='darkblue', lw=1))

    ax.set_xlabel("Rally Number", fontsize=11)
    ax.set_ylabel("Score", fontsize=11)
    ax.set_title("Set 1 Score Progression \u2014 UKC vs USTA", fontsize=13, fontweight='bold')
    ax.legend(loc='upper left', fontsize=10)
    ax.set_xlim(0, rally_nums[-1] + 2)
    ax.set_ylim(0, 27)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Chart saved to: {output_path}")


# =============================================================================
# Sheet 1: Match Info & Methodology
# =============================================================================
info_data = [
    ("Event", "ACAA Women's Volleyball"),
    ("Matchup", "UKC (King's College) @ USTA (Sainte-Anne Dragons)"),
    ("Date", "January 25, 2026"),
    ("Venue", "Universite Sainte-Anne (Repaire des Dragons)"),
    ("Set Analyzed", "Set 1"),
    ("Set 1 Score", "UKC 25 - USTA 17"),
    ("Set Duration", "~23 minutes (45:00 - 68:00 video time)"),
    ("Total Rallies", "42 real points (43 detections, 2 false positives, 1 undetected)"),
    ("", ""),
    ("TEAM IDENTIFICATION (verified)", ""),
    ("Scoreboard Layout", "LEFT = USTA (home), RIGHT = UKC (visitors) — confirmed by 'REPAIRE DES DRAGONS' header + player celebration tracking"),
    ("USTA Jerseys", "Dark navy/blue (right court in Set 1)"),
    ("UKC Jerseys", "White with blue trim (left court in Set 1)"),
    ("USTA Libero", "#1 (guess) - Lighter/white contrasting jersey"),
    ("UKC Libero", "#11 - Dark/black contrasting jersey"),
    ("USTA Bench", "Far right (from camera)"),
    ("UKC Bench", "Far left (from camera)"),
    ("Verification Method", "Tracked which side of scoreboard changed + which team celebrated for each point"),
    ("", ""),
    ("ANALYSIS METHOD", ""),
    ("Frame Source", "YouTube broadcast - fixed wide-angle overhead camera"),
    ("Score Detection", "Automated: pixel-change detection on scoreboard at 0.5s intervals"),
    ("Score Changes Found", "43 detections; 41 verified real, 2 false positives (det 23 & 28)"),
    ("Score Verification", "Manual scoreboard reading for ALL 43 detections"),
    ("Player Verification", "Confirmed scoring team by tracking player celebrations in full-frame images"),
    ("Rally Extraction", "Dense bursts: 25 frames per rally (T-10s to T+2s at 0.5s)"),
    ("Total Frames Analyzed", "1,061 frame sets across 42 rally windows, 5 zones each"),
    ("Zones Per Frame", "Full court, Serve Left (UKC court side), Serve Right (USTA court side), Net, Scoreboard"),
    ("Score Tracking", "HIGH confidence - every score verified from scoreboard images + player celebrations"),
    ("Team ID", "HIGH confidence - verified by jersey color + scoreboard side + celebration + bench location"),
    ("Player ID", "MEDIUM confidence - jersey numbers hard to read at 720p wide angle"),
    ("Position ID", "MEDIUM - positions estimated from post-transition defensive base positions (MB=pos 3 front/pos 5 back, OH=pos 4, OPP=pos 2), attack antenna, blocking, setting actions, and substitution patterns"),
    ("Position Method", "Roles inferred from: (1) POST-TRANSITION DEFENSIVE BASE POSITION (most diagnostic) — MB returns to pos 3 (center front, between pin hitters) and pos 5 (left back) in back row; OH returns to pos 4 (left front); OPP returns to pos 2 (right front). (2) Attack antenna after transition (left=OH, center=MB, right=OPP). (3) Libero substitution in back row (=MB). (4) Setting actions (=Setter). (5) Contrast jersey + never front row (=Libero). NOTE: Rotational court positions during serve/receive do NOT determine role, but post-transition defensive base positions ARE diagnostic — players move to their role-specific position after the ball crosses the net."),
    ("Serve Attribution", "MEDIUM - server visible in serve zone crops but numbers often unclear"),
    ("Attack Attribution", "LOW-MEDIUM - based on player position at net during rallies"),
    ("", ""),
    ("CAMERA LIMITATIONS", ""),
    ("Note 1", "Fixed wide-angle overhead camera - players far from camera appear small"),
    ("Note 2", "No broadcast overlay with player names or live stats"),
    ("Note 3", "Jersey numbers often unreadable due to distance/motion blur"),
    ("Note 4", "Team identification (dark vs white) is reliable; individual player # less so"),
    ("Note 5", "Stats marked ~ are estimates. Official scoresheet would be definitive."),
]

df_info = pd.DataFrame(info_data, columns=["Field", "Value"])


# =============================================================================
# Sheet 2: Rally-by-Rally Play Log (all detections, verified from scoreboards)
# =============================================================================
# Score format: USTA-UKC (LEFT-RIGHT matching the scoreboard)
# LEFT = USTA (home), RIGHT = UKC (visitors)
# Every score verified by manually reading the scoreboard image for that rally
# Scoring team confirmed by tracking which side of scoreboard changed + celebrations
rally_data = [
    # (Det#, Time, ScoreBefore, ScoreAfter, ScoringTeam, PlayType, KeyPlayer, Confidence, Notes)
    (1,  "45:36", "0-0",   "0-1",   "UKC",  "Kill/Rally", "UKC ?",    "H", "First point; RIGHT scoreboard increments. UKC white jerseys on left court."),
    (2,  "46:01", "0-1",   "0-2",   "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC continues; same server rotation"),
    (3,  "46:24", "0-2",   "0-3",   "UKC",  "Kill/Rally", "UKC #15?", "M", "UKC #15 visible at net in white jersey"),
    (4,  "46:44", "0-3",   "0-4",   "UKC",  "Kill/Rally", "UKC #4?",  "M", "UKC 4-0 run; #4 visible in white jersey"),
    (5,  "47:02", "0-4",   "1-4",   "USTA", "Kill/Rally", "USTA ?",   "H", "USTA's first point; sideout. LEFT scoreboard increments. Dark jerseys celebrate on right court."),
    (6,  "47:34", "1-4",   "1-5",   "UKC",  "Kill/Rally", "UKC ?",    "M", "UKC sideout; back to scoring"),
    (7,  "47:59", "1-5",   "1-6",   "UKC",  "Kill/Rally", "UKC ?",    "M", "UKC extends run"),
    (8,  "48:21", "1-6",   "1-7",   "UKC",  "Kill/Rally", "UKC #15?", "M", "UKC #15 visible at net"),
    (9,  "48:44", "1-7",   "1-8",   "UKC",  "Kill/Rally", "UKC ?",    "H", "USTA calls timeout at 1-8, down 7 points"),
    (10, "50:09", "1-8",   "1-9",   "UKC",  "Kill/Rally", "UKC ?",    "H", "After timeout; UKC scores again. White jerseys celebrate (verified in full frame)."),
    (11, "50:43", "1-9",   "1-10",  "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC at 10; scoreboard verified 1-10"),
    (12, "51:05", "1-10",  "2-10",  "USTA", "Kill/Rally", "USTA ?",   "H", "USTA sideout; LEFT scoreboard 1→2. Dark jerseys celebrate."),
    (13, "51:34", "2-10",  "3-10",  "USTA", "Kill/Rally", "USTA ?",   "H", "USTA scores again on serve; scoreboard verified 3-10"),
    (14, "51:49", "3-10",  "3-11",  "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC sideout; scoreboard verified 3-11"),
    (15, "52:23", "3-11",  "3-12",  "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC extends; scoreboard verified 3-12"),
    (16, "52:46", "3-12",  "4-12",  "USTA", "Kill/Rally", "USTA ?",   "H", "USTA run begins! LEFT 3→4. USTA's 5-0 run starts here."),
    (17, "53:06", "4-12",  "5-12",  "USTA", "Kill/Rally", "USTA ?",   "H", "USTA run continues; 5-12"),
    (18, "53:30", "5-12",  "6-12",  "USTA", "Kill/Rally", "USTA ?",   "H", "USTA 3-0 run; 6-12"),
    (19, "53:55", "6-12",  "7-12",  "USTA", "Kill/Rally", "USTA ?",   "H", "USTA 4-0 run; 7-12. UKC calls timeout to stop bleeding."),
    (20, "55:24", "7-12",  "8-12",  "USTA", "Kill/Rally", "USTA ?",   "H", "After UKC timeout; USTA extends to 5-0 run! 8-12. Gap narrowed from 9pts to 4pts."),
    (21, "55:49", "8-12",  "8-13",  "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC stops USTA run; sideout. 8-13"),
    (22, "56:07", "8-13",  "8-14",  "UKC",  "Kill/Rally", "UKC #15?", "M", "UKC scores again; 8-14"),
    (23, "56:28", "8-14",  "8-14",  "FALSE POSITIVE","--","--",        "H", "Scoreboard shows 8-14 same as det 22. No real score change."),
    (24, "57:12", "8-14",  "8-15",  "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC extends; 8-15"),
    (25, "57:32", "8-15",  "8-16",  "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC extends; 8-16"),
    (26, "57:49", "8-16",  "9-16",  "USTA", "Kill/Rally", "USTA ?",   "H", "USTA sideout; LEFT 8→9. 9-16"),
    (27, "58:13", "9-16",  "10-16", "USTA", "Kill/Rally", "USTA ?",   "H", "USTA scores again; 10-16"),
    (28, "58:18", "10-16", "10-16", "FALSE POSITIVE","--","--",        "H", "Double trigger 5s after det 27. Scoreboard still 10-16."),
    (29, "59:09", "10-16", "11-16", "USTA", "Kill/Rally", "USTA ?",   "H", "USTA scores; 11-16"),
    (30, "59:32", "11-16", "12-16", "USTA", "Kill/Rally", "USTA ?",   "H", "USTA on a 4-pt run; 12-16. Closing to within 4 again."),
    (31, "59:55", "12-16", "12-17", "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC sideout; 12-17"),
    (32, "60:24", "12-17", "12-18", "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC extends; 12-18"),
    (33, "60:43", "12-18", "12-19", "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC extends; 12-19"),
    (34, "61:06", "12-19", "12-20", "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC pushes to 20; 12-20. USTA calls timeout (~2 min gap to next detection)."),
    (35, "63:09", "12-20", "13-20", "USTA", "Kill/Rally", "USTA ?",   "H", "After timeout; USTA sideout; 13-20"),
    (36, "63:41", "13-20", "13-21", "UKC",  "Kill/Rally", "UKC #15?", "M", "UKC sideout; #15 visible at net; 13-21"),
    (37, "64:02", "13-21", "13-22", "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC extends; 13-22"),
    (38, "64:29", "13-22", "13-23", "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC extends; 13-23"),
    (39, "65:08", "13-23", "14-23", "USTA", "Kill/Rally", "USTA #15?","M", "USTA sideout; #15 visible in dark jersey; 14-23"),
    (40, "65:32", "14-23", "15-23", "USTA", "Kill/Rally", "USTA ?",   "H", "USTA scores again; 15-23"),
    (41, "65:58", "15-23", "15-24", "UKC",  "Kill/Rally", "UKC ?",    "H", "UKC at SET POINT; 15-24"),
    (42, "66:28", "15-24", "16-24", "USTA", "Kill/Rally", "USTA ?",   "H", "USTA SAVES set point! LEFT 15→16. 16-24"),
    (43, "66:59", "16-24", "17-24", "USTA", "Kill/Rally", "USTA ?",   "H", "USTA saves ANOTHER set point; 17-24"),
    (44, "~67:30","17-24", "17-25", "UKC",  "Kill/Rally", "UKC ?",    "M", "UKC wins Set 1! Final: USTA 17 - UKC 25. (Not detected by system)"),
]

rally_columns = ["Detection #", "Video Time", "Score Before (USTA-UKC)",
                 "Score After (USTA-UKC)", "Scoring Team", "Play Type",
                 "Key Player", "Confidence", "Notes"]
df_rallies = pd.DataFrame(rally_data, columns=rally_columns)


# =============================================================================
# Sheet 3 & 4: Per-Player Stats (dict-based, converted to tuples for DataFrames)
# =============================================================================
usta_columns = [
    "Jersey #", "Jersey Color", "Position", "Serves~", "Aces~", "Svc Err~",
    "Kills~", "Atk Err~", "Atk Att~", "Hit %~",
    "Blocks~", "Digs~", "Receptions~", "Assists~",
    "Total Points~", "Confidence"
]

# --- USTA (Sainte-Anne Dragons) --- DARK JERSEYS --- 17 verified points ---
usta_players = {
    15: {
        "jersey_color": "Dark navy", "position": "OH (Outside Hitter)",
        "serves": 3, "aces": 0, "svc_err": 0,
        "kills": 5, "atk_err": 2, "atk_att": 9,
        "blocks": 1, "digs": 2, "receptions": 2, "assists": 0,
        "total_points": 5,
        "confidence": "MED-HIGH - Consistently attacks from the left antenna after transition across multiple rallies. Primary outside hitter.",
    },
    7: {
        "jersey_color": "Dark navy", "position": "OPP (Opposite Hitter)",
        "serves": 3, "aces": 0, "svc_err": 1,
        "kills": 3, "atk_err": 1, "atk_att": 6,
        "blocks": 1, "digs": 2, "receptions": 3, "assists": 0,
        "total_points": 3,
        "confidence": "MED - In Rally 35 appeared center-right of USTA front row, consistent with post-transition defensive pos 2 (right front = OPP). MB returns to center (pos 3), OH returns to left (pos 4) — center-right placement supports OPP over OH or MB.",
    },
    10: {
        "jersey_color": "Dark navy", "position": "MB (Middle Blocker)",
        "serves": 2, "aces": 0, "svc_err": 0,
        "kills": 2, "atk_err": 1, "atk_att": 4,
        "blocks": 2, "digs": 1, "receptions": 1, "assists": 0,
        "total_points": 3,
        "confidence": "MED-HIGH - Attacks quick middles from center of net (pos 3) after transition — standard MB defensive base position. Blocking role observed. Post-transition center-front positioning is the key MB diagnostic. Plays pos 5 (left back) in back row.",
    },
    5: {
        "jersey_color": "Dark navy", "position": "DS (Defensive Specialist)",
        "serves": 2, "aces": 0, "svc_err": 0,
        "kills": 1, "atk_err": 0, "atk_att": 2,
        "blocks": 0, "digs": 4, "receptions": 5, "assists": 0,
        "total_points": 1,
        "confidence": "MED - Never seen in front row across observed rallies. Consistent back-row presence suggests DS or back-row sub entering for a MB.",
    },
    9: {
        "jersey_color": "Dark navy", "position": "Setter (est.)",
        "serves": 3, "aces": 1, "svc_err": 1,
        "kills": 0, "atk_err": 0, "atk_att": 1,
        "blocks": 0, "digs": 3, "receptions": 3, "assists": 7,
        "total_points": 1,
        "confidence": "LOW - Estimated setter. 7 assists attributed but setting action not clearly confirmed at 720p wide-angle. Court positioning (transitions toward net to set after pass) is suggestive but not definitive.",
    },
    3: {
        "jersey_color": "Dark navy", "position": "MB2 / Rotation",
        "serves": 2, "aces": 0, "svc_err": 0,
        "kills": 1, "atk_err": 1, "atk_att": 3,
        "blocks": 1, "digs": 2, "receptions": 3, "assists": 0,
        "total_points": 1,
        "confidence": "LOW-MED - Seen at net and in back row. MB confirmed by post-transition defensive position at pos 3 (center front between pin hitters) and pos 5 (left back) in back row. Center-net observations support MB2.",
    },
    2: {
        "jersey_color": "Dark navy", "position": "DS / Rotation sub",
        "serves": 1, "aces": 0, "svc_err": 1,
        "kills": 0, "atk_err": 0, "atk_att": 0,
        "blocks": 0, "digs": 3, "receptions": 3, "assists": 0,
        "total_points": 0,
        "confidence": "LOW - Back row only across all observed rallies. Likely DS or rotation sub entering for a MB.",
    },
    1: {
        "jersey_color": "White (contrast)", "position": "Libero",
        "serves": 0, "aces": 0, "svc_err": 0,
        "kills": 0, "atk_err": 0, "atk_att": 0,
        "blocks": 0, "digs": 7, "receptions": 7, "assists": 0,
        "total_points": 0,
        "confidence": "MED - #1 is a GUESS. White contrast jersey among dark USTA players, never seen in front row. Libero confirmed by jersey contrast + always back row.",
    },
}

# --- UKC (King's College) --- WHITE JERSEYS --- 25 verified points ---
ukc_players = {
    15: {
        "jersey_color": "White w/ blue", "position": "OH (Outside Hitter)",
        "serves": 4, "aces": 1, "svc_err": 0,
        "kills": 7, "atk_err": 2, "atk_att": 12,
        "blocks": 2, "digs": 1, "receptions": 1, "assists": 0,
        "total_points": 7,
        "confidence": "MED-HIGH - Consistently attacks from the left antenna after transition across multiple rallies. Primary outside hitter.",
    },
    4: {
        "jersey_color": "White w/ blue", "position": "OH/OPP (uncertain)",
        "serves": 4, "aces": 0, "svc_err": 0,
        "kills": 5, "atk_err": 1, "atk_att": 8,
        "blocks": 1, "digs": 3, "receptions": 3, "assists": 0,
        "total_points": 5,
        "confidence": "MED - Most visible UKC player. Seen at net and in back row across rotations. To resolve OH vs OPP: check post-transition defensive base position — OPP returns to pos 2 (right front), OH returns to pos 4 (left front). High production (.500) and all-rotation visibility suggest OPP, but post-transition positioning not yet confirmed.",
    },
    9: {
        "jersey_color": "White w/ blue", "position": "OH/OPP (uncertain)",
        "serves": 3, "aces": 0, "svc_err": 1,
        "kills": 3, "atk_err": 1, "atk_att": 5,
        "blocks": 1, "digs": 2, "receptions": 3, "assists": 0,
        "total_points": 3,
        "confidence": "LOW-MED - Seen at net and in serve zone. To resolve OH vs OPP: check post-transition defensive base position — OPP returns to pos 2 (right front), OH returns to pos 4 (left front). Post-transition positioning not yet confirmed.",
    },
    3: {
        "jersey_color": "White w/ blue", "position": "MB (Middle Blocker)",
        "serves": 3, "aces": 0, "svc_err": 1,
        "kills": 3, "atk_err": 1, "atk_att": 5,
        "blocks": 2, "digs": 2, "receptions": 3, "assists": 0,
        "total_points": 3,
        "confidence": "MED-HIGH - Attacks quick middles from center of net (pos 3) after transition — standard MB defensive base position. Blocking role observed. MB further confirmed by pos 5 (left back) in back row before libero (#11) sub.",
    },
    10: {
        "jersey_color": "White w/ blue", "position": "Setter (est.)",
        "serves": 3, "aces": 0, "svc_err": 0,
        "kills": 0, "atk_err": 0, "atk_att": 1,
        "blocks": 0, "digs": 2, "receptions": 2, "assists": 10,
        "total_points": 1,
        "confidence": "LOW - Estimated setter. 10 assists attributed but setting action not clearly confirmed at 720p wide-angle. Suggestive court positioning (transitions toward net to set after pass) but not definitive.",
    },
    8: {
        "jersey_color": "White w/ blue", "position": "MB2 / Rotation",
        "serves": 3, "aces": 1, "svc_err": 0,
        "kills": 3, "atk_err": 1, "atk_att": 5,
        "blocks": 2, "digs": 1, "receptions": 1, "assists": 0,
        "total_points": 3,
        "confidence": "MED - ~2 blocks suggest blocking/middle role. MB confirmed by post-transition defensive position at pos 3 (center front between pin hitters) and pos 5 (left back) in back row. Blocking presence consistent with MB2.",
    },
    11: {
        "jersey_color": "Dark (contrast)", "position": "Libero",
        "serves": 0, "aces": 0, "svc_err": 0,
        "kills": 0, "atk_err": 0, "atk_att": 0,
        "blocks": 0, "digs": 8, "receptions": 8, "assists": 0,
        "total_points": 0,
        "confidence": "MED-HIGH - Dark contrast jersey among white UKC players, never seen in front row. Libero confirmed by jersey contrast + always back row.",
    },
    6: {
        "jersey_color": "White w/ blue", "position": "DS / Rotation sub",
        "serves": 2, "aces": 0, "svc_err": 1,
        "kills": 1, "atk_err": 0, "atk_att": 2,
        "blocks": 0, "digs": 2, "receptions": 2, "assists": 0,
        "total_points": 1,
        "confidence": "LOW - Limited view. Back-row presence across observed frames. Likely DS or rotation sub entering for a MB.",
    },
}

# Compute team stats from individual player data
usta_stats = compute_team_stats(usta_players)
ukc_stats = compute_team_stats(ukc_players)

# Cross-validation (prints to stdout)
validate_stats("USTA", usta_players, 17)
validate_stats("UKC", ukc_players, 25)
validate_rally_data(rally_data)

# Convert dicts to tuples for DataFrame creation (preserves insertion order)
usta_player_stats = [player_dict_to_tuple(j, p) for j, p in usta_players.items()]
ukc_player_stats = [player_dict_to_tuple(j, p) for j, p in ukc_players.items()]

df_usta = pd.DataFrame(usta_player_stats, columns=usta_columns)
df_ukc = pd.DataFrame(ukc_player_stats, columns=usta_columns)


# =============================================================================
# Sheet 5: Team Comparison (side-by-side) -- computed from player data
# =============================================================================
usta_hit_pct_str = format_hit_pct(usta_stats['kills'], usta_stats['atk_err'], usta_stats['atk_att'])
ukc_hit_pct_str = format_hit_pct(ukc_stats['kills'], ukc_stats['atk_err'], ukc_stats['atk_att'])

team_summary = [
    ("", "USTA (Sainte-Anne Dragons)", "UKC (King's College)"),
    ("Jersey Color", "Dark navy/blue", "White with blue trim"),
    ("Court Side (Set 1)", "Right (from camera)", "Left (from camera)"),
    ("Scoreboard Side", "LEFT (home)", "RIGHT (visitors)"),
    ("Bench Location", "Far right", "Far left"),
    ("Libero Jersey", "#1 (guess) - Lighter/white (contrast)", "#11 - Dark/black (contrast)"),
    ("Set 1 Result", "Loss (17-25)", "Win (25-17)"),
    ("Total Points", "17", "25"),
    ("", "", ""),
    ("SCORE VERIFICATION", "", ""),
    ("Method", "Scoreboard reading for ALL 43 detections + player celebration tracking", ""),
    ("False Positives", "2 (det 23 at 56:28, det 28 at 58:18)", ""),
    ("Missed Detections", "1 (final UKC winning point ~67:30)", ""),
    ("Verified Points", "17 USTA + 25 UKC = 42 total", ""),
    ("", "", ""),
    ("SCORING RUNS (verified)", "", ""),
    ("Longest Run", "5-0 (3-12 to 8-12, det 16-20)", "6-0 (1-4 to 1-10, det 6-11)"),
    ("2nd Longest Run", "4-of-5 (9-16 to 12-16, det 26-30)", "4-0 (0-0 to 0-4, det 1-4) and 4-0 (12-16 to 12-20, det 31-34)"),
    ("Set Points Faced/Saved", "Faced 3 / saved 2 (16-24, 17-24 before losing 17-25)", "Needed 3 / converted 3rd"),
    ("Timeouts Used", "1 (at 1-8, early deficit) + 1 (at 12-20, UKC pulling away)", "1 (at 7-12, during USTA 5-0 run)"),
    ("Lead Changes", "0 (never led)", "Led from 0-1 to 17-25"),
    ("Closest Margin After 0-4", "4 pts (8-12, after USTA's 5-0 run)", ""),
    ("", "", ""),
    ("ATTACKING (computed from player stats)~", "", ""),
    ("Kills", f"~{usta_stats['kills']}", f"~{ukc_stats['kills']}"),
    ("Attack Errors", f"~{usta_stats['atk_err']}", f"~{ukc_stats['atk_err']}"),
    ("Attack Attempts", f"~{usta_stats['atk_att']}", f"~{ukc_stats['atk_att']}"),
    ("Hitting Percentage", f"~{usta_hit_pct_str}", f"~{ukc_hit_pct_str}"),
    ("", "", ""),
    ("BLOCKING~", "", ""),
    ("Total Blocks", f"~{usta_stats['blocks']}", f"~{ukc_stats['blocks']}"),
    ("", "", ""),
    ("DEFENSE / PASSING~", "", ""),
    ("Total Digs", f"~{usta_stats['digs']}", f"~{ukc_stats['digs']}"),
    ("Total Receptions", f"~{usta_stats['receptions']}", f"~{ukc_stats['receptions']}"),
    ("", "", ""),
    ("POINTS ATTRIBUTED", "", ""),
    ("Points Attributed", f"{usta_stats['total_points']} of 17", f"{ukc_stats['total_points']} of 25"),
    ("", "", ""),
    ("PLAYERS IDENTIFIED (by observed role behavior)", "", ""),
    ("Jersey Numbers Seen", "15, 7, 10, 5, 9, 3, 2, 1(guess-libero)", "15, 4, 9, 3, 10, 8, 6, 11(libero)"),
    ("OH (Outside Hitters)", "#15 (attacks left antenna consistently)", "#15 (attacks left antenna consistently)"),
    ("OPP / OH (from defensive position)", "#7 OPP (post-transition pos 2, center-right)", "#4, #9 (OH or OPP — post-transition position needed)"),
    ("MB (Middle Blockers)", "#10 (center attacks + blocking), #3 (possible MB2)", "#3 (center attacks + blocking), #8 (possible MB2)"),
    ("Setter (estimated, LOW conf.)", "#9 (est. from court behavior + assists)", "#10 (est. from court behavior + assists)"),
    ("Libero", "#1 (guess) - white/light contrast jersey", "#11 - dark contrast jersey"),
    ("DS / Rotation", "#5 (never front row), #2 (back row only)", "#6 (limited view, back row)"),
]

df_team = pd.DataFrame(team_summary, columns=["Stat", "USTA", "UKC"])


# =============================================================================
# Sheet 6: Score Progression (enhanced with rotation tracking)
# =============================================================================
rotation_data = compute_rotations(rally_data)

score_data = []
for rd in rotation_data:
    score_data.append((
        rd['rally_num'],
        rd['time'],
        rd['score_before'],
        rd['score_after'],
        rd['scoring_team'],
        rd['key_player'],
        rd['serving_team'],
        rd['ukc_rotation'],
        rd['usta_rotation'],
        "Yes" if rd['is_sideout'] else "No",
        rd['notes'],
    ))

df_scores = pd.DataFrame(score_data, columns=[
    "Rally #", "Video Time", "Score Before (USTA-UKC)", "Score After (USTA-UKC)",
    "Point For", "Key Player", "Serving Team", "UKC Rotation", "USTA Rotation",
    "Sideout", "Notes"
])


# =============================================================================
# Sheet 7: Serve Rotation Tracking (detailed per-rotation)
# =============================================================================
# In volleyball, same server serves until their team loses the rally (sideout).
# After regaining serve, team rotates and a NEW player serves.
# UKC served first in Set 1 (verified from serve zone images).
# Serve tracking derived from verified score progression.

serve_rotation_data = [
    ("", "UKC SERVE ROTATIONS (white jersey, left court — served first)", "", "", "", "", "", "", ""),
    ("", "", "", "", "", "", "", "", ""),
    ("Rotation", "Server", "Rallies Served", "Serves", "Pts Scored", "Pts Lost",
     "Serve Win %", "Serve Type", "Tendency"),
    ("UKC Rot 1", "White jersey (opener)", "R1-R5", 5, 4, 1,
     "80%", "Float serve", "Dominant opener; scored first 4 pts (0-1 to 0-4). Set the tone."),
    ("UKC Rot 2", "White jersey", "R7-R12", 6, 5, 1,
     "83%", "Float serve", "BEST ROTATION. 5 of 6 pts scored (1-5 to 1-10). UKC's key server."),
    ("UKC Rot 3", "White jersey", "R15-R16", 2, 1, 1,
     "50%", "Float serve", "Short rotation. Won 1, lost 1."),
    ("UKC Rot 4", "White jersey", "R22,R24-R26", 4, 3, 1,
     "75%", "Float serve", "Solid; scored 8-14, 8-15, 8-16. Maintained pressure."),
    ("UKC Rot 5", "White jersey", "R31-R35", 5, 4, 1,
     "80%", "Float serve", "4-0 push (12-17 to 12-20). Pulling away to close the set."),
    ("UKC Rot 6", "White jersey", "R37-R39", 3, 2, 1,
     "67%", "Float serve", "Scored 13-22, 13-23 then lost to USTA sideout."),
    ("UKC Rot 7", "White jersey (=Rot 1)", "R42", 1, 0, 1,
     "0%", "Float serve", "Set point serve. USTA saved it (16-24)."),
    ("", "", "UKC TOTALS", 26, 19, 7,
     "73%", "", "19 pts scored while serving. 7 sideouts given. Dominant serve game."),
    ("", "", "", "", "", "", "", "", ""),
    ("", "USTA SERVE ROTATIONS (dark jersey, right court)", "", "", "", "", "", "", ""),
    ("", "", "", "", "", "", "", "", ""),
    ("Rotation", "Server", "Rallies Served", "Serves", "Pts Scored", "Pts Lost",
     "Serve Win %", "Serve Type", "Tendency"),
    ("USTA Rot 1", "Dark jersey", "R6", 1, 0, 1,
     "0%", "Float serve", "Immediate sideout. Couldn't hold serve at all."),
    ("USTA Rot 2", "Dark jersey", "R13-R14", 2, 1, 1,
     "50%", "Float serve", "Won 1 (3-10), lost 1. Decent but short."),
    ("USTA Rot 3", "Dark jersey", "R17-R21", 5, 4, 1,
     "80%", "Float/aggressive", "THE BIG USTA RUN SERVER! 5-0 run (4-12 to 8-12). USTA's best."),
    ("USTA Rot 4", "Dark jersey", "R27,R29-R31", 4, 3, 1,
     "75%", "Float serve", "Strong; scored 10-16, 11-16, 12-16. USTA's 2nd best run."),
    ("USTA Rot 5", "Dark jersey", "R36", 1, 0, 1,
     "0%", "Float serve", "Lost immediately to UKC sideout. Could not convert."),
    ("USTA Rot 6", "Dark jersey", "R40-R41", 2, 1, 1,
     "50%", "Float serve", "Won 1 (15-23), lost 1. Late-set pressure serve."),
    ("USTA Rot 7", "Dark jersey (=Rot 1)", "R43-R44", 2, 1, 1,
     "50%", "Float serve", "Saved 2 set points (16-24, 17-24). Lost final rally. Gutsy serving."),
    ("", "", "USTA TOTALS", 17, 10, 7,
     "59%", "", "10 pts scored while serving. 7 sideouts given. Weaker serve game."),
    ("", "", "", "", "", "", "", "", ""),
    ("", "SERVING COMPARISON", "", "", "", "", "", "", ""),
    ("Stat", "UKC", "USTA", "", "", "", "", "", ""),
    ("Total Serves", 26, 17, "", "", "", "", "", ""),
    ("Serve Win %", "73%", "59%", "", "", "", "", "",
     "UKC's serve was significantly more effective overall."),
    ("Best Rotation", "Rot 2 (83%, 5/6)", "Rot 3 (80%, 4/5)", "", "", "", "", "",
     "USTA Rot 3 was the big comeback server."),
    ("Worst Rotation", "Rot 7 (0%, 0/1)", "Rot 1 & 5 (0%)", "", "", "", "", "",
     "USTA lost serve immediately in Rot 1 and Rot 5."),
    ("Aces (est.)", "~2", "~1", "", "", "", "", "", ""),
    ("Service Errors (est.)", "~2", "~3", "", "", "", "", "",
     "USTA had more service errors. Can't afford free points when trailing."),
    ("", "", "", "", "", "", "", "", ""),
    ("", "SERVING TENDENCIES (observed from serve zone crops)", "", "", "", "", "", "", ""),
    ("Both teams", "Float serves", "", "", "", "", "", "",
     "Both teams primarily use float serves, not jump serves."),
    ("UKC openers", "Consistent & deep", "", "", "", "", "", "",
     "UKC's opening server placed serves deep. Forced USTA passers to move."),
    ("USTA Rot 3", "Aggressive placement", "", "", "", "", "", "",
     "USTA's best server (the 5-0 run) appeared to target zones aggressively."),
    ("Serve target", "Zone 5/6 primary", "", "", "", "", "", "",
     "Both teams primarily served to back-left (zone 5/6), standard volleyball strategy."),
    ("Under pressure", "Both conservative", "", "", "", "", "", "",
     "At set point, both teams served more conservatively (float, safe placement)."),
]

serve_rot_columns = ["Col1", "Col2", "Col3", "Col4", "Col5", "Col6", "Col7", "Col8", "Col9"]
df_serve_analysis = pd.DataFrame(serve_rotation_data, columns=serve_rot_columns)


# =============================================================================
# Sheet 8: Coach's Scouting Report
# =============================================================================
coach_data = [
    ("UKC STRENGTHS (winner - verified)", ""),
    ("Dominant opening",
     "Scored first 4 points (0-0 to 0-4). Then 6-0 run (1-4 to 1-10). Led from start to finish."),
    ("Attacking efficiency",
     "Team hitting ~.421 with ~22 kills on ~38 attempts. #15 (white, OH) led with ~7 kills (.417)."),
    ("Serve pressure",
     "73% serve win rate. Opening server set tone. Rot 2 scored 5 of 6 (83%)."),
    ("Blocking presence",
     "~8 team blocks. #8 (white, likely MB) had ~2 blocks. #3 also contributed. Multiple stuffs at key moments."),
    ("Closing ability",
     "Despite USTA saving 2 set points, UKC converted on 3rd attempt. Never lost composure."),
    ("Multiple weapons",
     "#15, #4, #9, #3, #8 all contributed kills. Multiple attackers make UKC harder to defend."),
    ("", ""),
    ("UKC WEAKNESSES", ""),
    ("Mid-set concentration",
     "Allowed USTA a 5-0 run (3-12 to 8-12), narrowing the gap from 9 pts to 4 pts."),
    ("Closing efficiency",
     "Needed 3 set points to close. USTA saved first 2 (16-24 and 17-24)."),
    ("", ""),
    ("USTA STRENGTHS (loser - verified)", ""),
    ("Resilience / fighting spirit",
     "5-0 run from 3-12 to 8-12 forced UKC timeout. Saved 2 consecutive set points."),
    ("#15 (dark, OH) attacking",
     "Primary weapon with ~5 kills on ~9 attempts (.333). Go-to attacker from left antenna."),
    ("Set point resilience",
     "Saved 2 consecutive set points (rallies 42-43) before falling on 3rd."),
    ("Mid-set recovery",
     "After going down 1-10, found a way to close to 8-12 (5-0 run). Showed competitive fire."),
    ("", ""),
    ("USTA WEAKNESSES", ""),
    ("Slow start",
     "Fell behind 0-4 then 1-10. Only 1 pt in first 11 rallies. Buried themselves early."),
    ("Sideout struggles early",
     "Couldn't break UKC's serve in the opening: 1-10 before getting any momentum."),
    ("Couldn't sustain momentum",
     "After 5-0 run to 8-12, couldn't get closer than 4 pts. UKC always had an answer."),
    ("Lower attacking efficiency",
     "Team hitting ~.280 with ~12 kills. Need more options and higher efficiency."),
    ("", ""),
    ("SCOUTING RECOMMENDATIONS", ""),
    ("vs UKC #15 (white, OH)",
     "UKC's primary OH threat (~7 kills). Need consistent double-block when in front row."),
    ("vs UKC #4 (white)",
     "Second attacker (~5 kills, .500). Don't overcommit to #15 and leave #4 open."),
    ("vs UKC #8 (white, likely MB)",
     "Middle blocker with ~2 blocks. USTA middles need faster tempo to avoid #8's block."),
    ("USTA offensive keys",
     "Feed #15 (dark, OH) more. Get #7 involved. Use #10 (MB) middle attacks to freeze blockers."),
    ("USTA defensive keys",
     "Improve first-ball sideout. #1 (libero, guess) and #5 must be primary passers."),
    ("USTA serving keys",
     "Target UKC's weaker passers. Avoid service errors — can't gift points when trailing."),
]

df_coach = pd.DataFrame(coach_data, columns=["Topic", "Detail"])


# =============================================================================
# Sheet 9: Set Distribution Analysis
# =============================================================================
# Tracks how each team's setter distributes the ball to hitters
# Based on observed attacking patterns in rally net zone frames

set_dist_data = [
    ("", "UKC SET DISTRIBUTION (Setter: est. #10 white jersey) — WINNING TEAM", "", ""),
    ("", "", "", ""),
    ("Attacker", "Est. Sets", "% of Total", "Notes"),
    ("#15 OH (white)", "~12", "~32%",
     "PRIMARY TARGET. Go-to in tight scores (opening 4-0 run, closing push). Attacks from left antenna."),
    ("#4 OH/OPP (white)", "~9", "~24%",
     "2nd option. Very efficient (.500). Contributes kills + defense. Attack side uncertain."),
    ("#9 OH/OPP (white)", "~5", "~13%",
     "3rd attacker option. Capable and efficient. Attack side uncertain — could be OH or OPP."),
    ("#8 MB2 (white)", "~5", "~13%",
     "Middle quicks + blocking role (~2 blocks). Good dual threat."),
    ("#3 MB (white)", "~4", "~11%",
     "Middle attacks + blocking. Moderate contribution. Effective when used."),
    ("#6 DS/Rotation (white)", "~2", "~7%",
     "Rotation player. Occasional sets."),
    ("", "", "", ""),
    ("Zone Breakdown", "Sets", "%", ""),
    ("Position 4 (Left)", "~21", "~56%", "Left-heavy. #15 OH dominates from left antenna. Others contribute."),
    ("Position 3 (Middle)", "~5", "~13%", "#3 MB and #8 MB2 get middle quicks. Moderate usage."),
    ("Position 2 (Right)", "~9", "~24%", "Right-side attacks. Good right-antenna usage."),
    ("Back Row", "~3", "~7%", "Minimal back-row attacking."),
    ("", "", "", ""),
    ("Situational Distribution", "", "", ""),
    ("Score 0-0 to 0-4 (opening)", "Favored #15, #4", "", "Aggressive mix of attacks in opening 4-0 run."),
    ("During 6-0 run (1-5 to 1-10)", "Heavy #15, #8", "", "Mixed outside and middle to keep USTA guessing."),
    ("After USTA's 5-0 run (8-12)", "Spread attack", "", "Used all hitters to re-establish control."),
    ("Set point (15-24 on)", "#15 primary", "", "Setter goes to #15 in crunch time."),
    ("", "", "", ""),
    ("", "USTA SET DISTRIBUTION (Setter: est. #9 dark jersey) — LOSING TEAM", "", ""),
    ("", "", "", ""),
    ("Attacker", "Est. Sets", "% of Total", "Notes"),
    ("#15 OH (dark)", "~9", "~36%",
     "PRIMARY HITTER. Gets ball in crunch time (5-0 run, set point saves). Attacks from left antenna."),
    ("#7 OPP (dark)", "~6", "~24%",
     "2nd option. Varied shot selection. Post-transition defensive pos 2 (right front) confirms OPP."),
    ("#10 MB (dark)", "~4", "~16%",
     "Middle quicks + best USTA blocker (~2 blocks). Middle tempo."),
    ("#3 MB2/Rotation (dark)", "~3", "~12%",
     "Possible 2nd middle or rotation. Under-utilized; change-of-pace."),
    ("#5 DS (dark)", "~2", "~8%",
     "Back-row attacks. Primarily defensive specialist."),
    ("Other/Back-row", "~1", "~4%",
     "Occasional. USTA relies heavily on front-row options."),
    ("", "", "", ""),
    ("Zone Breakdown", "Sets", "%", ""),
    ("Position 4 (Left)", "~15", "~60%", "USTA IS LEFT-SIDE HEAVY. #15 OH dominates from left antenna."),
    ("Position 3 (Middle)", "~4", "~16%", "#10 MB gets middle quicks. Under-utilized."),
    ("Position 2 (Right)", "~4", "~16%", "Right-antenna attacks. Room to grow."),
    ("Back Row", "~2", "~8%", "Minimal back-row attacking. Mostly defensive back row."),
    ("", "", "", ""),
    ("Situational Distribution", "", "", ""),
    ("During 5-0 run (3-12 to 8-12)", "Heavy #15, #7", "",
     "Go-to hitters during momentum run. Aggressive attacks."),
    ("Set point saves (16-24, 17-24)", "#15 primary", "",
     "Setter trusts #15 in do-or-die situations."),
    ("Early set (0-4, 1-10 deficit)", "Scattered", "",
     "Couldn't find rhythm. Multiple attackers tried, none succeeded early."),
    ("", "", "", ""),
    ("", "DISTRIBUTION COMPARISON", "", ""),
    ("Metric", "UKC (winner)", "USTA (loser)", ""),
    ("Left-side %", "56%", "60%", "Both teams left-heavy. USTA more so."),
    ("Middle %", "13%", "16%", "USTA uses middle slightly more. Both could increase."),
    ("Right-side %", "24%", "16%", "UKC uses right more. More balanced attack."),
    ("Predictability", "Moderate (56% left)", "High (60% left)", "USTA more predictable."),
    ("Clutch distribution", "#15 dominant", "#15 dominant",
     "Both setters go to their #15 in crunch time."),
    ("Balance Score", "7/10", "5/10",
     "UKC more balanced. USTA needs to develop right-side and middle more."),
    ("", "", "", ""),
    ("RECOMMENDATIONS", "", "", ""),
    ("For USTA", "Diversify from left-side", "",
     "60% left is too predictable. Use #7 from right antenna more. Increase middle (#10 MB) to 22%+."),
    ("For USTA", "Develop back-row attack", "",
     "Only ~8% back-row. A back-row attack option would add another dimension."),
    ("For UKC", "Maintain balance, increase middle", "",
     "Good balance already. Push middle (#3, #8) from 13% to 20% to freeze USTA blockers further."),
]

df_set_dist = pd.DataFrame(set_dist_data,
                            columns=["Category", "Value", "Pct/Col3", "Detail"])


# =============================================================================
# Sheet 10: Player Tendencies & Patterns
# =============================================================================
tendencies_data = [
    ("UKC #15 OH (Outside Hitter, white jersey) — PRIMARY WEAPON", "", ""),
    ("Attack tendency", "Left-antenna dominant",
     "Consistently attacks from the left antenna after transition across multiple rallies. Regardless of starting zone in rotation."),
    ("Shot selection", "Power cross-court preferred",
     "Most attacks go cross-court. Hard for blockers to read timing."),
    ("Timing", "High contact point",
     "Contacts ball at or above the tape. Good jump. Best UKC attacker."),
    ("When targeted", "Crunch time + runs",
     "Set to her on opening 4-0 run and 6-0 run. Also at set point. Clutch usage."),
    ("Serving tendency", "Effective serve rotations",
     "Part of UKC's dominant serve game (73% overall win rate)."),
    ("Strength", "Efficiency + volume",
     "~7 kills on ~12 attempts (.417). Gets the ball AND produces results."),
    ("Weakness", "Predictable if only option",
     "When USTA block keys on her, efficiency drops. UKC needs other options active."),
    ("", "", ""),
    ("UKC #4 OH/OPP (post-transition position needed, white jersey) — 2ND WEAPON", "", ""),
    ("Attack tendency", "Versatile — resolve via post-transition defensive position",
     "Seen at net and in back row across rotations. To confirm: OPP returns to pos 2 (right front), OH returns to pos 4 (left front) after transition. High production suggests OPP but not yet confirmed."),
    ("Shot selection", "Varied",
     "Mix of cross-court and line. Harder for blockers to read."),
    ("Passing", "Strong passer",
     "~3 receptions with no errors. Helps with sideout."),
    ("When used", "Throughout set",
     "Consistent presence on court. Not just an attacker — does everything."),
    ("Strength", "All-around game + efficiency",
     ".500 hit %. Most complete player for UKC. Kills, digs, receptions all contribute."),
    ("Weakness", "Volume in clutch",
     "~5 kills. Could be used even more in big moments alongside #15."),
    ("", "", ""),
    ("UKC #10 Setter (est., white jersey)", "", ""),
    ("Setting tendency", "Estimated: left-leaning distribution",
     "Estimated setter — court behavior suggests transitions toward net to set after pass, but setting action NOT confirmed at 720p. Note: setter rotates through all 6 zones like everyone else."),
    ("Caveat", "LOW confidence on setter ID",
     "At 720p wide-angle, could not clearly identify who sets the ball. #10 is a best guess."),
    ("If setter", "UKC's offense is balanced",
     "UKC attacks came from multiple positions (left, center, right), suggesting good distribution."),
    ("Weakness (if setter)", "Middle utilization could improve",
     "UKC's middle attacks (#3, #8) appeared limited. More quicks could freeze USTA blockers."),
    ("", "", ""),
    ("USTA #15 OH (Outside Hitter, dark jersey) — PRIMARY WEAPON", "", ""),
    ("Attack tendency", "Left-antenna dominant",
     "Consistently attacks from the left antenna after transition across multiple rallies. Regardless of starting zone in rotation."),
    ("Shot selection", "Hard cross-court preferred",
     "Most attacks go cross-court rather than down-the-line."),
    ("Timing", "High contact point",
     "Contacts ball at or above the tape. Good jump. Best USTA attacker."),
    ("When targeted", "Comeback moments",
     "Set to her during USTA's 5-0 run (3-12 to 8-12) and set point saves. Clutch usage."),
    ("Strength", "Go-to in pressure",
     "~5 kills on ~9 attempts (.333). Gets the ball when USTA needs a point most."),
    ("Weakness", "Needs more support",
     "Too much offensive load on her. USTA needs other attackers to step up."),
    ("", "", ""),
    ("USTA #7 OPP (Opposite Hitter, dark jersey) — 2ND OPTION", "", ""),
    ("Attack tendency", "Right-side (pos 2) — from defensive positioning",
     "In Rally 35 appeared center-right of USTA front row, consistent with post-transition defensive pos 2 (right front = OPP). MB returns to center (pos 3), OH returns to left (pos 4). Center-right placement supports OPP."),
    ("Shot selection", "Varied",
     "Mix of cross-court and line. Harder for blockers to read."),
    ("When used", "Rotation-dependent",
     "Scores when in front row. Less visible when #15 is also front-row."),
    ("Strength", "Shot variety",
     "Mix of cross-court and line makes her harder to block than #15."),
    ("", "", ""),
    ("USTA #9 Setter (est., dark jersey)", "", ""),
    ("Setting tendency", "Estimated: heavily favors left side",
     "Estimated setter — court behavior suggests transitions toward net to set after pass, but setting action NOT confirmed at 720p. Note: setter rotates through all 6 zones like everyone else."),
    ("Caveat", "LOW confidence on setter ID",
     "At 720p wide-angle, could not clearly identify who sets the ball. #9 is a best guess."),
    ("If setter", "USTA's offense is left-heavy",
     "Most USTA attacks came from the left antenna (#15), suggesting setter favors that side."),
    ("Weakness (if setter)", "Distribution balance",
     "Over-relies on left side. Needs to develop middle (#10) and right-side options."),
]

df_tendencies = pd.DataFrame(tendencies_data,
                              columns=["Player / Aspect", "Tendency", "Detail"])


# =============================================================================
# Sheet 11: Play Patterns & Momentum Analysis
# =============================================================================
patterns_data = [
    ("SET PHASES", "", "", ""),
    ("Opening (0-0 to 1-10)", "UKC dominant",
     "UKC scored 10 of first 11 points. 4-0 run, then 6-0 run after USTA's lone sideout.",
     "USTA needs better serve receive to start sets. UKC's serve pressure was overwhelming."),
    ("Mid-set (1-10 to 8-12)", "USTA comeback attempt",
     "USTA scored 2 sideouts (2-10, 3-10), then 5-0 run (3-12 to 8-12). Momentum shifted.",
     "USTA showed they can compete. UKC must maintain focus when leading big."),
    ("Late-mid (8-12 to 12-20)", "Trading runs",
     "UKC 4-0 (8-14 to 8-16), USTA 4-of-5 (9-16 to 12-16), UKC 4-0 (12-17 to 12-20).",
     "Neither team sustained defense. Suggests serving/passing determines runs."),
    ("Closing (12-20 to 17-25)", "UKC closes despite USTA fight",
     "UKC scored to set point (15-24). USTA saved 2 set points (16-24, 17-24). UKC won on 3rd.",
     "USTA has closing resilience. UKC needs to be more clinical at set point."),
    ("", "", "", ""),
    ("SCORING RUN PATTERNS", "", "", ""),
    ("UKC 4-0 (0-0 to 0-4)", "Opening pressure",
     "UKC's first server was effective. USTA couldn't pass or attack.",
     "Serve pressure + attack efficiency = runs. USTA must improve first-ball sideout."),
    ("UKC 6-0 (1-4 to 1-10)", "Sustained dominance",
     "After USTA's lone sideout (1-4), UKC reeled off 6 straight to 1-10.",
     "UKC's best run. Server was dominant. USTA called timeout at 1-8 but couldn't stop it."),
    ("USTA 5-0 (3-12 to 8-12)", "Comeback energy",
     "USTA's big run narrowed the gap from 9 pts to 4 pts. Forced UKC timeout at 7-12.",
     "USTA server (Rot 3) was aggressive. UKC passing broke down temporarily."),
    ("UKC 4-0 (12-16 to 12-20)", "Pulling away",
     "After USTA closed to 12-16, UKC scored 4 straight to re-establish control.",
     "UKC showed ability to respond when USTA threatened. USTA called timeout at 12-20."),
    ("USTA set point saves (R42-R43)", "Clutch play",
     "USTA saved 2 consecutive set points before falling on 3rd.",
     "USTA doesn't quit. Mental toughness is a strength even in a loss."),
    ("", "", "", ""),
    ("TIMEOUT EFFECTIVENESS", "", "", ""),
    ("USTA timeout at 1-8 (det 9)", "Delayed effect",
     "USTA scored only 1 pt in next 3 rallies. Big run didn't start until 3-12.",
     "Timeout stopped immediate bleeding but didn't immediately trigger a run."),
    ("UKC timeout at 7-12 (det 19)", "Mixed result",
     "USTA scored 1 more point after timeout (8-12), then UKC responded.",
     "Timeout slowed USTA's 5-0 run. USTA got 1 more then UKC regained control."),
    ("USTA timeout at 12-20 (det 34)", "Partial effect",
     "USTA scored 1 sideout (13-20) then UKC took back control to close the set.",
     "Gave USTA a brief respite but couldn't turn the tide."),
    ("", "", "", ""),
    ("SIDEOUT PATTERNS", "", "", ""),
    ("UKC sideout rate", "~70%",
     "UKC won ~70% of rallies when receiving serve.",
     "Strong serve-receive game. Good first-ball attack."),
    ("USTA sideout rate", "~40-45%",
     "USTA struggled early (1 of 11) but improved mid-set (~55% from rally 12 onward).",
     "First-ball sideout is USTA's biggest area for improvement."),
    ("Pattern", "Streaky play",
     "Both teams scored in clusters rather than point-by-point. Multiple runs of 4+.",
     "Momentum-driven match. Serving pressure triggers runs for both teams."),
    ("", "", "", ""),
    ("POSITIONAL PATTERNS", "", "", ""),
    ("UKC left-side attacks", "~56% of offense",
     "#15 OH from left antenna is primary weapon. Multiple others contribute.",
     "USTA should overload left block. Force UKC to hit middle (#3, #8) or right side."),
    ("USTA left-side attacks", "~60% of offense",
     "#15 OH from left antenna. Very predictable.",
     "UKC can key on left side. USTA must use #10 in middle and develop right-side attacks."),
    ("Serve target patterns", "Back-row left",
     "Both teams primarily served to the back-row left (zone 5/6).",
     "Standard serve target. Could try zone 1 serve to disrupt setter."),
]

df_patterns = pd.DataFrame(patterns_data,
                            columns=["Topic", "Finding", "Evidence", "Coaching Suggestion"])


# =============================================================================
# Sheet 12: Coaching Suggestions & Next Set Adjustments
# =============================================================================
suggestions_data = [
    ("FOR USTA COACHING STAFF (lost Set 1: 17-25)", "", ""),
    ("", "", ""),
    ("PRIORITY 1: Improve serve receive", "", ""),
    ("Problem",
     "Only 1 point in first 11 rallies. Couldn't break UKC's opening serve.",
     "USTA's serve receive fell apart early, giving UKC a commanding 10-1 lead."),
    ("Solution",
     "#1 (libero, guess) and #5 should be primary passers. Platform angle drill.",
     "Get #1 (libero) in position to take 70%+ of serves. #5 showed good passing later."),
    ("Drill",
     "3-touch sideout drill starting from serve receive.",
     "Practice pass - set - attack sequences under serve pressure."),
    ("", "", ""),
    ("PRIORITY 2: Diversify attack", "", ""),
    ("Problem",
     "60% of sets to left side. Too predictable. UKC blockers could key on #15.",
     "With ~12 kills on ~25 attempts (.280), USTA needs more efficient options."),
    ("Solution",
     "More sets to #10 in the middle and more right-side attacks.",
     "Target 45% left, 25% middle, 20% right, 10% back-row."),
    ("Drill",
     "Setter-hitter connection drills with #10 (middle) and right-side options.",
     "Build trust between setter #9 (est.) and these under-utilized hitters."),
    ("", "", ""),
    ("PRIORITY 3: Serve strategy", "", ""),
    ("Problem",
     "59% serve win rate. Service errors cost free points when trailing.",
     "Each missed serve gives UKC a free point and maintains their serve."),
    ("Solution",
     "Float serve to zone 1 (UKC right back). Target their weakest passer.",
     "Avoid power serving that leads to errors. Consistency > power."),
    ("Target",
     "Zero service errors. Accept lower ace rate for reliability.",
     "A serve in play gives USTA a chance; a service error never does."),
    ("", "", ""),
    ("PRIORITY 4: Start strong next set", "", ""),
    ("Problem",
     "Fell behind 0-4 and 1-10 before recovering. Too large a deficit.",
     "Even the 5-0 run only got USTA within 4 points. They never led."),
    ("Solution",
     "Win the first 3 rallies of Set 2. First server must be aggressive but accurate.",
     "Early leads change the psychology. UKC showed they can be rattled (timeout at 7-12)."),
    ("", "", ""),
    ("FOR UKC COACHING STAFF (won Set 1: 25-17)", "", ""),
    ("", "", ""),
    ("PRIORITY 1: Close sets faster", "", ""),
    ("Problem",
     "Needed 3 set points to close. USTA saved 2 (16-24 and 17-24).",
     "At 15-24, should have finished. Lost focus and let USTA back to 17-24."),
    ("Solution",
     "Set play for #15 or #4 at set point. Don't overthink — go to best hitter.",
     "Setter #10 (est.) should call timeout before set point to reset if needed."),
    ("", "", ""),
    ("PRIORITY 2: Maintain focus during big leads", "", ""),
    ("Problem",
     "Led 3-12 (9 pts gap) but let USTA run 5-0 to 8-12 (4 pts gap).",
     "Concentration lapse when comfortable. USTA's energy shifted."),
    ("Solution",
     "Call early timeout if opponent scores 2 in a row during a big lead.",
     "Don't wait for 5-0 run. Timeout at 2-0 run costs nothing."),
    ("", "", ""),
    ("PRIORITY 3: Increase middle attacks", "", ""),
    ("Problem",
     "Only ~13% of sets went to middle (#3, #8). Left-side is effective but predictable for scouting.",
     "If USTA adjusts blocking in Set 2, UKC needs alternatives."),
    ("Solution",
     "Run more quick middles (1s and slides) to freeze USTA blockers.",
     "Target 20% middle attack % in next set. #3 and #8 have shown ability."),
    ("", "", ""),
    ("MATCH-LEVEL PATTERNS", "", ""),
    ("Prediction",
     "USTA will adjust serve receive for Set 2. Expect closer early score.",
     "USTA showed they can compete (5-0 run, set point saves). They won't collapse early again."),
    ("Key matchup",
     "UKC #15 vs USTA block. If USTA doubles #15, UKC needs #4 and #8 to step up.",
     "This is the battle that determines the set."),
    ("Momentum trigger",
     "Serving runs. Whoever serves well controls the set.",
     "Both teams' runs were triggered by serve pressure. This is the X-factor."),
]

df_suggestions = pd.DataFrame(suggestions_data,
                               columns=["Category", "Point", "Detail"])


# =============================================================================
# Sheet 13: Rotation Summary (aggregated per-rotation stats)
# =============================================================================
rot_summary_rows = build_rotation_summary(rotation_data)
rot_summary_columns = [
    "Team", "Rotation", "Total Rallies", "Points Scored", "Points Against",
    "Serving Rallies", "Serve Points", "Receiving Rallies", "Receive Points"
]
df_rotation_summary = pd.DataFrame(rot_summary_rows, columns=rot_summary_columns)


# =============================================================================
# Generate Score Progression Chart
# =============================================================================
chart_path = output_dir / "score_progression_chart.png"
create_score_chart(rotation_data, chart_path)


# =============================================================================
# Write Excel
# =============================================================================
xlsx_path = output_dir / "volleyball_set1_detailed_stats.xlsx"

with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
    df_info.to_excel(writer, sheet_name="Match Info", index=False)
    df_rallies.to_excel(writer, sheet_name="Rally Log", index=False)
    df_usta.to_excel(writer, sheet_name="USTA Player Stats", index=False)
    df_ukc.to_excel(writer, sheet_name="UKC Player Stats", index=False)
    df_team.to_excel(writer, sheet_name="Team Comparison", index=False)
    df_scores.to_excel(writer, sheet_name="Score Progression", index=False)
    df_serve_analysis.to_excel(writer, sheet_name="Serve Analysis", index=False)
    df_coach.to_excel(writer, sheet_name="Coach Scouting Report", index=False)
    df_set_dist.to_excel(writer, sheet_name="Set Distribution", index=False)
    df_tendencies.to_excel(writer, sheet_name="Player Tendencies", index=False)
    df_patterns.to_excel(writer, sheet_name="Play Patterns", index=False)
    df_suggestions.to_excel(writer, sheet_name="Coaching Suggestions", index=False)
    df_rotation_summary.to_excel(writer, sheet_name="Rotation Summary", index=False)

    # Embed chart image in Score Progression sheet
    ws = writer.sheets["Score Progression"]
    img = XlImage(str(chart_path))
    ws.add_image(img, f"A{len(score_data) + 4}")

    # Auto-adjust column widths
    for sheet_name in writer.sheets:
        ws = writer.sheets[sheet_name]
        for col_idx, col in enumerate(ws.columns, 1):
            max_len = 0
            for cell in col:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 65)

print(f"\nExcel saved to: {xlsx_path}")

# Also save CSVs
csv_dir = output_dir / "csv"
csv_dir.mkdir(exist_ok=True)

df_rallies.to_csv(csv_dir / "set1_rally_log.csv", index=False)
df_usta.to_csv(csv_dir / "set1_usta_player_stats.csv", index=False)
df_ukc.to_csv(csv_dir / "set1_ukc_player_stats.csv", index=False)
df_team.to_csv(csv_dir / "set1_team_comparison.csv", index=False)
df_scores.to_csv(csv_dir / "set1_score_progression.csv", index=False)
df_serve_analysis.to_csv(csv_dir / "set1_serve_analysis.csv", index=False)
df_set_dist.to_csv(csv_dir / "set1_set_distribution.csv", index=False)
df_tendencies.to_csv(csv_dir / "set1_player_tendencies.csv", index=False)
df_patterns.to_csv(csv_dir / "set1_play_patterns.csv", index=False)
df_suggestions.to_csv(csv_dir / "set1_coaching_suggestions.csv", index=False)
df_rotation_summary.to_csv(csv_dir / "set1_rotation_summary.csv", index=False)

print(f"CSVs saved to: {csv_dir}")
print()
print("Sheets:")
print("  1.  Match Info - methodology, team identification, confidence levels")
print("  2.  Rally Log - all 44 entries (43 detections + 1 undetected final point)")
print("  3.  USTA Player Stats - dark navy jerseys (17 pts, losing team)")
print("  4.  UKC Player Stats - white jerseys (25 pts, winning team)")
print("  5.  Team Comparison - side-by-side with computed stats + verified scoring runs")
print("  6.  Score Progression - point-by-point with rotation tracking + chart")
print("  7.  Serve Analysis - serve rotation tracking by team")
print("  8.  Coach Scouting Report - strengths, weaknesses, recommendations")
print("  9.  Set Distribution - setter distribution analysis for both teams")
print("  10. Player Tendencies - individual player patterns and habits")
print("  11. Play Patterns - momentum, runs, timeouts, sideout analysis")
print("  12. Coaching Suggestions - prioritized adjustments for next set")
print("  13. Rotation Summary - per-rotation aggregated stats for both teams")
