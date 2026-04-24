from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Optional

import requests


SAFE_RE = re.compile(r"[^a-zA-Z0-9._-]+")
FEAT_RE = re.compile(r"\s*(\(|\[)?(feat\.?|ft\.?|featuring)\s+[^)\]]+(\)|\])?\s*$", re.IGNORECASE)
EXTRA_RE = re.compile(r"\s*[\(\[\-–—].*$")


@dataclass
class LyricsResult:
    synced: Optional[str]
    plain: Optional[str]
    source: str


class LyricsService:
    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self.cache_dir = cache_dir or Path.home() / ".cache" / "lyrics-overlay"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _safe_name(self, artist: str, title: str) -> str:
        base = f"{artist}-{title}".strip().lower()
        return SAFE_RE.sub("_", base)[:200]

    def _cache_paths(self, artist: str, title: str) -> tuple[Path, Path]:
        name = self._safe_name(artist, title)
        return self.cache_dir / f"{name}.lrc", self.cache_dir / f"{name}.txt"

    def _normalize_artist(self, artist: str) -> str:
        clean = artist.strip()
        if "," in clean:
            clean = clean.split(",")[0].strip()
        if "&" in clean:
            clean = clean.split("&")[0].strip()
        return clean

    def _normalize_title(self, title: str) -> str:
        clean = title.strip()
        clean = FEAT_RE.sub("", clean).strip()
        clean = EXTRA_RE.sub("", clean).strip()
        return clean or title.strip()

    def _variants(self, title: str, artist: str) -> list[tuple[str, str]]:
        t1 = title.strip()
        a1 = artist.strip()
        t2 = self._normalize_title(t1)
        a2 = self._normalize_artist(a1)
        pairs = [
            (t1, a1),
            (t2, a1),
            (t1, a2),
            (t2, a2),
        ]
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for t, a in pairs:
            key = f"{a.lower()}::{t.lower()}"
            if key not in seen and t and a:
                seen.add(key)
                out.append((t, a))
        return out

    def _read_cache(self, artist: str, title: str) -> Optional[LyricsResult]:
        lrc_path, txt_path = self._cache_paths(artist, title)
        if lrc_path.exists():
            return LyricsResult(synced=lrc_path.read_text(encoding="utf-8"), plain=None, source="cache:lrc")
        if txt_path.exists():
            return LyricsResult(synced=None, plain=txt_path.read_text(encoding="utf-8"), source="cache:plain")
        return None

    def _write_cache(self, artist: str, title: str, synced: Optional[str], plain: Optional[str]) -> None:
        lrc_path, txt_path = self._cache_paths(artist, title)
        if synced:
            lrc_path.write_text(synced, encoding="utf-8")
        elif plain:
            txt_path.write_text(plain, encoding="utf-8")

    def _extract_payload(self, payload: dict) -> Optional[LyricsResult]:
        synced = (payload.get("syncedLyrics") or "").strip() or None
        plain = (payload.get("plainLyrics") or "").strip() or None
        if not synced and not plain:
            return None
        return LyricsResult(synced=synced, plain=plain, source="lrclib")

    def _http_get(self, url: str, params: dict) -> Optional[requests.Response]:
        try:
            return requests.get(
                url,
                params=params,
                timeout=5,
                headers={"User-Agent": "lyricfetch/0.1"},
            )
        except requests.RequestException:
            return None

    def fetch(self, title: str, artist: str, album: str = "") -> Optional[LyricsResult]:
        for v_title, v_artist in self._variants(title, artist):
            cached = self._read_cache(v_artist, v_title)
            if cached:
                return cached

        for v_title, v_artist in self._variants(title, artist):
            params = {"track_name": v_title, "artist_name": v_artist}
            if album:
                params["album_name"] = album
            response = self._http_get("https://lrclib.net/api/get", params=params)
            if not response or response.status_code != 200:
                continue
            try:
                payload = response.json()
            except ValueError:
                continue
            result = self._extract_payload(payload)
            if result:
                self._write_cache(v_artist, v_title, result.synced, result.plain)
                return result

        for v_title, v_artist in self._variants(title, artist):
            params = {"track_name": v_title, "artist_name": v_artist}
            response = self._http_get("https://lrclib.net/api/search", params=params)
            if not response or response.status_code != 200:
                continue
            try:
                payload = response.json()
            except ValueError:
                continue
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict):
                    continue
                result = self._extract_payload(item)
                if result:
                    self._write_cache(v_artist, v_title, result.synced, result.plain)
                    return result

        return None
