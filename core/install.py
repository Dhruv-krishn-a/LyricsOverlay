from __future__ import annotations

from pathlib import Path
import subprocess


def install_user_services(project_root: Path, python_path: str, enable_now: bool = False) -> list[Path]:
    user_dir = Path.home() / ".config" / "systemd" / "user"
    user_dir.mkdir(parents=True, exist_ok=True)

    daemon = user_dir / "lyrics-overlay-daemon.service"
    ui = user_dir / "lyrics-overlay-ui.service"
    config = user_dir / "lyrics-overlay-config.service"

    daemon.write_text(
        f"""[Unit]\nDescription=LyricFetch Daemon\nAfter=graphical-session.target\n\n[Service]\nType=simple\nWorkingDirectory={project_root}\nExecStart={python_path} {project_root / 'main.py'} daemon\nRestart=always\nRestartSec=2\n\n[Install]\nWantedBy=default.target\n""",
        encoding="utf-8",
    )

    ui.write_text(
        f"""[Unit]\nDescription=LyricFetch GTK Overlay UI\nAfter=lyrics-overlay-daemon.service\nRequires=lyrics-overlay-daemon.service\n\n[Service]\nType=simple\nWorkingDirectory={project_root}\nExecStart={python_path} {project_root / 'main.py'} overlay\nRestart=always\nRestartSec=2\n\n[Install]\nWantedBy=default.target\n""",
        encoding="utf-8",
    )

    config.write_text(
        f"""[Unit]\nDescription=LyricFetch Config UI\nAfter=graphical-session.target\n\n[Service]\nType=simple\nWorkingDirectory={project_root}\nExecStart={python_path} {project_root / 'main.py'} config\n\n[Install]\nWantedBy=default.target\n""",
        encoding="utf-8",
    )

    hypr_conf = Path.home() / ".config" / "hypr" / "lyricfetch.conf"
    hypr_conf.parent.mkdir(parents=True, exist_ok=True)
    hypr_conf.write_text(
        "# LyricFetch optional blur hint\n"
        "layerrule = blur, lyricfetch\n"
        "layerrule = ignorezero, lyricfetch\n"
        "layerrule = xray 1, lyricfetch\n",
        encoding="utf-8",
    )

    if enable_now:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "--user", "enable", "--now", "lyrics-overlay-daemon.service"], check=False)
        subprocess.run(["systemctl", "--user", "enable", "--now", "lyrics-overlay-ui.service"], check=False)

    return [daemon, ui, config, hypr_conf]
