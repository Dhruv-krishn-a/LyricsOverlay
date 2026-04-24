from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


CONFIG_PATH = Path("config/config.json")

DEFAULT_CONFIG: dict[str, Any] = {
    "position": "free",
    "monitor": "primary",
    "render_x_pct": 50,
    "render_y_pct": 85,
    "font_size": 34,
    "font_family": "JetBrains Mono, Sans",
    "font_weight": 850,
    "letter_spacing": 0.0,
    "line_spacing": 1.12,
    "highlight_color": "#ffffff",
    "secondary_color": "#7ad7ff",
    "fade_color": "#9aa0a6",
    "color_mode": "solid",
    "dynamic_sampling_backend": "auto",
    "dynamic_interval_ms": 320,
    "dynamic_hysteresis": 0.3,
    "dynamic_panel_boost": 0.0,
    "hide_when_no_lyrics": False,
    "animation_speed": 0.2,
    "animation_style": "slide_up",
    "animation_preset": "custom",
    "offset_ms": 0,
    "update_interval_ms": 100,
    "retry_interval_sec": 8,
    "line_width_percent": 70,
    "visible_line_count": 3,
    "bottom_margin": 72,
    "top_margin": 72,
    "show_shadow": True,
    "bg_opacity": 0.62,
    "bg_blur_hint": True,
}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        if isinstance(data, dict):
            merged.update(data)
        return merged
    except (OSError, ValueError, TypeError):
        return dict(DEFAULT_CONFIG)


def save_config(config: dict[str, Any]) -> None:
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile("w", encoding="utf-8", dir=CONFIG_PATH.parent, delete=False) as tmp:
        json.dump(merged, tmp, indent=2, ensure_ascii=True)
        tmp.write("\n")
        tmp.flush()
        tmp_path = Path(tmp.name)

    tmp_path.replace(CONFIG_PATH)
