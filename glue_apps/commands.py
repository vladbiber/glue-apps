"""Safe argv construction and execution for install/update actions."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from . import aur


_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._+:-]{0,254}$")


@dataclass(frozen=True)
class Command:
    argv: tuple[str, ...]
    label: str
    # a failure is logged and the plan goes on, e.g. the NVIDIA GL extension
    optional: bool = False


def _safe(ref: str) -> str:
    if not _REF.fullmatch(ref):
        raise ValueError(f"invalid application reference: {ref!r}")
    return ref


NVIDIA_VERSION = Path("/sys/module/nvidia/version")
FLATPAK_ROOTS = {"--user": Path.home() / ".local/share/flatpak",
                 "--system": Path("/var/lib/flatpak")}
GL_BRANCH = "1.4"


def gl_extension_plan(scope: str = "--user", version_file: Path | None = None,
                      root: Path | None = None) -> tuple[Command, ...]:
    """The NVIDIA GL extensions matching the loaded driver that SCOPE still lacks.

    Same refs as glue-flatpak-gl, which only catches up at boot; this lets a
    new Flatpak use the GPU the first time it starts.
    """
    try:
        version = (version_file or NVIDIA_VERSION).read_text().strip()
    except OSError:
        return ()
    if not re.fullmatch(r"[0-9]+(\.[0-9]+)*", version):
        return ()
    root = root or FLATPAK_ROOTS[scope]
    plan = []
    for kind in ("GL", "GL32"):
        ref = f"org.freedesktop.Platform.{kind}.nvidia-{version.replace('.', '-')}"
        if any((root / "runtime" / ref).glob(f"*/{GL_BRANCH}")):
            continue
        plan.append(Command(("flatpak", "install", "-y", "--noninteractive", scope,
                             "flathub", f"{ref}//{GL_BRANCH}"),
                            "Installing the NVIDIA graphics driver for Flatpak", optional=True))
    return tuple(plan)


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
                *gl_extension_plan("--user"),
            )
        # runtimes nothing uses any more (often a GB or more) go with the app
        return (Command(("flatpak", "uninstall", "-y", "--noninteractive", ref),
                        "Removing the app"),
                Command(("flatpak", "uninstall", "--unused", "-y", "--noninteractive"),
                        "Removing runtimes no app uses"))
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
    # pacman runs through the same polkit action as the AUR helper's
    # "pkexec pacman" calls, so one password covers the whole update;
    # --ask=20 says yes to conflict removals and to skipping packages that
    # cannot be upgraded (see helpers/update.sh)
    plan = [Command(("/usr/lib/glue-apps/update-check.sh",), "Checking the drivers"),
            Command(("pkexec", "pacman", "-Syu", "--noconfirm", "--ask=20"),
                    "Updating the system")]
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
            if command.optional:
                continue
            return 127
        assert process.stdout is not None
        for line in process.stdout:
            if on_output:
                on_output(line)
        code = process.wait()
        if code and command.optional:
            if on_output:
                on_output(f"{command.label} failed (exit {code}), carrying on\n")
        elif code:
            return code
    return 0
