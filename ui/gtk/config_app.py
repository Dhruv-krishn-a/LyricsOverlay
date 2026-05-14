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
        self.set_default_size(840, 720)

        self.preview_w = 480
        self.preview_h = 270
        self.marker_w = 120
        self.marker_h = 48
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

        # Main Layout
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # HeaderBar
        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        
        # Main content with Sidebar
        main_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        
        sidebar = Gtk.StackSidebar()
        sidebar.set_stack(self.stack)
        sidebar.set_size_request(180, -1)
        
        main_content.append(sidebar)
        main_content.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        scroll.set_child(self.stack)
        main_content.append(scroll)
        
        root.append(main_content)

        # Footer
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        footer.set_margin_start(16)
        footer.set_margin_end(16)
        footer.set_margin_top(12)
        footer.set_margin_bottom(12)
        footer.add_css_class("footer-bar")
        
        self.status = Gtk.Label(label="All changes saved")
        self.status.set_xalign(0)
        self.status.set_hexpand(True)
        self.status.add_css_class("dim-label")
        footer.append(self.status)

        reset_btn = Gtk.Button(label="Reset Defaults")
        reset_btn.add_css_class("destructive-action")
        reset_btn.connect("clicked", self._on_reset)

        footer.append(reset_btn)
        root.append(footer)

        # --- Tab: Display ---
        display_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        display_page.set_margin_top(24)
        display_page.set_margin_bottom(24)
        display_page.set_margin_start(24)
        display_page.set_margin_end(24)
        
        # Placement Group
        self.position_combo = self._combo(["free", "top", "bottom"], str(self.config.get("position", "free")))
        monitor_options = self._monitor_options()
        self.monitor_combo = self._combo(monitor_options, str(self.config.get("monitor", "primary")))
        self.live_place_switch = Gtk.Switch()
        self.live_place_switch.set_active(True)
        
        display_page.append(self._group("General Display", [
            self._row("Placement Mode", self.position_combo, "Static preset or free drag"),
            self._row("Monitor", self.monitor_combo, "Select target display"),
            self._row("Live Placement", self.live_place_switch, "Update overlay while dragging"),
        ]))

        # Position Preview Group
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

        preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        preview_box.set_halign(Gtk.Align.CENTER)
        preview_box.append(self.preview_fixed)
        preview_hint = Gtk.Label(label="Drag rectangle to place overlay")
        preview_hint.add_css_class("dim-label")
        preview_box.append(preview_hint)
        
        display_page.append(self._group("On-Screen Position", [preview_box]))

        # Live Sample Preview Group
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
        
        display_page.append(self._group("Style Preview", [self.sample_frame]))
        
        self.stack.add_titled(display_page, "display", "Display")

        # --- Tab: Typography ---
        type_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        type_page.set_margin_top(24)
        type_page.set_margin_bottom(24)
        type_page.set_margin_start(24)
        type_page.set_margin_end(24)

        self.font_family = Gtk.Entry()
        self.font_size = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 14, 96, 1)
        self.font_weight = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 300, 900, 50)
        self.line_width = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 35, 95, 1)
        self.visible_lines = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 11, 1)
        self.letter_spacing = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -1.0, 4.0, 0.1)
        self.line_spacing = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.8, 2.0, 0.02)

        for s in [self.font_size, self.font_weight, self.line_width, self.visible_lines, self.letter_spacing, self.line_spacing]:
            s.set_draw_value(True)
            s.set_value_pos(Gtk.PositionType.RIGHT)

        type_page.append(self._group("Font", [
            self._row("Family", self.font_family, "e.g. JetBrains Mono, Sans"),
            self._row("Size", self.font_size),
            self._row("Weight", self.font_weight),
        ]))
        
        type_page.append(self._group("Layout", [
            self._row("Line Width %", self.line_width, "Max width of text area"),
            self._row("Visible Lines", self.visible_lines, "Number of lines shown"),
            self._row("Letter Spacing", self.letter_spacing),
            self._row("Line Spacing", self.line_spacing),
        ]))

        self.stack.add_titled(type_page, "typography", "Typography")

        # --- Tab: Animation ---
        anim_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        anim_page.set_margin_top(24)
        anim_page.set_margin_bottom(24)
        anim_page.set_margin_start(24)
        anim_page.set_margin_end(24)

        self.preset_combo = self._combo(list(PRESETS.keys()), str(self.config.get("animation_preset", "custom")))
        preset_btn = Gtk.Button(label="Apply Preset")
        preset_btn.connect("clicked", self._on_apply_preset)
        preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        preset_row.append(self.preset_combo)
        preset_row.append(preset_btn)

        self.anim_style = self._combo(
            ["crossfade", "line_flow_up", "slide_up", "slide_left_right", "over_up_down"],
            str(self.config.get("animation_style", "slide_up")),
        )
        self.anim_speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.05, 2.0, 0.05)
        self.anim_speed.set_draw_value(True)
        self.anim_speed.set_value_pos(Gtk.PositionType.RIGHT)

        anim_page.append(self._group("Presets", [
            self._row("Animation Preset", preset_row, "Quick config templates"),
        ]))
        
        anim_page.append(self._group("Fine Tuning", [
            self._row("Style", self.anim_style, "Transition effect"),
            self._row("Speed (s)", self.anim_speed, "Duration of animation"),
        ]))

        self.stack.add_titled(anim_page, "animation", "Animation")

        # --- Tab: Appearance ---
        app_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        app_page.set_margin_top(24)
        app_page.set_margin_bottom(24)
        app_page.set_margin_start(24)
        app_page.set_margin_end(24)

        self.color_mode = self._combo(
            ["solid", "bg", "rainbow", "wal", "auto_dynamic"],
            str(self.config.get("color_mode", "solid")),
        )
        self.highlight = Gtk.Entry()
        self.secondary = Gtk.Entry()
        self.fade = Gtk.Entry()
        self.bg_opacity = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.05, 0.95, 0.01)
        self.shadow_switch = Gtk.Switch()
        self.blur_hint = Gtk.Switch()

        self.bg_opacity.set_draw_value(True)
        self.bg_opacity.set_value_pos(Gtk.PositionType.RIGHT)

        app_page.append(self._group("Color Mode", [
            self._row("Mode", self.color_mode, "Theme source"),
        ]))
        
        app_page.append(self._group("Colors", [
            self._row("Highlight", self.highlight, "Active line color"),
            self._row("Secondary", self.secondary, "Near line color"),
            self._row("Fade", self.fade, "Distant line color"),
        ]))
        
        app_page.append(self._group("Effects", [
            self._row("BG Opacity", self.bg_opacity, "For 'bg' and 'dynamic' modes"),
            self._row("Text Shadow", self.shadow_switch),
            self._row("Blur Hint", self.blur_hint, "Request Hyprland blur"),
        ]))

        self.stack.add_titled(app_page, "appearance", "Appearance")

        # --- Tab: Advanced ---
        adv_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        adv_page.set_margin_top(24)
        adv_page.set_margin_bottom(24)
        adv_page.set_margin_start(24)
        adv_page.set_margin_end(24)

        self.dynamic_backend = self._combo(
            ["auto", "grim"],
            str(self.config.get("dynamic_sampling_backend", "auto")),
        )
        self.dynamic_interval = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 120, 1200, 20)
        self.dynamic_hysteresis = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.05, 1.5, 0.05)
        self.dynamic_panel_boost = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 0.5, 0.01)
        self.offset = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -2000, 2000, 10)
        self.hide_no_lyrics = Gtk.Switch()
        self.hide_on_pause = Gtk.Switch()

        for s in [self.dynamic_interval, self.dynamic_hysteresis, self.dynamic_panel_boost, self.offset]:
            s.set_draw_value(True)
            s.set_value_pos(Gtk.PositionType.RIGHT)

        adv_page.append(self._group("Dynamic Sampling", [
            self._row("Backend", self.dynamic_backend, "Capture method"),
            self._row("Interval (ms)", self.dynamic_interval, "Sampling frequency"),
            self._row("Hysteresis", self.dynamic_hysteresis, "Color change threshold"),
            self._row("Panel Boost", self.dynamic_panel_boost, "Extra contrast for background"),
        ]))
        
        adv_page.append(self._group("Behavior", [
            self._row("Sync Offset (ms)", self.offset, "Adjust lyrics timing"),
            self._row("Hide if Empty", self.hide_no_lyrics, "Auto-hide when no lyrics"),
            self._row("Hide on Pause", self.hide_on_pause, "Hide overlay when playback is paused"),
        ]))

        self.stack.add_titled(adv_page, "advanced", "Advanced")

        self._preview_css = Gtk.CssProvider()
        self._apply_styles()
        self._apply_to_widgets(self.config)
        self._connect_preview_watchers()
        self._tick_preview()
        GLib.timeout_add(1400, self._tick_preview)

        self.set_child(root)

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
.boxed-list {
  background-color: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
}
.boxed-list row {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding: 8px 12px;
}
.boxed-list row:last-child {
  border-bottom: none;
}
.heading {
  font-weight: 600;
  font-size: 1.05em;
}
.caption {
  font-size: 0.88em;
  opacity: 0.7;
}
.dim-label {
  opacity: 0.6;
}
.footer-bar {
  background-color: rgba(255, 255, 255, 0.02);
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
stacksidebar list {
  background: transparent;
}
stacksidebar row {
  padding: 10px 16px;
  border-radius: 8px;
  margin: 2px 8px;
}
stacksidebar row:selected {
  background-color: rgba(255, 255, 255, 0.1);
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
        self._auto_save_id = 0
        controls = [
            self.font_size,
            self.font_weight,
            self.letter_spacing,
            self.line_spacing,
            self.line_width,
            self.visible_lines,
            self.offset,
            self.anim_speed,
            self.anim_style,
            self.color_mode,
            self.dynamic_backend,
            self.dynamic_interval,
            self.dynamic_hysteresis,
            self.dynamic_panel_boost,
            self.bg_opacity,
            self.highlight,
            self.secondary,
            self.fade,
            self.shadow_switch,
            self.hide_no_lyrics,
            self.hide_on_pause,
            self.blur_hint,
            self.font_family,
            self.position_combo,
            self.monitor_combo,
        ]
        for c in controls:
            if isinstance(c, Gtk.Scale):
                c.connect("value-changed", self._on_control_changed)
            elif isinstance(c, Gtk.Entry):
                c.connect("changed", self._on_control_changed)
            elif isinstance(c, Gtk.DropDown):
                c.connect("notify::selected", self._on_control_changed)
            elif isinstance(c, Gtk.Switch):
                c.connect("notify::active", self._on_control_changed)

    def _on_control_changed(self, *args: Any) -> None:
        self._refresh_preview_style()
        self.status.set_text("Saving changes...")
        if self._auto_save_id:
            GLib.source_remove(self._auto_save_id)
        self._auto_save_id = GLib.timeout_add(350, self._perform_auto_save)

    def _perform_auto_save(self) -> bool:
        self._auto_save_id = 0
        cfg = load_config()
        cfg.update(self._collect())
        save_config(cfg)
        self.status.set_text("All changes saved")
        return False

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

    def _group(self, title: str, rows: list[Gtk.Widget]) -> Gtk.Box:
        group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
        if title:
            lbl = Gtk.Label()
            lbl.set_markup(f"<span weight='bold' size='large'>{title}</span>")
            lbl.set_xalign(0)
            lbl.set_margin_start(4)
            group.append(lbl)
            
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        
        for row_widget in rows:
            listbox.append(row_widget)
            
        group.append(listbox)
        return group

    def _row(self, label: str, widget: Gtk.Widget, description: str | None = None) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_hexpand(True)
        vbox.set_valign(Gtk.Align.CENTER)
        
        lbl = Gtk.Label(label=label)
        lbl.set_xalign(0)
        lbl.add_css_class("heading")
        vbox.append(lbl)
        
        if description:
            desc_lbl = Gtk.Label(label=description)
            desc_lbl.set_xalign(0)
            desc_lbl.add_css_class("caption")
            vbox.append(desc_lbl)
            
        row.append(vbox)
        
        widget.set_valign(Gtk.Align.CENTER)
        if isinstance(widget, (Gtk.Scale, Gtk.Entry, Gtk.DropDown)):
            widget.set_size_request(240, -1)
            
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
            "hide_on_pause": self.hide_on_pause.get_active(),
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
        self.hide_on_pause.set_active(bool(cfg.get("hide_on_pause", False)))
        self.blur_hint.set_active(bool(cfg.get("bg_blur_hint", True)))

        self._pct_to_marker(int(cfg.get("render_x_pct", 50)), int(cfg.get("render_y_pct", 85)))
        self._refresh_preview_style()

    def _save_current(self, label: str) -> None:
        cfg = load_config()
        cfg.update(self._collect())
        save_config(cfg)
        self.status.set_text(label)

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
