#!/usr/bin/env bash

set -e

echo "🎵 LyricFetch Universal Installer"
echo "================================="

# 1. Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "❌ Cannot detect OS."
    exit 1
fi

echo "📦 Detected OS: $OS"
echo "🛠️  Installing system dependencies..."

if [[ "$OS" == "arch" || "$OS" == "manjaro" || "$OS" == "endeavouros" ]]; then
    sudo pacman -S --needed --noconfirm python python-pip python-gobject playerctl gtk4 gtk-layer-shell grim maim cairo gobject-introspection
elif [[ "$OS" == "ubuntu" || "$OS" == "debian" || "$OS" == "linuxmint" || "$OS" == "pop" ]]; then
    sudo apt update
    sudo apt install -y python3 python3-pip python3-venv python3-gi gir1.2-gtk-4.0 playerctl libgtk-4-dev libgtk4-layer-shell-dev grim maim libcairo2-dev libgirepository1.0-dev
elif [[ "$OS" == "fedora" ]]; then
    sudo dnf install -y python3 python3-pip python3-gobject playerctl gtk4-devel gtk4-layer-shell-devel grim maim cairo-devel
else
    echo "⚠️  Unsupported OS for automatic dependency installation."
    echo "Please ensure you have python, pip, playerctl, PyGObject, GTK4, and gtk4-layer-shell installed."
fi

# 2. Setup Virtual Environment
INSTALL_DIR="$HOME/.local/share/lyricfetch"
VENV_DIR="$INSTALL_DIR/venv"

echo "🐍 Setting up Python Virtual Environment in $VENV_DIR..."
mkdir -p "$INSTALL_DIR"

if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="python"
fi

$PYTHON_CMD -m venv "$VENV_DIR" --system-site-packages

# 3. Install Python Dependencies
echo "📥 Installing Python packages..."
"$VENV_DIR/bin/pip" install -r requirements.txt

# 4. Copy project files
echo "📂 Copying project files..."
cp -r core services ui config main.py "$INSTALL_DIR/"

# 5. Install Systemd Services
echo "⚙️  Setting up systemd services..."
cd "$INSTALL_DIR"
"$VENV_DIR/bin/python" main.py install-services --enable

# 6. Create Desktop Entry
echo "🖥️  Creating Desktop Entry..."
DESKTOP_FILE="$HOME/.local/share/applications/lyricfetch-config.desktop"
cat << EOF > "$DESKTOP_FILE"
[Desktop Entry]
Name=LyricFetch Settings
Comment=Configure LyricFetch Overlay
Exec=$VENV_DIR/bin/python $INSTALL_DIR/main.py config
Icon=preferences-system
Terminal=false
Type=Application
Categories=Settings;AudioVideo;
EOF

chmod +x "$DESKTOP_FILE"

echo ""
echo "✅ Installation Complete!"
echo "The LyricFetch daemon and overlay are now running in the background."
echo "You can open 'LyricFetch Settings' from your app launcher to configure it."
