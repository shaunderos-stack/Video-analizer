from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PlayType(Enum):
    ACE = "Ace"
    SERVICE_ERROR = "Service Error"
    KILL = "Kill"
    ATTACK_ERROR = "Attack Error"
    BLOCK = "Block"
    BLOCK_ERROR = "Block Error"
    BALL_HANDLING_ERROR = "Ball Handling Error"
    RALLY = "Rally"


class EventType(Enum):
    SERVE = "serve"
    ACE = "ace"
    KILL = "kill"
    ATTACK_ERROR = "attack_error"
    ATTACK_ATTEMPT = "attack_attempt"
    ASSIST = "assist"
    SOLO_BLOCK = "solo_block"
    BLOCK_ASSIST = "block_assist"
    BLOCK_ERROR = "block_error"
    DIG = "dig"
    DIG_ERROR = "dig_error"
    RECEPTION = "reception"
    RECEPTION_ERROR = "reception_error"
    PERFECT_PASS = "perfect_pass"
    SERVICE_ERROR = "service_error"
    BALL_HANDLING_ERROR = "ball_handling_error"
    SUBSTITUTION = "substitution"
    POINT_SCORED = "point_scored"
    ROTATION = "rotation"


@dataclass
class Player:
    jersey_number: int
    team: str  # e.g. "home" or "away", or team color/name
    name: Optional[str] = None

    @property
    def id(self) -> str:
        return f"{self.team}_{self.jersey_number}"


@dataclass
class GameEvent:
    timestamp: float  # seconds into the video
    event_type: EventType
    player: Optional[Player] = None
    details: str = ""
    set_number: int = 1
    score_home: Optional[int] = None
    score_away: Optional[int] = None


@dataclass
class PlayerStats:
    player: Player

    # Attacking
    kills: int = 0
    attack_errors: int = 0
    attack_attempts: int = 0

    # Serving
    aces: int = 0
    service_errors: int = 0
    total_serves: int = 0

    # Passing / Reception
    receptions: int = 0
    reception_errors: int = 0
    perfect_passes: int = 0

    # Defense
    digs: int = 0
    dig_errors: int = 0

    # Blocking
    solo_blocks: int = 0
    block_assists: int = 0
    block_errors: int = 0

    # Setting
    assists: int = 0
    ball_handling_errors: int = 0

    # General
    points_scored: int = 0
    sets_played: set = field(default_factory=set)

    @property
    def hitting_percentage(self) -> float:
        if self.attack_attempts == 0:
            return 0.0
        return (self.kills - self.attack_errors) / self.attack_attempts

    @property
    def total_blocks(self) -> int:
        return self.solo_blocks + self.block_assists

    @property
    def sets_played_count(self) -> int:
        return len(self.sets_played)


@dataclass
class GameState:
    score_home: int = 0
    score_away: int = 0
    current_set: int = 1
    set_scores: list = field(default_factory=list)  # list of (home, away) tuples
    home_team: str = "Home"
    away_team: str = "Away"
