"""Installed apps with a window, from Pacman/AUR packages and Flatpak."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .commands import action_plan, run_commands
from .updates import parse_desktop_entry

APPLICATIONS = Path("/usr/share/applications")


@dataclass(frozen=True)
class InstalledApp:
    title: str
    icon: str
    source: str      # repo | aur | flatpak
    ref: str         # package name or Flatpak app id
    launcher: str    # desktop id for gtk-launch, or Flatpak app id
    version: str = ""


def parse_owners(files: list[str], output: str) -> dict[str, str]:
    """`pacman -Qo f1 f2…` lines ("/path is owned by pkg ver") to {path: pkg}."""
    owners: dict[str, str] = {}
    for line in output.splitlines():
        head, sep, tail = line.partition(" is owned by ")
        if sep and head in files:
            owners[head] = tail.split()[0]
    return owners


def parse_flatpak_list(output: str) -> list[tuple[str, str, str]]:
    rows = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split("\t")]
        if parts and parts[0]:
            rows.append((parts[0], parts[1] if len(parts) > 1 else parts[0],
                         parts[2] if len(parts) > 2 else ""))
    return rows


def installed_apps(
    foreign: set[str],
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    root: Path = APPLICATIONS,
) -> list[InstalledApp]:
    def call(argv: list[str]) -> str:
        try:
            return runner(argv, check=False, capture_output=True, text=True,
                          timeout=20).stdout
        except (OSError, subprocess.TimeoutExpired):
            return ""

    entries: dict[str, tuple[str, str]] = {}
    for path in sorted(root.glob("*.desktop")):
        try:
            entry = parse_desktop_entry(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if entry:
            entries[str(path)] = entry
    owners = parse_owners(list(entries), call(["pacman", "-Qo", *entries])) if entries else {}
    apps = [InstalledApp(title, icon, "aur" if owners[path] in foreign else "repo",
                         owners[path], Path(path).stem)
            for path, (title, icon) in entries.items() if path in owners]
    seen: set[str] = set()
    for app_id, title, version in parse_flatpak_list(call(
            ["flatpak", "list", "--app", "--columns=application,name,version"])):
        if app_id not in seen:      # installed both per-user and system-wide
            seen.add(app_id)
            apps.append(InstalledApp(title, app_id, "flatpak", app_id, app_id, version))
    return sorted(apps, key=lambda app: app.title.casefold())


def launcher_for(package: str, pacman_ql: str) -> str:
    """Desktop id (file stem) of the first launcher a package ships."""
    for path in pacman_ql.split():
        if path.startswith("/usr/share/applications/") and path.endswith(".desktop"):
            return Path(path).stem
    return package


def open_installed(kind: str, ref: str,
                   runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> int:
    if kind != "flatpak":
        try:
            listing = runner(["pacman", "-Qlq", ref], check=False, capture_output=True,
                             text=True, timeout=10).stdout
        except (OSError, subprocess.TimeoutExpired):
            listing = ""
        ref = launcher_for(ref, listing)
    return run_commands(action_plan(kind, "open", ref))
