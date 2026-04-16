from __future__ import annotations

import re
from enum import Enum
from typing import List

from core.types import GameState


class VoiceIntentEN(str, Enum):
    """High-level intents derived from English phrases (expand per locale later)."""

    TRAJECTORY_ASSIST_ON = "trajectory_assist_on"
    TRAJECTORY_ASSIST_OFF = "trajectory_assist_off"
    SHOW_BREAK_BOX = "show_break_box"
    HIDE_BREAK_BOX = "hide_break_box"
    SHOW_BREAK_STRING = "show_break_string"
    HIDE_BREAK_STRING = "hide_break_string"
    SHOW_SCORE = "show_score"
    HIDE_SCORE = "hide_score"
    SHOW_MY_STATS = "show_my_stats"
    HIDE_MY_STATS = "hide_my_stats"
    SHOW_BEST_NEXT_SHOT = "show_best_next_shot"
    HIDE_BEST_NEXT_SHOT = "hide_best_next_shot"
    SHOW_ALT_NEXT_SHOT = "show_alt_next_shot"
    HIDE_ALT_NEXT_SHOT = "hide_alt_next_shot"
    CYCLE_ALT_NEXT_SHOT = "cycle_alt_next_shot"
    HIGHLIGHT_BALLS = "highlight_balls"
    CLEAR_HIGHLIGHTS = "clear_highlights"


def parse_english_intents(text: str) -> List[VoiceIntentEN]:
    """
    Minimal keyword router for offline demos; replace with ASR + NLU in production.

    Matching is case-insensitive and substring-based on normalized text.
    """
    t = re.sub(r"\s+", " ", (text or "").lower().strip())
    if not t:
        return []
    out: List[VoiceIntentEN] = []

    def hit(*phrases: str) -> bool:
        return any(p in t for p in phrases)

    if hit("trajectory", "shot line", "aim line", "where will", "path help"):
        if hit("trajectory off", "stop trajectory", "hide trajectory", "no trajectory", "turn off trajectory"):
            out.append(VoiceIntentEN.TRAJECTORY_ASSIST_OFF)
        else:
            out.append(VoiceIntentEN.TRAJECTORY_ASSIST_ON)

    if hit("break box"):
        out.append(VoiceIntentEN.HIDE_BREAK_BOX if hit("hide", "off") else VoiceIntentEN.SHOW_BREAK_BOX)
    if hit("break string", "head string", "kitchen line"):
        out.append(VoiceIntentEN.HIDE_BREAK_STRING if hit("hide", "off") else VoiceIntentEN.SHOW_BREAK_STRING)
    if hit("score", "scoreboard"):
        out.append(VoiceIntentEN.HIDE_SCORE if hit("hide", "off") else VoiceIntentEN.SHOW_SCORE)
    if hit("my stats", "my statistics"):
        out.append(VoiceIntentEN.HIDE_MY_STATS if hit("hide", "off") else VoiceIntentEN.SHOW_MY_STATS)
    if hit("best shot", "best next", "recommended shot"):
        out.append(VoiceIntentEN.HIDE_BEST_NEXT_SHOT if hit("hide", "off") else VoiceIntentEN.SHOW_BEST_NEXT_SHOT)
    if hit("other shot", "alternative", "another option", "next option"):
        if hit("hide", "off"):
            out.append(VoiceIntentEN.HIDE_ALT_NEXT_SHOT)
        elif hit("another", "next", "other", "again", "cycle"):
            out.append(VoiceIntentEN.CYCLE_ALT_NEXT_SHOT)
        else:
            out.append(VoiceIntentEN.SHOW_ALT_NEXT_SHOT)

    if re.search(r"highlight\s+(?:the\s+)?(.+?)\s+ball", t):
        out.append(VoiceIntentEN.HIGHLIGHT_BALLS)
    if hit("clear highlight", "no highlight"):
        out.append(VoiceIntentEN.CLEAR_HIGHLIGHTS)

    # de-dupe preserving order
    seen = set()
    uniq: List[VoiceIntentEN] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def extract_highlight_ball_tokens(text: str) -> tuple[str, ...]:
    """Parse phrases like 'highlight the 8 and 9 balls' → ('8','9')."""
    t = re.sub(r"\s+", " ", (text or "").lower())
    m = re.search(r"highlight\s+(?:the\s+)?(.+?)\s+balls?\b", t)
    if not m:
        return ()
    body = m.group(1)
    parts = re.split(r"\s+and\s+|,\s*|\s+", body.strip())
    return tuple(p for p in parts if p and p not in ("the", "a", "an"))


def apply_voice_intents_to_state(state: GameState, intents: List[VoiceIntentEN], *, utterance: str = "") -> None:
    """Mutates `state.projector_layers` and trajectory flags in-place."""
    layers = state.projector_layers
    for it in intents:
        if it == VoiceIntentEN.SHOW_BREAK_BOX:
            layers.show_break_box = True
        elif it == VoiceIntentEN.HIDE_BREAK_BOX:
            layers.show_break_box = False
        elif it == VoiceIntentEN.SHOW_BREAK_STRING:
            layers.show_break_string = True
        elif it == VoiceIntentEN.HIDE_BREAK_STRING:
            layers.show_break_string = False
        elif it == VoiceIntentEN.SHOW_SCORE:
            layers.show_score = True
        elif it == VoiceIntentEN.HIDE_SCORE:
            layers.show_score = False
        elif it == VoiceIntentEN.SHOW_MY_STATS:
            layers.show_my_stats = True
        elif it == VoiceIntentEN.HIDE_MY_STATS:
            layers.show_my_stats = False
        elif it == VoiceIntentEN.SHOW_BEST_NEXT_SHOT:
            layers.show_best_next_shot = True
        elif it == VoiceIntentEN.HIDE_BEST_NEXT_SHOT:
            layers.show_best_next_shot = False
        elif it == VoiceIntentEN.SHOW_ALT_NEXT_SHOT:
            layers.show_alt_next_shot = True
        elif it == VoiceIntentEN.HIDE_ALT_NEXT_SHOT:
            layers.show_alt_next_shot = False
        elif it == VoiceIntentEN.CYCLE_ALT_NEXT_SHOT:
            layers.cycle_alt_shot()
        elif it == VoiceIntentEN.CLEAR_HIGHLIGHTS:
            layers.highlighted_ball_labels = ()
        elif it == VoiceIntentEN.HIGHLIGHT_BALLS:
            parts = extract_highlight_ball_tokens(utterance)
            if parts:
                layers.highlighted_ball_labels = parts
        elif it == VoiceIntentEN.TRAJECTORY_ASSIST_ON:
            state.trajectory_assist_enabled = True
        elif it == VoiceIntentEN.TRAJECTORY_ASSIST_OFF:
            state.trajectory_assist_enabled = False
