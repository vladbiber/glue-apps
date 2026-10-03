"""AUR helper commands; yay and paru are both supported."""

from __future__ import annotations

import shutil
from pathlib import Path

HELPERS = ("yay", "paru")


def helper(which=shutil.which) -> str | None:
    """The first AUR helper on PATH, or None."""
    return next((name for name in HELPERS if which(name)), None)


def label(which=shutil.which) -> str:
    return f"AUR ({helper(which) or 'yay'})"


def _no_prompts(name: str) -> tuple[str, ...]:
    if name == "paru":
        return ("--noconfirm", "--skipreview", "--sudo", "pkexec")
    return ("--noconfirm", "--answerclean", "None", "--answerdiff", "None",
            "--answeredit", "None", "--sudo", "pkexec")


def install_argv(name: str, ref: str) -> tuple[str, ...]:
    return (name, "-S", "--aur", "--needed", *_no_prompts(name), ref)


def upgrade_argv(name: str) -> tuple[str, ...]:
    return (name, "-Sua", *_no_prompts(name))


def search_argv(name: str, query: str) -> list[str]:
    return [name, "-Ssa", "--color", "never", query]


def info_argv(name: str, package: str) -> list[str]:
    return [name, "-Sia", "--color", "never", package]


def pending_argv(name: str) -> list[str]:
    return [name, "-Qua", "--color", "never"]


def has_systemd(root: Path = Path("/run/systemd/system")) -> bool:
    return root.is_dir()
