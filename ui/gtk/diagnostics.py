from __future__ import annotations

import json
import socket
import threading
from typing import Any

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from core.event_bus import StateBusClient
from core.state_file import StateFile


class DiagnosticsWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title="LyricFetch Diagnostics")
        self.set_default_size(640, 420)

        self.state_file = StateFile()
        self.client = StateBusClient()
        self._stop = False

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(14)
        root.set_margin_bottom(14)
        root.set_margin_start(14)
        root.set_margin_end(14)

        self.header = Gtk.Label(label="Waiting for daemon state...")
        self.header.set_xalign(0)
        root.append(self.header)

        self.grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        root.append(self.grid)

        self.fields = [
            "player",
            "artist",
            "title",
            "playback_state",
            "position_sec",
            "lyrics_source",
            "lyrics_available",
            "has_synced_lyrics",
            "fetch_status",
            "animation_style",
            "color_mode",
        ]
        self.labels: dict[str, Gtk.Label] = {}
        for idx, key in enumerate(self.fields):
            k = Gtk.Label(label=f"{key}:")
            k.set_xalign(0)
            v = Gtk.Label(label="-")
            v.set_xalign(0)
            v.set_selectable(True)
            self.grid.attach(k, 0, idx, 1, 1)
            self.grid.attach(v, 1, idx, 1, 1)
            self.labels[key] = v

        self.curr = Gtk.Label(label="")
        self.curr.set_xalign(0)
        self.curr.set_wrap(True)
        root.append(self.curr)

        self.set_child(root)

        GLib.timeout_add(500, self._poll_state_file)
        self.connect("close-request", self._on_close)
        self._start_bus_thread()

    def _on_close(self, _widget: Gtk.Widget) -> bool:
        self._stop = True
        return False

    def _apply_payload(self, payload: dict[str, Any]) -> None:
        self.header.set_text(f"Last update: {payload.get('ts', '-')}")
        for key in self.fields:
            self.labels[key].set_text(str(payload.get(key, "-")))
        self.curr.set_text(f"Current line: {payload.get('curr_line', '')}")

    def _poll_state_file(self) -> bool:
        if self._stop:
            return False
        payload = self.state_file.read()
        if payload:
            self._apply_payload(payload)
        return True

    def _start_bus_thread(self) -> None:
        thread = threading.Thread(target=self._bus_loop, daemon=True)
        thread.start()

    def _bus_loop(self) -> None:
        sock = self.client.connect()
        if not sock:
            return
        with sock:
            file_obj = sock.makefile("r", encoding="utf-8")
            while not self._stop:
                try:
                    line = file_obj.readline()
                    if not line:
                        break
                    payload = json.loads(line)
                    GLib.idle_add(self._apply_payload, payload)
                except (OSError, ValueError, json.JSONDecodeError):
                    break


def run_diagnostics_app() -> None:
    app = Gtk.Application(application_id="dev.lyricfetch.diagnostics")

    def on_activate(application: Gtk.Application) -> None:
        win = DiagnosticsWindow(application)
        win.present()

    app.connect("activate", on_activate)
    app.run()
