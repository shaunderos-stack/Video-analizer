"""Volleyball Analytics Platform — Streamlit App.

Multi-page app with sidebar navigation: Dashboard, New Game, Games, Game Detail,
Season Analytics, Teams, Players, Export.  Data persisted in SQLite via db.py.
"""

import io
import datetime
from pathlib import Path

import streamlit as st
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import db
import config

# ── Page config (must be first Streamlit call) ───────────────────────────────
st.set_page_config(page_title="Volleyball Analytics", page_icon="🏐", layout="wide")

# ── Initialise database on first run ─────────────────────────────────────────
db.init_db()

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
header[data-testid="stHeader"] {background: #1a1a2e;}
div[data-testid="stAppViewBlockContainer"] {padding-top: 1rem;}
.big-score {font-size: 2.4rem; font-weight: 700; text-align: center;}
.team-label {font-size: 1.1rem; text-align: center; color: #888;}
</style>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═════════════════════════════════════════════════════════════════════════════

def format_hit_pct(kills, errors, attempts):
    if attempts == 0:
        return "--"
    pct = (kills - errors) / attempts
    s = f"{pct:.3f}"
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    return s


def nav(page, **extra):
    """Set navigation state and rerun."""
    st.session_state["page"] = page
    for k, v in extra.items():
        st.session_state[k] = v
    st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
#  Sidebar navigation
# ═════════════════════════════════════════════════════════════════════════════

PAGES = ["Dashboard", "New Game", "Games", "Game Detail", "Season Analytics",
         "Teams", "Players", "Export"]

with st.sidebar:
    st.title("🏐 Volleyball Analytics")
    st.divider()
    for p in PAGES:
        if p == "Game Detail":
            continue  # accessed via View buttons
        if st.button(p, key=f"nav_{p}", use_container_width=True):
            nav(p)
    st.divider()
    st.caption("Volleyball-first analytics platform")

current_page = st.session_state.get("page", "Dashboard")


# ═════════════════════════════════════════════════════════════════════════════
#  Page 1: Dashboard
# ═════════════════════════════════════════════════════════════════════════════

def page_dashboard():
    st.header("Dashboard")

    games = db.get_all_games()
    teams = db.get_all_teams()
    with db.get_connection() as conn:
        player_count = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]

    # Metric cards
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Games", len(games))
    c2.metric("Teams", len(teams))
    c3.metric("Players", player_count)

    # Recent games
    st.subheader("Recent Games")
    if games:
        for g in games[:10]:
            cols = st.columns([3, 2, 1, 1])
            cols[0].write(f"**{g['home_abbr']} vs {g['away_abbr']}**")
            cols[1].write(g.get("date", ""))
            cols[2].write(g.get("status", ""))
            if cols[3].button("View", key=f"dash_view_{g['id']}"):
                nav("Game Detail", selected_game_id=g["id"])
    else:
        st.info("No games yet. Create one from the New Game page.")

    # Top scorers
    st.subheader("Top Scorers")
    with db.get_connection() as conn:
        top = conn.execute("""
            SELECT p.name, p.jersey_number, t.abbreviation as team,
                   COALESCE(SUM(pss.points), 0) as total_points,
                   COALESCE(SUM(pss.kills), 0) as kills,
                   COALESCE(SUM(pss.aces), 0) as aces
            FROM player_set_stats pss
            JOIN players p ON pss.player_id = p.id
            JOIN teams t ON p.team_id = t.id
            GROUP BY p.id
            HAVING total_points > 0
            ORDER BY total_points DESC
            LIMIT 10
        """).fetchall()
    if top:
        df = pd.DataFrame([dict(r) for r in top])
        df.columns = ["Player", "Jersey", "Team", "Points", "Kills", "Aces"]
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Team standings
    st.subheader("Team Standings")
    if teams:
        rows = []
        for t in teams:
            w, l = db.get_team_record(t["id"])
            rows.append({"Team": t["name"], "Abbr": t.get("abbreviation", ""), "W": w, "L": l})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════════════════════
#  Page 2: New Game
# ═════════════════════════════════════════════════════════════════════════════

def page_new_game():
    st.header("New Game")

    teams = db.get_all_teams()
    team_names = [f"{t['abbreviation']} — {t['name']}" for t in teams]
    team_ids = [t["id"] for t in teams]

    # Create new team inline
    with st.expander("Create New Team"):
        with st.form("new_team_form"):
            nt_name = st.text_input("Team Name")
            nt_abbr = st.text_input("Abbreviation (3-5 chars)")
            nt_conf = st.text_input("Conference")
            nt_color = st.text_input("Jersey Color")
            if st.form_submit_button("Create Team"):
                if nt_name:
                    db.create_team(nt_name, nt_abbr, nt_conf, nt_color)
                    st.success(f"Created team: {nt_name}")
                    st.rerun()
                else:
                    st.error("Team name is required.")

    if len(teams) < 2:
        st.warning("You need at least 2 teams to create a game. Add teams above.")
        return

    # Game form
    st.subheader("Game Details")
    col1, col2 = st.columns(2)
    with col1:
        home_idx = st.selectbox("Home Team", range(len(team_names)), format_func=lambda i: team_names[i], key="ng_home")
    with col2:
        away_default = 1 if len(team_names) > 1 else 0
        away_idx = st.selectbox("Away Team", range(len(team_names)), format_func=lambda i: team_names[i],
                                index=away_default, key="ng_away")

    col3, col4 = st.columns(2)
    with col3:
        game_date = st.date_input("Date", value=datetime.date.today())
    with col4:
        venue = st.text_input("Venue")

    seasons = db.get_all_seasons()
    season_names = [s["name"] for s in seasons]
    season_idx = st.selectbox("Season", range(len(season_names)),
                              format_func=lambda i: season_names[i]) if seasons else None

    st.subheader("Video Source")
    video_source = st.text_input("YouTube URL or local file path",
                                 placeholder="https://youtube.com/watch?v=... or C:/path/to/video.mp4")

    # Start analysis
    if st.button("Start Analysis", type="primary", disabled=not video_source):
        home_id = team_ids[home_idx]
        away_id = team_ids[away_idx]
        season_id = seasons[season_idx]["id"] if season_idx is not None else None

        game_id = db.create_game(
            season_id=season_id, home_team_id=home_id, away_team_id=away_id,
            date=str(game_date), venue=venue, video_url=video_source, status="analyzing",
        )

        with st.status("Running analysis pipeline...", expanded=True) as status:
            progress_bar = st.progress(0.0)
            log = st.empty()

            def on_progress(stage, pct):
                progress_bar.progress(min(pct, 1.0))
                log.write(stage)

            try:
                from pipeline import run_full_pipeline
                result = run_full_pipeline(video_source, game_id, home_id, away_id, on_progress)
                status.update(label="Analysis complete!", state="complete")
                st.success(f"Done! Found {result['events_count']} events, "
                           f"{result['players_found']} players, {result['sets_detected']} sets.")
                if st.button("View Game"):
                    nav("Game Detail", selected_game_id=game_id)
            except Exception as e:
                status.update(label="Analysis failed", state="error")
                db.update_game(game_id, status="error")
                st.error(f"Pipeline error: {e}")


# ═════════════════════════════════════════════════════════════════════════════
#  Page 3: Games List
# ═════════════════════════════════════════════════════════════════════════════

def page_games():
    st.header("Games")

    games = db.get_all_games()
    if not games:
        st.info("No games found. Create one from the New Game page.")
        return

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        teams = db.get_all_teams()
        team_filter = st.selectbox("Filter by team", ["All"] + [t["name"] for t in teams], key="games_team_filter")
    with col2:
        status_filter = st.selectbox("Filter by status", ["All", "completed", "analyzing", "pending", "error"],
                                     key="games_status_filter")

    for g in games:
        # Apply filters
        if team_filter != "All":
            if g["home_team_name"] != team_filter and g["away_team_name"] != team_filter:
                continue
        if status_filter != "All" and g.get("status") != status_filter:
            continue

        sets = db.get_sets_for_game(g["id"])
        set_scores = "  |  ".join(f"S{s['set_number']}: {s['home_score']}-{s['away_score']}" for s in sets)

        cols = st.columns([3, 2, 2, 1])
        cols[0].write(f"**{g['home_abbr']} vs {g['away_abbr']}**")
        cols[1].write(f"{g.get('date', '')}  —  {set_scores}")
        cols[2].write(f"Status: {g.get('status', 'unknown')}")
        if cols[3].button("View", key=f"games_view_{g['id']}"):
            nav("Game Detail", selected_game_id=g["id"])


# ═════════════════════════════════════════════════════════════════════════════
#  Page 4: Game Detail (7 sub-tabs)
# ═════════════════════════════════════════════════════════════════════════════

def page_game_detail():
    game_id = st.session_state.get("selected_game_id")
    if not game_id:
        st.warning("No game selected. Go to Games to pick one.")
        return

    game = db.get_game(game_id)
    if not game:
        st.error("Game not found.")
        return

    st.header(f"{game['home_abbr']} vs {game['away_abbr']}")
    st.caption(f"{game.get('date', '')}  |  {game.get('venue', '')}  |  {game.get('season_name', '')}")

    sets = db.get_sets_for_game(game_id)

    tabs = st.tabs([
        "Match Overview", "Rally Log", "Player Stats", "Team Comparison",
        "Rotation Analysis", "Score Progression", "Video Clips", "Scouting Notes"
    ])

    # ── Tab 1: Match Overview ────────────────────────────────────────────────
    with tabs[0]:
        _tab_match_overview(game, sets)

    # ── Tab 2: Rally Log ─────────────────────────────────────────────────────
    with tabs[1]:
        _tab_rally_log(game, sets)

    # ── Tab 3: Player Stats ──────────────────────────────────────────────────
    with tabs[2]:
        _tab_player_stats(game, sets)

    # ── Tab 4: Team Comparison ───────────────────────────────────────────────
    with tabs[3]:
        _tab_team_comparison(game)

    # ── Tab 5: Rotation Analysis ─────────────────────────────────────────────
    with tabs[4]:
        _tab_rotation_analysis(game, sets)

    # ── Tab 6: Score Progression ─────────────────────────────────────────────
    with tabs[5]:
        _tab_score_progression(game, sets)

    # ── Tab 7: Video Clips ───────────────────────────────────────────────────
    with tabs[6]:
        _tab_video_clips(game, sets)

    # ── Tab 8: Scouting Notes ────────────────────────────────────────────────
    with tabs[7]:
        _tab_scouting_notes(game)


def _tab_match_overview(game, sets):
    """Set scores, key metrics, score progression chart."""
    # Set scores
    if sets:
        set_cols = st.columns(len(sets))
        for i, s in enumerate(sets):
            with set_cols[i]:
                st.metric(f"Set {s['set_number']}",
                          f"{s['home_score']} - {s['away_score']}",
                          delta=None)

    # Aggregate stats per team
    stats = db.get_stats_for_game(game["id"])
    if not stats:
        st.info("No player stats available for this game.")
        return

    df = pd.DataFrame(stats)
    home_stats = df[df["team_id"] == game["home_team_id"]]
    away_stats = df[df["team_id"] == game["away_team_id"]]

    def _team_agg(tdf):
        return {
            "Kills": int(tdf["kills"].sum()),
            "Atk Errors": int(tdf["attack_errors"].sum()),
            "Atk Attempts": int(tdf["attack_attempts"].sum()),
            "Hit %": format_hit_pct(int(tdf["kills"].sum()), int(tdf["attack_errors"].sum()),
                                    int(tdf["attack_attempts"].sum())),
            "Blocks": int(tdf["solo_blocks"].sum() + tdf["block_assists"].sum()),
            "Digs": int(tdf["digs"].sum()),
            "Aces": int(tdf["aces"].sum()),
            "Assists": int(tdf["assists"].sum()),
            "Points": int(tdf["points"].sum()),
        }

    st.subheader("Key Metrics")
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**{game['home_abbr']}**")
        if not home_stats.empty:
            for k, v in _team_agg(home_stats).items():
                st.write(f"  {k}: **{v}**")
    with c2:
        st.write(f"**{game['away_abbr']}**")
        if not away_stats.empty:
            for k, v in _team_agg(away_stats).items():
                st.write(f"  {k}: **{v}**")

    # Play type distribution pie chart
    st.subheader("Play Type Distribution")
    from play_classifier import get_play_type_distribution
    dist = get_play_type_distribution(game["id"])
    if dist:
        fig_pie, ax_pie = plt.subplots(figsize=(6, 4))
        labels = list(dist.keys())
        sizes = list(dist.values())
        colors = plt.cm.Set3(range(len(labels)))
        ax_pie.pie(sizes, labels=labels, autopct="%1.0f%%", colors=colors, startangle=90)
        ax_pie.set_title("Play Types")
        fig_pie.tight_layout()
        st.pyplot(fig_pie)
        plt.close(fig_pie)
    else:
        st.info("No play type data available. Use 'Classify Plays' in the Rally Log tab.")

    # Score progression chart
    st.subheader("Score Progression")
    _render_score_chart(game, sets)


def _render_score_chart(game, sets):
    """Draw a matplotlib score progression chart from rally data."""
    all_rallies = []
    for s in sets:
        rallies = db.get_rallies_for_set(s["id"])
        all_rallies.extend(rallies)

    if not all_rallies:
        st.info("No rally data available for chart.")
        return

    rally_nums = []
    home_scores = []
    away_scores = []

    for r in all_rallies:
        rally_nums.append(r["rally_number"])
        after = r.get("score_after", "0-0")
        parts = after.split("-")
        if len(parts) == 2:
            try:
                home_scores.append(int(parts[0]))
                away_scores.append(int(parts[1]))
            except ValueError:
                home_scores.append(0)
                away_scores.append(0)
        else:
            home_scores.append(0)
            away_scores.append(0)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(rally_nums, home_scores, color="darkred", linewidth=2, label=game["home_abbr"],
            marker="s", markersize=3)
    ax.plot(rally_nums, away_scores, color="darkblue", linewidth=2, label=game["away_abbr"],
            marker="o", markersize=3)
    ax.fill_between(rally_nums, home_scores, away_scores, alpha=0.1, color="gray")
    ax.set_xlabel("Rally Number")
    ax.set_ylabel("Score")
    ax.set_title(f"Score Progression — {game['home_abbr']} vs {game['away_abbr']}")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def _tab_rally_log(game, sets):
    """Editable rally log per set, with action buttons for OCR/classify/detect."""
    # ── Action buttons row ──────────────────────────────────────────────────
    st.subheader("Batch Actions")
    btn_cols = st.columns(4)

    with btn_cols[0]:
        if st.button("Re-read Scores (OCR)", key="btn_ocr"):
            _run_score_ocr(game)

    with btn_cols[1]:
        if st.button("Classify Plays", key="btn_classify"):
            from play_classifier import classify_all_rallies
            n = classify_all_rallies(game["id"])
            st.success(f"Classified {n} rallies.")
            st.rerun()

    with btn_cols[2]:
        detect_method = st.radio(
            "Detection method",
            ["YOLO Tracking (recommended)", "HSV Color (legacy)"],
            key="detect_method",
            horizontal=True,
            label_visibility="collapsed",
        )
        if st.button("Auto-detect Players", key="btn_detect"):
            if detect_method.startswith("YOLO"):
                _run_player_tracking(game)
            else:
                _run_jersey_detection(game)

    with btn_cols[3]:
        if st.button("Extract Video Clips", key="btn_clips"):
            _run_clip_extraction(game)

    st.divider()

    # ── Per-set rally tables ────────────────────────────────────────────────
    for s in sets:
        st.subheader(f"Set {s['set_number']}")
        rallies = db.get_rallies_for_set(s["id"])
        if not rallies:
            st.info("No rallies recorded for this set.")
            continue

        df = pd.DataFrame(rallies)
        display_cols = ["rally_number", "video_time", "score_before", "score_after",
                        "scoring_team", "play_type", "key_player", "notes"]
        available = [c for c in display_cols if c in df.columns]
        edit_df = df[available].copy()

        edited = st.data_editor(
            edit_df,
            key=f"rally_edit_{s['id']}",
            use_container_width=True,
            hide_index=True,
            disabled=["rally_number"],
        )

        # Inline video clips per rally
        for r in rallies:
            clip_path = r.get("clip_path")
            if clip_path:
                full_path = Path(config.PROJECT_DIR) / clip_path
                if full_path.exists():
                    with st.expander(f"Rally {r['rally_number']} clip"):
                        st.video(str(full_path))

        if st.button(f"Save Rally Changes (Set {s['set_number']})", key=f"save_rallies_{s['id']}"):
            for idx, row in edited.iterrows():
                rally_id = rallies[idx]["id"]
                db.update_rally(
                    rally_id,
                    scoring_team=row.get("scoring_team", ""),
                    play_type=row.get("play_type", ""),
                    key_player=row.get("key_player", ""),
                    notes=row.get("notes", ""),
                )
            st.success("Rally log saved!")
            st.rerun()


def _run_score_ocr(game):
    """Run Score OCR on all rallies for this game."""
    video_path = game.get("video_path", "")
    if not video_path or not Path(video_path).exists():
        st.warning("No video file found for this game. Set the video path in game settings.")
        return

    with st.spinner("Running Score OCR..."):
        from score_ocr import ocr_rally_scores
        rallies = db.get_rallies_for_game(game["id"])
        results = ocr_rally_scores(video_path, rallies)

        updated = 0
        for r in results:
            if r["home"] is not None and r["away"] is not None:
                score_str = f"{r['home']}-{r['away']}"
                db.update_rally(r["rally_id"], score_after=score_str)
                updated += 1

    st.success(f"OCR complete: updated {updated}/{len(results)} rally scores.")
    st.rerun()


def _run_jersey_detection(game):
    """Run jersey detection on all rallies missing key_player."""
    video_path = game.get("video_path", "")
    if not video_path or not Path(video_path).exists():
        st.warning("No video file found for this game.")
        return

    with st.spinner("Detecting players (this may take a while)..."):
        from jersey_detector import detect_players_for_game
        progress_bar = st.progress(0.0)

        def on_progress(current, total):
            progress_bar.progress(current / total)

        n = detect_players_for_game(video_path, game["id"], on_progress)

    st.success(f"Identified servers in {n} rallies.")
    st.rerun()


def _run_player_tracking(game):
    """Run YOLO+ByteTrack player tracking on all rallies missing key_player."""
    video_path = game.get("video_path", "")
    if not video_path or not Path(video_path).exists():
        st.warning("No video file found for this game.")
        return

    try:
        from player_tracker import detect_players_for_game_tracked
    except ImportError:
        st.error(
            "YOLO tracking requires the `ultralytics` package. "
            "Install it with: `pip install ultralytics>=8.0.0`"
        )
        return

    with st.spinner("Tracking players with YOLO+ByteTrack (this may take a while)..."):
        progress_bar = st.progress(0.0)

        def on_progress(current, total):
            progress_bar.progress(current / total)

        n = detect_players_for_game_tracked(video_path, game["id"], on_progress)

    st.success(f"Identified servers in {n} rallies (YOLO+ByteTrack).")
    st.rerun()


def _run_clip_extraction(game):
    """Extract video clips for all rallies in this game."""
    video_path = game.get("video_path", "")
    if not video_path or not Path(video_path).exists():
        st.warning("No video file found for this game.")
        return

    with st.spinner("Extracting clips..."):
        from clip_extractor import extract_all_clips
        progress_bar = st.progress(0.0)

        def on_progress(current, total):
            progress_bar.progress(current / total)

        clips = extract_all_clips(video_path, game["id"], on_progress)

    st.success(f"Extracted {len(clips)} clips.")
    st.rerun()


def _tab_player_stats(game, sets):
    """Editable player stats per team per set."""
    for s in sets:
        st.subheader(f"Set {s['set_number']}")
        stats = db.get_stats_for_set(s["id"])
        if not stats:
            st.info("No player stats for this set.")
            continue

        df = pd.DataFrame(stats)

        # Split by team
        for team_id, label in [(game["home_team_id"], game["home_abbr"]),
                               (game["away_team_id"], game["away_abbr"])]:
            team_df = df[df["team_id"] == team_id].copy()
            if team_df.empty:
                continue

            st.write(f"**{label}**")
            edit_cols = ["player_name", "jersey_number", "position",
                         "serves", "aces", "service_errors", "kills", "attack_errors",
                         "attack_attempts", "solo_blocks", "block_assists", "digs",
                         "receptions", "assists", "points"]
            available = [c for c in edit_cols if c in team_df.columns]
            edit_df = team_df[available].copy()

            edited = st.data_editor(
                edit_df,
                key=f"pstats_{s['id']}_{team_id}",
                use_container_width=True,
                hide_index=True,
            )

            if st.button(f"Save {label} Stats (Set {s['set_number']})", key=f"save_pstats_{s['id']}_{team_id}"):
                for idx in edited.index:
                    orig = stats[idx]
                    row = edited.loc[idx]

                    # Update player info
                    db.update_player(
                        orig["player_id"],
                        name=row.get("player_name", ""),
                        position=row.get("position", ""),
                    )

                    # Update stats
                    stat_kwargs = {}
                    for col in ["serves", "aces", "service_errors", "kills", "attack_errors",
                                "attack_attempts", "solo_blocks", "block_assists", "digs",
                                "receptions", "assists", "points"]:
                        if col in row.index:
                            stat_kwargs[col] = int(row[col])
                    db.update_player_set_stats(orig["id"], **stat_kwargs)

                st.success(f"Saved {label} stats!")
                st.rerun()


def _tab_team_comparison(game):
    """Side-by-side aggregated team stats."""
    stats = db.get_stats_for_game(game["id"])
    if not stats:
        st.info("No stats available.")
        return

    df = pd.DataFrame(stats)
    home = df[df["team_id"] == game["home_team_id"]]
    away = df[df["team_id"] == game["away_team_id"]]

    stat_cols = ["kills", "attack_errors", "attack_attempts", "aces", "service_errors",
                 "solo_blocks", "block_assists", "digs", "receptions", "assists", "points"]
    labels = ["Kills", "Atk Errors", "Atk Attempts", "Aces", "Svc Errors",
              "Solo Blocks", "Block Assists", "Digs", "Receptions", "Assists", "Points"]

    rows = []
    for col, label in zip(stat_cols, labels):
        h = int(home[col].sum()) if not home.empty else 0
        a = int(away[col].sum()) if not away.empty else 0
        rows.append({"Stat": label, game["home_abbr"]: h, game["away_abbr"]: a})

    # Add hit %
    h_k, h_e, h_a = (int(home["kills"].sum()), int(home["attack_errors"].sum()),
                      int(home["attack_attempts"].sum())) if not home.empty else (0, 0, 0)
    a_k, a_e, a_a = (int(away["kills"].sum()), int(away["attack_errors"].sum()),
                      int(away["attack_attempts"].sum())) if not away.empty else (0, 0, 0)
    rows.append({"Stat": "Hit %", game["home_abbr"]: format_hit_pct(h_k, h_e, h_a),
                 game["away_abbr"]: format_hit_pct(a_k, a_e, a_a)})

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _tab_rotation_analysis(game, sets):
    """Rotation summary and serve analysis from rally data."""
    all_rallies = []
    for s in sets:
        rallies = db.get_rallies_for_set(s["id"])
        all_rallies.extend(rallies)

    if not all_rallies:
        st.info("No rally data available.")
        return

    st.subheader("Rotation Summary")
    for team_abbr, team_id, rot_key in [
        (game["home_abbr"], game["home_team_id"], "home_rotation"),
        (game["away_abbr"], game["away_team_id"], "away_rotation"),
    ]:
        st.write(f"**{team_abbr}**")
        rows = []
        for rot_num in range(1, 7):
            rots = [r for r in all_rallies if r.get(rot_key) == rot_num]
            if not rots:
                continue
            pts = sum(1 for r in rots if r["scoring_team"] == team_abbr)
            against = len(rots) - pts
            serving = [r for r in rots if r.get("serving_team") == team_abbr]
            serve_pts = sum(1 for r in serving if r["scoring_team"] == team_abbr)
            rows.append({
                "Rotation": rot_num, "Rallies": len(rots),
                "Points For": pts, "Points Against": against,
                "Serving Rallies": len(serving), "Serve Points": serve_pts,
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.subheader("Serve Analysis")
    for team_abbr in [game["home_abbr"], game["away_abbr"]]:
        serving_rallies = [r for r in all_rallies if r.get("serving_team") == team_abbr]
        total = len(serving_rallies)
        won = sum(1 for r in serving_rallies if r["scoring_team"] == team_abbr)
        st.write(f"**{team_abbr}**: Served {total} rallies, won {won} "
                 f"({won/total*100:.0f}%)" if total > 0 else f"**{team_abbr}**: No serve data")


def _tab_score_progression(game, sets):
    """Point-by-point table with rotations."""
    for s in sets:
        st.subheader(f"Set {s['set_number']}")
        rallies = db.get_rallies_for_set(s["id"])
        if not rallies:
            st.info("No rallies.")
            continue

        df = pd.DataFrame(rallies)
        display_cols = ["rally_number", "video_time", "score_before", "score_after",
                        "scoring_team", "serving_team", "home_rotation", "away_rotation",
                        "is_sideout", "key_player"]
        available = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available], use_container_width=True, hide_index=True)


def _tab_video_clips(game, sets):
    """Grid of rally video clips with st.video(), filterable."""
    st.subheader("Video Clips")

    rallies = db.get_rallies_for_game(game["id"])
    clipped = [r for r in rallies if r.get("clip_path")]

    if not clipped:
        st.info("No clips extracted yet. Use 'Extract Video Clips' in the Rally Log tab.")
        return

    # Filters
    fc1, fc2 = st.columns(2)
    with fc1:
        set_nums = sorted(set(r.get("set_number", 1) for r in clipped))
        set_filter = st.selectbox("Filter by set", ["All"] + [f"Set {n}" for n in set_nums],
                                  key="clip_set_filter")
    with fc2:
        play_types = sorted(set(r.get("play_type", "") for r in clipped if r.get("play_type")))
        type_filter = st.selectbox("Filter by play type", ["All"] + play_types,
                                   key="clip_type_filter")

    # Apply filters
    filtered = clipped
    if set_filter != "All":
        sn = int(set_filter.split()[-1])
        filtered = [r for r in filtered if r.get("set_number") == sn]
    if type_filter != "All":
        filtered = [r for r in filtered if r.get("play_type") == type_filter]

    if not filtered:
        st.info("No clips match the current filters.")
        return

    # Display in a grid (3 columns)
    cols_per_row = 3
    for i in range(0, len(filtered), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(filtered):
                break
            r = filtered[idx]
            full_path = Path(config.PROJECT_DIR) / r["clip_path"]
            with col:
                st.caption(f"S{r.get('set_number', '?')} R{r['rally_number']} — "
                           f"{r.get('play_type', '?')} | {r.get('scoring_team', '?')}")
                if full_path.exists():
                    st.video(str(full_path))
                else:
                    st.warning("Clip file not found")


def _tab_scouting_notes(game):
    """Free-form notes stored in games.notes."""
    current_notes = game.get("notes", "") or ""
    notes = st.text_area("Scouting / Coaching Notes", value=current_notes, height=300,
                         key="scouting_notes")
    if st.button("Save Notes"):
        db.update_game(game["id"], notes=notes)
        st.success("Notes saved!")
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
#  Page 5: Season Analytics (Feature 4)
# ═════════════════════════════════════════════════════════════════════════════

def page_season_analytics():
    st.header("Season Analytics")

    teams = db.get_all_teams()
    seasons = db.get_all_seasons()

    if not teams:
        st.info("No teams found. Add teams and games first.")
        return

    subtabs = st.tabs([
        "Player Trends", "Team Efficiency", "Rotation Performance",
        "Head-to-Head", "Leaderboards"
    ])

    # ── Sub-tab 1: Player Trends ────────────────────────────────────────────
    with subtabs[0]:
        _season_player_trends(teams)

    # ── Sub-tab 2: Team Efficiency ──────────────────────────────────────────
    with subtabs[1]:
        _season_team_efficiency(teams)

    # ── Sub-tab 3: Rotation Performance ─────────────────────────────────────
    with subtabs[2]:
        _season_rotation_performance(teams)

    # ── Sub-tab 4: Head-to-Head ─────────────────────────────────────────────
    with subtabs[3]:
        _season_head_to_head(teams)

    # ── Sub-tab 5: Leaderboards ─────────────────────────────────────────────
    with subtabs[4]:
        _season_leaderboards(seasons)


def _season_player_trends(teams):
    """Player trend charts: kills, digs, hit% per set over time."""
    st.subheader("Player Trends")

    # Player selection
    all_players = db.get_all_players_list()
    if not all_players:
        st.info("No players found.")
        return

    player_labels = [f"#{p['jersey_number']} {p['name']} ({p['team_abbr']})" for p in all_players]
    sel_idx = st.selectbox("Select player", range(len(player_labels)),
                           format_func=lambda i: player_labels[i], key="trend_player")
    player = all_players[sel_idx]

    set_stats = db.get_player_stats_by_set(player["id"])
    if not set_stats:
        st.info("No set-level stats available for this player.")
        return

    df = pd.DataFrame(set_stats)
    df["label"] = df.apply(lambda r: f"{r['home_abbr']}v{r['away_abbr']} S{r['set_number']}", axis=1)
    df["hit_pct"] = df.apply(
        lambda r: (r["kills"] - r["attack_errors"]) / r["attack_attempts"]
        if r["attack_attempts"] > 0 else 0.0, axis=1)
    df["total_blocks"] = df["solo_blocks"] + df["block_assists"]

    # Line charts
    stat_options = ["kills", "digs", "aces", "assists", "points", "hit_pct", "total_blocks"]
    selected_stats = st.multiselect("Stats to plot", stat_options, default=["kills", "digs"],
                                     key="trend_stats")

    if selected_stats:
        fig, ax = plt.subplots(figsize=(12, 5))
        x = range(len(df))
        for stat in selected_stats:
            if stat in df.columns:
                ax.plot(x, df[stat], marker="o", linewidth=2, label=stat)
        ax.set_xticks(list(x))
        ax.set_xticklabels(df["label"], rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("Value")
        ax.set_title(f"Trends: #{player['jersey_number']} {player['name']}")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    # Per-game aggregated table
    game_stats = db.get_player_stats_by_game(player["id"])
    if game_stats:
        st.subheader("Per-Game Summary")
        gdf = pd.DataFrame(game_stats)
        gdf["matchup"] = gdf["home_abbr"] + " vs " + gdf["away_abbr"]
        gdf["hit_pct"] = gdf.apply(
            lambda r: format_hit_pct(r["kills"], r["attack_errors"], r["attack_attempts"]), axis=1)
        display = gdf[["date", "matchup", "sets_played", "kills", "aces", "digs",
                        "assists", "points", "hit_pct"]]
        st.dataframe(display, use_container_width=True, hide_index=True)


def _season_team_efficiency(teams):
    """Side-out percentage and scoring runs analysis per game."""
    st.subheader("Team Efficiency")

    team_labels = [f"{t['abbreviation']} — {t['name']}" for t in teams]
    sel = st.selectbox("Select team", range(len(team_labels)),
                       format_func=lambda i: team_labels[i], key="eff_team")
    team = teams[sel]

    # Side-out stats
    st.write("**Side-out Analysis**")
    games = db.get_all_games()
    team_games = [g for g in games
                  if g["home_team_id"] == team["id"] or g["away_team_id"] == team["id"]]

    if not team_games:
        st.info("No games found for this team.")
        return

    so_rows = []
    for g in team_games:
        so = db.get_team_sideout_pct(team["id"], g["id"])
        so_rows.append({
            "Game": f"{g['home_abbr']} vs {g['away_abbr']}",
            "Date": g.get("date", ""),
            "Receiving Rallies": so["total"],
            "Side-outs Won": so["won"],
            "SO %": f"{so['pct']:.1f}%",
        })
    st.dataframe(pd.DataFrame(so_rows), use_container_width=True, hide_index=True)

    # Overall side-out
    overall = db.get_team_sideout_pct(team["id"])
    st.metric("Overall Side-out %", f"{overall['pct']:.1f}%",
              delta=f"{overall['won']}/{overall['total']} rallies")

    # Scoring runs
    st.write("**Scoring Runs**")
    for g in team_games:
        game_sets = db.get_sets_for_game(g["id"])
        for s in game_sets:
            runs = db.get_scoring_runs(s["id"])
            team_runs = [r for r in runs if r["team"] == team.get("abbreviation", "")]
            if team_runs:
                st.write(f"*{g['home_abbr']} vs {g['away_abbr']} — Set {s['set_number']}*")
                for r in team_runs[:5]:
                    st.write(f"  {r['length']}-point run (ended rally #{r['ended_at_rally']})")


def _season_rotation_performance(teams):
    """Aggregate rotation data with points for/against."""
    st.subheader("Rotation Performance")

    team_labels = [f"{t['abbreviation']} — {t['name']}" for t in teams]
    sel = st.selectbox("Select team", range(len(team_labels)),
                       format_func=lambda i: team_labels[i], key="rot_team")
    team = teams[sel]

    # Optional game filter
    games = db.get_all_games()
    team_games = [g for g in games
                  if g["home_team_id"] == team["id"] or g["away_team_id"] == team["id"]]
    game_labels = ["All Games"] + [f"{g['home_abbr']} vs {g['away_abbr']} ({g.get('date', '')})"
                                   for g in team_games]
    game_sel = st.selectbox("Game", range(len(game_labels)),
                            format_func=lambda i: game_labels[i], key="rot_game")
    game_id = team_games[game_sel - 1]["id"] if game_sel > 0 else None

    rot_data = db.get_rotation_summary(team["id"], game_id)
    if not rot_data or all(r["rallies"] == 0 for r in rot_data):
        st.info("No rotation data available.")
        return

    df = pd.DataFrame(rot_data)
    df = df[df["rallies"] > 0]
    df["net"] = df["pts_for"] - df["pts_against"]
    df.columns = ["Rotation", "Rallies", "Points For", "Points Against", "Net"]

    st.dataframe(df, use_container_width=True, hide_index=True)

    # Heatmap-style bar chart
    fig, ax = plt.subplots(figsize=(8, 4))
    rots = df["Rotation"].tolist()
    x = range(len(rots))
    ax.bar(x, df["Points For"], color="green", alpha=0.7, label="Points For")
    ax.bar(x, [-v for v in df["Points Against"]], color="red", alpha=0.7, label="Points Against")
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"R{r}" for r in rots])
    ax.set_ylabel("Points")
    ax.set_title(f"Rotation Performance — {team['abbreviation']}")
    ax.legend()
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def _season_head_to_head(teams):
    """Compare two teams across all matchups."""
    st.subheader("Head-to-Head Comparison")

    if len(teams) < 2:
        st.info("Need at least 2 teams for comparison.")
        return

    team_labels = [f"{t['abbreviation']} — {t['name']}" for t in teams]
    c1, c2 = st.columns(2)
    with c1:
        t1_idx = st.selectbox("Team 1", range(len(team_labels)),
                               format_func=lambda i: team_labels[i], key="h2h_t1")
    with c2:
        t2_default = 1 if len(teams) > 1 and t1_idx == 0 else 0
        t2_idx = st.selectbox("Team 2", range(len(team_labels)),
                               format_func=lambda i: team_labels[i],
                               index=t2_default, key="h2h_t2")

    if t1_idx == t2_idx:
        st.warning("Select two different teams.")
        return

    matchups = db.get_head_to_head(teams[t1_idx]["id"], teams[t2_idx]["id"])
    if not matchups:
        st.info("No matchups found between these teams.")
        return

    t1_abbr = teams[t1_idx]["abbreviation"]
    t2_abbr = teams[t2_idx]["abbreviation"]
    t1_wins = 0
    t2_wins = 0

    rows = []
    for m in matchups:
        # Determine winner
        if m["home_sets_won"] > m["away_sets_won"]:
            winner = m["home_abbr"]
        else:
            winner = m["away_abbr"]

        if winner == t1_abbr:
            t1_wins += 1
        elif winner == t2_abbr:
            t2_wins += 1

        sets_str = ", ".join(f"{h}-{a}" for h, a in m["set_scores"])
        rows.append({
            "Date": m["date"],
            "Matchup": f"{m['home_abbr']} vs {m['away_abbr']}",
            "Sets": f"{m['home_sets_won']}-{m['away_sets_won']}",
            "Set Scores": sets_str,
            "Winner": winner,
        })

    c1, c2 = st.columns(2)
    c1.metric(f"{t1_abbr} Wins", t1_wins)
    c2.metric(f"{t2_abbr} Wins", t2_wins)

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _season_leaderboards(seasons):
    """Season stat leaders, filterable by stat."""
    st.subheader("Leaderboards")

    stat_options = {
        "Points": "points",
        "Kills": "kills",
        "Aces": "aces",
        "Digs": "digs",
        "Assists": "assists",
        "Blocks (Solo)": "solo_blocks",
        "Serves": "serves",
        "Receptions": "receptions",
        "Perfect Passes": "perfect_passes",
    }

    c1, c2 = st.columns(2)
    with c1:
        stat_label = st.selectbox("Stat", list(stat_options.keys()), key="lb_stat")
    with c2:
        season_labels = ["All Seasons"] + [s["name"] for s in seasons]
        season_sel = st.selectbox("Season", range(len(season_labels)),
                                  format_func=lambda i: season_labels[i], key="lb_season")

    stat_col = stat_options[stat_label]
    season_id = seasons[season_sel - 1]["id"] if season_sel > 0 else None

    leaders = db.get_season_leaderboard(stat_col, season_id)
    if not leaders:
        st.info("No data available.")
        return

    df = pd.DataFrame(leaders)
    df["hit_pct"] = df.apply(
        lambda r: format_hit_pct(r["kills"], r["attack_errors"], r["attack_attempts"]), axis=1)
    display_cols = ["player_name", "jersey_number", "team_abbr", "position",
                    "total", "sets_played", "points", "hit_pct"]
    available = [c for c in display_cols if c in df.columns]
    display = df[available].copy()
    display.columns = ["Player", "Jersey", "Team", "Pos",
                       stat_label, "Sets", "Points", "Hit %"][:len(available)]

    st.dataframe(display, use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════════════════════
#  Page 6: Teams
# ═════════════════════════════════════════════════════════════════════════════

def page_teams():
    st.header("Teams")

    # Add new team
    with st.expander("Add New Team"):
        with st.form("add_team_form"):
            t_name = st.text_input("Team Name")
            t_abbr = st.text_input("Abbreviation")
            t_conf = st.text_input("Conference")
            t_color = st.text_input("Jersey Color")
            if st.form_submit_button("Create"):
                if t_name:
                    db.create_team(t_name, t_abbr, t_conf, t_color)
                    st.success(f"Created: {t_name}")
                    st.rerun()
                else:
                    st.error("Name required.")

    teams = db.get_all_teams()
    for t in teams:
        w, l = db.get_team_record(t["id"])
        with st.expander(f"{t.get('abbreviation', '')} — {t['name']}  ({w}W-{l}L)"):
            with st.form(f"edit_team_{t['id']}"):
                new_name = st.text_input("Name", value=t["name"])
                new_abbr = st.text_input("Abbreviation", value=t.get("abbreviation", ""))
                new_conf = st.text_input("Conference", value=t.get("conference", ""))
                new_color = st.text_input("Jersey Color", value=t.get("jersey_color", ""))
                if st.form_submit_button("Update"):
                    db.update_team(t["id"], name=new_name, abbreviation=new_abbr,
                                   conference=new_conf, jersey_color=new_color)
                    st.success("Updated!")
                    st.rerun()

            # Players on this team
            players = db.get_players_for_team(t["id"])
            if players:
                st.write(f"**Roster ({len(players)} players)**")
                for p in players:
                    st.write(f"  #{p['jersey_number']} {p['name']} — {p.get('position', '')}")


# ═════════════════════════════════════════════════════════════════════════════
#  Page 6: Players
# ═════════════════════════════════════════════════════════════════════════════

def page_players():
    st.header("Players")

    teams = db.get_all_teams()
    team_names = ["All Teams"] + [f"{t['abbreviation']} — {t['name']}" for t in teams]
    team_filter_idx = st.selectbox("Filter by team", range(len(team_names)),
                                   format_func=lambda i: team_names[i], key="player_team_filter")

    # Add new player
    with st.expander("Add New Player"):
        with st.form("add_player_form"):
            p_team_idx = st.selectbox("Team", range(len(teams)),
                                      format_func=lambda i: f"{teams[i]['abbreviation']} — {teams[i]['name']}")
            p_jersey = st.number_input("Jersey Number", min_value=0, max_value=99, step=1)
            p_name = st.text_input("Name")
            p_pos = st.text_input("Position")
            if st.form_submit_button("Create"):
                db.create_player(teams[p_team_idx]["id"], p_jersey, p_name, p_pos)
                st.success(f"Created: #{p_jersey} {p_name}")
                st.rerun()

    # List players
    if team_filter_idx == 0:
        all_players = []
        for t in teams:
            for p in db.get_players_for_team(t["id"]):
                p["team_name"] = t["name"]
                p["team_abbr"] = t.get("abbreviation", "")
                all_players.append(p)
    else:
        t = teams[team_filter_idx - 1]
        all_players = db.get_players_for_team(t["id"])
        for p in all_players:
            p["team_name"] = t["name"]
            p["team_abbr"] = t.get("abbreviation", "")

    for p in all_players:
        career = db.get_player_career_stats(p["id"])
        kills = career.get("kills", 0)
        ae = career.get("attack_errors", 0)
        aa = career.get("attack_attempts", 0)
        hit_pct = format_hit_pct(kills, ae, aa)
        blocks = career.get("solo_blocks", 0) + career.get("block_assists", 0)
        header = (f"#{p['jersey_number']} {p['name']} — {p.get('team_abbr', '')} "
                  f"| {career.get('sets_played', 0)} sets | "
                  f"{kills} K | {hit_pct} hit% | {career.get('digs', 0)} D | "
                  f"{blocks} B | {career.get('aces', 0)} A")

        with st.expander(header):
            with st.form(f"edit_player_{p['id']}"):
                new_name = st.text_input("Name", value=p.get("name", ""))
                new_pos = st.text_input("Position", value=p.get("position", ""))
                new_notes = st.text_area("Notes", value=p.get("notes", ""))
                if st.form_submit_button("Update"):
                    db.update_player(p["id"], name=new_name, position=new_pos, notes=new_notes)
                    st.success("Updated!")
                    st.rerun()

            # Career stats table
            if career and career.get("sets_played", 0) > 0:
                st.write("**Career Stats**")
                career_display = {
                    "Sets": career["sets_played"],
                    "Kills": kills, "Hit %": hit_pct,
                    "Aces": career.get("aces", 0),
                    "Blocks": blocks,
                    "Digs": career.get("digs", 0),
                    "Assists": career.get("assists", 0),
                    "Points": career.get("points", 0),
                }
                st.dataframe(pd.DataFrame([career_display]), use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════════════════════
#  Page 7: Export
# ═════════════════════════════════════════════════════════════════════════════

def page_export():
    st.header("Export Data")

    export_type = st.selectbox("Export Type", [
        "Game Stats", "Rally Log", "Player Career Stats", "Team Records", "All Data"
    ])

    fmt = st.radio("Format", ["Excel (.xlsx)", "CSV (.csv)"], horizontal=True)
    use_excel = fmt.startswith("Excel")

    games = db.get_all_games()
    teams = db.get_all_teams()

    if export_type == "Game Stats":
        if not games:
            st.info("No games to export.")
            return
        game_labels = [f"{g['home_abbr']} vs {g['away_abbr']} ({g.get('date', '')})" for g in games]
        sel = st.selectbox("Select game", range(len(game_labels)), format_func=lambda i: game_labels[i])
        game_id = games[sel]["id"]
        df = db.game_stats_to_dataframe(game_id)
        _offer_download(df, f"game_stats_{game_id}", use_excel)

    elif export_type == "Rally Log":
        if not games:
            st.info("No games.")
            return
        game_labels = [f"{g['home_abbr']} vs {g['away_abbr']} ({g.get('date', '')})" for g in games]
        sel = st.selectbox("Select game", range(len(game_labels)), format_func=lambda i: game_labels[i])
        game_id = games[sel]["id"]
        df = db.rally_log_to_dataframe(game_id)
        _offer_download(df, f"rally_log_{game_id}", use_excel)

    elif export_type == "Player Career Stats":
        rows = []
        for t in teams:
            for p in db.get_players_for_team(t["id"]):
                career = db.get_player_career_stats(p["id"])
                career["player_name"] = p["name"]
                career["jersey_number"] = p["jersey_number"]
                career["team"] = t.get("abbreviation", t["name"])
                career["position"] = p.get("position", "")
                rows.append(career)
        df = pd.DataFrame(rows)
        if not df.empty:
            cols = ["team", "jersey_number", "player_name", "position"] + [
                c for c in df.columns if c not in ("team", "jersey_number", "player_name", "position")]
            df = df[cols]
        _offer_download(df, "player_career_stats", use_excel)

    elif export_type == "Team Records":
        rows = []
        for t in teams:
            w, l = db.get_team_record(t["id"])
            rows.append({"Team": t["name"], "Abbreviation": t.get("abbreviation", ""),
                         "Conference": t.get("conference", ""), "Wins": w, "Losses": l})
        _offer_download(pd.DataFrame(rows), "team_records", use_excel)

    elif export_type == "All Data":
        # Multi-sheet Excel or multiple CSV downloads
        if use_excel:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                for g in games:
                    gdf = db.game_stats_to_dataframe(g["id"])
                    if not gdf.empty:
                        sheet = f"Game {g['id']} Stats"[:31]
                        gdf.to_excel(writer, sheet_name=sheet, index=False)
                    rdf = db.rally_log_to_dataframe(g["id"])
                    if not rdf.empty:
                        sheet = f"Game {g['id']} Rallies"[:31]
                        rdf.to_excel(writer, sheet_name=sheet, index=False)
            buf.seek(0)
            st.download_button("Download All Data (Excel)", buf, "all_data.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("For CSV, select a specific export type above.")


def _offer_download(df, filename, use_excel):
    """Show a preview and download button."""
    if df is None or df.empty:
        st.info("No data to export.")
        return

    st.dataframe(df.head(20), use_container_width=True, hide_index=True)
    st.caption(f"{len(df)} total rows")

    if use_excel:
        buf = io.BytesIO()
        df.to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        st.download_button("Download Excel", buf, f"{filename}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        csv = df.to_csv(index=False)
        st.download_button("Download CSV", csv, f"{filename}.csv", "text/csv")


# ═════════════════════════════════════════════════════════════════════════════
#  Page router
# ═════════════════════════════════════════════════════════════════════════════

PAGE_MAP = {
    "Dashboard": page_dashboard,
    "New Game": page_new_game,
    "Games": page_games,
    "Game Detail": page_game_detail,
    "Season Analytics": page_season_analytics,
    "Teams": page_teams,
    "Players": page_players,
    "Export": page_export,
}

PAGE_MAP.get(current_page, page_dashboard)()
