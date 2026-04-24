from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import threading
from typing import Any


BUS_PATH = Path.home() / ".cache" / "lyrics-overlay" / "events.sock"


class StateBusServer:
    def __init__(self, path: Path = BUS_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.server: socket.socket | None = None
        self._clients: list[socket.socket] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError:
            pass

        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self.server.listen(8)
        self.server.settimeout(0.5)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self) -> None:
        assert self.server is not None
        while self._running:
            try:
                conn, _ = self.server.accept()
                conn.setblocking(True)
                with self._lock:
                    self._clients.append(conn)
            except socket.timeout:
                continue
            except OSError:
                break

    def publish(self, payload: dict[str, Any]) -> None:
        data = (json.dumps(payload, ensure_ascii=True) + "\n").encode("utf-8")
        dead: list[socket.socket] = []
        with self._lock:
            for client in self._clients:
                try:
                    client.sendall(data)
                except OSError:
                    dead.append(client)
            if dead:
                for client in dead:
                    if client in self._clients:
                        self._clients.remove(client)
                    try:
                        client.close()
                    except OSError:
                        pass

    def close(self) -> None:
        self._running = False
        with self._lock:
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            try:
                client.close()
            except OSError:
                pass
        if self.server:
            try:
                self.server.close()
            except OSError:
                pass
            self.server = None
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError:
            pass


class StateBusClient:
    def __init__(self, path: Path = BUS_PATH) -> None:
        self.path = path

    def connect(self) -> socket.socket | None:
        if not self.path.exists():
            return None
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(self.path))
            return sock
        except OSError:
            try:
                sock.close()
            except OSError:
                pass
            return None
