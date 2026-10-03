"""Pending updates, split into apps with a window and packages without one."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .aur import helper as aur_helper, pending_argv as aur_pending
from .system import parse_checkupdates


@dataclass(frozen=True)
class UpdateItem:
    ref: str
    old: str
    new: str
    source: str            # repo | aur | flatpak
    title: str = ""
    icon: str = ""

    @property
    def is_app(self) -> bool:
        return bool(self.title)


def parse_desktop_entry(text: str) -> tuple[str, str] | None:
    """Name and Icon of a launcher shown in menus, or None for hidden entries."""
    values: dict[str, str] = {}
    in_entry = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_entry = line == "[Desktop Entry]"
            continue
        if in_entry and "=" in line:
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip())
    if values.get("Type", "Application") != "Application":
        return None
    if values.get("NoDisplay", "").lower() == "true" or values.get("Hidden", "").lower() == "true":
        return None
    if not values.get("Name"):
        return None
    return values["Name"], values.get("Icon", "")


def desktop_files(pacman_ql: str) -> dict[str, list[str]]:
    """`pacman -Ql pkg…` output to {pkg: [/usr/share/applications/*.desktop]}."""
    found: dict[str, list[str]] = {}
    for line in pacman_ql.splitlines():
        pkg, _sep, path = line.partition(" ")
        if path.startswith("/usr/share/applications/") and path.endswith(".desktop"):
            found.setdefault(pkg, []).append(path)
    return found


def parse_flatpak_remote_updates(output: str) -> list[tuple[str, str, str]]:
    """`flatpak remote-ls --updates --columns=application,name,version` rows."""
    rows = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split("\t")]
        if parts and parts[0]:
            rows.append((parts[0], parts[1] if len(parts) > 1 else parts[0],
                         parts[2] if len(parts) > 2 else ""))
    return rows


def classify(updates: list[tuple[str, str, str]], source: str,
             launchers: dict[str, list[str]],
             read: Callable[[str], str]) -> list[UpdateItem]:
    items = []
    for name, old, new in updates:
        title = icon = ""
        for path in launchers.get(name, []):
            try:
                entry = parse_desktop_entry(read(path))
            except OSError:
                entry = None
            if entry:
                title, icon = entry
                break
        items.append(UpdateItem(name, old, new, source, title, icon))
    return items


def sort_updates(items: list[UpdateItem]) -> list[UpdateItem]:
    """Apps with a window first (by title), then everything else (by name)."""
    return sorted(items, key=lambda item: (not item.is_app,
                                           (item.title or item.ref).casefold()))


def check_updates(
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    read: Callable[[str], str] = lambda path: Path(path).read_text(encoding="utf-8",
                                                                     errors="replace"),
) -> list[UpdateItem]:
    def call(argv: list[str], timeout: int = 60) -> str:
        try:
            done = runner(argv, check=False, capture_output=True, text=True, timeout=timeout)
            return done.stdout if done.returncode in (0, 1) else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""

    native = parse_checkupdates(call(["checkupdates"]))
    helper = aur_helper()
    aur = parse_checkupdates(call(aur_pending(helper))) if helper else []
    names = [name for name, _old, _new in native + aur]
    launchers = desktop_files(call(["pacman", "-Ql", *names])) if names else {}
    items = classify(native, "repo", launchers, read) + classify(aur, "aur", launchers, read)
    columns = "--columns=application,name,version"
    for kind in ("--app", "--runtime"):
        rows = parse_flatpak_remote_updates(call(
            ["flatpak", "remote-ls", "--updates", kind, columns]))
        # runtimes (drivers, SDKs, codecs) have no window: list them with packages
        items += [UpdateItem(app_id, "", version, "flatpak",
                             title if kind == "--app" else "", app_id)
                  for app_id, title, version in rows]
    unique = {(item.source, item.ref): item for item in items}   # user + system Flatpaks
    return sort_updates(list(unique.values()))


def counts(items: list[UpdateItem]) -> tuple[int, int, int]:
    return (sum(item.source == "repo" for item in items),
            sum(item.source == "flatpak" for item in items),
            sum(item.source == "aur" for item in items))
