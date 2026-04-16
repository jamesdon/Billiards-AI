from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.types import BallId, GameState


@dataclass
class TrajectoryAssistConfig:
    """Tuning for physics-lite cue-ball path preview (future: integrate spin, cushions)."""

    max_history_s: float = 3.0
    table_friction_decay: float = 0.02  # placeholder coefficient


@dataclass
class TrajectoryAssistController:
    """
    Owns cue-ball path history and future projection for **trajectory prediction** only.

    **Does not** evaluate fouls or legality; rules engine consumes separate events.
    After cue–ball contact, UI may show `history` + parallel **rules verdict** stream.
    """

    cfg: TrajectoryAssistConfig = field(default_factory=TrajectoryAssistConfig)
    _cue_positions_m: List[Tuple[float, float, float]] = field(default_factory=list)  # (t, x, y)

    def on_shot_start(self, ts: float, cue_ball_id: Optional[BallId] = None) -> None:
        self._cue_positions_m.clear()

    def append_cue_sample(self, ts: float, state: GameState) -> None:
        cue_xy = self._cue_table_xy(state)
        if cue_xy is None:
            return
        self._cue_positions_m.append((float(ts), float(cue_xy[0]), float(cue_xy[1])))
        cutoff = ts - self.cfg.max_history_s
        self._cue_positions_m[:] = [row for row in self._cue_positions_m if row[0] >= cutoff]

    def history_polyline_table_m(self) -> List[Tuple[float, float]]:
        return [(x, y) for _, x, y in self._cue_positions_m]

    def projected_stub_table_m(self) -> List[Tuple[float, float]]:
        """Placeholder straight-line extrapolation; replace with rail-aware integrator."""
        hist = self.history_polyline_table_m()
        if len(hist) < 2:
            return []
        (x0, y0), (x1, y1) = hist[-2], hist[-1]
        dx, dy = x1 - x0, y1 - y0
        n = float((dx * dx + dy * dy) ** 0.5 + 1e-9)
        dx, dy = dx / n, dy / n
        out: List[Tuple[float, float]] = []
        for i in range(1, 21):
            s = 0.05 * i
            out.append((x1 + dx * s, y1 + dy * s))
        return out

    @staticmethod
    def _cue_table_xy(state: GameState) -> Optional[Tuple[float, float]]:
        from core.types import BallClass

        for _, t in state.balls.items():
            if t.best_class() == BallClass.CUE:
                return float(t.pos_xy[0]), float(t.pos_xy[1])
        return None
