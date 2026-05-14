from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from tempfile import NamedTemporaryFile
from typing import Any

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import GLib, Gdk, Gtk, Gtk4LayerShell, Pango

from core.config import load_config
from core.event_bus import StateBusClient
from core.state_file import StateFile
from ui.gtk.animations.line_flow_up import LineFlowUpAnimator


class OverlayWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title="LyricFetchOverlay")
        self.set_decorated(False)
        self.set_focusable(False)
        self.set_can_target(False)
        self.set_default_size(1, 1)

        Gtk4LayerShell.init_for_window(self)
        display = Gdk.Display.get_default()
        display_name = display.get_name() if display else "none"
        self.layer_shell_supported = bool(Gtk4LayerShell.is_supported())
        if not self.layer_shell_supported:
            print(
                "Warning: gtk4-layer-shell reports unsupported "
                f"(display={display_name}, GDK_BACKEND={os.environ.get('GDK_BACKEND', '')}). "
                "Window may behave like a normal toplevel."
            )

        Gtk4LayerShell.set_namespace(self, "lyricfetch")
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_exclusive_zone(self, 0)
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.NONE)

        self._cfg_mtime = 0.0
        self._state_mtime = 0.0
        self._last_curr = ""
        self._overlay_w = 640
        self._overlay_h = 180
        self._monitor_cfg = "primary"
        self._monitor_origin = (0, 0)
        self._region_rect = (0, 0, 640, 180)
        self._dynamic_enabled = False
        self._dynamic_theme = "light-on-dark"
        self._dynamic_interval_ms = 320
        self._dynamic_hysteresis = 0.08
        self._dynamic_panel_boost = 0.18
        self._dynamic_backend = "auto"
        self._dynamic_base_bg_opacity = 0.62
        self._style_state: dict[str, Any] = {}
        self._last_dynamic_apply = 0.0
        self._has_grim = bool(shutil.which("grim"))
        self._dynamic_fail_count = 0
        self._visible_line_count = 3
        self._last_window_signature: tuple[tuple[str, ...], int] | None = None
        self._animation_style = "slide_up"
        self._line_flow_up = LineFlowUpAnimator()

        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.root.set_halign(Gtk.Align.CENTER)
        self.root.set_valign(Gtk.Align.CENTER)
        self.root.set_can_target(False)
        self.root.add_css_class("overlay-root")

        self.flow_area = Gtk.Fixed()
        self.flow_area.set_halign(Gtk.Align.FILL)
        self.flow_area.set_valign(Gtk.Align.FILL)
        self.flow_area.set_can_target(False)
        self.flow_area.add_css_class("overlay-flow")

        self.flow_labels: list[Gtk.Label] = []
        self._flow_pos: list[tuple[float, float]] = []
        self._flow_current_opacity: list[float] = []
        self._flow_start_pos: list[tuple[float, float]] = []
        self._flow_target_pos: list[tuple[float, float]] = []
        self._flow_start_opacity: list[float] = []
        self._flow_target_opacity: list[float] = []
        self._flow_anim_source_id = 0
        self._flow_anim_start = 0.0
        self._flow_anim_duration_ms = 420
        self._flow_last_signature: tuple[tuple[str, ...], int] | None = None

        self.revealer = Gtk.Revealer()
        self.revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.revealer.set_transition_duration(220)
        self.revealer.set_reveal_child(True)
        self.revealer.set_child(self.flow_area)
        self.root.append(self.revealer)
        self.set_child(self.root)

        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.state_file = StateFile()
        self.bus_client = StateBusClient()
        self._stop_bus = False

        self.connect("realize", self._on_realize)
        self.connect("close-request", self._on_close)

        self._apply_config(load_config())
        self._read_state_once()
        self._start_bus_thread()

        GLib.timeout_add(150, self._poll_config)
        GLib.timeout_add(250, self._poll_state)
        GLib.timeout_add(120, self._dynamic_tick)

    def _on_realize(self, _widget: Gtk.Widget) -> None:
        GLib.idle_add(self._apply_clickthrough_once)

    def _on_close(self, _widget: Gtk.Widget) -> bool:
        self._stop_bus = True
        return False

    def _apply_clickthrough_once(self) -> bool:
        surface = self.get_surface()
        if surface and hasattr(surface, "set_input_region"):
            try:
                empty_region = cairo.Region()
                surface.set_input_region(empty_region)
            except Exception:
                pass
        return False

    def _make_line_label(self) -> Gtk.Label:
        lbl = Gtk.Label(xalign=0.5)
        lbl.set_wrap(True)
        lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        lbl.set_justify(Gtk.Justification.CENTER)
        lbl.set_max_width_chars(48)
        lbl.set_can_target(False)
        lbl.set_opacity(0.0)
        lbl.add_css_class("line-dim")
        return lbl

    def _ensure_line_labels(self, count: int) -> None:
        wanted = max(1, int(count))
        while len(self.flow_labels) < wanted:
            lbl = self._make_line_label()
            lbl.set_size_request(self._overlay_w, -1)
            self.flow_area.put(lbl, 0, 0)
            self.flow_labels.append(lbl)
            self._flow_pos.append((0.0, 0.0))
            self._flow_current_opacity.append(0.0)
        while len(self.flow_labels) > wanted:
            lbl = self.flow_labels.pop()
            self.flow_area.remove(lbl)
            self._flow_pos.pop()
            self._flow_current_opacity.pop()

        for lbl in self.flow_labels:
            lbl.set_size_request(self._overlay_w, -1)

    def _set_text_align_mode(self, mode: str) -> None:
        # `mode`: left | center | right
        if mode == "left":
            self.root.set_halign(Gtk.Align.START)
            for lbl in self.flow_labels:
                lbl.set_xalign(0.0)
                lbl.set_justify(Gtk.Justification.LEFT)
        elif mode == "right":
            self.root.set_halign(Gtk.Align.END)
            for lbl in self.flow_labels:
                lbl.set_xalign(1.0)
                lbl.set_justify(Gtk.Justification.RIGHT)
        else:
            self.root.set_halign(Gtk.Align.FILL)
            for lbl in self.flow_labels:
                lbl.set_xalign(0.5)
                lbl.set_justify(Gtk.Justification.CENTER)

    def _paint_labels(self, labels: list[Gtk.Label], lines: list[str], current_index: int, word_index: int = -1) -> None:
        highlight_color = self._style_state.get("highlight_color", "#ffffff")
        fade_color = self._style_state.get("fade_color", "#9aa0a6")

        for i, lbl in enumerate(labels):
            txt = lines[i] if i < len(lines) else ""
            lbl.remove_css_class("line-current")
            lbl.remove_css_class("line-near")
            lbl.remove_css_class("line-far")
            lbl.remove_css_class("line-dim")
            lbl.remove_css_class("line-prev-near")
            lbl.remove_css_class("line-next-near")
            lbl.remove_css_class("line-prev-far")
            lbl.remove_css_class("line-next-far")
            
            distance = abs(i - current_index)
            
            if txt == "---INSTRUMENTAL---":
                lbl.set_use_markup(False)
                if distance == 0:
                    t = time.time()
                    dots = ["♪", "♫", "♬"]
                    dot = dots[int(t * 2) % 3]
                    lbl.set_label(f"~ {dot} ~")
                    lbl.add_css_class("line-current")
                else:
                    lbl.set_label("~ ♪ ~")
                    if distance == 1:
                        lbl.add_css_class("line-near")
                    elif distance == 2:
                        lbl.add_css_class("line-far")
                    else:
                        lbl.add_css_class("line-dim")
                continue
            
            if distance == 0:
                lbl.add_css_class("line-current")
                if word_index >= 0 and txt:
                    words = txt.split()
                    if 0 <= word_index < len(words):
                        # Construct Pango markup for highlighted and unhighlighted words
                        highlighted = " ".join(words[:word_index + 1])
                        remaining = " ".join(words[word_index + 1:])
                        # Escape XML characters
                        highlighted = highlighted.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        remaining = remaining.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        
                        markup = f"<span color='{highlight_color}'>{highlighted}</span>"
                        if remaining:
                            markup += f" <span color='{fade_color}'>{remaining}</span>"
                        lbl.set_markup(markup)
                    else:
                        lbl.set_label(txt)
                else:
                    lbl.set_label(txt)
            else:
                lbl.set_use_markup(False)
                lbl.set_label(txt)
                if distance == 1:
                    lbl.add_css_class("line-near")
                elif distance == 2:
                    lbl.add_css_class("line-far")
                else:
                    lbl.add_css_class("line-dim")

    def _flow_step(self) -> int:
        font_size = int(self._style_state.get("font_size", 34))
        line_spacing = float(self._style_state.get("line_spacing", 1.12))
        return max(18, int(font_size * line_spacing * 1.18))

    def _flow_center_y(self, step: int) -> int:
        return max(0, (self._overlay_h - step) // 2)

    def _flow_opacity(self, distance: int) -> float:
        if distance == 0:
            return 1.0
        if distance == 1:
            return 0.92
        if distance == 2:
            return 0.82
        if distance == 3:
            return 0.72
        return 0.62
    
    def _flow_ease(self, t: float) -> float:
        t = max(0.0, min(1.0, t))
        return t * t * (3 - 2 * t)  # smoothstep

    def _stop_flow_animation(self) -> None:
        if self._flow_anim_source_id:
            GLib.source_remove(self._flow_anim_source_id)
            self._flow_anim_source_id = 0

    def _tick_flow_animation(self) -> bool:
        if not self._flow_start_pos or not self._flow_target_pos:
            self._flow_anim_source_id = 0
            return False

        elapsed_ms = (time.monotonic() - self._flow_anim_start) * 1000.0
        duration_ms = max(1, self._flow_anim_duration_ms)
        t = min(1.0, elapsed_ms / duration_ms)
        eased = self._flow_ease(t)

        for i, lbl in enumerate(self.flow_labels):
            sx, sy = self._flow_start_pos[i]
            tx, ty = self._flow_target_pos[i]
            so = self._flow_start_opacity[i]
            to = self._flow_target_opacity[i]

            x = sx + (tx - sx) * eased
            y = sy + (ty - sy) * eased
            op = so + (to - so) * eased

            self.flow_area.move(lbl, int(x), int(y))
            lbl.set_opacity(max(0.0, min(1.0, op)))
            self._flow_pos[i] = (x, y)
            self._flow_current_opacity[i] = op

        if t >= 1.0:
            for i, lbl in enumerate(self.flow_labels):
                tx, ty = self._flow_target_pos[i]
                to = self._flow_target_opacity[i]
                self.flow_area.move(lbl, int(round(tx)), int(round(ty)))
                lbl.set_opacity(max(0.0, min(1.0, to)))
                self._flow_pos[i] = (tx, ty)
                self._flow_current_opacity[i] = to
            self._flow_anim_source_id = 0
            return False

        return True

    def _render_flow_lines(
        self,
        lines: list[str],
        current_index: int,
        transition: str | None,
        repaint_only: bool,
        word_index: int = -1,
    ) -> None:
        self._ensure_line_labels(len(lines))
        if not lines:
            lines = [""]
            current_index = 0

        current_index = max(0, min(current_index, len(lines) - 1))
        step = self._flow_step()
        center_y = self._flow_center_y(step)
        self.flow_area.set_size_request(self._overlay_w, self._overlay_h)

        self._paint_labels(self.flow_labels, lines, current_index, word_index)

        target_pos: list[tuple[float, float]] = []
        target_opacity: list[float] = []
        for i in range(len(self.flow_labels)):
            y = float(center_y + (i - current_index) * step)
            target_pos.append((0.0, y))
            target_opacity.append(self._flow_opacity(abs(i - current_index)))

        if repaint_only or transition is None or not self._flow_pos or len(self._flow_pos) != len(self.flow_labels):
            self._stop_flow_animation()
            self._flow_start_pos = list(target_pos)
            self._flow_target_pos = list(target_pos)
            self._flow_start_opacity = list(target_opacity)
            self._flow_target_opacity = list(target_opacity)
            for i, lbl in enumerate(self.flow_labels):
                x, y = target_pos[i]
                op = target_opacity[i]
                self.flow_area.move(lbl, int(round(x)), int(round(y)))
                lbl.set_opacity(op)
                self._flow_pos[i] = (x, y)
                self._flow_current_opacity[i] = op
            return

        direction = 1 if transition == "up" else -1 if transition == "down" else 0
        if direction == 0:
            self._stop_flow_animation()
            self._flow_start_pos = list(target_pos)
            self._flow_target_pos = list(target_pos)
            self._flow_start_opacity = list(target_opacity)
            self._flow_target_opacity = list(target_opacity)
            for i, lbl in enumerate(self.flow_labels):
                x, y = target_pos[i]
                op = target_opacity[i]
                self.flow_area.move(lbl, int(round(x)), int(round(y)))
                lbl.set_opacity(op)
                self._flow_pos[i] = (x, y)
                self._flow_current_opacity[i] = op
            return

        self._stop_flow_animation()
        self._flow_start_pos = []
        self._flow_target_pos = list(target_pos)
        self._flow_start_opacity = []
        self._flow_target_opacity = list(target_opacity)

        for i in range(len(self.flow_labels)):
            if i < len(self._flow_pos):
                sx, sy = self._flow_pos[i]
                so = self._flow_current_opacity[i] if i < len(self._flow_current_opacity) else target_opacity[i]
            else:
                sx = 0.0
                sy = target_pos[i][1] + (step * direction)
                so = 0.0

            self._flow_start_pos.append((sx, sy))
            self._flow_start_opacity.append(so)

        self._flow_anim_start = time.monotonic()
        self._flow_anim_duration_ms = max(260, min(520, self._flow_anim_duration_ms))        
        self._flow_anim_source_id = GLib.timeout_add(12, self._tick_flow_animation)

    def _render_lines(self, lines: list[str], current_index: int, word_index: int = -1) -> None:
        if not lines:
            lines = [""]
            current_index = 0
        self._ensure_line_labels(len(lines))
        current_index = max(0, min(current_index, len(lines) - 1))
        sig = (tuple(lines), current_index, word_index)
        if sig == self._flow_last_signature:
            return
        self._flow_last_signature = sig
        current_text = lines[current_index] if lines else ""

        if self._animation_style == "line_flow_up":
            flow = self._line_flow_up.decide(lines, current_index)
            self._render_flow_lines(
                flow.render_lines,
                flow.render_index,
                flow.transition,
                flow.repaint_only,
                word_index
            )
            self._last_curr = current_text
            return

        self._stop_flow_animation()
        self._paint_labels(self.flow_labels, lines, current_index, word_index)
        step = self._flow_step()
        center_y = self._flow_center_y(step)
        self.flow_area.set_size_request(self._overlay_w, self._overlay_h)

        for i, lbl in enumerate(self.flow_labels):
            y = float(center_y + (i - current_index) * step)
            op = self._flow_opacity(abs(i - current_index))
            self.flow_area.move(lbl, 0, int(round(y)))
            lbl.set_opacity(op)
            self._flow_pos[i] = (0.0, y)
            self._flow_current_opacity[i] = op

        self._last_curr = current_text

    def _safe_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _safe_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _monitor_entries(self) -> list[tuple[str, Gdk.Monitor, int, int]]:
        display = Gdk.Display.get_default()
        if not display:
            return []
        monitors = display.get_monitors()
        if not monitors:
            return []

        out: list[tuple[str, Gdk.Monitor, int, int]] = []
        for i in range(monitors.get_n_items()):
            mon = monitors.get_item(i)
            if not mon:
                continue
            geometry = mon.get_geometry()
            width = geometry.width if geometry and geometry.width > 0 else 1920
            height = geometry.height if geometry and geometry.height > 0 else 1080
            connector = ""
            if hasattr(mon, "get_connector"):
                try:
                    connector = mon.get_connector() or ""
                except Exception:
                    connector = ""
            label = connector or f"monitor-{i}"
            out.append((label, mon, width, height))
        return out

    def _apply_monitor(self, monitor_key: str) -> tuple[int, int]:
        entries = self._monitor_entries()
        if not entries:
            self._monitor_origin = (0, 0)
            return 1920, 1080

        selected = entries[0]
        if monitor_key == "primary":
            display = Gdk.Display.get_default()
            if display and hasattr(display, "get_primary_monitor"):
                try:
                    primary = display.get_primary_monitor()
                    if primary:
                        for e in entries:
                            if e[1] == primary:
                                selected = e
                                break
                except Exception:
                    pass
        else:
            for e in entries:
                if e[0] == monitor_key:
                    selected = e
                    break

        if hasattr(Gtk4LayerShell, "set_monitor"):
            try:
                Gtk4LayerShell.set_monitor(self, selected[1])
            except Exception:
                pass
        geometry = selected[1].get_geometry()
        if geometry:
            self._monitor_origin = (geometry.x, geometry.y)
        else:
            self._monitor_origin = (0, 0)
        return selected[2], selected[3]

    def _set_anchors_free(self, x_margin: int, y_margin: int) -> None:
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, False)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.BOTTOM, False)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.LEFT, max(0, x_margin))
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, max(0, y_margin))
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.RIGHT, 0)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.BOTTOM, 0)

    def _apply_anchors(self, position: str, x_pct: int, y_pct: int, monitor_w: int, monitor_h: int) -> None:
        if position == "top":
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, False)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, False)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.BOTTOM, False)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, 36)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.LEFT, 0)
            self._set_text_align_mode("center")
            self.root.set_valign(Gtk.Align.START)
            left = (monitor_w - self._overlay_w) // 2
            self._region_rect = (left, 36, self._overlay_w, self._overlay_h)
            return

        if position == "bottom":
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, False)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, False)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, False)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.BOTTOM, True)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.BOTTOM, 36)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.LEFT, 0)
            self._set_text_align_mode("center")
            self.root.set_valign(Gtk.Align.END)
            left = (monitor_w - self._overlay_w) // 2
            top = max(0, monitor_h - self._overlay_h - 36)
            self._region_rect = (left, top, self._overlay_w, self._overlay_h)
            return

        # --- Free positioning: always LEFT+TOP anchored, margins do all the work ---
        max_x = max(0, monitor_w - self._overlay_w)
        max_y = max(0, monitor_h - self._overlay_h)
        edge_padding = 24  # keeps overlay from sticking hard to edges
        usable_w = max(0, monitor_w - self._overlay_w - edge_padding * 2)
        usable_h = max(0, monitor_h - self._overlay_h - edge_padding * 2)

        x_ratio = max(0, min(100, x_pct)) / 100.0
        y_ratio = max(0, min(100, y_pct)) / 100.0

        x_margin = int(edge_padding + usable_w * x_ratio)
        y_margin = int(edge_padding + usable_h * y_ratio)

        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, False)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.BOTTOM, False)

        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.LEFT, x_margin)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, y_margin)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.RIGHT, 0)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.BOTTOM, 0)

        self._set_text_align_mode("center")
        self.root.set_valign(Gtk.Align.START)
        self._region_rect = (x_margin, y_margin, self._overlay_w, self._overlay_h)

    def _load_wal_colors(self) -> tuple[str, str, str] | None:
        wal_path = Path.home() / ".cache" / "wal" / "colors.json"
        if not wal_path.exists():
            return None
        try:
            payload = json.loads(wal_path.read_text(encoding="utf-8"))
            colors = payload.get("colors", {}) if isinstance(payload, dict) else {}
            c1 = str(colors.get("color15", "#ffffff"))
            c2 = str(colors.get("color6", "#7ad7ff"))
            c3 = str(colors.get("color8", "#9aa0a6"))
            return c1, c2, c3
        except (OSError, ValueError, TypeError):
            return None

    def _load_wal_special(self) -> tuple[str, str] | None:
        wal_path = Path.home() / ".cache" / "wal" / "colors.json"
        if not wal_path.exists():
            return None
        try:
            payload = json.loads(wal_path.read_text(encoding="utf-8"))
            special = payload.get("special", {}) if isinstance(payload, dict) else {}
            bg = str(special.get("background", "#10141a"))
            fg = str(special.get("foreground", "#f2f5f9"))
            return bg, fg
        except (OSError, ValueError, TypeError):
            return None

    def _hex_to_rgb(self, color: str, fallback: tuple[int, int, int] = (16, 20, 26)) -> tuple[int, int, int]:
        c = color.strip().lstrip("#")
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        if len(c) != 6:
            return fallback
        try:
            return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        except ValueError:
            return fallback

    def _relative_luminance(self, r: int, g: int, b: int) -> float:
        def to_lin(v: int) -> float:
            x = v / 255.0
            return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

        return 0.2126 * to_lin(r) + 0.7152 * to_lin(g) + 0.0722 * to_lin(b)

    def _contrast_text_on(self, bg_hex: str) -> tuple[str, str, str]:
        r, g, b = self._hex_to_rgb(bg_hex)
        lum = self._relative_luminance(r, g, b)
        if lum > 0.45:
            return "#0b0f14", "#243245", "#3b4b60"
        return "#f4f7fb", "#c8d8ea", "#9aafc6"

    def _parse_ppm_luma(
        self,
        data: bytes,
        exclude_rect: tuple[int, int, int, int] | None = None,
    ) -> float | None:
        # P6 format: header then binary RGB payload.
        if not data.startswith(b"P6"):
            return None
        try:
            i = 2
            tokens: list[bytes] = []
            while len(tokens) < 3 and i < len(data):
                while i < len(data) and data[i] in b" \t\r\n":
                    i += 1
                if i < len(data) and data[i] == ord("#"):
                    while i < len(data) and data[i] != ord("\n"):
                        i += 1
                    continue
                start = i
                while i < len(data) and data[i] not in b" \t\r\n":
                    i += 1
                tokens.append(data[start:i])
            if len(tokens) < 3:
                return None
            width = int(tokens[0])
            height = int(tokens[1])
            maxval = int(tokens[2])
            if width <= 0 or height <= 0 or maxval <= 0:
                return None
            while i < len(data) and data[i] in b" \t\r\n":
                i += 1
            payload = data[i:]
            expected = width * height * 3
            if len(payload) < expected:
                return None
            step = max(1, (width * height) // 4000)
            total = 0.0
            count = 0
            ex_x, ex_y, ex_w, ex_h = exclude_rect if exclude_rect else (-1, -1, 0, 0)
            for px in range(0, width * height, step):
                py = px // width
                px_x = px % width
                if ex_x <= px_x < (ex_x + ex_w) and ex_y <= py < (ex_y + ex_h):
                    continue
                off = px * 3
                r = payload[off]
                g = payload[off + 1]
                b = payload[off + 2]
                total += self._relative_luminance(r, g, b)
                count += 1
            if count == 0:
                return None
            return total / count
        except Exception:
            return None

    def _sample_background_luma(self) -> float | None:
        backend = self._dynamic_backend
        if backend in {"auto", "grim"}:
            if self._has_grim:
                ox, oy = self._monitor_origin
                x, y, w, h = self._region_rect
                # With no dynamic panel boost we can sample the exact region for best relevance.
                if self._dynamic_panel_boost <= 0.01:
                    pad = 0
                    sw = max(12, w)
                    sh = max(12, h)
                else:
                    pad = 36
                    sw = max(12, w + pad * 2)
                    sh = max(12, h + pad * 2)
                gx = max(0, ox + x - pad)
                gy = max(0, oy + y - pad)
                try:
                    cmd_stdout = ["grim", "-g", f"{gx},{gy} {sw}x{sh}", "-t", "ppm", "-"]
                    proc = subprocess.run(cmd_stdout, capture_output=True, timeout=0.7, check=False)
                    if proc.returncode == 0 and proc.stdout:
                        ex = None if pad == 0 else (pad, pad, max(1, w), max(1, h))
                        l = self._parse_ppm_luma(proc.stdout, exclude_rect=ex)
                        if l is not None:
                            self._dynamic_fail_count = 0
                            return l
                    # Fallback path for compositors/setups where stdout ppm is flaky.
                    with NamedTemporaryFile(suffix=".ppm") as tmp:
                        cmd_file = ["grim", "-g", f"{gx},{gy} {sw}x{sh}", "-t", "ppm", tmp.name]
                        proc2 = subprocess.run(cmd_file, capture_output=True, timeout=0.9, check=False)
                        if proc2.returncode == 0:
                            data = Path(tmp.name).read_bytes()
                            ex = None if pad == 0 else (pad, pad, max(1, w), max(1, h))
                            l = self._parse_ppm_luma(data, exclude_rect=ex)
                            if l is not None:
                                self._dynamic_fail_count = 0
                                return l
                except Exception:
                    pass
                self._dynamic_fail_count += 1
                if self._dynamic_fail_count % 30 == 0:
                    print("LyricFetch: dynamic sampler failed repeatedly; keeping previous theme.")
        return None

    def _dynamic_tick(self) -> bool:
        if not self._dynamic_enabled:
            return True
        now = time.monotonic()
        if (now - self._last_dynamic_apply) * 1000.0 < self._dynamic_interval_ms:
            return True
        self._last_dynamic_apply = now
        luma = self._sample_background_luma()
        if luma is None:
            return True
        # Choose theme by strongest WCAG-style contrast against sampled background.
        contrast_black = (luma + 0.05) / 0.05
        contrast_white = 1.05 / (luma + 0.05)
        diff = contrast_black - contrast_white
        if diff > self._dynamic_hysteresis:
            next_theme = "dark-on-light"
        elif diff < -self._dynamic_hysteresis:
            next_theme = "light-on-dark"
        else:
            next_theme = self._dynamic_theme

        if next_theme != self._dynamic_theme:
            self._dynamic_theme = next_theme
            if self._style_state:
                st = dict(self._style_state)
                if next_theme == "dark-on-light":
                    st["highlight_color"] = "#11161d"
                    st["secondary_color"] = "#273449"
                    st["fade_color"] = "#3b4b60"
                    if self._dynamic_panel_boost > 0.01:
                        st["panel_bg_css"] = (
                            f"background: rgba(242, 246, 252, {min(0.96, self._dynamic_base_bg_opacity + self._dynamic_panel_boost):.3f});"
                        )
                        st["panel_border_css"] = "border: 1px solid rgba(0,0,0,0.18);"
                    else:
                        st["panel_bg_css"] = "background: transparent;"
                        st["panel_border_css"] = "border: none;"
                else:
                    st["highlight_color"] = "#f4f7fb"
                    st["secondary_color"] = "#c8d8ea"
                    st["fade_color"] = "#9aafc6"
                    if self._dynamic_panel_boost > 0.01:
                        st["panel_bg_css"] = (
                            f"background: rgba(16, 20, 28, {min(0.96, self._dynamic_base_bg_opacity + self._dynamic_panel_boost):.3f});"
                        )
                        st["panel_border_css"] = "border: 1px solid rgba(255,255,255,0.18);"
                    else:
                        st["panel_bg_css"] = "background: transparent;"
                        st["panel_border_css"] = "border: none;"
                self._render_css(st)
        return True

    def _render_css(self, st: dict[str, Any]) -> None:
        shadow = st.get("shadow", "")
        css_text = f"""
window {{
  background: transparent;
}}
.overlay-root {{
  {st.get("panel_bg_css", "background: transparent;")}
  {st.get("panel_border_css", "border: none;")}
  border-radius: 14px;
  padding: 12px 28px;
}}
.line-near {{
  color: {st["fade_color"]};
  font-size: {max(12, int(st["font_size"] * 0.62))}px;
  font-family: '{st["font_family"]}';
  font-weight: {max(300, min(900, int(st["font_weight"] * 0.65)))};
  letter-spacing: {st["letter_spacing"]}px;
  line-height: {st["line_spacing"]};
  {shadow}
}}
.line-prev-near {{
  color: {st["fade_color"]};
  font-size: {max(12, int(st["font_size"] * 0.62))}px;
  font-family: '{st["font_family"]}';
  font-weight: {max(300, min(900, int(st["font_weight"] * 0.65)))};
  letter-spacing: {st["letter_spacing"]}px;
  line-height: {st["line_spacing"]};
  opacity: 0.58;
  {shadow}
}}
.line-next-near {{
  color: {st["secondary_color"]};
  font-size: {max(12, int(st["font_size"] * 0.62))}px;
  font-family: '{st["font_family"]}';
  font-weight: {max(300, min(900, int(st["font_weight"] * 0.65)))};
  letter-spacing: {st["letter_spacing"]}px;
  line-height: {st["line_spacing"]};
  opacity: 0.76;
  {shadow}
}}
.line-far {{
  color: {st["secondary_color"]};
  font-size: {max(12, int(st["font_size"] * 0.62))}px;
  font-family: '{st["font_family"]}';
  font-weight: {max(300, min(900, int(st["font_weight"] * 0.65)))};
  letter-spacing: {st["letter_spacing"]}px;
  line-height: {st["line_spacing"]};
  {shadow}
}}
.line-prev-far {{
  color: {st["fade_color"]};
  font-size: {max(11, int(st["font_size"] * 0.58))}px;
  font-family: '{st["font_family"]}';
  font-weight: {max(300, min(900, int(st["font_weight"] * 0.60)))};
  letter-spacing: {st["letter_spacing"]}px;
  line-height: {st["line_spacing"]};
  {shadow}
}}
.line-next-far {{
  color: {st["secondary_color"]};
  font-size: {max(11, int(st["font_size"] * 0.58))}px;
  font-family: '{st["font_family"]}';
  font-weight: {max(300, min(900, int(st["font_weight"] * 0.60)))};
  letter-spacing: {st["letter_spacing"]}px;
  line-height: {st["line_spacing"]};
  opacity: 0.55;
  {shadow}
}}
.line-dim {{
  color: {st["fade_color"]};
  font-size: {max(11, int(st["font_size"] * 0.56))}px;
  font-family: '{st["font_family"]}';
  font-weight: {max(300, min(900, int(st["font_weight"] * 0.58)))};
  letter-spacing: {st["letter_spacing"]}px;
  line-height: {st["line_spacing"]};
  {shadow}
}}
.line-current {{
  color: {st["highlight_color"]};
  font-size: {max(14, st["font_size"])}px;
  font-family: '{st["font_family"]}';
  font-weight: {max(300, min(900, st["font_weight"]))};
  letter-spacing: {st["letter_spacing"]}px;
  line-height: {st["line_spacing"]};
  opacity: 1.0;
  {shadow}
  {st.get("current_gradient", "")}
}}
"""
        self.css.load_from_data(css_text.encode("utf-8"))

    def _apply_config(self, cfg: dict[str, Any]) -> None:
        position = str(cfg.get("position", "free")).lower()
        monitor_key = str(cfg.get("monitor", "primary"))
        x_pct = self._safe_int(cfg.get("render_x_pct", 50), 50)
        y_pct = self._safe_int(cfg.get("render_y_pct", 85), 85)
        font_size = self._safe_int(cfg.get("font_size", 34), 34)
        font_family = str(cfg.get("font_family", "JetBrains Mono, Sans"))
        font_weight = self._safe_int(cfg.get("font_weight", 850), 850)
        letter_spacing = self._safe_float(cfg.get("letter_spacing", 0.0), 0.0)
        line_spacing = self._safe_float(cfg.get("line_spacing", 1.12), 1.12)
        visible_line_count = max(1, self._safe_int(cfg.get("visible_line_count", 3), 3))
        highlight_color = str(cfg.get("highlight_color", "#ffffff"))
        secondary_color = str(cfg.get("secondary_color", "#aabed6"))
        fade_color = str(cfg.get("fade_color", "#9aa0a6"))
        color_mode = str(cfg.get("color_mode", "solid")).lower()
        dynamic_backend = str(cfg.get("dynamic_sampling_backend", "auto")).lower()
        dynamic_interval_ms = max(120, self._safe_int(cfg.get("dynamic_interval_ms", 320), 320))
        dynamic_hysteresis = max(0.05, min(1.5, self._safe_float(cfg.get("dynamic_hysteresis", 0.3), 0.3)))
        dynamic_panel_boost = max(0.0, min(0.5, self._safe_float(cfg.get("dynamic_panel_boost", 0.18), 0.18)))
        bg_opacity = max(0.05, min(0.95, self._safe_float(cfg.get("bg_opacity", 0.62), 0.62)))
        animation_speed = self._safe_float(cfg.get("animation_speed", 0.2), 0.2)
        animation_style = str(cfg.get("animation_style", "slide_up")).lower()
        self._animation_style = animation_style
        line_width_percent = min(95, max(35, self._safe_int(cfg.get("line_width_percent", 70), 70)))
        show_shadow = bool(cfg.get("show_shadow", True))
        self._dynamic_enabled = color_mode == "auto_dynamic"
        self._dynamic_backend = dynamic_backend
        self._dynamic_interval_ms = dynamic_interval_ms
        self._dynamic_hysteresis = dynamic_hysteresis
        self._dynamic_panel_boost = dynamic_panel_boost
        self._dynamic_base_bg_opacity = bg_opacity

        monitor_w, monitor_h = self._apply_monitor(monitor_key)
        self._monitor_cfg = monitor_key

        if color_mode == "wal":
            wal = self._load_wal_colors()
            if wal:
                highlight_color, secondary_color, fade_color = wal

        duration = int(max(0.05, min(animation_speed, 2.0)) * 1000)
        self._visible_line_count = visible_line_count
        self._ensure_line_labels(self._visible_line_count)
        self._last_window_signature = None
        self._flow_last_signature = None
        self._line_flow_up.reset()
        self._stop_flow_animation()
        self.revealer.set_transition_duration(duration)
        self._flow_anim_duration_ms = duration
        if animation_style == "crossfade":
            self.revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        elif animation_style == "slide_left_right":
            self.revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_RIGHT)
        elif animation_style == "over_up_down":
            self.revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        elif animation_style == "line_flow_up":
            self.revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        else:
            self.revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)

        text_width = int(monitor_w * (line_width_percent / 100.0))
        self._overlay_w = max(360, min(980, text_width))
        self._overlay_h = max(140, int(font_size * (self._visible_line_count * 1.6)))
        self.root.set_size_request(self._overlay_w, -1)

        self._apply_anchors(position, x_pct=x_pct, y_pct=y_pct, monitor_w=monitor_w, monitor_h=monitor_h)

        shadow = "text-shadow: 0 2px 12px rgba(0,0,0,0.55);" if show_shadow else ""
        panel_bg_css = "background: transparent;"
        panel_border_css = "border: none;"
        current_gradient = ""
        if color_mode == "rainbow":
            current_gradient = (
                "background-image: linear-gradient(90deg, #ff4f7d, #ffc857, #5dd39e, #50c5ff, #c084fc);"
                "color: transparent;"
                "-gtk-icon-shadow: none;"
                "background-clip: text;"
            )
        elif color_mode == "bg":
            wal_special = self._load_wal_special()
            if wal_special:
                bg_base, _ = wal_special
                panel_r, panel_g, panel_b = self._hex_to_rgb(bg_base, fallback=(16, 20, 26))
                highlight_color, secondary_color, fade_color = self._contrast_text_on(bg_base)
            else:
                panel_r, panel_g, panel_b = (14, 18, 24)
                highlight_color, secondary_color, fade_color = ("#f4f7fb", "#c8d8ea", "#9aafc6")
            panel_bg_css = f"background: rgba({panel_r}, {panel_g}, {panel_b}, {bg_opacity:.3f});"
            panel_border_css = "border: 1px solid rgba(255,255,255,0.16);"
        elif color_mode == "auto_dynamic":
            # Initial default until sampler updates: text-only unless panel boost requested.
            if dynamic_panel_boost > 0.01:
                panel_bg_css = f"background: rgba(16, 20, 28, {min(0.96, bg_opacity + dynamic_panel_boost):.3f});"
                panel_border_css = "border: 1px solid rgba(255,255,255,0.18);"
            else:
                panel_bg_css = "background: transparent;"
                panel_border_css = "border: none;"
            highlight_color, secondary_color, fade_color = ("#f4f7fb", "#c8d8ea", "#9aafc6")

        self._style_state = {
            "font_size": font_size,
            "font_family": font_family,
            "font_weight": font_weight,
            "letter_spacing": letter_spacing,
            "line_spacing": line_spacing,
            "highlight_color": highlight_color,
            "secondary_color": secondary_color,
            "fade_color": fade_color,
            "panel_bg_css": panel_bg_css,
            "panel_border_css": panel_border_css,
            "current_gradient": current_gradient,
            "shadow": shadow,
        }
        self._render_css(self._style_state)

    def _apply_state_payload(self, payload: dict[str, Any]) -> None:
        has_player = bool(payload.get("has_player", False))
        display_visible = bool(payload.get("display_visible", True))
        if not has_player:
            self._render_lines(["No active player"], 0)
            self.revealer.set_reveal_child(True)
            return

        if not display_visible:
            self.revealer.set_reveal_child(False)
            return

        lines_raw = payload.get("window_lines")
        if isinstance(lines_raw, list) and lines_raw:
            lines = [str(x) for x in lines_raw]
            curr_idx = int(payload.get("current_window_index", 0))
        else:
            prev_line = str(payload.get("prev_line", "")).strip()
            curr_line = str(payload.get("curr_line", "")).strip() or "No lyrics available"
            next_line = str(payload.get("next_line", "")).strip()
            lines = [x for x in [prev_line, curr_line, next_line] if x != ""]
            if not lines:
                lines = ["No lyrics available"]
            curr_idx = lines.index(curr_line) if curr_line in lines else min(1, len(lines) - 1)
        playback_state = str(payload.get("playback_state", "Stopped"))
        ms_to_next = int(payload.get("ms_to_next_line", 0))
        word_index = int(payload.get("current_word_index", -1))

        if self._animation_style == "line_flow_up" and ms_to_next > 0:
            # Base duration (stable, readable)
            base = 320

            # Speed factor (faster song = slightly faster animation, not instant)
            speed_factor = max(0.6, min(1.4, ms_to_next / 600.0))

            # Final duration
            dur = int(base * speed_factor)

            # Clamp to keep smoothness
            dur = max(220, min(520, dur))

            self._flow_anim_duration_ms = dur

        self._render_lines(lines, curr_idx, word_index)
        self.revealer.set_reveal_child(playback_state != "Stopped")

    def _read_state_once(self) -> None:
        payload = self.state_file.read()
        if payload:
            self._apply_state_payload(payload)

    def _poll_config(self) -> bool:
        cfg_path = Path("config/config.json")
        try:
            mtime = cfg_path.stat().st_mtime
        except OSError:
            mtime = 0.0

        if mtime != self._cfg_mtime:
            self._cfg_mtime = mtime
            self._apply_config(load_config())
        return True

    def _poll_state(self) -> bool:
        # Fallback if event bus not connected.
        try:
            mtime = self.state_file.path.stat().st_mtime
        except OSError:
            mtime = 0.0
        if mtime != self._state_mtime:
            self._state_mtime = mtime
            self._read_state_once()
        return True

    def _start_bus_thread(self) -> None:
        thread = threading.Thread(target=self._bus_loop, daemon=True)
        thread.start()

    def _bus_loop(self) -> None:
        sock = self.bus_client.connect()
        if not sock:
            return
        with sock:
            file_obj = sock.makefile("r", encoding="utf-8")
            while not self._stop_bus:
                try:
                    line = file_obj.readline()
                    if not line:
                        break
                    payload = json.loads(line)
                    GLib.idle_add(self._apply_state_payload, payload)
                except (OSError, ValueError, json.JSONDecodeError):
                    break


def run_overlay_app() -> None:
    app = Gtk.Application(application_id="dev.lyricfetch.overlay")

    def on_activate(application: Gtk.Application) -> None:
        win = OverlayWindow(application)
        win.present()

    app.connect("activate", on_activate)
    app.run()
