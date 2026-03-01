"""SQLite database for volleyball analytics platform.

Schema: teams, players, seasons, games, sets, rallies, player_set_stats.
Seeds initial UKC vs USTA Set 1 data from generate_excel.py on first run.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

import pandas as pd

DB_PATH = Path(__file__).parent / "volleyball.db"


@contextmanager
def get_connection():
    """Yield a SQLite connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                abbreviation TEXT,
                conference TEXT,
                jersey_color TEXT,
                sport TEXT DEFAULT 'volleyball'
            );

            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL REFERENCES teams(id),
                name TEXT,
                jersey_number INTEGER NOT NULL,
                position TEXT,
                notes TEXT,
                UNIQUE(team_id, jersey_number)
            );

            CREATE TABLE IF NOT EXISTS seasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sport TEXT DEFAULT 'volleyball',
                year INTEGER
            );

            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER REFERENCES seasons(id),
                home_team_id INTEGER NOT NULL REFERENCES teams(id),
                away_team_id INTEGER NOT NULL REFERENCES teams(id),
                date TEXT,
                venue TEXT,
                video_url TEXT,
                video_path TEXT,
                status TEXT DEFAULT 'completed',
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL REFERENCES games(id),
                set_number INTEGER NOT NULL,
                home_score INTEGER DEFAULT 0,
                away_score INTEGER DEFAULT 0,
                UNIQUE(game_id, set_number)
            );

            CREATE TABLE IF NOT EXISTS rallies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                set_id INTEGER NOT NULL REFERENCES sets(id),
                rally_number INTEGER NOT NULL,
                video_time TEXT,
                score_before TEXT,
                score_after TEXT,
                scoring_team TEXT,
                play_type TEXT,
                key_player TEXT,
                serving_team TEXT,
                home_rotation INTEGER,
                away_rotation INTEGER,
                is_sideout INTEGER DEFAULT 0,
                confidence TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS player_set_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL REFERENCES players(id),
                set_id INTEGER NOT NULL REFERENCES sets(id),
                serves INTEGER DEFAULT 0,
                aces INTEGER DEFAULT 0,
                service_errors INTEGER DEFAULT 0,
                kills INTEGER DEFAULT 0,
                attack_errors INTEGER DEFAULT 0,
                attack_attempts INTEGER DEFAULT 0,
                solo_blocks INTEGER DEFAULT 0,
                block_assists INTEGER DEFAULT 0,
                block_errors INTEGER DEFAULT 0,
                digs INTEGER DEFAULT 0,
                dig_errors INTEGER DEFAULT 0,
                receptions INTEGER DEFAULT 0,
                reception_errors INTEGER DEFAULT 0,
                perfect_passes INTEGER DEFAULT 0,
                assists INTEGER DEFAULT 0,
                ball_handling_errors INTEGER DEFAULT 0,
                points INTEGER DEFAULT 0,
                confidence TEXT,
                UNIQUE(player_id, set_id)
            );

            CREATE TABLE IF NOT EXISTS player_detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rally_id INTEGER REFERENCES rallies(id),
                frame_timestamp REAL,
                zone TEXT,
                team TEXT,
                jersey_number INTEGER,
                confidence REAL,
                role TEXT
            );
        """)
        # Schema migration: add clip_path column to rallies if missing
        cols = [row[1] for row in conn.execute("PRAGMA table_info(rallies)").fetchall()]
        if "clip_path" not in cols:
            conn.execute("ALTER TABLE rallies ADD COLUMN clip_path TEXT")

        # Schema migration: add track_id column to player_detections if missing
        det_cols = [row[1] for row in conn.execute("PRAGMA table_info(player_detections)").fetchall()]
        if "track_id" not in det_cols:
            conn.execute("ALTER TABLE player_detections ADD COLUMN track_id INTEGER")
    if is_db_empty():
        seed_initial_data()


def is_db_empty():
    """Return True if there are no teams in the database."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM teams").fetchone()
        return row[0] == 0


# ─── Seed ────────────────────────────────────────────────────────────────────

def seed_initial_data():
    """Import UKC vs USTA Set 1 data from generate_excel.py dicts."""
    from generate_excel import usta_players, ukc_players, rally_data, compute_rotations

    with get_connection() as conn:
        # Season
        conn.execute(
            "INSERT INTO seasons (name, sport, year) VALUES (?, ?, ?)",
            ("ACAA 2025-26", "volleyball", 2026),
        )
        season_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Teams
        conn.execute(
            "INSERT INTO teams (name, abbreviation, conference, jersey_color, sport) VALUES (?, ?, ?, ?, ?)",
            ("Sainte-Anne Dragons", "USTA", "ACAA", "Dark navy", "volleyball"),
        )
        usta_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            "INSERT INTO teams (name, abbreviation, conference, jersey_color, sport) VALUES (?, ?, ?, ?, ?)",
            ("King's College", "UKC", "ACAA", "White w/ blue", "volleyball"),
        )
        ukc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Game (USTA is home)
        conn.execute(
            """INSERT INTO games (season_id, home_team_id, away_team_id, date, venue,
               video_url, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (season_id, usta_id, ukc_id, "2026-01-25",
             "Université Sainte-Anne, Repaire des Dragons",
             "https://www.youtube.com/watch?v=example", "completed",
             "Set 1 analyzed. UKC wins 25-17."),
        )
        game_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Set 1
        conn.execute(
            "INSERT INTO sets (game_id, set_number, home_score, away_score) VALUES (?, ?, ?, ?)",
            (game_id, 1, 17, 25),
        )
        set_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Players + stats — USTA
        for jersey, pdata in usta_players.items():
            conn.execute(
                "INSERT INTO players (team_id, name, jersey_number, position, notes) VALUES (?, ?, ?, ?, ?)",
                (usta_id, f"USTA #{jersey}", jersey, pdata["position"], pdata.get("confidence", "")),
            )
            player_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                """INSERT INTO player_set_stats
                   (player_id, set_id, serves, aces, service_errors, kills, attack_errors,
                    attack_attempts, solo_blocks, digs, receptions, assists, points, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (player_id, set_id, pdata["serves"], pdata["aces"], pdata["svc_err"],
                 pdata["kills"], pdata["atk_err"], pdata["atk_att"],
                 pdata["blocks"], pdata["digs"], pdata["receptions"], pdata["assists"],
                 pdata["total_points"], pdata["confidence"]),
            )

        # Players + stats — UKC
        for jersey, pdata in ukc_players.items():
            conn.execute(
                "INSERT INTO players (team_id, name, jersey_number, position, notes) VALUES (?, ?, ?, ?, ?)",
                (ukc_id, f"UKC #{jersey}", jersey, pdata["position"], pdata.get("confidence", "")),
            )
            player_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                """INSERT INTO player_set_stats
                   (player_id, set_id, serves, aces, service_errors, kills, attack_errors,
                    attack_attempts, solo_blocks, digs, receptions, assists, points, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (player_id, set_id, pdata["serves"], pdata["aces"], pdata["svc_err"],
                 pdata["kills"], pdata["atk_err"], pdata["atk_att"],
                 pdata["blocks"], pdata["digs"], pdata["receptions"], pdata["assists"],
                 pdata["total_points"], pdata["confidence"]),
            )

        # Rallies (from rotation data which includes serving/rotation info)
        rotation_data = compute_rotations(rally_data)
        for rd in rotation_data:
            # Map scoring_team name to home/away label
            scoring_label = rd["scoring_team"]  # "UKC" or "USTA"
            serving_label = rd["serving_team"]
            conn.execute(
                """INSERT INTO rallies
                   (set_id, rally_number, video_time, score_before, score_after,
                    scoring_team, play_type, key_player, serving_team,
                    home_rotation, away_rotation, is_sideout, confidence, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (set_id, rd["rally_num"], rd["time"], rd["score_before"], rd["score_after"],
                 scoring_label, "Kill/Rally", rd["key_player"], serving_label,
                 rd["usta_rotation"], rd["ukc_rotation"], int(rd["is_sideout"]),
                 "H", rd["notes"]),
            )


# ─── Teams ───────────────────────────────────────────────────────────────────

def get_all_teams():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM teams ORDER BY name").fetchall()]


def get_team(team_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        return dict(row) if row else None


def create_team(name, abbreviation="", conference="", jersey_color="", sport="volleyball"):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO teams (name, abbreviation, conference, jersey_color, sport) VALUES (?, ?, ?, ?, ?)",
            (name, abbreviation, conference, jersey_color, sport),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_team(team_id, **kwargs):
    allowed = {"name", "abbreviation", "conference", "jersey_color", "sport"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [team_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE teams SET {set_clause} WHERE id = ?", values)


def get_team_record(team_id):
    """Return (wins, losses) for a team across all completed games."""
    with get_connection() as conn:
        games = conn.execute(
            """SELECT g.id, g.home_team_id, g.away_team_id FROM games g
               WHERE (g.home_team_id = ? OR g.away_team_id = ?) AND g.status = 'completed'""",
            (team_id, team_id),
        ).fetchall()
        wins = 0
        losses = 0
        for g in games:
            sets = conn.execute(
                "SELECT home_score, away_score FROM sets WHERE game_id = ?", (g["id"],)
            ).fetchall()
            home_sets_won = sum(1 for s in sets if s["home_score"] > s["away_score"])
            away_sets_won = sum(1 for s in sets if s["away_score"] > s["home_score"])
            if g["home_team_id"] == team_id:
                if home_sets_won > away_sets_won:
                    wins += 1
                else:
                    losses += 1
            else:
                if away_sets_won > home_sets_won:
                    wins += 1
                else:
                    losses += 1
        return wins, losses


# ─── Players ─────────────────────────────────────────────────────────────────

def get_players_for_team(team_id):
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM players WHERE team_id = ? ORDER BY jersey_number", (team_id,)
        ).fetchall()]


def get_player(player_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
        return dict(row) if row else None


def create_player(team_id, jersey_number, name="", position="", notes=""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO players (team_id, name, jersey_number, position, notes) VALUES (?, ?, ?, ?, ?)",
            (team_id, name, jersey_number, position, notes),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_player(player_id, **kwargs):
    allowed = {"name", "jersey_number", "position", "notes"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [player_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE players SET {set_clause} WHERE id = ?", values)


def get_or_create_player(team_id, jersey_number, name="", position=""):
    """Find player by team + jersey; create if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM players WHERE team_id = ? AND jersey_number = ?",
            (team_id, jersey_number),
        ).fetchone()
        if row:
            return row[0]
    return create_player(team_id, jersey_number, name, position)


def get_player_career_stats(player_id):
    """Aggregate all set stats for a player across their career."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                COUNT(DISTINCT pss.set_id) as sets_played,
                COALESCE(SUM(pss.serves), 0) as serves,
                COALESCE(SUM(pss.aces), 0) as aces,
                COALESCE(SUM(pss.service_errors), 0) as service_errors,
                COALESCE(SUM(pss.kills), 0) as kills,
                COALESCE(SUM(pss.attack_errors), 0) as attack_errors,
                COALESCE(SUM(pss.attack_attempts), 0) as attack_attempts,
                COALESCE(SUM(pss.solo_blocks), 0) as solo_blocks,
                COALESCE(SUM(pss.block_assists), 0) as block_assists,
                COALESCE(SUM(pss.block_errors), 0) as block_errors,
                COALESCE(SUM(pss.digs), 0) as digs,
                COALESCE(SUM(pss.dig_errors), 0) as dig_errors,
                COALESCE(SUM(pss.receptions), 0) as receptions,
                COALESCE(SUM(pss.reception_errors), 0) as reception_errors,
                COALESCE(SUM(pss.perfect_passes), 0) as perfect_passes,
                COALESCE(SUM(pss.assists), 0) as assists,
                COALESCE(SUM(pss.ball_handling_errors), 0) as ball_handling_errors,
                COALESCE(SUM(pss.points), 0) as points
            FROM player_set_stats pss
            WHERE pss.player_id = ?
        """, (player_id,)).fetchone()
        return dict(row) if row else {}


# ─── Seasons ─────────────────────────────────────────────────────────────────

def get_all_seasons():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM seasons ORDER BY year DESC, name").fetchall()]


def create_season(name, sport="volleyball", year=None):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO seasons (name, sport, year) VALUES (?, ?, ?)",
            (name, sport, year),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ─── Games ───────────────────────────────────────────────────────────────────

def get_all_games():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT g.*, ht.name as home_team_name, ht.abbreviation as home_abbr,
                   at.name as away_team_name, at.abbreviation as away_abbr,
                   s.name as season_name
            FROM games g
            JOIN teams ht ON g.home_team_id = ht.id
            JOIN teams at ON g.away_team_id = at.id
            LEFT JOIN seasons s ON g.season_id = s.id
            ORDER BY g.date DESC
        """).fetchall()]


def get_game(game_id):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT g.*, ht.name as home_team_name, ht.abbreviation as home_abbr,
                   at.name as away_team_name, at.abbreviation as away_abbr,
                   s.name as season_name
            FROM games g
            JOIN teams ht ON g.home_team_id = ht.id
            JOIN teams at ON g.away_team_id = at.id
            LEFT JOIN seasons s ON g.season_id = s.id
            WHERE g.id = ?
        """, (game_id,)).fetchone()
        return dict(row) if row else None


def create_game(season_id, home_team_id, away_team_id, date="", venue="",
                video_url="", video_path="", status="pending", notes=""):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO games (season_id, home_team_id, away_team_id, date, venue,
               video_url, video_path, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (season_id, home_team_id, away_team_id, date, venue, video_url, video_path, status, notes),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_game(game_id, **kwargs):
    allowed = {"season_id", "home_team_id", "away_team_id", "date", "venue",
               "video_url", "video_path", "status", "notes"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [game_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE games SET {set_clause} WHERE id = ?", values)


# ─── Sets ────────────────────────────────────────────────────────────────────

def get_sets_for_game(game_id):
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM sets WHERE game_id = ? ORDER BY set_number", (game_id,)
        ).fetchall()]


def create_set(game_id, set_number, home_score=0, away_score=0):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sets (game_id, set_number, home_score, away_score) VALUES (?, ?, ?, ?)",
            (game_id, set_number, home_score, away_score),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_set(set_id, **kwargs):
    allowed = {"set_number", "home_score", "away_score"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [set_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE sets SET {set_clause} WHERE id = ?", values)


# ─── Rallies ─────────────────────────────────────────────────────────────────

def get_rallies_for_set(set_id):
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM rallies WHERE set_id = ? ORDER BY rally_number", (set_id,)
        ).fetchall()]


def upsert_rally(set_id, rally_number, **kwargs):
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM rallies WHERE set_id = ? AND rally_number = ?",
            (set_id, rally_number),
        ).fetchone()
        if existing:
            update_rally(existing[0], **kwargs)
            return existing[0]
        cols = ["set_id", "rally_number"] + list(kwargs.keys())
        vals = [set_id, rally_number] + list(kwargs.values())
        placeholders = ", ".join("?" for _ in vals)
        col_names = ", ".join(cols)
        conn.execute(f"INSERT INTO rallies ({col_names}) VALUES ({placeholders})", vals)
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_rally(rally_id, **kwargs):
    allowed = {"rally_number", "video_time", "score_before", "score_after",
               "scoring_team", "play_type", "key_player", "serving_team",
               "home_rotation", "away_rotation", "is_sideout", "confidence", "notes",
               "clip_path"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [rally_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE rallies SET {set_clause} WHERE id = ?", values)


def delete_rally(rally_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM rallies WHERE id = ?", (rally_id,))


# ─── Player Set Stats ───────────────────────────────────────────────────────

def get_stats_for_set(set_id):
    """Get all player stats for a given set, joined with player info."""
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT pss.*, p.name as player_name, p.jersey_number, p.position, p.team_id,
                   t.name as team_name, t.abbreviation as team_abbr
            FROM player_set_stats pss
            JOIN players p ON pss.player_id = p.id
            JOIN teams t ON p.team_id = t.id
            WHERE pss.set_id = ?
            ORDER BY t.name, p.jersey_number
        """, (set_id,)).fetchall()]


def get_stats_for_game(game_id):
    """Get aggregated player stats across all sets in a game."""
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT p.id as player_id, p.name as player_name, p.jersey_number, p.position,
                   p.team_id, t.name as team_name, t.abbreviation as team_abbr,
                   COUNT(DISTINCT pss.set_id) as sets_played,
                   COALESCE(SUM(pss.serves), 0) as serves,
                   COALESCE(SUM(pss.aces), 0) as aces,
                   COALESCE(SUM(pss.service_errors), 0) as service_errors,
                   COALESCE(SUM(pss.kills), 0) as kills,
                   COALESCE(SUM(pss.attack_errors), 0) as attack_errors,
                   COALESCE(SUM(pss.attack_attempts), 0) as attack_attempts,
                   COALESCE(SUM(pss.solo_blocks), 0) as solo_blocks,
                   COALESCE(SUM(pss.block_assists), 0) as block_assists,
                   COALESCE(SUM(pss.block_errors), 0) as block_errors,
                   COALESCE(SUM(pss.digs), 0) as digs,
                   COALESCE(SUM(pss.dig_errors), 0) as dig_errors,
                   COALESCE(SUM(pss.receptions), 0) as receptions,
                   COALESCE(SUM(pss.reception_errors), 0) as reception_errors,
                   COALESCE(SUM(pss.perfect_passes), 0) as perfect_passes,
                   COALESCE(SUM(pss.assists), 0) as assists,
                   COALESCE(SUM(pss.ball_handling_errors), 0) as ball_handling_errors,
                   COALESCE(SUM(pss.points), 0) as points
            FROM player_set_stats pss
            JOIN players p ON pss.player_id = p.id
            JOIN teams t ON p.team_id = t.id
            JOIN sets s ON pss.set_id = s.id
            WHERE s.game_id = ?
            GROUP BY p.id
            ORDER BY t.name, p.jersey_number
        """, (game_id,)).fetchall()]


def upsert_player_set_stats(player_id, set_id, **kwargs):
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM player_set_stats WHERE player_id = ? AND set_id = ?",
            (player_id, set_id),
        ).fetchone()
        if existing:
            update_player_set_stats(existing[0], **kwargs)
            return existing[0]
        cols = ["player_id", "set_id"] + list(kwargs.keys())
        vals = [player_id, set_id] + list(kwargs.values())
        placeholders = ", ".join("?" for _ in vals)
        col_names = ", ".join(cols)
        conn.execute(f"INSERT INTO player_set_stats ({col_names}) VALUES ({placeholders})", vals)
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_player_set_stats(stat_id, **kwargs):
    allowed = {"serves", "aces", "service_errors", "kills", "attack_errors",
               "attack_attempts", "solo_blocks", "block_assists", "block_errors",
               "digs", "dig_errors", "receptions", "reception_errors", "perfect_passes",
               "assists", "ball_handling_errors", "points", "confidence"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [stat_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE player_set_stats SET {set_clause} WHERE id = ?", values)


# ─── Export helpers ──────────────────────────────────────────────────────────

def game_stats_to_dataframe(game_id):
    """Return a DataFrame of player stats for a game."""
    stats = get_stats_for_game(game_id)
    if not stats:
        return pd.DataFrame()
    df = pd.DataFrame(stats)
    # Compute hitting percentage
    df["hit_pct"] = df.apply(
        lambda r: (r["kills"] - r["attack_errors"]) / r["attack_attempts"]
        if r["attack_attempts"] > 0 else 0.0, axis=1
    )
    df["total_blocks"] = df["solo_blocks"] + df["block_assists"]
    return df


def rally_log_to_dataframe(game_id):
    """Return a DataFrame of all rallies for a game across all sets."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT r.*, s.set_number
            FROM rallies r
            JOIN sets s ON r.set_id = s.id
            WHERE s.game_id = ?
            ORDER BY s.set_number, r.rally_number
        """, (game_id,)).fetchall()
        return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


# ─── Season Analytics queries (Feature 4) ──────────────────────────────────

def get_player_stats_by_set(player_id):
    """Per-set stats with game context for trend analysis."""
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT pss.*, s.set_number, s.game_id,
                   g.date, ht.abbreviation as home_abbr, at.abbreviation as away_abbr
            FROM player_set_stats pss
            JOIN sets s ON pss.set_id = s.id
            JOIN games g ON s.game_id = g.id
            JOIN teams ht ON g.home_team_id = ht.id
            JOIN teams at ON g.away_team_id = at.id
            WHERE pss.player_id = ?
            ORDER BY g.date, s.set_number
        """, (player_id,)).fetchall()]


def get_player_stats_by_game(player_id):
    """Aggregated per-game stats for a player."""
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT g.id as game_id, g.date,
                   ht.abbreviation as home_abbr, at.abbreviation as away_abbr,
                   COUNT(DISTINCT pss.set_id) as sets_played,
                   COALESCE(SUM(pss.kills), 0) as kills,
                   COALESCE(SUM(pss.attack_errors), 0) as attack_errors,
                   COALESCE(SUM(pss.attack_attempts), 0) as attack_attempts,
                   COALESCE(SUM(pss.aces), 0) as aces,
                   COALESCE(SUM(pss.service_errors), 0) as service_errors,
                   COALESCE(SUM(pss.digs), 0) as digs,
                   COALESCE(SUM(pss.solo_blocks), 0) as solo_blocks,
                   COALESCE(SUM(pss.block_assists), 0) as block_assists,
                   COALESCE(SUM(pss.assists), 0) as assists,
                   COALESCE(SUM(pss.points), 0) as points,
                   COALESCE(SUM(pss.serves), 0) as serves,
                   COALESCE(SUM(pss.receptions), 0) as receptions,
                   COALESCE(SUM(pss.reception_errors), 0) as reception_errors,
                   COALESCE(SUM(pss.perfect_passes), 0) as perfect_passes
            FROM player_set_stats pss
            JOIN sets s ON pss.set_id = s.id
            JOIN games g ON s.game_id = g.id
            JOIN teams ht ON g.home_team_id = ht.id
            JOIN teams at ON g.away_team_id = at.id
            WHERE pss.player_id = ?
            GROUP BY g.id
            ORDER BY g.date
        """, (player_id,)).fetchall()]


def get_team_stats_by_game(team_id):
    """Team-level aggregated stats per game."""
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT g.id as game_id, g.date,
                   ht.abbreviation as home_abbr, at.abbreviation as away_abbr,
                   COALESCE(SUM(pss.kills), 0) as kills,
                   COALESCE(SUM(pss.attack_errors), 0) as attack_errors,
                   COALESCE(SUM(pss.attack_attempts), 0) as attack_attempts,
                   COALESCE(SUM(pss.aces), 0) as aces,
                   COALESCE(SUM(pss.service_errors), 0) as service_errors,
                   COALESCE(SUM(pss.digs), 0) as digs,
                   COALESCE(SUM(pss.solo_blocks), 0) as solo_blocks,
                   COALESCE(SUM(pss.block_assists), 0) as block_assists,
                   COALESCE(SUM(pss.assists), 0) as assists,
                   COALESCE(SUM(pss.points), 0) as points
            FROM player_set_stats pss
            JOIN players p ON pss.player_id = p.id
            JOIN sets s ON pss.set_id = s.id
            JOIN games g ON s.game_id = g.id
            JOIN teams ht ON g.home_team_id = ht.id
            JOIN teams at ON g.away_team_id = at.id
            WHERE p.team_id = ?
            GROUP BY g.id
            ORDER BY g.date
        """, (team_id,)).fetchall()]


def get_team_sideout_pct(team_id, game_id=None):
    """Side-out percentage from rally is_sideout data.

    Returns dict with total_receiving_rallies and sideout_won.
    """
    with get_connection() as conn:
        teams = conn.execute("SELECT abbreviation FROM teams WHERE id = ?", (team_id,)).fetchone()
        if not teams:
            return {"total": 0, "won": 0, "pct": 0.0}
        abbr = teams[0]

        game_filter = "AND s.game_id = ?" if game_id else ""
        params = [abbr] + ([game_id] if game_id else [])

        # Receiving rallies = rallies where the team is NOT serving
        rows = conn.execute(f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN r.scoring_team = ? THEN 1 ELSE 0 END) as won
            FROM rallies r
            JOIN sets s ON r.set_id = s.id
            WHERE r.serving_team != ?
            {game_filter}
        """, [abbr] + params).fetchone()

        total = rows[0] or 0
        won = rows[1] or 0
        return {"total": total, "won": won, "pct": (won / total * 100) if total > 0 else 0.0}


def get_rotation_summary(team_id, game_id=None):
    """Points for/against per rotation for a team."""
    with get_connection() as conn:
        team = conn.execute("SELECT abbreviation FROM teams WHERE id = ?", (team_id,)).fetchone()
        if not team:
            return []
        abbr = team[0]

        # Determine if home or away
        if game_id:
            g = conn.execute("SELECT home_team_id FROM games WHERE id = ?", (game_id,)).fetchone()
            is_home = g and g[0] == team_id
        else:
            is_home = True  # default

        rot_key = "home_rotation" if is_home else "away_rotation"

        game_filter = "AND s.game_id = ?" if game_id else ""
        params = [game_id] if game_id else []

        results = []
        for rot in range(1, 7):
            row = conn.execute(f"""
                SELECT COUNT(*) as rallies,
                       SUM(CASE WHEN r.scoring_team = ? THEN 1 ELSE 0 END) as pts_for,
                       SUM(CASE WHEN r.scoring_team != ? THEN 1 ELSE 0 END) as pts_against
                FROM rallies r
                JOIN sets s ON r.set_id = s.id
                WHERE r.{rot_key} = ?
                {game_filter}
            """, [abbr, abbr, rot] + params).fetchone()
            results.append({
                "rotation": rot,
                "rallies": row[0] or 0,
                "pts_for": row[1] or 0,
                "pts_against": row[2] or 0,
            })
        return results


def get_scoring_runs(set_id):
    """Consecutive points by the same team in a set."""
    rallies = get_rallies_for_set(set_id)
    if not rallies:
        return []

    runs = []
    current_team = None
    current_run = 0

    for r in rallies:
        team = r.get("scoring_team", "")
        if team == current_team:
            current_run += 1
        else:
            if current_team and current_run > 1:
                runs.append({"team": current_team, "length": current_run,
                             "ended_at_rally": r["rally_number"] - 1})
            current_team = team
            current_run = 1

    # Final run
    if current_team and current_run > 1:
        runs.append({"team": current_team, "length": current_run,
                     "ended_at_rally": rallies[-1]["rally_number"]})

    return sorted(runs, key=lambda x: x["length"], reverse=True)


def get_season_leaderboard(stat, season_id=None, limit=20):
    """Top players for any stat column, optionally filtered by season."""
    valid_stats = {"kills", "aces", "digs", "solo_blocks", "block_assists",
                   "assists", "points", "serves", "receptions", "perfect_passes",
                   "attack_attempts", "attack_errors", "service_errors"}
    if stat not in valid_stats:
        return []

    with get_connection() as conn:
        season_filter = "AND g.season_id = ?" if season_id else ""
        params = [season_id] if season_id else []

        return [dict(r) for r in conn.execute(f"""
            SELECT p.id as player_id, p.name as player_name,
                   p.jersey_number, p.position,
                   t.name as team_name, t.abbreviation as team_abbr,
                   COALESCE(SUM(pss.{stat}), 0) as total,
                   COUNT(DISTINCT pss.set_id) as sets_played,
                   COALESCE(SUM(pss.kills), 0) as kills,
                   COALESCE(SUM(pss.attack_errors), 0) as attack_errors,
                   COALESCE(SUM(pss.attack_attempts), 0) as attack_attempts,
                   COALESCE(SUM(pss.points), 0) as points
            FROM player_set_stats pss
            JOIN players p ON pss.player_id = p.id
            JOIN teams t ON p.team_id = t.id
            JOIN sets s ON pss.set_id = s.id
            JOIN games g ON s.game_id = g.id
            WHERE 1=1 {season_filter}
            GROUP BY p.id
            HAVING total > 0
            ORDER BY total DESC
            LIMIT ?
        """, params + [limit]).fetchall()]


def get_head_to_head(team1_id, team2_id):
    """Matchup history between two teams."""
    with get_connection() as conn:
        games = conn.execute("""
            SELECT g.id, g.date, g.venue,
                   ht.abbreviation as home_abbr, at.abbreviation as away_abbr,
                   g.home_team_id, g.away_team_id
            FROM games g
            JOIN teams ht ON g.home_team_id = ht.id
            JOIN teams at ON g.away_team_id = at.id
            WHERE (g.home_team_id = ? AND g.away_team_id = ?)
               OR (g.home_team_id = ? AND g.away_team_id = ?)
            ORDER BY g.date
        """, (team1_id, team2_id, team2_id, team1_id)).fetchall()

        results = []
        for g in games:
            sets = conn.execute(
                "SELECT home_score, away_score FROM sets WHERE game_id = ? ORDER BY set_number",
                (g["id"],)
            ).fetchall()
            home_sets = sum(1 for s in sets if s["home_score"] > s["away_score"])
            away_sets = sum(1 for s in sets if s["away_score"] > s["home_score"])
            results.append({
                "game_id": g["id"],
                "date": g["date"],
                "venue": g["venue"],
                "home_abbr": g["home_abbr"],
                "away_abbr": g["away_abbr"],
                "home_sets_won": home_sets,
                "away_sets_won": away_sets,
                "set_scores": [(s["home_score"], s["away_score"]) for s in sets],
            })
        return results


# ─── Feature 2 & 3 queries ─────────────────────────────────────────────────

def get_unclassified_rallies(game_id):
    """Rallies with generic play_type (for classification)."""
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT r.*, s.set_number
            FROM rallies r
            JOIN sets s ON r.set_id = s.id
            WHERE s.game_id = ?
              AND (r.play_type IS NULL OR r.play_type = '' OR r.play_type = 'Kill/Rally'
                   OR r.play_type = 'Rally')
            ORDER BY s.set_number, r.rally_number
        """, (game_id,)).fetchall()]


def get_rallies_without_players(game_id):
    """Rallies with no key_player assigned."""
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT r.*, s.set_number
            FROM rallies r
            JOIN sets s ON r.set_id = s.id
            WHERE s.game_id = ?
              AND (r.key_player IS NULL OR r.key_player = '')
            ORDER BY s.set_number, r.rally_number
        """, (game_id,)).fetchall()]


# ─── Player Detections (Feature 2) ─────────────────────────────────────────

def insert_player_detection(rally_id, frame_timestamp, zone, team,
                            jersey_number, confidence, role="", track_id=None):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO player_detections
            (rally_id, frame_timestamp, zone, team, jersey_number, confidence, role, track_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (rally_id, frame_timestamp, zone, team, jersey_number, confidence, role, track_id))


def get_detections_for_rally(rally_id):
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM player_detections WHERE rally_id = ? ORDER BY frame_timestamp",
            (rally_id,)
        ).fetchall()]


def clear_detections_for_game(game_id):
    """Delete all player_detections for rallies in a game (for re-detection)."""
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM player_detections
            WHERE rally_id IN (
                SELECT r.id FROM rallies r
                JOIN sets s ON r.set_id = s.id
                WHERE s.game_id = ?
            )
        """, (game_id,))


def delete_game(game_id):
    """Cascade delete a game and all associated data (detections, rallies, stats, sets)."""
    with get_connection() as conn:
        # Get all set IDs for this game
        set_ids = [r[0] for r in conn.execute(
            "SELECT id FROM sets WHERE game_id = ?", (game_id,)
        ).fetchall()]

        if set_ids:
            placeholders = ", ".join("?" for _ in set_ids)

            # 1. Delete player_detections (via rallies -> sets)
            conn.execute(f"""
                DELETE FROM player_detections
                WHERE rally_id IN (
                    SELECT id FROM rallies WHERE set_id IN ({placeholders})
                )
            """, set_ids)

            # 2. Delete rallies
            conn.execute(
                f"DELETE FROM rallies WHERE set_id IN ({placeholders})", set_ids
            )

            # 3. Delete player_set_stats
            conn.execute(
                f"DELETE FROM player_set_stats WHERE set_id IN ({placeholders})", set_ids
            )

        # 4. Delete sets
        conn.execute("DELETE FROM sets WHERE game_id = ?", (game_id,))

        # 5. Delete game
        conn.execute("DELETE FROM games WHERE id = ?", (game_id,))


def delete_team(team_id):
    """Cascade delete a team: all games it played in, its players, and the team itself."""
    with get_connection() as conn:
        # Find all games this team played in (home or away)
        game_ids = [r[0] for r in conn.execute(
            "SELECT id FROM games WHERE home_team_id = ? OR away_team_id = ?",
            (team_id, team_id),
        ).fetchall()]

    # Delete each game with full cascade
    for gid in game_ids:
        delete_game(gid)

    with get_connection() as conn:
        # Get player IDs for this team
        player_ids = [r[0] for r in conn.execute(
            "SELECT id FROM players WHERE team_id = ?", (team_id,)
        ).fetchall()]

        # Delete any remaining player_set_stats for these players
        if player_ids:
            placeholders = ", ".join("?" for _ in player_ids)
            conn.execute(
                f"DELETE FROM player_set_stats WHERE player_id IN ({placeholders})",
                player_ids,
            )

        # Delete players
        conn.execute("DELETE FROM players WHERE team_id = ?", (team_id,))

        # Delete team
        conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))


def get_all_players_list():
    """Return all players with team info."""
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT p.*, t.name as team_name, t.abbreviation as team_abbr
            FROM players p
            JOIN teams t ON p.team_id = t.id
            ORDER BY t.name, p.jersey_number
        """).fetchall()]


def get_rallies_for_game(game_id):
    """Get all rallies for a game across all sets."""
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT r.*, s.set_number
            FROM rallies r
            JOIN sets s ON r.set_id = s.id
            WHERE s.game_id = ?
            ORDER BY s.set_number, r.rally_number
        """, (game_id,)).fetchall()]


def get_detections_for_game(game_id):
    """Batch fetch all player_detections for a game, keyed by rally_id."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT pd.*
            FROM player_detections pd
            JOIN rallies r ON pd.rally_id = r.id
            JOIN sets s ON r.set_id = s.id
            WHERE s.game_id = ?
            ORDER BY pd.rally_id, pd.frame_timestamp
        """, (game_id,)).fetchall()
        result = {}
        for row in rows:
            d = dict(row)
            rid = d["rally_id"]
            result.setdefault(rid, []).append(d)
        return result
