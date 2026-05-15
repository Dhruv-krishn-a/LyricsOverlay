from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any

from core.config import load_config
from core.event_bus import StateBusServer
from core.install import install_user_services
from core.state_manager import AppState
from core.state_file import StateFile
from core.sync_engine import SyncEngine
from services.lyrics import LyricsService
from services.player import PlayerService


def _terminal_render(payload: dict[str, Any]) -> None:
    print("\033[2J\033[H", end="")
    print("LyricFetch Daemon (debug)")
    print("=" * 48)
    if not payload.get("has_player"):
        print("No active player found.")
        return

    print(f"Player:       {payload.get('player', '')}")
    print(f"Now Playing:  {payload.get('artist', '')} - {payload.get('title', '')}")
    print(f"State:        {payload.get('playback_state', '')}")
    print(f"Position:     {payload.get('position_sec', 0.0):.2f}s")
    print(f"Lyrics:       {payload.get('lyrics_source', 'none')}")
    print(f"Status:       {payload.get('fetch_status', '')}")
    print("-" * 48)
    print(f"  {payload.get('prev_line', '')}")
    print(f"> {payload.get('curr_line', '')}")
    print(f"  {payload.get('next_line', '')}")


def _build_empty_payload(config: dict[str, Any]) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "version": 2,
        "ts": now_iso,
        "has_player": False,
        "player": "",
        "title": "",
        "artist": "",
        "album": "",
        "album_art": "",
        "track_key": "",
        "playback_state": "Stopped",
        "position_sec": 0.0,
        "lyrics_source": "",
        "lyrics_available": False,
        "has_synced_lyrics": False,
        "fetch_status": "idle",
        "prev_line": "",
        "curr_line": "",
        "next_line": "",
        "display_visible": True,
        "line_progress": 0.0,
        "ms_to_next_line": 0,
        "position": str(config.get("position", "free")),
        "monitor": str(config.get("monitor", "primary")),
        "render_x_pct": int(config.get("render_x_pct", 50)),
        "render_y_pct": int(config.get("render_y_pct", 85)),
        "font_size": int(config.get("font_size", 34)),
        "font_family": str(config.get("font_family", "JetBrains Mono, Sans")),
        "font_weight": int(config.get("font_weight", 850)),
        "letter_spacing": float(config.get("letter_spacing", 0.0)),
        "line_spacing": float(config.get("line_spacing", 1.12)),
        "highlight_color": str(config.get("highlight_color", "#ffffff")),
        "secondary_color": str(config.get("secondary_color", "#7ad7ff")),
        "fade_color": str(config.get("fade_color", "#9aa0a6")),
        "color_mode": str(config.get("color_mode", "solid")),
        "dynamic_sampling_backend": str(config.get("dynamic_sampling_backend", "auto")),
        "dynamic_interval_ms": int(config.get("dynamic_interval_ms", 320)),
        "dynamic_hysteresis": float(config.get("dynamic_hysteresis", 0.08)),
        "dynamic_panel_boost": float(config.get("dynamic_panel_boost", 0.18)),
        "bg_opacity": float(config.get("bg_opacity", 0.62)),
        "animation_speed": float(config.get("animation_speed", 0.2)),
        "animation_style": str(config.get("animation_style", "slide_up")),
        "animation_preset": str(config.get("animation_preset", "custom")),
        "offset_ms": int(config.get("offset_ms", 0)),
        "line_width_percent": int(config.get("line_width_percent", 70)),
        "visible_line_count": int(config.get("visible_line_count", 3)),
        "show_shadow": bool(config.get("show_shadow", True)),
        "hide_when_no_lyrics": bool(config.get("hide_when_no_lyrics", False)),
        "hide_on_pause": bool(config.get("hide_on_pause", False)),
        "bg_blur_hint": bool(config.get("bg_blur_hint", True)),
    }


def daemon_loop(debug_terminal: bool = False) -> None:
    player_service = PlayerService()
    lyrics_service = LyricsService()
    sync_engine = SyncEngine()
    state = AppState()
    state_file = StateFile()
    bus = StateBusServer()
    bus.start()

    try:
        while True:
            cfg = load_config()
            offset_sec = float(cfg.get("offset_ms", 0)) / 1000.0
            interval_sec = max(0.05, float(cfg.get("update_interval_ms", 100)) / 1000.0)
            retry_sec = max(2.0, float(cfg.get("retry_interval_sec", 8)))
            hide_when_no_lyrics = bool(cfg.get("hide_when_no_lyrics", False))
            hide_on_pause = bool(cfg.get("hide_on_pause", False))
            visible_line_count = max(1, int(cfg.get("visible_line_count", 3)))
            fetch_status = "ok"

            try:
                track = player_service.get_track_info()
                if not track:
                    state = AppState()
                    payload = _build_empty_payload(cfg)
                    payload["fetch_status"] = "no-player"
                    state_file.write(payload)
                    bus.publish(payload)
                    if debug_terminal:
                        _terminal_render(payload)
                    time.sleep(interval_sec)
                    continue

                state.playback_state = track.status
                if track.track_key != state.track_key:
                    state.set_track(track.track_key, track.title, track.artist, track.album, track.album_art, track.player)
                    state.set_lyrics([], "")
                    state.mark_lyrics_attempt()
                    state.fetch_status = "fetching"

                    def _do_fetch(t_key, t_title, t_artist, t_album, t_duration):
                        lyr = lyrics_service.fetch(t_title, t_artist, t_album, t_duration)
                        if state.track_key == t_key:
                            if lyr:
                                if lyr.synced:
                                    state.set_lyrics(sync_engine.parse_lrc(lyr.synced), lyr.source)
                                elif lyr.plain:
                                    state.set_lyrics(sync_engine.build_unsynced(lyr.plain), lyr.source)
                                state.fetch_status = "ok"
                            else:
                                state.fetch_status = "lyrics-not-found"

                    threading.Thread(
                        target=_do_fetch,
                        args=(track.track_key, track.title, track.artist, track.album, track.duration_sec),
                        daemon=True
                    ).start()
                    fetch_status = state.fetch_status

                elif not state.lyrics and state.fetch_status != "fetching" and (time.time() - state.lyrics_last_attempt_at) >= retry_sec:
                    state.mark_lyrics_attempt()
                    state.fetch_status = "fetching"
                    
                    def _do_retry(t_key, t_title, t_artist, t_album, t_duration):
                        lyr = lyrics_service.fetch(t_title, t_artist, t_album, t_duration)
                        if state.track_key == t_key:
                            if lyr:
                                if lyr.synced:
                                    state.set_lyrics(sync_engine.parse_lrc(lyr.synced), lyr.source)
                                elif lyr.plain:
                                    state.set_lyrics(sync_engine.build_unsynced(lyr.plain), lyr.source)
                                state.fetch_status = "ok"
                            else:
                                state.fetch_status = "retry-miss"
                                
                    threading.Thread(
                        target=_do_retry,
                        args=(track.track_key, track.title, track.artist, track.album, track.duration_sec),
                        daemon=True
                    ).start()
                    fetch_status = state.fetch_status
                else:
                    fetch_status = state.fetch_status

                position = max(0.0, track.position_sec + offset_sec)
                prev, curr, next_ = sync_engine.get_context(state.lyrics, position)
                window_lines, current_window_index = sync_engine.get_window(
                    state.lyrics, position, visible_line_count
                )
                _, _, next_t, progress = sync_engine.get_timing_info(state.lyrics, position)
                
                # Word and Timing Info
                idx, curr_t, next_t, progress = sync_engine.get_timing_info(state.lyrics, position)
                
                word_idx = -1
                if state.lyrics and 0 <= idx < len(state.lyrics):
                    current_line_obj = state.lyrics[idx]
                    word_idx, _ = sync_engine.get_word_info(current_line_obj, position, next_t)
                
                ms_to_next = int(max(0.0, ((next_t - position) * 1000.0))) if next_t is not None else 0

                lyrics_available = bool(state.lyrics)
                has_synced = bool(state.lyrics and state.lyrics_source.endswith("lrc"))

                display_visible = True
                if hide_on_pause and track.status == "Paused":
                    display_visible = False

                if not lyrics_available:
                    if hide_when_no_lyrics:
                        display_visible = False
                        prev = ""
                        curr = ""
                        next_ = ""
                        window_lines = []
                        current_window_index = 0
                    else:
                        if state.fetch_status == "fetching":
                            curr = "Fetching lyrics..."
                        elif state.fetch_status == "lyrics-not-found":
                            curr = "No lyrics found"
                        else:
                            curr = "No lyrics available"
                        window_lines = [curr]
                        current_window_index = 0

                payload = _build_empty_payload(cfg)
                payload.update(
                    {
                        "has_player": True,
                        "player": track.player,
                        "title": track.title,
                        "artist": track.artist,
                        "album": track.album,
                        "album_art": track.album_art,
                        "track_key": track.track_key,
                        "playback_state": track.status,
                        "position_sec": round(position, 3),
                        "lyrics_source": state.lyrics_source,
                        "lyrics_available": lyrics_available,
                        "has_synced_lyrics": has_synced,
                        "fetch_status": fetch_status,
                        "prev_line": prev,
                        "curr_line": curr,
                        "next_line": next_,
                        "window_lines": window_lines,
                        "current_window_index": current_window_index,
                        "current_word_index": word_idx,
                        "line_progress": round(progress, 4),
                        "ms_to_next_line": ms_to_next,
                        "display_visible": display_visible,
                    }
                )
                state_file.write(payload)
                bus.publish(payload)
                if debug_terminal:
                    _terminal_render(payload)
                time.sleep(interval_sec)
            except KeyboardInterrupt:
                break
            except Exception as exc:
                payload = _build_empty_payload(cfg)
                payload["curr_line"] = f"Runtime error: {exc}"
                payload["fetch_status"] = "runtime-error"
                state_file.write(payload)
                bus.publish(payload)
                if debug_terminal:
                    _terminal_render(payload)
                time.sleep(0.2)
    finally:
        bus.close()


def _can_import_gi() -> bool:
    try:
        import gi  # type: ignore

        _ = gi
        return True
    except ModuleNotFoundError:
        return False


def _resolve_layer_shell_lib() -> str | None:
    candidates = [
        "/usr/lib/libgtk4-layer-shell.so",
        "/usr/lib64/libgtk4-layer-shell.so",
        "/lib/libgtk4-layer-shell.so",
        "/lib64/libgtk4-layer-shell.so",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def _build_overlay_env() -> dict[str, str]:
    env = dict(os.environ)
    env["GDK_BACKEND"] = "wayland"
    env["XDG_SESSION_TYPE"] = "wayland"
    env.pop("DISPLAY", None)
    layer_shell_lib = _resolve_layer_shell_lib()
    if layer_shell_lib:
        preload = env.get("LD_PRELOAD", "").strip()
        parts = [p for p in preload.split(":") if p] if preload else []
        if layer_shell_lib not in parts:
            parts.insert(0, layer_shell_lib)
        env["LD_PRELOAD"] = ":".join(parts)
    return env


def _run_mode_subprocess(python_exe: str, mode: str, bootstrap_key: str | None = None) -> int:
    cmd = [python_exe, os.path.abspath(__file__), mode]
    env = _build_overlay_env() if mode in {"overlay", "diagnostics"} else dict(os.environ)
    if bootstrap_key:
        env[bootstrap_key] = "1"
    return subprocess.call(cmd, env=env)


def run_overlay() -> int:
    if os.environ.get("LYRICFETCH_OVERLAY_BOOTSTRAPPED") != "1":
        if _can_import_gi():
            return _run_mode_subprocess(sys.executable, "overlay", "LYRICFETCH_OVERLAY_BOOTSTRAPPED")
        return _run_mode_subprocess("/usr/bin/python3", "overlay", "LYRICFETCH_OVERLAY_BOOTSTRAPPED")

    if not _can_import_gi():
        print(
            "Overlay dependency missing: python 'gi' module not found.\n"
            "Install system packages (example Arch):\n"
            "  sudo pacman -S python-gobject gtk4 gtk4-layer-shell\n"
            "Then run again."
        )
        return 1

    from ui.gtk.overlay import run_overlay_app

    run_overlay_app()
    return 0


def run_config() -> int:
    if not _can_import_gi():
        if os.path.abspath(sys.executable) != "/usr/bin/python3":
            return _run_mode_subprocess("/usr/bin/python3", "config")
        print("Config UI requires PyGObject (gi). Install: sudo pacman -S python-gobject gtk4")
        return 1

    from ui.gtk.config_app import run_config_app

    run_config_app()
    return 0


def run_diagnostics() -> int:
    if not _can_import_gi():
        if os.path.abspath(sys.executable) != "/usr/bin/python3":
            return _run_mode_subprocess("/usr/bin/python3", "diagnostics")
        print("Diagnostics UI requires PyGObject (gi). Install: sudo pacman -S python-gobject gtk4")
        return 1

    from ui.gtk.diagnostics import run_diagnostics_app

    run_diagnostics_app()
    return 0


def run_install_services(enable_now: bool) -> int:
    project_root = Path(__file__).resolve().parent
    paths = install_user_services(project_root, sys.executable, enable_now=enable_now)
    print("Installed systemd user units:")
    for p in paths:
        print(f"- {p}")
    if not enable_now:
        print("Next:")
        print("  systemctl --user daemon-reload")
        print("  systemctl --user enable --now lyrics-overlay-daemon.service")
        print("  systemctl --user enable --now lyrics-overlay-ui.service")
    return 0


def run_all() -> None:
    child = subprocess.Popen([sys.executable, __file__, "daemon"])
    try:
        run_overlay()
    finally:
        child.terminate()
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LyricFetch daemon + GTK layer-shell overlay")
    parser.add_argument(
        "mode",
        nargs="?",
        default="all",
        choices=["daemon", "overlay", "all", "debug", "config", "diagnostics", "install-services"],
        help="Run backend daemon, overlay UI, settings UI, diagnostics, installer, both, or debug terminal daemon",
    )
    parser.add_argument("--enable", action="store_true", help="Only for install-services: enable and start services")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "daemon":
        daemon_loop(debug_terminal=False)
    elif args.mode == "overlay":
        raise SystemExit(run_overlay())
    elif args.mode == "config":
        raise SystemExit(run_config())
    elif args.mode == "diagnostics":
        raise SystemExit(run_diagnostics())
    elif args.mode == "install-services":
        raise SystemExit(run_install_services(enable_now=bool(args.enable)))
    elif args.mode == "debug":
        daemon_loop(debug_terminal=True)
    else:
        run_all()


if __name__ == "__main__":
    main()
