#!/usr/bin/env bash

set -e

echo "🗑️  LyricFetch Uninstaller"
echo "========================"

INSTALL_DIR="$HOME/.local/share/lyricfetch"
DESKTOP_FILE="$HOME/.local/share/applications/lyricfetch-config.desktop"
CACHE_DIR="$HOME/.cache/lyrics-overlay"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
HYPR_CONF="$HOME/.config/hypr/lyricfetch.conf"

echo "🛑 Stopping and disabling background services..."
systemctl --user stop lyrics-overlay-daemon.service lyrics-overlay-ui.service lyrics-overlay-config.service 2>/dev/null || true
systemctl --user disable lyrics-overlay-daemon.service lyrics-overlay-ui.service lyrics-overlay-config.service 2>/dev/null || true

echo "🧹 Removing systemd service files..."
rm -f "$SYSTEMD_USER_DIR/lyrics-overlay-daemon.service"
rm -f "$SYSTEMD_USER_DIR/lyrics-overlay-ui.service"
rm -f "$SYSTEMD_USER_DIR/lyrics-overlay-config.service"
systemctl --user daemon-reload

echo "📂 Removing application files and virtual environment..."
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "  -> Removed $INSTALL_DIR"
fi

echo "🖥️  Removing Desktop Entry..."
if [ -f "$DESKTOP_FILE" ]; then
    rm -f "$DESKTOP_FILE"
    echo "  -> Removed $DESKTOP_FILE"
fi

echo "🗄️  Removing cached lyrics and album art..."
if [ -d "$CACHE_DIR" ]; then
    rm -rf "$CACHE_DIR"
    echo "  -> Removed $CACHE_DIR"
fi

echo "⚙️  Removing Hyprland blur configuration..."
if [ -f "$HYPR_CONF" ]; then
    rm -f "$HYPR_CONF"
    echo "  -> Removed $HYPR_CONF"
fi

# We intentionally DO NOT uninstall system packages (like python, gtk4, playerctl) 
# because other applications on the user's system might be relying on them.

echo ""
echo "✅ Uninstallation Complete!"
echo "LyricFetch has been completely removed from your system."
