from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


BallId = int


class GameType(str, Enum):
    EIGHT_BALL = "8ball"
    NINE_BALL = "9ball"
    STRAIGHT_POOL = "straight_pool"
    UK_POOL = "uk_pool"
    SNOOKER = "snooker"


class EightBallRuleSet(str, Enum):
    APA = "apa"
    BCA_WPA = "bca_wpa"
    BAR = "bar"


class NineBallRuleSet(str, Enum):
    WPA = "wpa"
    APA = "apa"
    USAPL = "usapl"


class StraightPoolRuleSet(str, Enum):
    WPA = "wpa"
    BCA = "bca"
    HOUSE = "house"


class UKPoolRuleSet(str, Enum):
    BLACKBALL_WPA = "blackball_wpa"
    WEPF = "wepf"
    PUB = "pub"


class SnookerRuleSet(str, Enum):
    WPBSA = "wpbsa"
    IBSF = "ibsf"
    CLUB = "club"


class PlayMode(str, Enum):
    SINGLES = "singles"
    DOUBLES = "doubles"
    SCOTCH_DOUBLES = "scotch_doubles"


class PocketLabel(str, Enum):
    TOP_LEFT_CORNER = "top_left_corner"
    TOP_RIGHT_CORNER = "top_right_corner"
    BOTTOM_LEFT_CORNER = "bottom_left_corner"
    BOTTOM_RIGHT_CORNER = "bottom_right_corner"
    LEFT_SIDE_POCKET = "left_side_pocket"
    RIGHT_SIDE_POCKET = "right_side_pocket"


class BallClass(str, Enum):
    UNKNOWN = "unknown"

    CUE = "cue"
    EIGHT = "eight"
    NINE = "nine"

    SOLID = "solid"
    STRIPE = "stripe"

    UK_RED = "uk_red"
    UK_YELLOW = "uk_yellow"
    UK_BLACK = "uk_black"

    SNOOKER_RED = "snooker_red"
    SNOOKER_YELLOW = "snooker_yellow"
    SNOOKER_GREEN = "snooker_green"
    SNOOKER_BROWN = "snooker_brown"
    SNOOKER_BLUE = "snooker_blue"
    SNOOKER_PINK = "snooker_pink"
    SNOOKER_BLACK = "snooker_black"


@dataclass(frozen=True)
class BallObservation:
    """Single-frame observation in pixel space."""

    bbox_xyxy: Tuple[float, float, float, float]
    conf: float
    label: str = "ball"


@dataclass
class BallTrack:
    """Tracked ball state in table coordinates (meters)."""

    id: BallId
    pos_xy: Tuple[float, float]
    vel_xy: Tuple[float, float] = (0.0, 0.0)
    last_seen_ts: float = 0.0
    class_probs: Dict[BallClass, float] = field(default_factory=dict)
    number: Optional[int] = None
    last_bbox_px: Optional[Tuple[float, float, float, float]] = None
    last_center_px: Optional[Tuple[float, float]] = None

    def best_class(self) -> BallClass:
        if not self.class_probs:
            return BallClass.UNKNOWN
        return max(self.class_probs.items(), key=lambda kv: kv[1])[0]


@dataclass
class RackTrack:
    """Tracked rack state in pixel space."""

    id: int
    center_px: Tuple[float, float]
    bbox_xyxy: Tuple[float, float, float, float]
    last_seen_ts: float = 0.0


@dataclass(frozen=True)
class Ball:
    id: BallId
    pos_xy: Tuple[float, float]
    vel_xy: Tuple[float, float]
    ball_class: BallClass
    number: Optional[int]


class EventType(str, Enum):
    SHOT_START = "shot_start"
    SHOT_END = "shot_end"
    CUE_STRIKE = "cue_strike"

    BALL_POCKETED = "ball_pocketed"
    BALL_COLLISION = "ball_collision"
    FOUL = "foul"

    PLAYER_SEEN = "player_seen"
    STICK_SEEN = "stick_seen"
    RACK_DETECTED = "rack_detected"
    RAIL_HIT = "rail_hit"
    SHOT_SUMMARY = "shot_summary"
    GAME_OVER = "game_over"


class FoulType(str, Enum):
    # Technical & shot-based
    CUE_BALL_SCRATCH = "cue_ball_scratch"
    WRONG_BALL_FIRST = "wrong_ball_first"
    NO_CONTACT = "no_contact"
    NO_RAIL_AFTER_CONTACT = "no_rail_after_contact"
    DOUBLE_HIT_OR_PUSH = "double_hit_or_push"
    BALLS_STILL_MOVING = "balls_still_moving"
    JUMP_SHOT_INFRACTION = "jump_shot_infraction"
    # Physical & conduct
    TOUCHED_BALL = "touched_ball"
    NO_FOOT_ON_FLOOR = "no_foot_on_floor"
    BAD_CUE_BALL_PLACEMENT = "bad_cue_ball_placement"
    UNSPORTSMANLIKE_CONDUCT = "unsportsmanlike_conduct"


@dataclass(frozen=True)
class Event:
    type: EventType
    ts: float
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlayerState:
    name: str
    score: int = 0
    fouls: int = 0
    balls_pocketed: List[BallClass] = field(default_factory=list)
    group: Optional[BallClass] = None  # e.g., SOLID/STRIPE or UK_RED/UK_YELLOW
    shots_taken: int = 0
    innings: int = 0
    profile_id: Optional[str] = None


@dataclass
class TeamState:
    name: str
    player_indices: List[int]
    score: int = 0
    fouls: int = 0
    balls_pocketed: List[BallClass] = field(default_factory=list)
    group: Optional[BallClass] = None
    innings: int = 0


@dataclass(frozen=True)
class PlayerProfile:
    id: str
    display_name: str
    color_signature: List[float] = field(default_factory=list)  # e.g., HSV histogram


@dataclass(frozen=True)
class StickProfile:
    id: str
    display_name: str
    color_signature: List[float] = field(default_factory=list)
    length_signature: float = 0.0  # bbox aspect/length proxy for stick identity


class ShotTag(str, Enum):
    STUN = "stun"
    FOLLOW = "follow"
    DRAW = "draw"
    CUT = "cut"
    BANK = "bank"
    KICK = "kick"
    COMBINATION = "combination"
    JUMP = "jump"
    MASSE = "masse"
    ENGLISH = "english"
    CAROM = "carom"
    BREAK = "break"


@dataclass
class ShotSummary:
    shot_idx: int
    ts_start: float
    ts_end: float
    shooter_player_idx: int
    shooter_team_idx: int
    cue_peak_speed_mps: float
    shooter_profile_id: Optional[str] = None
    stick_profile_id: Optional[str] = None
    tags: List[ShotTag] = field(default_factory=list)
    # Key distances (meters)
    follow_distance_m: float = 0.0
    draw_distance_m: float = 0.0
    cut_angle_deg: Optional[float] = None
    masse_max_lateral_deviation_m: Optional[float] = None
    # Break-only stats
    break_rail_hits: int = 0
    break_pocketed: List[BallId] = field(default_factory=list)
    rail_hits_by_ball: Dict[BallId, int] = field(default_factory=dict)


@dataclass
class ShotState:
    in_shot: bool = False
    shot_start_ts: Optional[float] = None
    last_cue_contact_ts: Optional[float] = None
    first_object_ball_hit: Optional[BallId] = None
    pocketed_this_shot: List[BallId] = field(default_factory=list)
    fouls_this_shot: List[str] = field(default_factory=list)
    shooter_player_idx: Optional[int] = None
    shooter_team_idx: Optional[int] = None
    stick_profile_id: Optional[str] = None
    shot_max_cue_speed_mps: float = 0.0
    rail_hits_this_shot: int = 0


@dataclass
class GameConfig:
    game_type: GameType
    play_mode: PlayMode = PlayMode.SINGLES
    table_length_m: float = 2.84  # ~9ft default
    table_width_m: float = 1.42
    num_players: int = 2
    # For doubles/scotch: list of teams as lists of player indices.
    # Defaults to [[0,1],[2,3]] when num_players == 4 if not provided by caller.
    teams: Optional[List[List[int]]] = None
    # Straight pool: first to this many points wins (typical tournament is 150).
    straight_pool_target_points: int = 150
    # League/variant ruleset selection (top 3 per game).
    eight_ball_ruleset: EightBallRuleSet = EightBallRuleSet.BCA_WPA
    nine_ball_ruleset: NineBallRuleSet = NineBallRuleSet.WPA
    straight_pool_ruleset: StraightPoolRuleSet = StraightPoolRuleSet.WPA
    uk_pool_ruleset: UKPoolRuleSet = UKPoolRuleSet.BLACKBALL_WPA
    snooker_ruleset: SnookerRuleSet = SnookerRuleSet.WPBSA


@dataclass
class GameState:
    config: GameConfig
    players: List[PlayerState]
    teams: List[TeamState] = field(default_factory=list)
    current_team_idx: int = 0
    current_player_idx: int = 0  # derived from play mode/team rotation
    inning: int = 1
    balls: Dict[BallId, BallTrack] = field(default_factory=dict)
    pocketed: Dict[BallId, float] = field(default_factory=dict)  # ball_id -> ts
    shot: ShotState = field(default_factory=ShotState)
    winner_team: Optional[int] = None
    game_over_reason: Optional[str] = None
    ball_in_hand_for_team: Optional[int] = None
    player_profiles: Dict[str, PlayerProfile] = field(default_factory=dict)
    stick_profiles: Dict[str, StickProfile] = field(default_factory=dict)
    shot_history: List[ShotSummary] = field(default_factory=list)
    shot_count: int = 0
    # transient UI hint for overlays (edge-only; not persisted)
    _ui_banner: Optional[str] = None

    def current_player(self) -> PlayerState:
        return self.players[self.current_player_idx]

    def current_team(self) -> Optional[TeamState]:
        return self.teams[self.current_team_idx] if self.teams else None

    def resolve_rotation(self) -> None:
        """
        Ensure `teams`, `current_team_idx`, and `current_player_idx` are consistent.
        Call this after constructing state or changing config.
        """
        if not self.teams:
            self._init_teams_from_config()
        self.current_player_idx = self._active_player_for_team(self.current_team_idx)

    def next_player(self) -> None:
        if not self.teams:
            # singles legacy fallback
            self.current_player_idx = (self.current_player_idx + 1) % len(self.players)
            if self.current_player_idx == 0:
                self.inning += 1
            return

        # pass turn to next team; update active shooter depending on play mode
        self.current_team_idx = (self.current_team_idx + 1) % len(self.teams)
        if self.current_team_idx == 0:
            self.inning += 1
            for t in self.teams:
                t.innings += 1
        self.current_player_idx = self._active_player_for_team(self.current_team_idx)

    def advance_within_team(self) -> None:
        """For scotch doubles: rotate shooter within the current team."""
        if self.config.play_mode != PlayMode.SCOTCH_DOUBLES:
            return
        team = self.current_team()
        if team is None or len(team.player_indices) < 2:
            return
        # Alternate between team players based on shot count parity.
        # (More sophisticated rotation can use an explicit pointer; parity is sufficient baseline.)
        p0, p1 = team.player_indices[0], team.player_indices[1]
        cur = self.current_player_idx
        self.current_player_idx = p1 if cur == p0 else p0

    def _init_teams_from_config(self) -> None:
        if self.config.play_mode == PlayMode.SINGLES:
            self.teams = [TeamState(name=self.players[i].name, player_indices=[i]) for i in range(len(self.players))]
            self.current_team_idx = self.current_player_idx
            return

        teams = self.config.teams
        if teams is None:
            if len(self.players) == 4:
                teams = [[0, 1], [2, 3]]
            else:
                # fallback: split sequentially into 2 teams
                mid = len(self.players) // 2
                teams = [list(range(0, mid)), list(range(mid, len(self.players)))]

        self.teams = []
        for ti, pidxs in enumerate(teams):
            nm = " / ".join(self.players[i].name for i in pidxs)
            self.teams.append(TeamState(name=f"Team {ti+1}: {nm}", player_indices=pidxs))

    def _active_player_for_team(self, team_idx: int) -> int:
        team = self.teams[team_idx]
        if self.config.play_mode == PlayMode.DOUBLES:
            # default: team captain (first listed)
            return team.player_indices[0]
        if self.config.play_mode == PlayMode.SCOTCH_DOUBLES:
            # baseline: alternate each turn using inning parity
            if len(team.player_indices) == 1:
                return team.player_indices[0]
            a, b = team.player_indices[0], team.player_indices[1]
            return a if (self.inning % 2 == 1) else b
        return team.player_indices[0]

