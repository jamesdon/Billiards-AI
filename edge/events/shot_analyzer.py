from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.types import BallClass, BallId, Event, EventType, GameState, PocketLabel, ShotSummary, ShotTag


def _speed(vxy: Tuple[float, float]) -> float:
    return float((vxy[0] * vxy[0] + vxy[1] * vxy[1]) ** 0.5)


def _angle_deg(a: Tuple[float, float], b: Tuple[float, float]) -> Optional[float]:
    ax, ay = a
    bx, by = b
    na = (ax * ax + ay * ay) ** 0.5
    nb = (bx * bx + by * by) ** 0.5
    if na < 1e-6 or nb < 1e-6:
        return None
    dot = ax * bx + ay * by
    c = max(-1.0, min(1.0, dot / (na * nb)))
    import math

    return float(math.degrees(math.acos(c)))


@dataclass
class ShotAnalyzerConfig:
    stun_speed_after_contact_thres: float = 0.06
    follow_speed_thres: float = 0.10
    draw_speed_thres: float = 0.10
    follow_measure_window_s: float = 0.7
    draw_measure_window_s: float = 0.7
    cut_angle_thres_deg: float = 10.0
    rail_band_m: float = 0.05
    rail_bounce_cooldown_s: float = 0.2


@dataclass
class ShotAnalyzer:
    """
    Shot-type inference using only 2D table-plane kinematics + collision events.

    Notes:
    - Jump/masse/english are hard from a top-down single camera without 3D/spin sensing.
      We provide placeholders and only mark them when strong heuristics exist later.
    - Bank/kick/combo rely on collision sequences and (optional) rail-bounce detection.
    """

    cfg: ShotAnalyzerConfig = field(default_factory=ShotAnalyzerConfig)

    _shot_start_ts: Optional[float] = None
    _shot_start_cue_pos: Optional[Tuple[float, float]] = None
    _shot_start_cue_dir: Optional[Tuple[float, float]] = None
    _first_contact_ts: Optional[float] = None
    _cue_pos_at_contact: Optional[Tuple[float, float]] = None
    _obj_hit_id: Optional[BallId] = None
    _obj_vel_after_contact: Optional[Tuple[float, float]] = None
    _cue_vel_after_contact: Optional[Tuple[float, float]] = None
    _cue_min_proj_after_contact: float = 0.0
    _cue_max_proj_after_contact: float = 0.0
    _contact_basis_dir: Optional[Tuple[float, float]] = None

    _collisions: List[Tuple[float, BallId, BallId]] = field(default_factory=list)
    _rail_hits: int = 0
    _last_rail_ts: float = -1e9
    _rail_hits_by_ball: Dict[BallId, int] = field(default_factory=dict)
    _rail_hit_events: List[Tuple[float, BallId, str]] = field(default_factory=list)
    _ball_pocket_events: List[Tuple[float, BallId, Optional[PocketLabel]]] = field(default_factory=list)

    def on_state(self, state: GameState, ts: float) -> None:
        if not state.shot.in_shot:
            return
        cue_id = self._cue_id(state)
        if cue_id is None or cue_id not in state.balls:
            return

        cue = state.balls[cue_id]

        # initialize shot start context
        if self._shot_start_ts is not None and self._shot_start_cue_pos is None:
            self._shot_start_cue_pos = cue.pos_xy
            self._shot_start_cue_dir = cue.vel_xy

        # track cue displacement along initial direction after first contact
        if self._first_contact_ts is not None and self._cue_pos_at_contact is not None and self._contact_basis_dir:
            dt = ts - self._first_contact_ts
            if dt <= max(self.cfg.follow_measure_window_s, self.cfg.draw_measure_window_s):
                dx = cue.pos_xy[0] - self._cue_pos_at_contact[0]
                dy = cue.pos_xy[1] - self._cue_pos_at_contact[1]
                bx, by = self._contact_basis_dir
                bnorm = (bx * bx + by * by) ** 0.5
                if bnorm > 1e-6:
                    bx /= bnorm
                    by /= bnorm
                    proj = dx * bx + dy * by
                    self._cue_min_proj_after_contact = min(self._cue_min_proj_after_contact, proj)
                    self._cue_max_proj_after_contact = max(self._cue_max_proj_after_contact, proj)

        # rail hit heuristic: if any ball enters rail band and reverses component later.
        # For baseline we only count cue ball rail hits (works well for break rail count later too).
        if self._is_near_rail(state, cue.pos_xy) and (ts - self._last_rail_ts) > self.cfg.rail_bounce_cooldown_s:
            # require non-trivial speed to avoid idle near-rail false positives
            if _speed(cue.vel_xy) > 0.15:
                self._rail_hits += 1
                self._last_rail_ts = ts

    def on_event(self, state: GameState, event: Event) -> Optional[ShotSummary]:
        if event.type == EventType.SHOT_START:
            self._reset()
            self._shot_start_ts = event.ts
            return None

        if event.type == EventType.BALL_COLLISION:
            a = int(event.payload["a"])
            b = int(event.payload["b"])
            self._collisions.append((event.ts, a, b))

            cue_id = self._cue_id(state)
            if cue_id is None:
                return None

            # first cue->object contact
            if self._first_contact_ts is None and (a == cue_id or b == cue_id):
                obj = b if a == cue_id else a
                self._first_contact_ts = event.ts
                self._obj_hit_id = obj
                # snapshot cue/object states at contact
                if cue_id in state.balls:
                    cue = state.balls[cue_id]
                    self._cue_pos_at_contact = cue.pos_xy
                    self._cue_vel_after_contact = cue.vel_xy
                    self._contact_basis_dir = cue.vel_xy
                if obj in state.balls:
                    self._obj_vel_after_contact = state.balls[obj].vel_xy

            return None

        if event.type == EventType.RAIL_HIT:
            bid = int(event.payload["ball_id"])
            rail = str(event.payload.get("rail", "unknown"))
            self._rail_hits_by_ball[bid] = self._rail_hits_by_ball.get(bid, 0) + 1
            self._rail_hit_events.append((event.ts, bid, rail))
            return None

        if event.type == EventType.BALL_POCKETED:
            bid = int(event.payload["ball_id"])
            pl = event.payload.get("pocket_label")
            pocket = PocketLabel(pl) if isinstance(pl, str) else None
            self._ball_pocket_events.append((event.ts, bid, pocket))
            return None

        if event.type == EventType.SHOT_END:
            if self._shot_start_ts is None:
                return None
            return self._finalize(state, event.ts)

        return None

    def _finalize(self, state: GameState, ts_end: float) -> ShotSummary:
        state.shot_count += 1
        shooter_player = state.current_player_idx
        shooter_team = state.current_team_idx if state.teams else state.current_player_idx
        ss = ShotSummary(
            shot_idx=state.shot_count,
            ts_start=float(self._shot_start_ts or ts_end),
            ts_end=float(ts_end),
            shooter_player_idx=shooter_player,
            shooter_team_idx=shooter_team,
            cue_peak_speed_mps=float(state.shot.shot_max_cue_speed_mps),
            shooter_profile_id=state.players[shooter_player].profile_id,
            stick_profile_id=state.shot.stick_profile_id,
        )

        is_break = (state.shot_count == 1) and (len(state.pocketed) == 0)
        if is_break:
            ss.tags.append(ShotTag.BREAK)
            ss.break_rail_hits = int(self._rail_hits)
            ss.break_pocketed = list(state.shot.pocketed_this_shot)
        ss.rail_hits_by_ball = dict(self._rail_hits_by_ball)

        # Do not compute bank/combo on break per requirement.
        if not is_break:
            self._tag_follow_draw_stun(ss)
            self._tag_cut(ss)
            self._tag_combo_carom_bank_kick(ss)

        if state.shot.thread_the_needle_eligible:
            ss.tags.append(ShotTag.THREAD_THE_NEEDLE)
            state.shot.thread_the_needle_eligible = False

        state.shot_history.append(ss)
        return ss

    def _tag_follow_draw_stun(self, ss: ShotSummary) -> None:
        if self._first_contact_ts is None or self._cue_vel_after_contact is None:
            return

        v_after = _speed(self._cue_vel_after_contact)

        # Follow/draw distance measured along initial cue direction at contact:
        follow = max(0.0, self._cue_max_proj_after_contact)
        draw = max(0.0, -self._cue_min_proj_after_contact)
        ss.follow_distance_m = float(follow)
        ss.draw_distance_m = float(draw)

        # Classify:
        # - stun: cue speed after contact very small and neither follow/draw significant
        # - follow: positive projection dominates + non-trivial speed
        # - draw: negative projection dominates + non-trivial speed
        if v_after <= self.cfg.stun_speed_after_contact_thres and follow < 0.05 and draw < 0.05:
            ss.tags.append(ShotTag.STUN)
        else:
            if follow >= 0.10 and v_after >= self.cfg.follow_speed_thres:
                ss.tags.append(ShotTag.FOLLOW)
            if draw >= 0.10 and v_after >= self.cfg.draw_speed_thres:
                ss.tags.append(ShotTag.DRAW)

    def _tag_cut(self, ss: ShotSummary) -> None:
        if self._contact_basis_dir is None or self._obj_vel_after_contact is None:
            return
        ang = _angle_deg(self._contact_basis_dir, self._obj_vel_after_contact)
        ss.cut_angle_deg = ang
        if ang is not None and ang >= self.cfg.cut_angle_thres_deg:
            ss.tags.append(ShotTag.CUT)

    def _tag_combo_carom_bank_kick(self, ss: ShotSummary) -> None:
        # Combination: cue hits A then A hits B (object-object collision after cue-object).
        # Carom: cue hits A then cue hits B later (cue involved in 2+ object collisions).
        # Bank/kick: requires rail hit before pocket/contact; we use rail hit count as a proxy for now.
        object_object = 0
        # We cannot reliably resolve cue ball id if not classified; keep heuristic
        # by counting collisions involving first_object_ball_hit if present.
        if ss.ts_start is None:
            return

        # Determine if multiple collisions occurred in the shot.
        for _, a, b in self._collisions:
            if a == b:
                continue
            # object-object collision
            object_object += 1
        if object_object >= 2:
            ss.tags.append(ShotTag.COMBINATION)

        # Carom heuristic: many collisions generally implies multi-contact.
        if len(self._collisions) >= 3:
            ss.tags.append(ShotTag.CAROM)

        # Kick: cue ball rail hit BEFORE first object contact.
        if self._first_contact_ts is not None:
            cue_rail_pre = any((t < self._first_contact_ts) and (bid == self._cue_id_for_summary(ss)) for t, bid, _ in self._rail_hit_events)
            if cue_rail_pre:
                ss.tags.append(ShotTag.KICK)

        # Bank: deterministic if a pocketed object ball had a valid rail hit between first contact and pocket time,
        # excluding rails connected to the pocket (to avoid "pocket jaw" false positives).
        if self._first_contact_ts is not None and self._ball_pocket_events:
            for pocket_ts, bid, pocket in self._ball_pocket_events:
                if bid is None or pocket is None:
                    continue
                invalid = _pocket_connected_rails(pocket)
                # count valid rail hits after first contact and before pocket
                valid_hits = 0
                for rh_ts, rh_bid, rail in self._rail_hit_events:
                    if rh_bid != bid:
                        continue
                    if rh_ts < self._first_contact_ts or rh_ts > pocket_ts:
                        continue
                    if rail in invalid:
                        continue
                    valid_hits += 1
                if valid_hits > 0:
                    ss.tags.append(ShotTag.BANK)
                    break

        # Combination: if any pocketed ball (not the first hit) had an object-object collision chain before pocket.
        if self._ball_pocket_events and self._collisions:
            for pocket_ts, bid, _ in self._ball_pocket_events:
                if bid is None:
                    continue
                if self._obj_hit_id is not None and bid == self._obj_hit_id:
                    continue
                # any collision involving this ball before it was pocketed => likely combination/carom sequence
                if any((t <= pocket_ts) and (a == bid or b == bid) for t, a, b in self._collisions):
                    ss.tags.append(ShotTag.COMBINATION)
                    break

    def _cue_id(self, state: GameState) -> Optional[BallId]:
        for bid, t in state.balls.items():
            if t.best_class() == BallClass.CUE:
                return bid
        return None

    def _cue_id_for_summary(self, ss: ShotSummary) -> Optional[BallId]:
        # Cue ID is not encoded in ShotSummary; we use None (rail kick detection may be conservative).
        return None

    def _is_near_rail(self, state: GameState, xy: Tuple[float, float]) -> bool:
        x, y = xy
        L = float(state.config.table_length_m)
        W = float(state.config.table_width_m)
        return (x <= self.cfg.rail_band_m) or (x >= L - self.cfg.rail_band_m) or (y <= self.cfg.rail_band_m) or (
            y >= W - self.cfg.rail_band_m
        )

    def _reset(self) -> None:
        self._shot_start_ts = None
        self._shot_start_cue_pos = None
        self._shot_start_cue_dir = None
        self._first_contact_ts = None
        self._cue_pos_at_contact = None
        self._obj_hit_id = None
        self._obj_vel_after_contact = None
        self._cue_vel_after_contact = None
        self._cue_min_proj_after_contact = 0.0
        self._cue_max_proj_after_contact = 0.0
        self._contact_basis_dir = None
        self._collisions.clear()
        self._rail_hits = 0
        self._last_rail_ts = -1e9
        self._rail_hits_by_ball.clear()
        self._rail_hit_events.clear()
        self._ball_pocket_events.clear()


def _pocket_connected_rails(p: PocketLabel) -> set[str]:
    # Rails connected to the pocket opening (exclude these to avoid counting pocket jaws as a "bank").
    if p == PocketLabel.TOP_LEFT_CORNER:
        return {"top", "left"}
    if p == PocketLabel.TOP_RIGHT_CORNER:
        return {"top", "right"}
    if p == PocketLabel.BOTTOM_LEFT_CORNER:
        return {"bottom", "left"}
    if p == PocketLabel.BOTTOM_RIGHT_CORNER:
        return {"bottom", "right"}
    if p == PocketLabel.LEFT_SIDE_POCKET:
        return {"left"}
    if p == PocketLabel.RIGHT_SIDE_POCKET:
        return {"right"}
    return set()

