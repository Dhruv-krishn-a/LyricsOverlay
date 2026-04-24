from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import re


TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]")


@dataclass(order=True)
class LyricLine:
    time_sec: float
    text: str


class SyncEngine:
    def parse_lrc(self, lrc_text: str) -> list[LyricLine]:
        lines: list[LyricLine] = []
        for raw_line in lrc_text.splitlines():
            text = TIMESTAMP_RE.sub("", raw_line).strip()
            timestamps = TIMESTAMP_RE.findall(raw_line)
            for mm, ss, frac in timestamps:
                frac_part = float(f"0.{frac}") if frac else 0.0
                t = int(mm) * 60 + int(ss) + frac_part
                lines.append(LyricLine(time_sec=t, text=text))

        lines.sort(key=lambda x: x.time_sec)
        return lines

    def build_unsynced(self, text: str, sec_per_line: float = 4.0) -> list[LyricLine]:
        lines: list[LyricLine] = []
        t = 0.0
        for raw in text.splitlines():
            clean = raw.strip()
            if clean:
                lines.append(LyricLine(time_sec=t, text=clean))
                t += sec_per_line
        return lines

    def get_context(
        self,
        lyrics: list[LyricLine],
        time_sec: float,
    ) -> tuple[str, str, str]:
        if not lyrics:
            return "", "", ""

        stamps = [line.time_sec for line in lyrics]
        idx = bisect_right(stamps, time_sec) - 1
        idx = max(0, min(idx, len(lyrics) - 1))

        prev_line = lyrics[idx - 1].text if idx - 1 >= 0 else ""
        curr_line = lyrics[idx].text
        next_line = lyrics[idx + 1].text if idx + 1 < len(lyrics) else ""

        return prev_line, curr_line, next_line

    def get_window(
        self,
        lyrics: list[LyricLine],
        time_sec: float,
        visible_count: int,
    ) -> tuple[list[str], int]:
        if not lyrics:
            return [], 0

        count = max(1, int(visible_count))
        stamps = [line.time_sec for line in lyrics]
        idx = bisect_right(stamps, time_sec) - 1
        idx = max(0, min(idx, len(lyrics) - 1))

        before = count // 2
        after = count - before - 1
        start = max(0, idx - before)
        end = min(len(lyrics), idx + after + 1)

        # Keep requested window size when near song edges.
        window_len = end - start
        if window_len < count:
            missing = count - window_len
            left_expand = min(start, missing)
            start -= left_expand
            missing -= left_expand
            end = min(len(lyrics), end + missing)

        lines = [line.text for line in lyrics[start:end]]
        current_in_window = idx - start
        return lines, current_in_window

    def get_timing_info(
        self,
        lyrics: list[LyricLine],
        time_sec: float,
    ) -> tuple[int, float | None, float | None, float]:
        if not lyrics:
            return 0, None, None, 0.0
        stamps = [line.time_sec for line in lyrics]
        idx = bisect_right(stamps, time_sec) - 1
        idx = max(0, min(idx, len(lyrics) - 1))
        curr_t = lyrics[idx].time_sec
        next_t = lyrics[idx + 1].time_sec if idx + 1 < len(lyrics) else None
        progress = 0.0
        if next_t is not None and next_t > curr_t:
            progress = max(0.0, min(1.0, (time_sec - curr_t) / (next_t - curr_t)))
        return idx, curr_t, next_t, progress
