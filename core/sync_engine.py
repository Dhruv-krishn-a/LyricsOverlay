from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
import re


TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]")


@dataclass(order=True)
class LyricWord:
    time_sec: float
    text: str


@dataclass(order=True)
class LyricLine:
    time_sec: float
    text: str
    words: list[LyricWord] = field(default_factory=list)


WORD_TIMESTAMP_RE = re.compile(r"<(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?>")


class SyncEngine:
    def _insert_gaps(self, lines: list[LyricLine], min_gap: float = 4.0) -> list[LyricLine]:
        if not lines:
            return lines
        out: list[LyricLine] = []
        
        # Intro gap (if first lyric is far into the song)
        if lines[0].time_sec > min_gap:
            out.append(LyricLine(time_sec=0.1, text="---INSTRUMENTAL---", words=[]))
            
        for i in range(len(lines) - 1):
            out.append(lines[i])
            if lines[i].text.strip() == "---INSTRUMENTAL---":
                continue
                
            curr_t = lines[i].time_sec
            next_t = lines[i+1].time_sec
            gap = next_t - curr_t
            
            # Estimate how long the current line takes to sing.
            # Assume roughly 1.0 seconds per word (generous for stretched vocals)
            # Minimum 4.0s duration, maximum 15.0s.
            word_count = len(lines[i].text.split())
            estimated_duration = max(4.0, min(15.0, word_count * 1.0))
            
            # If the gap is significantly longer than the estimated singing time + buffer
            if gap >= (estimated_duration + min_gap):
                # Put the instrumental marker after the singing is likely done
                gap_time = curr_t + estimated_duration + 1.0
                out.append(LyricLine(time_sec=gap_time, text="---INSTRUMENTAL---", words=[]))
                
        out.append(lines[-1])
        return out

    def parse_lrc(self, lrc_text: str) -> list[LyricLine]:
        lines: list[LyricLine] = []
        for raw_line in lrc_text.splitlines():
            # Line-level timestamp
            line_match = TIMESTAMP_RE.search(raw_line)
            if not line_match:
                continue

            mm, ss, frac = line_match.groups()
            frac_part = float(f"0.{frac}") if frac else 0.0
            line_time = int(mm) * 60 + int(ss) + frac_part

            # Clean line for text-only search
            clean_line = TIMESTAMP_RE.sub("", raw_line).strip()
            
            # Word-level parsing (Enhanced LRC)
            words: list[LyricWord] = []
            word_matches = list(WORD_TIMESTAMP_RE.finditer(clean_line))
            
            if word_matches:
                # If enhanced LRC exists
                for i, m in enumerate(word_matches):
                    w_mm, w_ss, w_frac = m.groups()
                    w_frac_part = float(f"0.{w_frac}") if w_frac else 0.0
                    w_time = int(w_mm) * 60 + int(w_ss) + w_frac_part
                    
                    # Text for this word is everything between this match and the next
                    start = m.end()
                    end = word_matches[i+1].start() if i+1 < len(word_matches) else len(clean_line)
                    word_text = clean_line[start:end].strip()
                    if word_text:
                        words.append(LyricWord(time_sec=w_time, text=word_text))
                
                # The "clean" text should now have tags removed
                display_text = WORD_TIMESTAMP_RE.sub("", clean_line).strip()
            else:
                # Standard LRC: split by space and estimate word timing
                display_text = clean_line
                raw_words = display_text.split()
                if raw_words:
                    # We'll set these later or leave empty if duration is unknown
                    pass

            lines.append(LyricLine(time_sec=line_time, text=display_text, words=words))

        lines.sort(key=lambda x: x.time_sec)
        return self._insert_gaps(lines)

    def get_word_info(
        self,
        line: LyricLine,
        time_sec: float,
        next_line_time: float | None
    ) -> tuple[int, float]:
        """Returns (current_word_index, line_percent_progress)"""
        if not line.words:
            # Fallback: Simulate word progress based on line duration
            if next_line_time is None or next_line_time <= line.time_sec:
                return 0, 0.0
            
            duration = next_line_time - line.time_sec
            progress = max(0.0, min(1.0, (time_sec - line.time_sec) / duration))
            
            words = line.text.split()
            if not words: return 0, progress
            
            word_idx = int(progress * len(words))
            return min(word_idx, len(words) - 1), progress

        # Real enhanced LRC logic
        idx = bisect_right([w.time_sec for w in line.words], time_sec) - 1
        idx = max(0, min(idx, len(line.words) - 1))
        
        # Calculate progress through the whole line
        if next_line_time:
            line_duration = next_line_time - line.time_sec
            line_progress = max(0.0, min(1.0, (time_sec - line.time_sec) / line_duration))
        else:
            line_progress = 0.0
            
        return idx, line_progress

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
