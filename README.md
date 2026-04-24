# LyricFetch (Wayland GTK4 Layer Shell)

Wayland-native synced lyrics overlay for Hyprland.

## Implemented

- MPRIS player detection via `playerctl`
- Metadata/state/position polling with per-player normalization (Spotify/browser/YouTube-style titles)
- LRCLIB fetch with normalization + `/api/search` fallback
- Local lyric cache in `~/.cache/lyrics-overlay`
- LRC parsing + current/prev/next sync engine
- Backend daemon writes `~/.cache/lyrics-overlay/state.json`
- Local socket event bus (`~/.cache/lyrics-overlay/events.sock`) for lower-latency UI updates
- GTK4 + `gtk4-layer-shell` transparent overlay UI
- True click-through (empty input region on surface)
- Draggable on-screen placement preview in settings GUI
- Live placement preview while dragging in settings GUI
- Per-monitor targeting
- Typography controls + animation presets + live preview
- Color modes: `solid`, `bg`, `rainbow`, `wal`, `auto_dynamic`
- Diagnostics window
- Service installer command + Hypr blur snippet writer

## Commands

- `python main.py all`
  Runs daemon + overlay.
- `python main.py daemon`
  Backend only.
- `python main.py overlay`
  Overlay only.
- `python main.py config`
  Settings GUI.
- `python main.py diagnostics`
  Diagnostics GUI.
- `python main.py debug`
  Terminal debug daemon.
- `python main.py install-services`
  Writes user systemd units + `~/.config/hypr/lyricfetch.conf` blur snippet.
- `python main.py install-services --enable`
  Writes and enables daemon/ui services immediately.

## Config Keys

Edit [config/config.json](/home/dhruv/LyricFetch/config/config.json):

- `position`: `free` | `top` | `bottom`
- `monitor`: `primary` or monitor connector name
- `render_x_pct`, `render_y_pct`
- `font_size`, `font_family`, `font_weight`, `letter_spacing`, `line_spacing`
- `line_width_percent`
- `visible_line_count`
- `offset_ms`
- `animation_preset`: `custom` | `minimal` | `smooth` | `snappy` | `cinematic`
- `animation_style`: `crossfade` | `line_flow_up` | `slide_up` | `slide_left_right` | `over_up_down`
- `animation_speed`
- `color_mode`: `solid` | `bg` | `rainbow` | `wal` | `auto_dynamic`
- `highlight_color`, `secondary_color`, `fade_color`
- `bg_opacity` (`bg` mode)
- `dynamic_sampling_backend`: `auto` | `grim`
- `dynamic_interval_ms`, `dynamic_hysteresis`, `dynamic_panel_boost` (`auto_dynamic` mode)
- `show_shadow`
- `hide_when_no_lyrics`
- `bg_blur_hint`
- `update_interval_ms`, `retry_interval_sec`

## Runtime Requirements

- Python 3.10+
- `playerctl`
- `grim` (recommended for `auto_dynamic`)
- `requests` Python package
- GTK4 + PyGObject + gtk4-layer-shell GIR

Arch example:

```bash
sudo pacman -S playerctl grim gtk4 gtk4-layer-shell python-gobject
pip install -r requirements.txt
```

## Hyprland Blur Hint

`install-services` writes `~/.config/hypr/lyricfetch.conf` containing:

- `layerrule = blur, lyricfetch`
- `layerrule = ignorezero, lyricfetch`
- `layerrule = xray 1, lyricfetch`

Include it in your Hypr config and reload Hyprland if needed.
# LyricsOverlay
