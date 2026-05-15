from __future__ import annotations

from dataclasses import dataclass
import re
import threading
import time
from typing import Optional

import gi
gi.require_version("Playerctl", "2.0")
from gi.repository import Playerctl, GLib


@dataclass
class TrackInfo:
    player: str
    title: str
    artist: str
    album: str
    album_art: str
    status: str
    position_sec: float
    duration_sec: float

    @property
    def track_key(self) -> str:
        return f"{self.artist}::{self.title}::{self.duration_sec}".lower().strip()


class PlayerService:
    YT_SUFFIX_RE = re.compile(r"\s*(\||-|–|—)\s*YouTube(\s*Music)?\s*$", re.IGNORECASE)
    BRACKET_RE = re.compile(r"\s*[\(\[][^\)\]]*(official|video|lyrics?|audio|hd|4k)[^\)\]]*[\)\]]\s*$", re.IGNORECASE)

    def __init__(self) -> None:
        self._active_player: Playerctl.Player | None = None
        self._players: dict[Playerctl.PlayerName, Playerctl.Player] = {}

        # Local state for interpolation
        self._lock = threading.Lock()
        self._last_position_us = 0
        self._last_update_time = time.monotonic()

        # Start a GLib main loop in a background thread to handle DBus events
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        # Wait until the manager is initialized by the background thread
        while not hasattr(self, 'manager'):
            time.sleep(0.01)

    def _run_loop(self) -> None:
        context = GLib.MainContext.new()
        context.push_thread_default()
        
        self.manager = Playerctl.PlayerManager()
        self.manager.connect("name-appeared", self._on_name_appeared)
        self.manager.connect("player-vanished", self._on_player_vanished)

        # Initialize existing players
        for name in self.manager.props.player_names:
            self._init_player(name)
            
        loop = GLib.MainLoop.new(context, False)
        loop.run()

    def _init_player(self, name: Playerctl.PlayerName) -> None:
        player = Playerctl.Player.new_from_name(name)
        player.connect("playback-status::playing", self._on_playback_status, name)
        player.connect("playback-status::paused", self._on_playback_status, name)
        player.connect("playback-status::stopped", self._on_playback_status, name)
        player.connect("metadata", self._on_metadata, name)
        player.connect("seeked", self._on_seeked, name)
        self.manager.manage_player(player)
        self._players[name] = player
        self._update_active_player()

    def _on_name_appeared(self, manager: Playerctl.PlayerManager, name: Playerctl.PlayerName) -> None:
        self._init_player(name)

    def _on_player_vanished(self, manager: Playerctl.PlayerManager, player: Playerctl.Player) -> None:
        name = player.props.player_name
        if name in self._players:
            del self._players[name]
        self._update_active_player()

    def _on_playback_status(self, player: Playerctl.Player, status: Playerctl.PlaybackStatus, name: Playerctl.PlayerName) -> None:
        self._update_active_player()
        self._resync_position(player)

    def _on_metadata(self, player: Playerctl.Player, metadata: GLib.Variant, name: Playerctl.PlayerName) -> None:
        self._update_active_player()
        self._resync_position(player)

    def _on_seeked(self, player: Playerctl.Player, position: int, name: Playerctl.PlayerName) -> None:
        if self._active_player and self._active_player.props.player_name == name:
            with self._lock:
                self._last_position_us = position
                self._last_update_time = time.monotonic()

    def _resync_position(self, player: Playerctl.Player) -> None:
        if self._active_player and self._active_player == player:
            try:
                pos = player.get_position()
                with self._lock:
                    self._last_position_us = pos
                    self._last_update_time = time.monotonic()
            except Exception:
                pass

    def _update_active_player(self) -> None:
        players = self.manager.props.players
        if not players:
            with self._lock:
                self._active_player = None
            return

        # Prefer Playing
        for player in players:
            if player.props.playback_status == Playerctl.PlaybackStatus.PLAYING:
                if self._active_player != player:
                    with self._lock:
                        self._active_player = player
                    self._resync_position(player)
                return

        # Then Paused
        for player in players:
            if player.props.playback_status == Playerctl.PlaybackStatus.PAUSED:
                if self._active_player != player:
                    with self._lock:
                        self._active_player = player
                    self._resync_position(player)
                return

        with self._lock:
            self._active_player = players[0]
            self._resync_position(players[0])

    def _clean(self, value: str, fallback: str = "Unknown") -> str:
        if not value:
            return fallback
        cleaned = value.strip()
        if not cleaned or cleaned.lower() in {"unknown", "(null)", "none"}:
            return fallback
        return cleaned

    def _normalize_by_player(self, player_name: str, title: str, artist: str) -> tuple[str, str]:
        t = title.strip()
        a = artist.strip()
        p = player_name.lower()

        if any(x in p for x in ["chromium", "firefox", "brave", "chrome", "edge"]):
            t = self.YT_SUFFIX_RE.sub("", t).strip()
            t = self.BRACKET_RE.sub("", t).strip()
            if (" - " in t) and (a.lower() in {"unknown artist", "unknown", ""}):
                left, right = t.split(" - ", 1)
                if left and right:
                    a = left.strip()
                    t = right.strip()

        if "spotify" in p:
            t = self.BRACKET_RE.sub("", t).strip()

        return t or title, a or artist

    def get_track_info(self) -> Optional[TrackInfo]:
        with self._lock:
            player = self._active_player
            last_pos_us = self._last_position_us
            last_time = self._last_update_time

        if not player:
            return None

        try:
            player_name = player.props.player_name
            title = self._clean(player.get_title(), "Unknown Title")
            artist = self._clean(player.get_artist(), "Unknown Artist")
            album = self._clean(player.get_album(), "")
            
            # Fetch Album Art & Duration
            duration_sec = 0.0
            try:
                metadata = player.props.metadata
                album_art = ""
                if metadata:
                    if "mpris:artUrl" in metadata:
                        album_art = metadata["mpris:artUrl"]
                    if "mpris:length" in metadata:
                        # length is in microseconds
                        duration_sec = float(metadata["mpris:length"]) / 1_000_000.0
            except Exception:
                album_art = ""

            title, artist = self._normalize_by_player(player_name, title, artist)
            
            status_enum = player.props.playback_status
            if status_enum == Playerctl.PlaybackStatus.PLAYING:
                status = "Playing"
            elif status_enum == Playerctl.PlaybackStatus.PAUSED:
                status = "Paused"
            else:
                status = "Stopped"

            # Interpolate position
            now = time.monotonic()
            if status == "Playing":
                current_pos_us = last_pos_us + int((now - last_time) * 1_000_000)
            else:
                current_pos_us = last_pos_us

            # Periodically force a resync to fix drift (every 5 seconds)
            if (now - last_time) > 5.0:
                self._resync_position(player)

            position_sec = current_pos_us / 1_000_000.0

            return TrackInfo(
                player=player_name,
                title=title,
                artist=artist,
                album=album,
                album_art=album_art,
                status=status,
                position_sec=max(0.0, position_sec),
                duration_sec=duration_sec,
            )
        except Exception:
            return None
