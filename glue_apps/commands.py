"""Safe argv construction and execution for install/update actions."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Iterable

from . import aur


_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._+:-]{0,254}$")


@dataclass(frozen=True)
class Command:
    argv: tuple[str, ...]
    label: str


def _safe(ref: str) -> str:
    if not _REF.fullmatch(ref):
        raise ValueError(f"invalid application reference: {ref!r}")
    return ref


def action_plan(kind: str, action: str, ref: str) -> tuple[Command, ...]:
    ref = _safe(ref)
    if action not in {"install", "remove", "open"}:
        raise ValueError(f"unknown action: {action}")
    if kind == "repo":
        if action == "open":
            return (Command(("gtk-launch", ref), "Opening the app"),)
        return (Command(("pkexec", "/usr/lib/glue-apps/pkg.sh", action, ref),
                        "Changing the app"),)
    if kind == "flatpak":
        if action == "open":
            return (Command(("flatpak", "run", ref), "Opening the app"),)
        if action == "install":
            return (
                Command(("flatpak", "remote-add", "--user", "--if-not-exists",
                         "flathub", "https://flathub.org/repo/flathub.flatpakrepo"),
                        "Preparing Flathub"),
                Command(("flatpak", "install", "-y", "--user", "flathub", ref),
                        "Installing the app"),
            )
        return (Command(("flatpak", "uninstall", "-y", "--noninteractive", ref),
                        "Removing the app"),)
    if kind == "aur":
        if action == "open":
            return (Command(("gtk-launch", ref), "Opening the app"),)
        if action == "remove":
            return (Command(("pkexec", "/usr/lib/glue-apps/pkg.sh", "remove", ref),
                            "Removing the app"),)
        return (Command(aur.install_argv(aur.helper() or "yay", ref),
                        "Building and installing the community app"),)
    raise ValueError(f"unknown source: {kind}")


def update_plan(which=shutil.which) -> tuple[Command, ...]:
    """System packages first, then Flatpak and AUR apps when those tools exist."""
    plan = [Command(("pkexec", "/usr/lib/glue-apps/update.sh"), "Updating the system")]
    if which("flatpak"):
        plan.append(Command(("flatpak", "update", "-y", "--noninteractive"),
                            "Updating Flatpak apps"))
    if helper := aur.helper(which):
        plan.append(Command(aur.upgrade_argv(helper), "Updating community apps"))
    return tuple(plan)


def run_commands(
    commands: Iterable[Command],
    on_output: Callable[[str], None] | None = None,
) -> int:
    for command in commands:
        if on_output:
            on_output(f"{command.label}…\n")
        try:
            process = subprocess.Popen(
                command.argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except OSError as exc:
            if on_output:
                on_output(f"Could not start: {exc}\n")
            return 127
        assert process.stdout is not None
        for line in process.stdout:
            if on_output:
                on_output(line)
        code = process.wait()
        if code:
            return code
    return 0
