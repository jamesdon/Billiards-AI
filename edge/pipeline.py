from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.geometry import Homography
from core.stats import StatsAggregator
from core.rules.turn_events import player_shot_begin_event, player_shot_over_event
from core.types import BallClass, BallId, BallObservation, BallTrack, Event, EventType, GameState, RackTrack

from .calib.calib_store import Calibration
from .events.collision_detector import CollisionDetector
from .events.foul_detector import FoulDetector
from .events.pocket_detector import PocketDetector
from .events.shot_detector import ShotDetector
from .events.shot_analyzer import ShotAnalyzer
from .events.rail_hit_detector import RailHitDetector
from .events.thread_the_needle import ThreadTheNeedleDetector
from .events.micro_foul_audio import MicroFoulAudioDetector
from .tracking.iou_tracker import IoUTracker
from .trajectory.assist import TrajectoryAssistController
from .game_phase import estimate_vision_game_phase
from .assist.shot_hints import stub_alt_shot_polyline_table_m, stub_best_shot_polyline_table_m
from .classify.ball_classifier import BallClassifier
from .classify.player_stick_id import PlayerStickIdentifier
from core.identity_store import IdentityStore
from .vision.detector_base import Detector


@dataclass
class EdgePipelineConfig:
    """`detect_every_n` throttles the *detector*; the tracker still runs every frame when dets exist.

    Ball positions (and finite-difference velocities) update on detection frames only unless you
    add motion prediction upstream. Event detectors (shot/collision/rail) run every frame and
    therefore see velocities that may be stale for up to N−1 frames — tune thresholds accordingly.
    """

    detect_every_n: int = 2
    track_max_age_s: float = 0.5  # mirrored in tracker


@dataclass
class EdgePipeline:
    detector: Optional[Detector] = None
    tracker: IoUTracker = field(default_factory=IoUTracker)
    player_tracker: IoUTracker = field(default_factory=IoUTracker)
    stick_tracker: IoUTracker = field(default_factory=IoUTracker)
    ball_classifier: BallClassifier = field(default_factory=BallClassifier)
    identity_store: Optional[IdentityStore] = None
    player_stick_id: Optional[PlayerStickIdentifier] = None
    shot: ShotDetector = field(default_factory=ShotDetector)
    shot_analyzer: ShotAnalyzer = field(default_factory=ShotAnalyzer)
    rail: RailHitDetector = field(default_factory=RailHitDetector)
    pocket: PocketDetector = field(default_factory=PocketDetector)
    collision: CollisionDetector = field(default_factory=CollisionDetector)
    foul: FoulDetector = field(default_factory=FoulDetector)
    stats: StatsAggregator = field(default_factory=StatsAggregator)
    cfg: EdgePipelineConfig = field(default_factory=EdgePipelineConfig)
    trajectory: TrajectoryAssistController = field(default_factory=TrajectoryAssistController)
    micro_foul_audio: Optional[MicroFoulAudioDetector] = None
    thread_needle: ThreadTheNeedleDetector = field(default_factory=ThreadTheNeedleDetector)

    _frame_idx: int = 0
    _last_table_pos: Dict[BallId, Tuple[float, float]] = field(default_factory=dict)
    _last_table_ts: Dict[BallId, float] = field(default_factory=dict)
    _last_seen_stick_profile_id: Optional[str] = None
    _last_seen_stick_ts: float = -1e9
    _player_centers_px: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    _stick_centers_px: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    _last_ui_stick_profile_id: Optional[str] = None
    _ui_stick_banner: Optional[str] = None
    _ui_stick_banner_until_ts: float = 0.0
    _game_over_emitted: bool = False
    _rack_tracker: IoUTracker = field(default_factory=IoUTracker)
    _rack_tracks: Dict[int, RackTrack] = field(default_factory=dict)
    _pending_rack_game_over_ts: Optional[float] = None

    def step(
        self,
        state: GameState,
        frame_bgr: np.ndarray,
        ts: float,
        calib: Optional[Calibration],
        on_event,
    ) -> None:
        self._frame_idx += 1

        dets: List[BallObservation] = []
        if self.detector is not None and (self._frame_idx % self.cfg.detect_every_n == 0):
            dets = self.detector.detect(frame_bgr, ts)

        ball_dets = [d for d in dets if d.label in ("ball", "cue_ball", "object_ball", "0", "1")]
        player_dets = [d for d in dets if d.label in ("person", "player")]
        stick_dets = [d for d in dets if d.label in ("cue_stick", "stick")]
        rack_dets = [d for d in dets if d.label in ("rack",)]

        # Track each category separately
        tracks_px = self.tracker.update(ball_dets, ts)
        player_tracks = self.player_tracker.update(player_dets, ts)
        stick_tracks = self.stick_tracker.update(stick_dets, ts)
        rack_tracks = self._rack_tracker.update(rack_dets, ts)

        H = calib.H if calib is not None else None
        self._update_rack_tracks(rack_tracks, ts)
        rack_boxes = [rt.bbox_xyxy for rt in self._rack_tracks.values()]
        self._update_ball_tracks(state, frame_bgr, tracks_px, ts, H, rack_boxes)

        # Identity: players and sticks
        if self.player_stick_id is not None:
            for tid, (_, bbox, _) in player_tracks.items():
                x1, y1, x2, y2 = [int(v) for v in bbox]
                roi = frame_bgr[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
                if roi.size == 0:
                    continue
                prof = self.player_stick_id.match_or_create_player(roi)
                cx = (bbox[0] + bbox[2]) * 0.5
                cy = (bbox[1] + bbox[3]) * 0.5
                self._player_centers_px[prof.id] = (float(cx), float(cy))
                fw = int(frame_bgr.shape[1]) if frame_bgr.ndim >= 2 else 0
                self.player_stick_id.assign_profile_to_players(
                    state, prof, center_x_px=float(cx), frame_width_px=fw if fw > 0 else None
                )
                on_event(Event(type=EventType.PLAYER_SEEN, ts=ts, payload={"track_id": tid, "profile_id": prof.id, "display_name": prof.display_name}))
            for tid, (_, bbox, _) in stick_tracks.items():
                x1, y1, x2, y2 = [int(v) for v in bbox]
                roi = frame_bgr[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
                if roi.size == 0:
                    continue
                prof = self.player_stick_id.match_or_create_stick(roi)
                cx = (bbox[0] + bbox[2]) * 0.5
                cy = (bbox[1] + bbox[3]) * 0.5
                self._stick_centers_px[prof.id] = (float(cx), float(cy))
                self._last_seen_stick_profile_id = prof.id
                self._last_seen_stick_ts = ts
                # UI: only announce when we detect a *new* stick identity.
                if prof.id != self._last_ui_stick_profile_id:
                    self._last_ui_stick_profile_id = prof.id
                    self._ui_stick_banner = f"Stick: {prof.display_name}"
                    self._ui_stick_banner_until_ts = ts + 3.0
                on_event(Event(type=EventType.STICK_SEEN, ts=ts, payload={"track_id": tid, "profile_id": prof.id, "display_name": prof.display_name}))

        # Update shot peak cue speed if cue ball known
        for bid, t in state.balls.items():
            if t.best_class() == BallClass.CUE:
                spd = float((t.vel_xy[0] ** 2 + t.vel_xy[1] ** 2) ** 0.5)
                state.shot.shot_max_cue_speed_mps = max(state.shot.shot_max_cue_speed_mps, spd)

        # Event detectors
        events: List[Event] = []
        events += self.shot.update(state, ts)
        events += self.collision.update(state, ts)
        events += self.rail.update(state, ts)
        events += self.pocket.update(state, ts, calib)
        events += self.foul.update(state, ts)
        events += self._rack_events(state, ts)

        # Shot analyzer needs per-frame state too (for follow/draw distances, rail hits).
        self.shot_analyzer.on_state(state, ts)

        # Deliver events to rules and stats through callback
        for ev in events:
            if ev.type == EventType.SHOT_END:
                pso = player_shot_over_event(state, ev.ts)
                on_event(pso)
                self.stats.on_event(state, pso)
                state.last_player_shot_over_ts = ev.ts
            if ev.type == EventType.SHOT_START:
                self.thread_needle.on_shot_start()
                state.shot.thread_the_needle_eligible = False
                psb = player_shot_begin_event(state, ev.ts)
                on_event(psb)
                self.stats.on_event(state, psb)
                cue_id = ev.payload.get("cue_ball_id") if ev.payload else None
                self.trajectory.on_shot_start(ev.ts, cue_id)
                if self.micro_foul_audio is not None:
                    self.micro_foul_audio.on_shot_start(ev.ts)
                # Stick association is per-shot and intentionally NOT tied to player identity.
                state.shot.stick_profile_id = self._pick_stick_for_shot(state)
            on_event(ev)
            self.stats.on_event(state, ev)
            summary = self.shot_analyzer.on_event(state, ev)
            if summary is not None:
                on_event(Event(type=EventType.SHOT_SUMMARY, ts=ev.ts, payload={"shot_summary": summary.__dict__}))

        if self.micro_foul_audio is not None:
            for ev in self.micro_foul_audio.update(state, ts):
                on_event(ev)
                self.stats.on_event(state, ev)
                summary = self.shot_analyzer.on_event(state, ev)
                if summary is not None:
                    on_event(Event(type=EventType.SHOT_SUMMARY, ts=ev.ts, payload={"shot_summary": summary.__dict__}))

        if state.shot.in_shot:
            self.thread_needle.update(state, ts)

        self.stats.on_state_update(state)

        phase = estimate_vision_game_phase(
            rack_track_count=len(self._rack_tracks),
            ball_track_count=len(state.balls),
            in_shot=state.shot.in_shot,
        )
        setattr(state, "_vision_phase", phase.value)

        if state.trajectory_assist_enabled:
            self.trajectory.append_cue_sample(ts, state)
            setattr(state, "_traj_history_table_m", self.trajectory.history_polyline_table_m())
            setattr(state, "_traj_projection_table_m", self.trajectory.projected_stub_table_m())
        else:
            self.trajectory.clear()
            setattr(state, "_traj_history_table_m", [])
            setattr(state, "_traj_projection_table_m", [])

        layers = state.projector_layers
        setattr(
            state,
            "_hint_best_table_m",
            stub_best_shot_polyline_table_m(state) if layers.show_best_next_shot else [],
        )
        setattr(
            state,
            "_hint_alt_table_m",
            stub_alt_shot_polyline_table_m(state, int(layers.alt_shot_variant_index))
            if layers.show_alt_next_shot
            else [],
        )

        # Emit end-of-game event once (so backend can persist final stats).
        if state.winner_team is not None and not self._game_over_emitted:
            self._game_over_emitted = True
            on_event(
                Event(
                    type=EventType.GAME_OVER,
                    ts=ts,
                    payload={
                        "game_type": state.config.game_type.value,
                        "play_mode": state.config.play_mode.value,
                        "rulesets": {
                            "8ball": state.config.eight_ball_ruleset.value,
                            "9ball": state.config.nine_ball_ruleset.value,
                            "straight_pool": state.config.straight_pool_ruleset.value,
                            "uk_pool": state.config.uk_pool_ruleset.value,
                            "snooker": state.config.snooker_ruleset.value,
                        },
                        "winner_team": state.winner_team,
                        "game_over_reason": state.game_over_reason,
                        "inning": state.inning,
                        "shot_count": state.shot_count,
                        "players": [
                            {
                                "name": p.name,
                                "profile_id": p.profile_id,
                                "score": p.score,
                                "fouls": p.fouls,
                                "shots_taken": p.shots_taken,
                                "innings": p.innings,
                            }
                            for p in state.players
                        ],
                        "teams": [
                            {
                                "name": t.name,
                                "player_indices": t.player_indices,
                                "score": t.score,
                                "fouls": t.fouls,
                                "innings": t.innings,
                            }
                            for t in state.teams
                        ],
                    },
                )
            )

        # Expose UI banner through state for overlay to render.
        if self._ui_stick_banner is not None and ts <= self._ui_stick_banner_until_ts:
            setattr(state, "_ui_banner", self._ui_stick_banner)
        else:
            setattr(state, "_ui_banner", None)

    def _update_ball_tracks(
        self,
        state: GameState,
        frame_bgr: np.ndarray,
        tracks_px: Dict[BallId, Tuple[Tuple[float, float], Tuple[float, float, float, float], str]],
        ts: float,
        H: Optional[Homography],
        rack_bboxes_xyxy: List[Tuple[float, float, float, float]],
    ) -> None:
        # Update existing and create new ball tracks in table coords.
        for tid, (center, bbox, det_label) in tracks_px.items():
            xpx, ypx = center
            if H is not None:
                x, y = H.to_table((xpx, ypx))
            else:
                x, y = float(xpx), float(ypx)

            # velocity by finite difference
            vx, vy = 0.0, 0.0
            last_xy = self._last_table_pos.get(tid)
            last_ts = self._last_table_ts.get(tid)
            if last_xy is not None and last_ts is not None:
                dt = max(1e-3, ts - last_ts)
                vx = (x - last_xy[0]) / dt
                vy = (y - last_xy[1]) / dt

            self._last_table_pos[tid] = (x, y)
            self._last_table_ts[tid] = ts

            if tid not in state.balls:
                state.balls[tid] = BallTrack(
                    id=tid, pos_xy=(x, y), vel_xy=(vx, vy), last_seen_ts=ts, last_bbox_px=bbox
                )
                self.ball_classifier.reset_track(state.balls[tid])
            else:
                bt = state.balls[tid]
                bt.pos_xy = (x, y)
                bt.vel_xy = (vx, vy)
                bt.last_seen_ts = ts
                bt.last_bbox_px = bbox
            state.balls[tid].last_center_px = (float(xpx), float(ypx))

            # classify when we have a bbox (fast heuristic)
            self.ball_classifier.update_track(
                frame_bgr=frame_bgr,
                track=state.balls[tid],
                game_type=state.config.game_type,
                detector_hint=None,
                rack_bboxes_xyxy=rack_bboxes_xyxy or None,
            )

        # Remove stale tracks from state (so pocket detector can infer disappearance)
        stale = [bid for bid, t in state.balls.items() if (ts - t.last_seen_ts) > self.tracker.cfg.max_age_s]
        for bid in stale:
            if bid not in state.pocketed:
                state.balls.pop(bid, None)

    def _pick_stick_for_shot(self, state: GameState) -> Optional[str]:
        # Prefer stick closest to active player bbox center (if player has profile and we saw them).
        active_pid = state.current_player().profile_id
        if active_pid and active_pid in self._player_centers_px and self._stick_centers_px:
            px, py = self._player_centers_px[active_pid]
            best_sid, best_d2 = None, None
            for sid, (sx, sy) in self._stick_centers_px.items():
                d2 = (sx - px) ** 2 + (sy - py) ** 2
                if best_d2 is None or d2 < best_d2:
                    best_sid, best_d2 = sid, d2
            return best_sid

        # Fallback: closest stick to cue ball (pixel center if available).
        cue_center = None
        for bid, t in state.balls.items():
            if t.best_class() == BallClass.CUE and t.last_center_px is not None:
                cue_center = t.last_center_px
                break
        if cue_center and self._stick_centers_px:
            px, py = cue_center
            best_sid, best_d2 = None, None
            for sid, (sx, sy) in self._stick_centers_px.items():
                d2 = (sx - px) ** 2 + (sy - py) ** 2
                if best_d2 is None or d2 < best_d2:
                    best_sid, best_d2 = sid, d2
            return best_sid

        # Last resort: most recently seen stick
        return self._last_seen_stick_profile_id if (self._last_seen_stick_ts > -1e8) else None

    def _update_rack_tracks(
        self,
        rack_tracks: Dict[int, Tuple[Tuple[float, float], Tuple[float, float, float, float], str]],
        ts: float,
    ) -> None:
        for tid, (center, bbox, _) in rack_tracks.items():
            self._rack_tracks[tid] = RackTrack(
                id=int(tid),
                center_px=(float(center[0]), float(center[1])),
                bbox_xyxy=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
                last_seen_ts=float(ts),
            )
        stale = [rid for rid, rt in self._rack_tracks.items() if (ts - rt.last_seen_ts) > self._rack_tracker.cfg.max_age_s]
        for rid in stale:
            self._rack_tracks.pop(rid, None)

    def _rack_events(self, state: GameState, ts: float) -> List[Event]:
        """
        Optional fallback signal: if a rack object appears while no shot is active,
        assume the game/rack was concluded manually (e.g., concession) and emit a
        game_over event once after a short stability window.
        """
        events: List[Event] = []
        rack_present = bool(self._rack_tracks)
        if not rack_present or state.shot.in_shot:
            self._pending_rack_game_over_ts = None
            return events
        if state.winner_team is not None:
            return events
        if self._pending_rack_game_over_ts is None:
            self._pending_rack_game_over_ts = ts
            return events
        if ts - self._pending_rack_game_over_ts < 1.5:
            return events
        # Winner may be unknown for a concession/reset fallback.
        events.append(
            Event(
                type=EventType.GAME_OVER,
                ts=ts,
                payload={
                    "game_type": state.config.game_type.value,
                    "play_mode": state.config.play_mode.value,
                    "rulesets": {
                        "8ball": state.config.eight_ball_ruleset.value,
                        "9ball": state.config.nine_ball_ruleset.value,
                        "straight_pool": state.config.straight_pool_ruleset.value,
                        "uk_pool": state.config.uk_pool_ruleset.value,
                        "snooker": state.config.snooker_ruleset.value,
                    },
                    "winner_team": state.winner_team,
                    "game_over_reason": "rack_detected_manual_end",
                    "inning": state.inning,
                    "shot_count": state.shot_count,
                    "players": [
                        {
                            "name": p.name,
                            "profile_id": p.profile_id,
                            "score": p.score,
                            "fouls": p.fouls,
                            "shots_taken": p.shots_taken,
                            "innings": p.innings,
                        }
                        for p in state.players
                    ],
                    "teams": [
                        {
                            "name": t.name,
                            "player_indices": t.player_indices,
                            "score": t.score,
                            "fouls": t.fouls,
                            "innings": t.innings,
                        }
                        for t in state.teams
                    ],
                },
            )
        )
        self._pending_rack_game_over_ts = None
        return events

