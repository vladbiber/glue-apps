"""Curated store content: seed apps, featured banners and friendly categories."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .model import App, AppSource

FLATHUB_ICON = "https://dl.flathub.org/repo/appstream/x86_64/icons/128x128/{}.png"

# (id, name, summary, categories); id is a Flathub id or aur:/repo: plus a package name.
SEED = (
    # Internet
    ("org.mozilla.firefox", "Firefox", "Fast, private web browser", ("Network", "WebBrowser")),
    ("io.gitlab.librewolf-community", "LibreWolf", "Firefox with privacy settings built in", ("Network", "WebBrowser")),
    ("org.qutebrowser.qutebrowser", "qutebrowser", "Keyboard-driven browser with vim keys", ("Network", "WebBrowser")),
    ("com.brave.Browser", "Brave", "Browser with a built-in ad blocker", ("Network", "WebBrowser")),
    ("app.zen_browser.zen", "Zen Browser", "Calm browser with vertical tabs", ("Network", "WebBrowser")),
    ("org.chromium.Chromium", "Chromium", "Open-source base of Chrome", ("Network", "WebBrowser")),
    ("com.google.Chrome", "Google Chrome", "Google's web browser", ("Network", "WebBrowser")),
    ("dev.vencord.Vesktop", "Vesktop", "Discord with Vencord, smooth screen share", ("Network", "Chat")),
    ("org.qbittorrent.qBittorrent", "qBittorrent", "Download torrents", ("Network",)),
    ("org.localsend.localsend_app", "LocalSend", "Send files to nearby devices", ("Network", "Utility")),
    ("org.nickvision.tubeconverter", "Parabolic", "Download videos and music", ("Network", "AudioVideo")),
    # Chat
    ("com.discordapp.Discord", "Discord", "Voice, video and text chat", ("Network", "Chat")),
    ("org.telegram.desktop", "Telegram", "Fast and secure messaging", ("Network", "Chat")),
    ("org.signal.Signal", "Signal", "Private messaging", ("Network", "Chat")),
    ("com.rtosta.zapzap", "ZapZap", "WhatsApp on the desktop", ("Network", "Chat")),
    ("im.riot.Riot", "Element", "Secure chat over Matrix", ("Network", "Chat")),
    ("com.slack.Slack", "Slack", "Team chat for work", ("Network", "Chat")),
    ("us.zoom.Zoom", "Zoom", "Video meetings", ("Network", "Chat")),
    ("com.github.IsmaelMartinez.teams_for_linux", "Teams for Linux", "Microsoft Teams client",
     ("Network", "Chat")),
    # Office
    ("org.libreoffice.LibreOffice", "LibreOffice", "Documents, spreadsheets and slides", ("Office",)),
    ("org.onlyoffice.desktopeditors", "ONLYOFFICE", "Office files that open anywhere", ("Office",)),
    ("org.mozilla.Thunderbird", "Thunderbird", "Email and calendar", ("Office", "Network")),
    ("md.obsidian.Obsidian", "Obsidian", "Notes that link together", ("Office",)),
    ("net.cozic.joplin_desktop", "Joplin", "Notes and to-dos that sync", ("Office",)),
    ("org.kde.okular", "Okular", "Read PDFs and documents", ("Office",)),
    ("com.github.johnfactotum.Foliate", "Foliate", "Read e-books", ("Office",)),
    ("com.calibre_ebook.calibre", "calibre", "Manage your e-book library", ("Office",)),
    ("com.github.xournalpp.xournalpp", "Xournal++", "Handwritten notes and PDF markup", ("Office",)),
    # Media
    ("org.videolan.VLC", "VLC", "Plays every video and music file", ("AudioVideo", "Video")),
    ("com.spotify.Client", "Spotify", "Music and podcasts", ("AudioVideo", "Audio")),
    ("com.obsproject.Studio", "OBS Studio", "Record and stream your screen", ("AudioVideo", "Video")),
    ("org.kde.kdenlive", "Kdenlive", "Edit videos like a pro", ("AudioVideo", "Video")),
    ("org.shotcut.Shotcut", "Shotcut", "Simple video editor", ("AudioVideo", "Video")),
    ("org.audacityteam.Audacity", "Audacity", "Record and edit audio", ("AudioVideo", "Audio")),
    ("fr.handbrake.ghb", "HandBrake", "Convert videos to any format", ("AudioVideo", "Video")),
    ("io.mpv.Mpv", "mpv", "Minimal video player", ("AudioVideo", "Video")),
    ("org.kde.haruna", "Haruna", "Friendly video player", ("AudioVideo", "Video")),
    ("com.stremio.Stremio", "Stremio", "Movies and shows in one place", ("AudioVideo", "Video")),
    ("com.github.wwmm.easyeffects", "Easy Effects", "Sound effects and equalizer", ("AudioVideo", "Audio")),
    # Gaming
    ("com.valvesoftware.Steam", "Steam", "Play thousands of games", ("Game",)),
    ("org.vinegarhq.Sober", "Sober", "Play Roblox on Linux", ("Game",)),
    ("net.lutris.Lutris", "Lutris", "All your game launchers in one place", ("Game",)),
    ("com.heroicgameslauncher.hgl", "Heroic", "Epic, GOG and Amazon games", ("Game",)),
    ("org.prismlauncher.PrismLauncher", "Prism Launcher", "Minecraft with mods and instances", ("Game",)),
    ("net.davidotek.pupgui2", "ProtonUp-Qt", "Install Proton-GE and Wine-GE", ("Game", "Utility")),
    ("com.usebottles.bottles", "Bottles", "Run Windows software", ("Game", "Utility")),
    ("io.itch.itch", "itch", "Indie games from itch.io", ("Game",)),
    ("com.moonlight_stream.Moonlight", "Moonlight", "Stream games from your PC", ("Game",)),
    ("org.libretro.RetroArch", "RetroArch", "Every retro console in one app", ("Game",)),
    ("net.pcsx2.PCSX2", "PCSX2", "PlayStation 2 emulator", ("Game",)),
    ("net.rpcs3.RPCS3", "RPCS3", "PlayStation 3 emulator", ("Game",)),
    ("org.DolphinEmu.dolphin-emu", "Dolphin", "GameCube and Wii emulator", ("Game",)),
    ("info.cemu.Cemu", "Cemu", "Wii U emulator", ("Game",)),
    ("org.duckstation.DuckStation", "DuckStation", "PlayStation emulator", ("Game",)),
    ("sh.ppy.osu", "osu!", "Rhythm game with millions of maps", ("Game",)),
    ("net.supertuxkart.SuperTuxKart", "SuperTuxKart", "Free kart racing", ("Game",)),
    ("com.play0ad.zeroad", "0 A.D.", "Free historical strategy game", ("Game",)),
    # Graphics
    ("org.gimp.GIMP", "GIMP", "Edit photos and images", ("Graphics",)),
    ("org.kde.krita", "Krita", "Digital painting", ("Graphics",)),
    ("org.inkscape.Inkscape", "Inkscape", "Vector drawing and design", ("Graphics",)),
    ("org.blender.Blender", "Blender", "3D modeling and animation", ("Graphics",)),
    ("org.darktable.Darktable", "darktable", "Develop RAW photos", ("Graphics",)),
    ("com.github.PintaProject.Pinta", "Pinta", "Simple image editor", ("Graphics",)),
    ("org.upscayl.Upscayl", "Upscayl", "Upscale images with AI", ("Graphics",)),
    ("org.freecad.FreeCAD", "FreeCAD", "3D CAD for makers", ("Graphics",)),
    # Development
    ("com.vscodium.codium", "VSCodium", "Code editor", ("Development",)),
    ("com.visualstudio.code", "Visual Studio Code", "Code editor by Microsoft", ("Development",)),
    ("dev.zed.Zed", "Zed", "Fast collaborative code editor", ("Development",)),
    ("org.godotengine.Godot", "Godot", "Make 2D and 3D games", ("Development",)),
    ("io.github.shiftey.Desktop", "GitHub Desktop", "Git without the terminal", ("Development",)),
    ("com.google.AndroidStudio", "Android Studio", "Build Android apps", ("Development",)),
    ("io.dbeaver.DBeaverCommunity", "DBeaver", "Database manager", ("Development",)),
    ("com.usebruno.Bruno", "Bruno", "Test HTTP APIs", ("Development",)),
    # AI
    ("aur:claude-desktop", "Claude Desktop", "Claude app with chat, Cowork and Claude Code",
     ("AI", "Office")),
    ("aur:claude-code", "Claude Code", "AI coding agent in the terminal", ("Development", "AI")),
    ("aur:openai-codex-bin", "Codex", "OpenAI's coding agent in the terminal",
     ("Development", "AI")),
    ("aur:codex-app-unofficial", "Codex Desktop", "OpenAI's Codex app with a window",
     ("Development", "AI")),
    ("ai.opencode.opencode", "OpenCode", "Open-source AI coding agent", ("Development", "AI")),
    ("aur:cursor-bin", "Cursor", "Code editor built around AI", ("Development", "AI")),
    ("repo:ollama", "Ollama", "Run language models on your own PC", ("AI", "Development")),
    ("ai.lmstudio.lm-studio", "LM Studio", "Download and chat with local models", ("AI",)),
    ("ai.jan.Jan", "Jan", "Private offline AI assistant", ("AI",)),
    ("com.jeffser.Alpaca", "Alpaca", "Chat with local and online models", ("AI",)),
    ("io.gpt4all.gpt4all", "GPT4All", "Open-source assistant that runs offline", ("AI",)),
    ("io.github.qwersyk.Newelle", "Newelle", "AI assistant that can use your desktop", ("AI",)),
    # Utilities
    ("com.bitwarden.desktop", "Bitwarden", "Password manager", ("Utility",)),
    ("org.keepassxc.KeePassXC", "KeePassXC", "Offline password manager", ("Utility",)),
    ("io.missioncenter.MissionCenter", "Mission Center", "See what uses your CPU and RAM", ("Utility", "System")),
    ("com.github.tchx84.Flatseal", "Flatseal", "Manage app permissions", ("Utility",)),
    ("io.github.flattool.Warehouse", "Warehouse", "Manage installed Flathub apps", ("Utility",)),
    ("org.gnome.World.PikaBackup", "Pika Backup", "Back up your files", ("Utility",)),
    ("it.mijorus.gearlever", "Gear Lever", "Manage AppImages", ("Utility",)),
    ("org.bleachbit.BleachBit", "BleachBit", "Free up disk space", ("Utility", "System")),
)

ESSENTIALS = ("Firefox", "LibreOffice", "VLC", "Vesktop", "Spotify", "OBS Studio",
              "Thunderbird", "Telegram", "GIMP", "Bitwarden", "qBittorrent", "VSCodium")
GAMES = ("Steam", "Sober", "Lutris", "Heroic", "Prism Launcher", "ProtonUp-Qt", "Bottles",
         "itch", "Moonlight", "RetroArch", "PCSX2", "osu!")
CREATE = ("Kdenlive", "Blender", "Krita", "Inkscape", "Audacity", "GIMP")
AI_APPS = ("Claude Desktop", "Claude Code", "Codex Desktop", "Codex", "Cursor", "OpenCode",
           "Ollama", "LM Studio", "Jan", "Alpaca", "GPT4All", "Newelle")

RECOMMENDED = ESSENTIALS + GAMES + CREATE


@dataclass(frozen=True)
class Feature:
    app: str
    eyebrow: str
    title: str
    blurb: str
    colors: tuple[str, str]


FEATURED = (
    Feature("Steam", "Editors' choice", "Your games, ready on day one",
            "Proton is set up for you. Install Steam and press Play.", ("#1b2838", "#2a475e")),
    Feature("Kdenlive", "Create", "Cut your first video tonight",
            "A full editor with effects, titles and transitions.", ("#1d3b5c", "#5a3a7a")),
    Feature("Firefox", "Get started", "Browse fast, stay private",
            "Tracking protection on by default.", ("#5b2a86", "#e66000")),
    Feature("OBS Studio", "Play", "Stream and record anything",
            "Capture games, windows and webcams in one scene.", ("#1e1e2e", "#46325d")),
)

CATEGORIES = {
    "All": (), "Internet": ("Network", "WebBrowser"), "Office": ("Office",),
    "Media": ("AudioVideo", "Audio", "Video"), "Chat": ("Chat", "InstantMessaging"),
    "Gaming": ("Game",), "Graphics": ("Graphics",), "Development": ("Development",),
    "AI": ("AI",),
    "Utilities": ("Utility", "System"),
}

CATEGORY_ICONS = {
    "Internet": "web-browser-symbolic", "Office": "x-office-document-symbolic",
    "Media": "applications-multimedia-symbolic", "Chat": "user-available-symbolic",
    "Gaming": "input-gaming-symbolic", "Graphics": "applications-graphics-symbolic",
    "Development": "utilities-terminal-symbolic", "Utilities": "applications-utilities-symbolic",
    "AI": "applications-science-symbolic",
}

CATEGORY_COLORS = {
    "Internet": ("#2563eb", "#06b6d4"), "Office": ("#0f766e", "#22c55e"),
    "Media": ("#db2777", "#f97316"), "Chat": ("#7c3aed", "#ec4899"),
    "Gaming": ("#16a34a", "#84cc16"), "Graphics": ("#ea580c", "#facc15"),
    "Development": ("#334155", "#6366f1"), "Utilities": ("#0369a1", "#a855f7"),
    "AI": ("#0f766e", "#0ea5e9"),
}


SEED_ICONS = {"repo": "utilities-terminal", "aur": "application-x-executable"}
TERMINAL_APPS = {"claude-code", "openai-codex-bin", "ollama"}


def native_twin(name: str, native_installed, aur_installed=frozenset()) -> AppSource | None:
    """An installed pacman/AUR package that is this app under another source:
    Spotify from the AUR is "spotify", OBS Studio "obs-studio", Vesktop "vesktop-bin"."""
    base = "-".join(re.findall(r"[a-z0-9]+", name.casefold()))
    for package in (base, base.replace("-", ""), base + "-bin", base.replace("-", "") + "-bin"):
        if package and package in native_installed:
            return AppSource("aur" if package in aur_installed else "repo", package, "", True)
    return None


def seed_apps(flatpak_installed: set[str] | frozenset[str] = frozenset(),
              native_installed: set[str] | frozenset[str] = frozenset(),
              aur_installed: set[str] | frozenset[str] = frozenset()) -> list[App]:
    """Offline store front. Ids are Flathub ids, or "aur:<pkg>" / "repo:<pkg>"."""
    apps = []
    for ref, name, summary, categories in SEED:
        kind, _sep, package = ref.partition(":") if ref.startswith(("aur:", "repo:")) \
            else ("flatpak", "", ref)
        installed = package in (flatpak_installed if kind == "flatpak" else native_installed)
        icon = FLATHUB_ICON.format(package) if kind == "flatpak" else \
            "utilities-terminal" if package in TERMINAL_APPS else SEED_ICONS[kind]
        sources = (AppSource(kind, package, "", installed),)
        if kind == "flatpak" and (twin := native_twin(name, native_installed, aur_installed)):
            sources += (twin,)
        apps.append(App(app_id=package, name=name, summary=summary, icon=icon,
                        categories=categories, sources=sources))
    return apps


_CATEGORY_PRIORITY = ("Gaming", "Chat", "Graphics", "Development", "AI", "Office",
                      "Media", "Internet", "Utilities")


def category_of(app: App) -> str:
    for label in _CATEGORY_PRIORITY:
        if set(app.categories) & set(CATEGORIES[label]):
            return label
    return "Utilities"


def split_by_category(apps: list[App], category: str) -> tuple[list[App], list[App]]:
    """Matches inside the chosen category first, the rest of the matches after."""
    tags = set(CATEGORIES.get(category, ()))
    if not tags:
        return list(apps), []
    inside = [app for app in apps if tags & set(app.categories)]
    return inside, [app for app in apps if app not in inside]
