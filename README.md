# LyricFetch 🎵

A premium, seamlessly integrated, and highly customizable synced lyrics overlay for Linux desktop environments. 

LyricFetch is designed to feel like a native part of your OS. It floats transparently over your desktop, adapts to your background, and syncs flawlessly with whatever you are listening to.

![LyricFetch Demo](https://via.placeholder.com/800x400.png?text=LyricFetch+Screenshot+Placeholder)

## ✨ Premium Features

*   **Zero-Latency Sync (Event-Driven MPRIS):** Uses native DBus `Playerctl` bindings. Instead of polling your CPU, LyricFetch listens to system events. When a song changes, pauses, or seeks, the overlay reacts instantly with 0% idle CPU usage.
*   **Word-Wise Karaoke Highlighting:** Parses advanced `syncedLyrics` data to highlight words exactly as the singer sings them. Falls back to intelligent duration-based word estimation for standard LRC files.
*   **Intelligent Gap Detection & Visualizer:** If a song has a long instrumental intro or a mid-song guitar solo, the lyrics gracefully slide away, replaced by a mathematically animated **Flowing Wave** Cairo visualizer that pulses to the music.
*   **Duration-Matched Lyrics:** Ensures perfect sync by passing your exact audio file duration (down to the microsecond) to the LRCLIB API. This guarantees you get the right lyrics for your specific version of a song (e.g., Album Edit vs. Music Video Edit).
*   **"Now Playing" Toast:** When a new track starts, a sleek notification drops down displaying the Album Art, Track Title, and Artist before yielding focus to the lyrics.
*   **True Auto-Dynamic Transparency:** The overlay samples the screen directly behind it. If you drag it over a white window, the text instantly turns dark. Drag it over a dark wallpaper, it turns bright. No blurry background boxes—just pure, floating text.
*   **Universal Compatibility:** Built for Hyprland/Wayland using `gtk4-layer-shell`, but gracefully falls back to standard GTK window hints on X11 (i3, bspwm) and GNOME.

## 🚀 Installation (1-Click Universal Script)

We provide a robust bash script that automatically detects your OS (Arch, Ubuntu/Debian, Fedora), installs all native C-dependencies, sets up a secure Python virtual environment, and generates systemd services.

```bash
git clone https://github.com/yourusername/LyricFetch.git
cd LyricFetch
./install.sh
```

**That's it!** The daemon is now running in the background, and you can open "LyricFetch Settings" from your app launcher.

### Uninstallation
If you ever want to remove LyricFetch, simply run:
```bash
./uninstall.sh
```

## ⚙️ Configuration UI

LyricFetch comes with a beautiful GTK4 Settings application. All changes are **live** and instantly applied to the overlay as you tweak them.

*   **Placement:** Drag a visual bounding box to place the overlay anywhere on your screen.
*   **Typography:** Fine-tune font family, weight, size, letter spacing, and line spacing.
*   **Animation:** Choose transition styles (`crossfade`, `line_flow_up`, `slide_up`, etc.) and tweak the animation speed.
*   **Color Modes:** Choose `solid` colors, `rainbow` gradients, `pywal` integration, or the completely transparent `auto_dynamic` mode.

Open the settings via your app launcher or terminal:
```bash
python main.py config
```

## 🛠️ Advanced Manual Usage

If you prefer to run things manually (for debugging or custom setups):

```bash
# Run everything (Daemon + Overlay)
python main.py all

# Run only the backend daemon
python main.py daemon

# Run only the GTK overlay
python main.py overlay

# Open the Settings GUI
python main.py config
```

## 📂 How It Works

*   **Backend Daemon:** Connects to MPRIS via DBus, tracks playback, downloads album art and lyrics from LRCLIB, manages local caching (`~/.cache/lyrics-overlay`), runs the `SyncEngine` to calculate precise timing, and broadcasts state payloads via a Unix socket.
*   **GTK4 Overlay:** Listens to the socket and renders the UI using Pango markup, GTK Revealers, and Cairo drawing areas.
*   **Dynamic Sampler:** A background thread periodically uses `grim` (Wayland) or `maim` (X11) to sample the pixels directly underneath the overlay window to calculate WCAG relative luminance.

## 🤝 Dependencies
*(Automatically handled by `install.sh`)*
*   Python 3.10+
*   GTK4 & PyGObject (`gir1.2-gtk-4.0`)
*   Playerctl DBus interface
*   gtk4-layer-shell (Optional, for Wayland compositor support)
*   grim (Wayland) or maim (X11) for screen sampling
*   libcairo2
