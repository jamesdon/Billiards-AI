from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProjectorOverlayState:
    """
    Toggleable layers for overhead projector output (and mirrored on-camera preview).

    Controlled by voice / UI; independent of trajectory assist and rules engines.
    """

    show_break_box: bool = False
    show_break_string: bool = False
    show_score: bool = False
    show_my_stats: bool = False
    show_best_next_shot: bool = False
    show_alt_next_shot: bool = False
    # Cycles when the shooter asks for "another option" while alt overlay is on.
    alt_shot_variant_index: int = 0
    # Free-text or normalized labels: "8", "cue", "9", "13", … (language-specific parsing lives in voice layer).
    highlighted_ball_labels: tuple[str, ...] = field(default_factory=tuple)

    def cycle_alt_shot(self) -> None:
        self.alt_shot_variant_index = int(self.alt_shot_variant_index) + 1
