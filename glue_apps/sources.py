"""Where an app can be installed from: Pacman, Flatpak and the AUR, with details."""

from __future__ import annotations

import json
import re
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from .i18n import _
from .model import App

KINDS = ("repo", "flatpak", "aur")
# short source names on cards and detail pages
BADGES = {"repo": "Official", "flatpak": "Flatpak", "aur": "AUR"}
AUR_INFO = "https://aur.archlinux.org/rpc/v5/info?"
FLATHUB_SUMMARY = "https://flathub.org/api/v2/summary/{}"
FLATHUB_SEARCH = "https://flathub.org/api/v2/search"
FLATHUB_APPSTREAM = "https://flathub.org/api/v2/appstream/{}"

# Package names that cannot be guessed from the app name.
ALIASES = {
    "obsstudio": ("obs-studio",), "googlechrome": ("google-chrome",),
    "prismlauncher": ("prismlauncher",), "teamsforlinux": ("teams-for-linux",),
    "easyeffects": ("easyeffects",), "missioncenter": ("mission-center",),
    "pikabackup": ("pika-backup",), "gearlever": ("gearlever",),
    "githubdesktop": ("github-desktop-bin",), "zenbrowser": ("zen-browser-bin",),
    "0ad": ("0ad",), "osu": ("osu-lazer-bin",), "androidstudio": ("android-studio",),
    "element": ("element-desktop",), "signal": ("signal-desktop",),
    "telegram": ("telegram-desktop",), "libreoffice": ("libreoffice-fresh",),
    "onlyoffice": ("onlyoffice-bin",), "slack": ("slack-desktop",),
    "heroic": ("heroic-games-launcher-bin",), "protonupqt": ("protonup-qt",),
    "itch": ("itch-setup-bin",), "dolphin": ("dolphin-emu",), "upscayl": ("upscayl-bin",),
    "xournal": ("xournalpp",), "joplin": ("joplin-desktop",), "localsend": ("localsend-bin",),
    "brave": ("brave-bin",), "moonlight": ("moonlight-qt",), "rpcs3": ("rpcs3-bin",),
    "visualstudiocode": ("visual-studio-code-bin",), "dbeaver": ("dbeaver",),
    "bitwarden": ("bitwarden",), "spotify": ("spotify",), "zoom": ("zoom",),
    "discord": ("discord",), "vscodium": ("vscodium-bin",), "zed": ("zed",),
    "parabolic": ("parabolic",), "supertuxkart": ("supertuxkart",),
    "keepassxc": ("keepassxc",), "duckstation": ("duckstation-gpl",),
}


@dataclass
class SourceOption:
    kind: str
    available: bool = False
    ref: str = ""
    version: str = ""
    installed: bool = False
    details: list[tuple[str, str]] = field(default_factory=list)


def _compact(text: str) -> str:
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def candidate_names(app: App) -> list[str]:
    """Likely Arch/AUR package names for an app, most specific first."""
    names: list[str] = [s.ref for s in app.sources if s.kind in ("repo", "aur")]
    names += ALIASES.get(_compact(app.name), ())
    plain = app.name.casefold().strip()
    names += [re.sub(r"[^a-z0-9+]+", "-", plain).strip("-"), _compact(app.name)]
    return [name for name in dict.fromkeys(names) if name]


def parse_pacman_si(output: str) -> dict[str, dict[str, str]]:
    """`pacman -Si a b c` blocks keyed by package name (continuation lines dropped)."""
    packages: dict[str, dict[str, str]] = {}
    current: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            if current.get("Name"):
                packages[current["Name"]] = current
            current = {}
            continue
        match = re.match(r"^([A-Za-z][A-Za-z ]*?)\s*:\s(.*)$", line)
        if match and not line.startswith(" "):
            current[match.group(1)] = match.group(2).strip()
    if current.get("Name"):
        packages[current["Name"]] = current
    return packages


def parse_aur_info(payload: str | bytes | dict) -> dict[str, dict]:
    if not isinstance(payload, dict):
        payload = json.loads(payload)
    return {item["Name"]: item for item in payload.get("results", []) if item.get("Name")}


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1000 or unit == "GB":
            return f"{num:.0f} {unit}" if unit in ("B", "KB") else f"{num:.1f} {unit}"
        num /= 1000
    return ""


def pacman_option(app: App, info: dict[str, dict[str, str]],
                  installed: set[str]) -> SourceOption:
    for name in candidate_names(app):
        if name in info:
            data = info[name]
            return SourceOption("repo", True, name, data.get("Version", ""), name in installed, [
                ("Package", name), ("Repository", data.get("Repository", "")),
                ("Download", data.get("Download Size", "")),
                ("Installed size", data.get("Installed Size", "")),
            ])
    return SourceOption("repo")


def aur_option(app: App, info: dict[str, dict], installed: set[str]) -> SourceOption:
    for name in candidate_names(app):
        if name in info:
            data = info[name]
            details = [("Package", name), ("Votes", str(data.get("NumVotes", 0))),
                       ("Maintainer", data.get("Maintainer") or "orphan")]
            if data.get("OutOfDate"):
                details.append(("Status", "Flagged out of date"))
            return SourceOption("aur", True, name, str(data.get("Version", "")),
                                name in installed, details)
    return SourceOption("aur")


def flathub_version(appstream: dict) -> str:
    releases = appstream.get("releases") or []
    return str(releases[0].get("version", "")) if releases and isinstance(releases[0], dict) else ""


def flatpak_option(app_id: str, version: str, summary: dict, installed: set[str]) -> SourceOption:
    if not app_id:
        return SourceOption("flatpak")
    details = [("App ID", app_id)]
    if summary.get("download_size"):
        details.append(("Download", human_size(float(summary["download_size"]))))
    if summary.get("installed_size"):
        details.append(("Installed size", human_size(float(summary["installed_size"]))))
    return SourceOption("flatpak", True, app_id, version, app_id in installed, details)


def _get_json(url: str, opener, data: bytes | None = None, timeout: float = 8) -> dict:
    headers = {"User-Agent": "GlueApps/0.2"}
    if data:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers,
                                     method="POST" if data else "GET")
    with opener(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def probe_sources(
    app: App, native: set[str], aur: set[str], flatpaks: set[str],
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> list[SourceOption]:
    """Check all three sources; network failures leave a source 'not available'."""
    names = candidate_names(app)
    try:
        done = runner(["pacman", "-Si", *names], check=False, capture_output=True,
                      text=True, timeout=10)
        repo = pacman_option(app, parse_pacman_si(done.stdout), native)
    except (OSError, subprocess.TimeoutExpired):
        repo = SourceOption("repo")
    try:
        query = urllib.parse.urlencode([("arg[]", name) for name in names])
        aur_opt = aur_option(app, parse_aur_info(_get_json(AUR_INFO + query, opener)), aur)
    except (OSError, ValueError, TimeoutError):
        aur_opt = SourceOption("aur")
    flat = next((s for s in app.sources if s.kind == "flatpak"), None)
    app_id, version = (flat.ref, flat.version) if flat else ("", "")
    try:
        if not app_id:
            hits = _get_json(FLATHUB_SEARCH, opener,
                             json.dumps({"query": app.name}).encode()).get("hits", [])
            match = next((h for h in hits if _compact(str(h.get("name", "")))
                          == _compact(app.name)), None)
            app_id = str(match.get("app_id", "")) if match else ""
        summary = _get_json(FLATHUB_SUMMARY.format(app_id), opener) if app_id else {}
        if app_id and not version:
            version = flathub_version(_get_json(FLATHUB_APPSTREAM.format(app_id), opener))
    except (OSError, ValueError, TimeoutError):
        summary = {}
    return [repo, flatpak_option(app_id, version, summary, flatpaks), aur_opt]


def recommended(options: list[SourceOption]) -> SourceOption | None:
    """Installed source first, then Pacman, Flatpak, AUR."""
    available = [option for option in options if option.available]
    installed = [option for option in available if option.installed]
    return (installed or available or [None])[0]


def badge_kind(app: App) -> str:
    """The source a click on Get would use, for the card badge ("" when unknown)."""
    source = app.preferred_source
    return source.kind if source else ""


def safer_alternative(options: list[SourceOption]) -> SourceOption | None:
    """An available official or Flatpak option to offer instead of the AUR."""
    return next((o for o in options if o.available and o.kind in ("repo", "flatpak")), None)


def aur_warning(systemd: bool, alternative: SourceOption | None = None) -> str:
    """Text of the confirmation shown before every AUR install."""
    text = _("AUR packages are written by anyone and nobody reviews them. Their "
             "install scripts run as root, so a bad one can take over the whole "
             "system. Only continue if you trust this package and its maintainer.")
    if alternative is not None and alternative.kind == "flatpak":
        text += " " + _("This app is also on Flathub, where it runs sandboxed.")
    elif alternative is not None:
        text += " " + _("This app is also in the official repositories.")
    if not systemd:
        text += " " + _("Some recipes that need systemd will not work on this system.")
    return text
