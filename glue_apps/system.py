"""Parsers for pending-update listings."""

from __future__ import annotations


def parse_checkupdates(output: str) -> list[tuple[str, str, str]]:
    updates: list[tuple[str, str, str]] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[-2] == "->":
            updates.append((parts[0], parts[-3], parts[-1]))
    return updates


def parse_flatpak_updates(output: str) -> list[str]:
    return [line.split("\t", 1)[0].strip() for line in output.splitlines() if line.strip()]
