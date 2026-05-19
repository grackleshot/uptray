# Technology Stack

## Runtime
- **Python 3** — single script, no packaging
- **PyQt6** — system tray applet (optional dependency, imported dynamically)

## External Dependencies
- `topgrade` — the actual upgrade tool being wrapped
- `checkupdates` — pacman update checking (pacman-contrib package)
- `paru` or `yay` — AUR helper
- `flatpak` — flatpak update checking
- `notify-send` — desktop notifications (libnotify)

## Supported Terminals (hardcoded priority)
1. konsole
2. alacritty
3. kitty
4. xterm

## Platform
- Linux (Arch-centric)
- XDG Desktop Entry spec for autostart
