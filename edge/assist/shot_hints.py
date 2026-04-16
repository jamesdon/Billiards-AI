from __future__ import annotations

from typing import List, Tuple

from core.types import BallClass, GameState


def stub_best_shot_polyline_table_m(state: GameState) -> List[Tuple[float, float]]:
    """Placeholder straight line from cue toward table center; replace with solver."""
    cx, cy = 0.0, 0.0
    n = 0
    for _, t in state.balls.items():
        cx += t.pos_xy[0]
        cy += t.pos_xy[1]
        n += 1
    if n == 0:
        return []
    mx, my = cx / n, cy / n
    cue = None
    for _, t in state.balls.items():
        if t.best_class() == BallClass.CUE:
            cue = t.pos_xy
            break
    if cue is None:
        return []
    x0, y0 = float(cue[0]), float(cue[1])
    out: List[Tuple[float, float]] = []
    for i in range(1, 16):
        a = i / 15.0
        out.append((x0 + (mx - x0) * a, y0 + (my - y0) * a))
    return out


def stub_alt_shot_polyline_table_m(state: GameState, variant: int) -> List[Tuple[float, float]]:
    """Placeholder second aim; offset aim by small angle based on variant index."""
    base = stub_best_shot_polyline_table_m(state)
    if not base:
        return []
    off = 0.05 * (1 + (variant % 3))
    return [(x + off, y) for x, y in base]
