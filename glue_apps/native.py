"""The system package manager: pacman (Arch, CachyOS, Artix) or apk (Alpine, postmarketOS)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

APK = shutil.which("pacman") is None and shutil.which("apk") is not None
# changes on every install, removal or update (keys the catalog cache)
STATE = Path("/lib/apk/db/installed") if APK else Path("/var/lib/pacman/local")
LOCK = Path("/lib/apk/db/lock") if APK else Path("/var/lib/pacman/db.lck")

_NAME_VERSION = re.compile(r"^(.+)-(\d[^-\s]*-r\d+)$")


def split_name(text: str) -> tuple[str, str]:
    """"py3-foo-1.2-r0" -> ("py3-foo", "1.2-r0"); text without a version stays whole."""
    match = _NAME_VERSION.match(text.strip())
    return (match.group(1), match.group(2)) if match else (text.strip(), "")


def installed_argv() -> list[str]:
    return ["apk", "info"] if APK else ["pacman", "-Qq"]


def foreign_argv() -> list[str]:
    """Packages built from the AUR; Alpine has no such thing."""
    return ["true"] if APK else ["pacman", "-Qqm"]


def owners_argv(files: list[str]) -> list[str]:
    return ["apk", "info", "-W", *files] if APK else ["pacman", "-Qo", *files]


def files_argv(names: list[str]) -> list[str]:
    return ["apk", "info", "-L", *names] if APK else ["pacman", "-Ql", *names]


def parse_files(output: str) -> list[tuple[str, str]]:
    """(package, /absolute/path) pairs from `pacman -Ql` or `apk info -L`."""
    if not APK:
        return [(pkg, path) for pkg, _sep, path in
                (line.partition(" ") for line in output.splitlines()) if path]
    pairs, current = [], ""
    for line in output.splitlines():
        if line.endswith(" contains:"):
            current = split_name(line[:-len(" contains:")])[0]
        elif line.strip() and current:
            pairs.append((current, "/" + line.strip()))
    return pairs


def info_argv(names: list[str]) -> list[str]:
    return ["apk", "info", "-s", *names] if APK else ["pacman", "-Si", *names]


def parse_apk_info(output: str) -> dict[str, dict[str, str]]:
    """`apk info -s a b` to the same keys pacman -Si gives."""
    packages: dict[str, dict[str, str]] = {}
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if line.endswith(" installed size:"):
            name, version = split_name(line[:-len(" installed size:")])
            size = lines[i + 1].strip() if i + 1 < len(lines) else ""
            packages[name] = {"Name": name, "Version": version, "Repository": "Alpine",
                              "Installed Size": size}
    return packages


def pending_argv() -> list[str]:
    return ["apk", "version", "-l", "<"] if APK else ["checkupdates"]


def parse_pending(output: str) -> list[tuple[str, str, str]]:
    """(name, old, new) from `apk version -l '<'` ("foo-1.0-r0  <  1.1-r0")."""
    rows = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] == "<":
            name, old = split_name(parts[0])
            rows.append((name, old, parts[2]))
    return rows


if __name__ == "__main__":
    assert split_name("py3-gobject3-3.50.0-r1") == ("py3-gobject3", "3.50.0-r1")
    assert split_name("librewolf-160.0_p1-r0") == ("librewolf", "160.0_p1-r0")
    assert parse_pending("Installed: Available:\nfoo-bar-1.0-r0  <  1.1-r0\n") == \
        [("foo-bar", "1.0-r0", "1.1-r0")]
    info = parse_apk_info("firefox-160.0-r0 installed size:\n254 MiB\n")
    assert info["firefox"]["Version"] == "160.0-r0" and info["firefox"]["Installed Size"] == "254 MiB"
    print("ok")
