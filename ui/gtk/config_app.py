from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, Gtk

from core.config import DEFAULT_CONFIG, load_config, save_config


PRESETS: dict[str, dict[str, Any]] = {
    "custom": {},
    "minimal": {"animation_style": "crossfade", "animation_speed": 0.18, "show_shadow": False, "font_weight": 700},
    "smooth": {"animation_style": "line_flow_up", "animation_speed": 0.28, "show_shadow": True, "font_weight": 800},
    "snappy": {"animation_style": "slide_left_right", "animation_speed": 0.12, "show_shadow": True, "font_weight": 850},
    "cinematic": {"animation_style": "line_flow_up", "animation_speed": 0.45, "show_shadow": True, "font_weight": 900},
}


class ConfigWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title="LyricFetch Settings")
        self.set_default_size(720, 900)

        self.preview_w = 520
        self.preview_h = 292
        self.marker_w = 130
        self.marker_h = 52
        self.marker_x = 0.0
        self.marker_y = 0.0
        self.drag_start_x = 0.0
        self.drag_start_y = 0.0
        self._live_apply_source_id = 0

        self.config = load_config()
        self._preview_idx = 0
        self._preview_lines = [
            "A sky full of stars, and a line of code",
            "Sync with the beat, not a frame behind",
            "Now playing over the city lights",
            "Lyrics flowing clean on Hyprland",
        ]

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        root.set_margin_start(16)
        root.set_margin_end(16)

        header = Gtk.Label()
        header.set_markup("<b>LyricFetch Overlay Settings</b>")
        header.set_xalign(0)
        root.append(header)

        self.position_combo = self._combo(["free", "top", "bottom"], str(self.config.get("position", "free")))
        root.append(self._row("Placement Mode", self.position_combo))

        monitor_options = self._monitor_options()
        self.monitor_combo = self._combo(monitor_options, str(self.config.get("monitor", "primary")))
        root.append(self._row("Monitor", self.monitor_combo))

        self.preview_fixed = Gtk.Fixed()
        self.preview_fixed.set_size_request(self.preview_w, self.preview_h)
        self.preview_fixed.add_css_class("preview-screen")

        self.preview_bg = Gtk.DrawingArea()
        self.preview_bg.set_size_request(self.preview_w, self.preview_h)
        self.preview_bg.add_css_class("preview-bg")
        self.preview_fixed.put(self.preview_bg, 0, 0)

        self.marker = Gtk.Frame()
        self.marker.set_size_request(self.marker_w, self.marker_h)
        self.marker.add_css_class("preview-marker")
        marker_label = Gtk.Label(label="Lyrics")
        marker_label.add_css_class("preview-marker-label")
        self.marker.set_child(marker_label)

        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.marker.add_controller(drag)

        self.preview_fixed.put(self.marker, 0, 0)
        self.preview_hint = Gtk.Label(label="Drag rectangle to place overlay")
        self.preview_hint.set_xalign(0)
        self.live_place_switch = Gtk.Switch()
        self.live_place_switch.set_active(True)

        root.append(self._row("On-Screen Position", self.preview_fixed))
        root.append(self.preview_hint)
        root.append(self._row("Live Placement Preview", self.live_place_switch))

        self.sample_frame = Gtk.Frame()
        self.sample_frame.add_css_class("sample-frame")
        sample_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.sample_prev = Gtk.Label(label="")
        self.sample_curr = Gtk.Label(label="")
        self.sample_next = Gtk.Label(label="")
        self.sample_prev.add_css_class("sample-prev")
        self.sample_curr.add_css_class("sample-curr")
        self.sample_next.add_css_class("sample-next")
        for lbl in [self.sample_prev, self.sample_curr, self.sample_next]:
            lbl.set_wrap(True)
            lbl.set_xalign(0.5)
            lbl.set_justify(Gtk.Justification.CENTER)
        sample_box.append(self.sample_prev)
        sample_box.append(self.sample_curr)
        sample_box.append(self.sample_next)
        self.sample_frame.set_child(sample_box)
        root.append(self._row("Live Preview", self.sample_frame))

        self.preset_combo = self._combo(list(PRESETS.keys()), str(self.config.get("animation_preset", "custom")))
        preset_btn = Gtk.Button(label="Apply Preset")
        preset_btn.connect("clicked", self._on_apply_preset)
        preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        preset_row.append(self.preset_combo)
        preset_row.append(preset_btn)
        root.append(self._row("Animation Preset", preset_row))

        self.font_size = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 14, 96, 1)
        self.font_size.set_draw_value(True)
        root.append(self._row("Font Size", self.font_size))

        self.font_family = Gtk.Entry()
        root.append(self._row("Font Family", self.font_family))

        self.font_weight = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 300, 900, 50)
        self.font_weight.set_draw_value(True)
        root.append(self._row("Font Weight", self.font_weight))

        self.letter_spacing = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -1.0, 4.0, 0.1)
        self.letter_spacing.set_digits(1)
        self.letter_spacing.set_draw_value(True)
        root.append(self._row("Letter Spacing", self.letter_spacing))

        self.line_spacing = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.9, 1.8, 0.02)
        self.line_spacing.set_digits(2)
        self.line_spacing.set_draw_value(True)
        root.append(self._row("Line Spacing", self.line_spacing))

        self.line_width = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 35, 95, 1)
        self.line_width.set_draw_value(True)
        root.append(self._row("Line Width %", self.line_width))

        self.visible_lines = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 11, 1)
        self.visible_lines.set_draw_value(True)
        root.append(self._row("Visible Line Count", self.visible_lines))

        self.offset = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -2000, 2000, 10)
        self.offset.set_draw_value(True)
        root.append(self._row("Sync Offset (ms)", self.offset))

        self.anim_speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.05, 2.0, 0.05)
        self.anim_speed.set_digits(2)
        self.anim_speed.set_draw_value(True)
        root.append(self._row("Animation Speed (s)", self.anim_speed))

        self.anim_style = self._combo(
            ["crossfade", "line_flow_up", "slide_up", "slide_left_right", "over_up_down"],
            str(self.config.get("animation_style", "slide_up")),
        )
        root.append(self._row("Animation Style", self.anim_style))

        self.color_mode = self._combo(
            ["solid", "bg", "rainbow", "wal", "auto_dynamic"],
            str(self.config.get("color_mode", "solid")),
        )
        root.append(self._row("Color Mode", self.color_mode))

        self.dynamic_backend = self._combo(
            ["auto", "grim"],
            str(self.config.get("dynamic_sampling_backend", "auto")),
        )
        root.append(self._row("Dynamic Backend", self.dynamic_backend))

        self.dynamic_interval = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 120, 1200, 20)
        self.dynamic_interval.set_draw_value(True)
        root.append(self._row("Dynamic Interval (ms)", self.dynamic_interval))

        self.dynamic_hysteresis = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.05, 1.5, 0.05)
        self.dynamic_hysteresis.set_digits(2)
        self.dynamic_hysteresis.set_draw_value(True)
        root.append(self._row("Dynamic Hysteresis (contrast)", self.dynamic_hysteresis))

        self.dynamic_panel_boost = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 0.5, 0.01)
        self.dynamic_panel_boost.set_digits(2)
        self.dynamic_panel_boost.set_draw_value(True)
        root.append(self._row("Dynamic Panel Boost", self.dynamic_panel_boost))

        self.bg_opacity = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.05, 0.95, 0.01)
        self.bg_opacity.set_digits(2)
        self.bg_opacity.set_draw_value(True)
        root.append(self._row("BG Opacity (bg mode)", self.bg_opacity))

        self.highlight = Gtk.Entry()
        root.append(self._row("Highlight Color", self.highlight))

        self.secondary = Gtk.Entry()
        root.append(self._row("Secondary Color", self.secondary))

        self.fade = Gtk.Entry()
        root.append(self._row("Fade Color", self.fade))

        self.shadow_switch = Gtk.Switch()
        root.append(self._row("Text Shadow", self.shadow_switch))

        self.hide_no_lyrics = Gtk.Switch()
        root.append(self._row("Hide If No Lyrics", self.hide_no_lyrics))

        self.blur_hint = Gtk.Switch()
        root.append(self._row("BG Blur Hint (Hypr)", self.blur_hint))

        self.status = Gtk.Label(label="Changes are applied to config/config.json")
        self.status.set_xalign(0)
        root.append(self.status)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        apply_btn = Gtk.Button(label="Apply")
        save_btn = Gtk.Button(label="Save")
        reset_btn = Gtk.Button(label="Reset Defaults")

        apply_btn.connect("clicked", self._on_apply)
        save_btn.connect("clicked", self._on_save)
        reset_btn.connect("clicked", self._on_reset)

        buttons.append(apply_btn)
        buttons.append(save_btn)
        buttons.append(reset_btn)
        root.append(buttons)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(root)

        self._preview_css = Gtk.CssProvider()
        self._apply_styles()
        self._apply_to_widgets(self.config)
        self._connect_preview_watchers()
        self._tick_preview()
        GLib.timeout_add(1400, self._tick_preview)

        self.set_child(scroll)

    def _monitor_options(self) -> list[str]:
        options = ["primary"]
        display = Gdk.Display.get_default()
        if not display:
            return options
        monitors = display.get_monitors()
        if not monitors:
            return options
        for i in range(monitors.get_n_items()):
            mon = monitors.get_item(i)
            if not mon:
                continue
            name = f"monitor-{i}"
            if hasattr(mon, "get_connector"):
                try:
                    connector = mon.get_connector()
                    if connector:
                        name = connector
                except Exception:
                    pass
            options.append(name)
        return options

    def _apply_styles(self) -> None:
        css = Gtk.CssProvider()
        css.load_from_data(
            b"""
.preview-screen { background: transparent; }
.preview-bg {
  background-image: linear-gradient(135deg, rgba(28,36,54,0.85), rgba(15,22,34,0.85));
  border-radius: 12px;
  border: 1px solid rgba(180, 194, 213, 0.35);
}
.preview-marker {
  background: rgba(255,255,255,0.14);
  border: 1px solid rgba(122, 215, 255, 0.9);
  border-radius: 8px;
}
.preview-marker-label {
  font-weight: 700;
}
.sample-frame {
  border: 1px solid rgba(255,255,255,0.20);
  border-radius: 10px;
  padding: 10px;
}
"""
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self._preview_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )

    def _connect_preview_watchers(self) -> None:
        controls = [
            self.font_size,
            self.font_weight,
            self.letter_spacing,
            self.line_spacing,
            self.bg_opacity,
            self.visible_lines,
            self.color_mode,
            self.dynamic_backend,
            self.dynamic_interval,
            self.dynamic_hysteresis,
            self.dynamic_panel_boost,
            self.highlight,
            self.secondary,
            self.fade,
            self.shadow_switch,
            self.font_family,
        ]
        for c in controls:
            if isinstance(c, Gtk.Scale):
                c.connect("value-changed", lambda *_: self._refresh_preview_style())
            elif isinstance(c, Gtk.Entry):
                c.connect("changed", lambda *_: self._refresh_preview_style())
            elif isinstance(c, Gtk.DropDown):
                c.connect("notify::selected", lambda *_: self._refresh_preview_style())
            elif isinstance(c, Gtk.Switch):
                c.connect("notify::active", lambda *_: self._refresh_preview_style())

    def _tick_preview(self) -> bool:
        self._preview_idx = (self._preview_idx + 1) % len(self._preview_lines)
        i = self._preview_idx
        prev_i = (i - 1) % len(self._preview_lines)
        next_i = (i + 1) % len(self._preview_lines)
        self.sample_prev.set_text(self._preview_lines[prev_i])
        self.sample_curr.set_text(self._preview_lines[i])
        self.sample_next.set_text(self._preview_lines[next_i])
        return True

    def _refresh_preview_style(self) -> None:
        font_size = int(self.font_size.get_value())
        weight = int(self.font_weight.get_value())
        letter = float(self.letter_spacing.get_value())
        line = float(self.line_spacing.get_value())
        family = self.font_family.get_text().strip() or "JetBrains Mono, Sans"
        highlight = self.highlight.get_text().strip() or "#ffffff"
        secondary = self.secondary.get_text().strip() or "#7ad7ff"
        fade = self.fade.get_text().strip() or "#9aa0a6"
        color_mode = self._get_combo_value(self.color_mode) or "solid"
        dynamic_interval = int(self.dynamic_interval.get_value())
        dynamic_hysteresis = float(self.dynamic_hysteresis.get_value())
        dynamic_panel_boost = float(self.dynamic_panel_boost.get_value())
        shadow = "text-shadow: 0 2px 10px rgba(0,0,0,0.5);" if self.shadow_switch.get_active() else ""
        panel = "background: transparent; border: none;"
        if color_mode == "bg":
            op = float(self.bg_opacity.get_value())
            panel = f"background: rgba(18,22,28,{op:.3f}); border: 1px solid rgba(255,255,255,0.18); border-radius: 10px;"
        elif color_mode == "auto_dynamic":
            if dynamic_panel_boost > 0.01:
                op = min(0.96, float(self.bg_opacity.get_value()) + dynamic_panel_boost)
                panel = f"background: rgba(16,20,28,{op:.3f}); border: 1px solid rgba(255,255,255,0.18); border-radius: 10px;"
            else:
                panel = "background: transparent; border: none;"
            highlight = "#f4f7fb"
            secondary = "#c8d8ea"
            fade = "#9aafc6"
        gradient = ""
        if color_mode == "rainbow":
            gradient = "background-image: linear-gradient(90deg,#ff4f7d,#ffc857,#5dd39e,#50c5ff,#c084fc); color: transparent; background-clip: text;"

        self._preview_css.load_from_data(
            f"""
.sample-frame {{ {panel} padding: 10px; }}
.sample-prev {{ color: {fade}; font-size: {max(12,int(font_size*0.62))}px; font-family: '{family}'; font-weight: {max(300, int(weight*0.65))}; letter-spacing: {letter}px; line-height: {line}; opacity: 0.60; {shadow} }}
.sample-next {{ color: {secondary}; font-size: {max(12,int(font_size*0.62))}px; font-family: '{family}'; font-weight: {max(300, int(weight*0.65))}; letter-spacing: {letter}px; line-height: {line}; opacity: 0.72; {shadow} }}
.sample-curr {{ color: {highlight}; font-size: {font_size}px; font-family: '{family}'; font-weight: {weight}; letter-spacing: {letter}px; line-height: {line}; {shadow} {gradient} }}
""".encode("utf-8")
        )

    def _combo(self, options: list[str], current: str) -> Gtk.DropDown:
        dd = Gtk.DropDown.new_from_strings(options)
        try:
            idx = options.index(current)
        except ValueError:
            idx = 0
        dd.set_selected(idx)
        return dd

    def _row(self, label: str, widget: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        lbl = Gtk.Label(label=label)
        lbl.set_xalign(0)
        row.append(lbl)
        row.append(widget)
        return row

    def _get_combo_value(self, dd: Gtk.DropDown) -> str:
        model = dd.get_model()
        idx = dd.get_selected()
        if model is None or idx is None:
            return ""
        item = model.get_item(idx)
        return item.get_string() if item else ""

    def _max_marker_x(self) -> float:
        return float(self.preview_w - self.marker_w)

    def _max_marker_y(self) -> float:
        return float(self.preview_h - self.marker_h)

    def _move_marker(self) -> None:
        self.marker_x = max(0.0, min(self.marker_x, self._max_marker_x()))
        self.marker_y = max(0.0, min(self.marker_y, self._max_marker_y()))
        self.preview_fixed.move(self.marker, int(self.marker_x), int(self.marker_y))

    def _on_drag_begin(self, _gesture: Gtk.GestureDrag, _x: float, _y: float) -> None:
        self.drag_start_x = self.marker_x
        self.drag_start_y = self.marker_y

    def _on_drag_update(self, _gesture: Gtk.GestureDrag, dx: float, dy: float) -> None:
        self.marker_x = self.drag_start_x + dx
        self.marker_y = self.drag_start_y + dy
        self._move_marker()
        self.status.set_text("Position preview updated")
        if self.live_place_switch.get_active():
            self._schedule_live_apply()

    def _on_drag_end(self, _gesture: Gtk.GestureDrag, _dx: float, _dy: float) -> None:
        self._move_marker()
        if self.live_place_switch.get_active():
            self._save_current("Live placement applied.")

    def _schedule_live_apply(self) -> None:
        if self._live_apply_source_id:
            return
        self._live_apply_source_id = GLib.timeout_add(120, self._on_live_apply_timer)

    def _on_live_apply_timer(self) -> bool:
        self._live_apply_source_id = 0
        self._save_current("Live placement preview active.")
        return False

    def _marker_to_pct(self) -> tuple[int, int]:
        max_x = self._max_marker_x()
        max_y = self._max_marker_y()
        x_pct = int(round((self.marker_x / max_x) * 100.0)) if max_x > 0 else 50
        y_pct = int(round((self.marker_y / max_y) * 100.0)) if max_y > 0 else 50
        return x_pct, y_pct

    def _pct_to_marker(self, x_pct: int, y_pct: int) -> None:
        max_x = self._max_marker_x()
        max_y = self._max_marker_y()
        self.marker_x = max_x * (max(0, min(100, x_pct)) / 100.0)
        self.marker_y = max_y * (max(0, min(100, y_pct)) / 100.0)
        self._move_marker()

    def _on_apply_preset(self, _button: Gtk.Button) -> None:
        preset = self._get_combo_value(self.preset_combo) or "custom"
        values = PRESETS.get(preset, {})
        if "animation_style" in values:
            opts = ["crossfade", "line_flow_up", "slide_up", "slide_left_right", "over_up_down"]
            self.anim_style.set_selected(opts.index(values["animation_style"]))
        if "animation_speed" in values:
            self.anim_speed.set_value(float(values["animation_speed"]))
        if "show_shadow" in values:
            self.shadow_switch.set_active(bool(values["show_shadow"]))
        if "font_weight" in values:
            self.font_weight.set_value(float(values["font_weight"]))
        self.status.set_text(f"Preset applied: {preset}")
        self._refresh_preview_style()

    def _collect(self) -> dict[str, Any]:
        x_pct, y_pct = self._marker_to_pct()
        return {
            "position": self._get_combo_value(self.position_combo) or "free",
            "monitor": self._get_combo_value(self.monitor_combo) or "primary",
            "render_x_pct": x_pct,
            "render_y_pct": y_pct,
            "font_size": int(self.font_size.get_value()),
            "font_family": self.font_family.get_text().strip() or "JetBrains Mono, Sans",
            "font_weight": int(self.font_weight.get_value()),
            "letter_spacing": round(float(self.letter_spacing.get_value()), 2),
            "line_spacing": round(float(self.line_spacing.get_value()), 2),
            "line_width_percent": int(self.line_width.get_value()),
            "visible_line_count": int(self.visible_lines.get_value()),
            "offset_ms": int(self.offset.get_value()),
            "animation_speed": round(float(self.anim_speed.get_value()), 2),
            "animation_style": self._get_combo_value(self.anim_style) or "slide_up",
            "animation_preset": self._get_combo_value(self.preset_combo) or "custom",
            "color_mode": self._get_combo_value(self.color_mode) or "solid",
            "dynamic_sampling_backend": self._get_combo_value(self.dynamic_backend) or "auto",
            "dynamic_interval_ms": int(self.dynamic_interval.get_value()),
            "dynamic_hysteresis": round(float(self.dynamic_hysteresis.get_value()), 2),
            "dynamic_panel_boost": round(float(self.dynamic_panel_boost.get_value()), 2),
            "bg_opacity": round(float(self.bg_opacity.get_value()), 2),
            "highlight_color": self.highlight.get_text().strip() or "#ffffff",
            "secondary_color": self.secondary.get_text().strip() or "#7ad7ff",
            "fade_color": self.fade.get_text().strip() or "#9aa0a6",
            "show_shadow": self.shadow_switch.get_active(),
            "hide_when_no_lyrics": self.hide_no_lyrics.get_active(),
            "bg_blur_hint": self.blur_hint.get_active(),
        }

    def _apply_to_widgets(self, cfg: dict[str, Any]) -> None:
        pos_opts = ["free", "top", "bottom"]
        anim_opts = ["crossfade", "line_flow_up", "slide_up", "slide_left_right", "over_up_down"]
        color_opts = ["solid", "bg", "rainbow", "wal", "auto_dynamic"]
        preset_opts = list(PRESETS.keys())

        pos = str(cfg.get("position", "free"))
        anim = str(cfg.get("animation_style", "slide_up"))
        mode = str(cfg.get("color_mode", "solid"))
        preset = str(cfg.get("animation_preset", "custom"))

        self.position_combo.set_selected(pos_opts.index(pos) if pos in pos_opts else 0)
        self.anim_style.set_selected(anim_opts.index(anim) if anim in anim_opts else 1)
        self.color_mode.set_selected(color_opts.index(mode) if mode in color_opts else 0)
        self.preset_combo.set_selected(preset_opts.index(preset) if preset in preset_opts else 0)

        # monitor dropdown can change by hotplug; match if available
        mon_val = str(cfg.get("monitor", "primary"))
        mon_model = self.monitor_combo.get_model()
        if mon_model:
            found = 0
            for i in range(mon_model.get_n_items()):
                item = mon_model.get_item(i)
                if item and item.get_string() == mon_val:
                    found = i
                    break
            self.monitor_combo.set_selected(found)

        self.font_size.set_value(float(cfg.get("font_size", 34)))
        self.font_family.set_text(str(cfg.get("font_family", "JetBrains Mono, Sans")))
        self.font_weight.set_value(float(cfg.get("font_weight", 850)))
        self.letter_spacing.set_value(float(cfg.get("letter_spacing", 0.0)))
        self.line_spacing.set_value(float(cfg.get("line_spacing", 1.12)))
        self.line_width.set_value(float(cfg.get("line_width_percent", 70)))
        self.visible_lines.set_value(float(cfg.get("visible_line_count", 3)))
        self.offset.set_value(float(cfg.get("offset_ms", 0)))
        self.anim_speed.set_value(float(cfg.get("animation_speed", 0.2)))
        self.bg_opacity.set_value(float(cfg.get("bg_opacity", 0.62)))
        # dynamic controls
        back_opts = ["auto", "grim"]
        backend = str(cfg.get("dynamic_sampling_backend", "auto"))
        self.dynamic_backend.set_selected(back_opts.index(backend) if backend in back_opts else 0)
        self.dynamic_interval.set_value(float(cfg.get("dynamic_interval_ms", 320)))
        self.dynamic_hysteresis.set_value(float(cfg.get("dynamic_hysteresis", 0.08)))
        self.dynamic_panel_boost.set_value(float(cfg.get("dynamic_panel_boost", 0.18)))

        self.highlight.set_text(str(cfg.get("highlight_color", "#ffffff")))
        self.secondary.set_text(str(cfg.get("secondary_color", "#7ad7ff")))
        self.fade.set_text(str(cfg.get("fade_color", "#9aa0a6")))
        self.shadow_switch.set_active(bool(cfg.get("show_shadow", True)))
        self.hide_no_lyrics.set_active(bool(cfg.get("hide_when_no_lyrics", False)))
        self.blur_hint.set_active(bool(cfg.get("bg_blur_hint", True)))

        self._pct_to_marker(int(cfg.get("render_x_pct", 50)), int(cfg.get("render_y_pct", 85)))
        self._refresh_preview_style()

    def _save_current(self, label: str) -> None:
        cfg = load_config()
        cfg.update(self._collect())
        save_config(cfg)
        self.status.set_text(label)

    def _on_apply(self, _button: Gtk.Button) -> None:
        self._save_current("Applied. Overlay updates automatically.")

    def _on_save(self, _button: Gtk.Button) -> None:
        self._save_current("Saved to config/config.json")

    def _on_reset(self, _button: Gtk.Button) -> None:
        save_config(dict(DEFAULT_CONFIG))
        cfg = load_config()
        self._apply_to_widgets(cfg)
        self.status.set_text("Reset to defaults.")


def run_config_app() -> None:
    app = Gtk.Application(application_id="dev.lyricfetch.config")

    def on_activate(application: Gtk.Application) -> None:
        win = ConfigWindow(application)
        win.present()

    app.connect("activate", on_activate)
    app.run()
