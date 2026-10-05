"""Whole-system update that keeps going: the system first, then Flatpak and
AUR apps. pacman problems that would stop a beginner (a stale lock, old
keyrings, one package that cannot be upgraded) are worked around and the
packages left behind are reported instead of failing the whole update.

Every root step is "pkexec pacman" (one polkit action, auth kept), so the
password is asked once.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from . import aur

Output = Callable[[str], None]
Runner = Callable[[list[str], Output], tuple[int, str]]

LOCK = Path("/var/lib/pacman/db.lck")
CHECK = "/usr/lib/glue-apps/update-check.sh"
UNLOCK = "/usr/lib/glue-apps/unlock.sh"
KEYRINGS = ("archlinux-keyring", "artix-keyring", "cachyos-keyring")
PACMAN = ["pkexec", "pacman"]
# --ask=20: yes to removing a conflicting package and to skipping packages
# that cannot be upgraded, the two questions --noconfirm answers no to
ASK = "--ask=20"
MAX_TRIES = 4

_PKG = r"[A-Za-z0-9@._+-]+"
_BLOCKER_PATTERNS = (
    re.compile(rf"breaks dependency '({_PKG})[^']*' required by ({_PKG})"),
    re.compile(rf"unable to satisfy dependency '({_PKG})[^']*' required by ({_PKG})"),
    re.compile(rf"installing ({_PKG}) \([^)]*\) breaks dependency"),
    re.compile(rf"({_PKG})-[^ -]+-[^ -]+ and ({_PKG})-[^ -]+-[^ -]+ are in conflict"),
    re.compile(rf"^({_PKG}): /\S+ exists in filesystem", re.M),
    re.compile(rf"({_PKG})-[^ ]+-(?:x86_64|any)\.pkg\.tar\.\w+ is (?:corrupted|invalid)"),
    re.compile(rf"error: ({_PKG}): signature from"),
)


@dataclass
class UpdateResult:
    ok: bool = False
    skipped: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def stream(argv: list[str], output: Output) -> tuple[int, str]:
    """Run argv, pass every line to output, return (code, whole text)."""
    try:
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1)
    except OSError as exc:
        output(f"Could not start: {exc}\n")
        return 127, str(exc)
    lines = []
    assert process.stdout is not None
    for line in process.stdout:
        lines.append(line)
        output(line)
    return process.wait(), "".join(lines)


def blockers(text: str, pending: Iterable[str]) -> list[str]:
    """Packages named in pacman's error that are waiting for an upgrade:
    leaving those out lets the rest of the system update."""
    waiting = set(pending)
    found: list[str] = []
    for pattern in _BLOCKER_PATTERNS:
        for match in pattern.finditer(text):
            for name in match.groups():
                if name in waiting and name not in found:
                    found.append(name)
    return found


def pending_upgrades(runner: Runner) -> list[str]:
    code, text = runner(["pacman", "-Qu"], lambda _line: None)
    if code not in (0, 1):
        return []
    return [line.split()[0] for line in text.splitlines() if line.strip()]


def pacman_running(proc: Path = Path("/proc")) -> bool:
    for entry in proc.iterdir() if proc.is_dir() else ():
        try:
            if entry.name.isdigit() and (entry / "comm").read_text().strip() == "pacman":
                return True
        except OSError:
            continue
    return False


def _installed(runner: Runner, names: Iterable[str]) -> list[str]:
    code, text = runner(["pacman", "-Qq", *names], lambda _line: None)
    return [line.strip() for line in text.splitlines() if line.strip()
            and not line.startswith("error")]


def update_system(output: Output, runner: Runner = stream, lock: Path = LOCK,
                  running: Callable[[], bool] = pacman_running) -> UpdateResult:
    result = UpdateResult()
    output("Checking the drivers…\n")
    code, text = runner([CHECK], output)
    if code not in (0, 127):
        result.problems.append(text.strip() or "The driver check stopped the update.")
        return result
    if lock.exists() and not running():
        output("Removing a leftover pacman lock…\n")
        runner(["pkexec", UNLOCK], output)
    output("Updating the package keys…\n")
    keys = _installed(runner, KEYRINGS)
    synced = False
    if keys:
        code, _text = runner([*PACMAN, "-Sy", "--needed", "--noconfirm", ASK, *keys], output)
        synced = code == 0
    ignore: list[str] = []
    for _attempt in range(MAX_TRIES):
        output("Updating the system…\n")
        argv = [*PACMAN, "-Su" if synced else "-Syu", "--noconfirm", ASK]
        if ignore:
            argv += ["--ignore", ",".join(ignore)]
        code, text = runner(argv, output)
        if code == 0:
            result.ok = True
            result.skipped = ignore
            return result
        if "could not lock database" in text or "unable to lock database" in text:
            if not running():
                runner(["pkexec", UNLOCK], output)
                continue
            result.problems.append("Another program is installing packages. Try again when it finishes.")
            return result
        if "failed retrieving file" in text or "failed to synchronize" in text:
            result.problems.append("The download failed. Check the internet connection and try again.")
            return result
        synced = True
        new = [name for name in blockers(text, pending_upgrades(runner)) if name not in ignore]
        if not new:
            result.problems.append("pacman stopped the update; the details are in the log above.")
            return result
        output(f"Leaving {', '.join(new)} for later and trying again…\n")
        ignore += new
    result.problems.append("pacman kept stopping the update; the details are in the log above.")
    return result


def update_all(output: Output, runner: Runner = stream, which=shutil.which) -> UpdateResult:
    """System, then Flatpak, then AUR; a failing app never undoes the rest."""
    result = update_system(output, runner)
    if which("flatpak"):
        output("Updating Flatpak apps…\n")
        code, _text = runner(["flatpak", "update", "-y", "--noninteractive"], output)
        if code:
            result.problems.append("Some Flatpak apps could not be updated.")
    if result.ok and (helper := aur.helper(which)):
        output("Updating community apps…\n")
        code, _text = runner(list(aur.upgrade_argv(helper)), output)
        if code:
            result.problems.append("Some community (AUR) apps could not be rebuilt; "
                                   "they keep working with their current version.")
    return result


def summary(result: UpdateResult) -> str:
    if result.ok and not result.problems and not result.skipped:
        return "Everything is up to date."
    lines = []
    if result.ok:
        lines.append("The system is up to date.")
    if result.skipped:
        lines.append("Left for a later update: " + ", ".join(result.skipped) + ".")
    lines += result.problems
    return " ".join(lines)
