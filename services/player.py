from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
from typing import Optional


@dataclass
class TrackInfo:
    player: str
    title: str
    artist: str
    album: str
    status: str
    position_sec: float

    @property
    def track_key(self) -> str:
        return f"{self.artist}::{self.title}".lower().strip()


class PlayerService:
    YT_SUFFIX_RE = re.compile(r"\s*(\||-|–|—)\s*YouTube(\s*Music)?\s*$", re.IGNORECASE)
    BRACKET_RE = re.compile(r"\s*[\(\[][^\)\]]*(official|video|lyrics?|audio|hd|4k)[^\)\]]*[\)\]]\s*$", re.IGNORECASE)

    def _run(self, args: list[str]) -> str:
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def list_players(self) -> list[str]:
        raw = self._run(["playerctl", "-l"])
        if not raw:
            return []
        players = [line.strip() for line in raw.splitlines() if line.strip()]
        seen: set[str] = set()
        out: list[str] = []
        for player in players:
            if player not in seen:
                seen.add(player)
                out.append(player)
        return out

    def get_status(self, player: str) -> str:
        status = self._run(["playerctl", "-p", player, "status"])
        return status if status in {"Playing", "Paused", "Stopped"} else "Stopped"

    def get_active_player(self) -> Optional[str]:
        players = self.list_players()
        if not players:
            return None

        for player in players:
            if self.get_status(player) == "Playing":
                return player

        for player in players:
            if self.get_status(player) == "Paused":
                return player

        return players[0]

    def _clean(self, value: str, fallback: str = "Unknown") -> str:
        cleaned = value.strip()
        if not cleaned or cleaned.lower() in {"unknown", "(null)", "none"}:
            return fallback
        return cleaned

    def _normalize_by_player(self, player: str, title: str, artist: str) -> tuple[str, str]:
        t = title.strip()
        a = artist.strip()
        p = player.lower()

        if any(x in p for x in ["chromium", "firefox", "brave", "chrome", "edge"]):
            t = self.YT_SUFFIX_RE.sub("", t).strip()
            t = self.BRACKET_RE.sub("", t).strip()
            # Common browser format: "Artist - Title"
            if (" - " in t) and (a.lower() in {"unknown artist", "unknown", ""}):
                left, right = t.split(" - ", 1)
                if left and right:
                    a = left.strip()
                    t = right.strip()

        if "spotify" in p:
            t = self.BRACKET_RE.sub("", t).strip()

        return t or title, a or artist

    def get_metadata(self, player: str) -> tuple[str, str, str]:
        raw = self._run(
            [
                "playerctl",
                "-p",
                player,
                "metadata",
                "--format",
                "{{title}}\t{{artist}}\t{{album}}",
            ]
        )
        if not raw:
            return "Unknown Title", "Unknown Artist", ""

        parts = raw.split("\t")
        title = self._clean(parts[0] if len(parts) > 0 else "", fallback="Unknown Title")
        artist = self._clean(parts[1] if len(parts) > 1 else "", fallback="Unknown Artist")
        album = self._clean(parts[2] if len(parts) > 2 else "", fallback="")
        return title, artist, album

    def get_position(self, player: str) -> float:
        raw = self._run(["playerctl", "-p", player, "position"])
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0

    def get_track_info(self) -> Optional[TrackInfo]:
        player = self.get_active_player()
        if not player:
            return None

        title, artist, album = self.get_metadata(player)
        title, artist = self._normalize_by_player(player, title, artist)
        status = self.get_status(player)
        position = self.get_position(player)

        return TrackInfo(
            player=player,
            title=title,
            artist=artist,
            album=album,
            status=status,
            position_sec=position,
        )
