from __future__ import annotations

from dataclasses import dataclass, field
import time

from core.sync_engine import LyricLine


@dataclass
class AppState:
    track_key: str = ""
    title: str = ""
    artist: str = ""
    album: str = ""
    player: str = ""
    playback_state: str = "Stopped"
    lyrics: list[LyricLine] = field(default_factory=list)
    lyrics_source: str = ""
    lyrics_loaded_at: float = 0.0
    lyrics_last_attempt_at: float = 0.0

    def set_track(self, track_key: str, title: str, artist: str, album: str, player: str) -> None:
        self.track_key = track_key
        self.title = title
        self.artist = artist
        self.album = album
        self.player = player

    def set_lyrics(self, lyrics: list[LyricLine], source: str) -> None:
        self.lyrics = lyrics
        self.lyrics_source = source
        self.lyrics_loaded_at = time.time()

    def mark_lyrics_attempt(self) -> None:
        self.lyrics_last_attempt_at = time.time()
