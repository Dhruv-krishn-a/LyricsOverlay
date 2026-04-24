from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlowDecision:
    render_lines: list[str]
    render_index: int
    transition: str | None
    repaint_only: bool


class LineFlowUpAnimator:
    """
    Hybrid lyric flow decision helper.

    Rules:
    - Detect a real sliding window shift first (best case).
    - Fallback to current_index delta when the window itself did not shift cleanly.
    - Repaint only when nothing meaningful changed.
    """

    def __init__(self) -> None:
        self._prev_index: int | None = None
        self._prev_lines: list[str] = []

    def reset(self) -> None:
        self._prev_index = None
        self._prev_lines = []

    @staticmethod
    def _detect_window_shift(old: list[str], new: list[str]) -> str | None:
        """
        Returns:
            "up"   -> window moved forward
            "down" -> window moved backward
            None   -> no clean slide detected
        """
        if not old or not new:
            return None

        max_shift = min(len(old), len(new)) - 1
        if max_shift < 1:
            return None

        for distance in range(1, max_shift + 1):
            # Old window shifted up: old[distance:] matches new[:-distance]
            if old[distance:] == new[:-distance]:
                return "up"

            # Old window shifted down: old[:-distance] matches new[distance:]
            if old[:-distance] == new[distance:]:
                return "down"

        return None

    def decide(self, lines: list[str], current_index: int) -> FlowDecision:
        new_lines = list(lines)

        if not new_lines:
            self._prev_lines = []
            self._prev_index = 0
            return FlowDecision([], 0, None, True)

        current_index = max(0, min(current_index, len(new_lines) - 1))

        if self._prev_index is None:
            self._prev_lines = new_lines
            self._prev_index = current_index
            return FlowDecision(new_lines, current_index, None, False)

        same_lines = self._prev_lines == new_lines
        same_index = self._prev_index == current_index

        # Absolute no-op.
        if same_lines and same_index:
            return FlowDecision(new_lines, current_index, None, True)

        # Best signal: actual sliding window movement.
        shift_transition = self._detect_window_shift(self._prev_lines, new_lines)

        # Fallback signal: highlight moved by one step inside the same window.
        delta = current_index - self._prev_index

        if shift_transition is not None:
            transition = shift_transition
            repaint_only = False
        elif delta == 1:
            transition = "up"
            repaint_only = False
        elif delta == -1:
            transition = "down"
            repaint_only = False
        elif same_lines:
            transition = None
            repaint_only = True
        else:
            # Jump, seek, reload, or mismatch.
            transition = None
            repaint_only = False

        self._prev_lines = new_lines
        self._prev_index = current_index

        return FlowDecision(
            render_lines=new_lines,
            render_index=current_index,
            transition=transition,
            repaint_only=repaint_only,
        )