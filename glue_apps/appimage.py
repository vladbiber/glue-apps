"""AppImage install: copy to ~/Applications, add a menu entry and an icon."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

PREFIX = "glue-appimage-"
FUSE2 = (Path("/usr/lib/libfuse.so.2"), Path("/usr/lib64/libfuse.so.2"))


@dataclass(frozen=True)
class AppImage:
    name: str
    path: Path
    desktop: Path
    icon: str


def is_appimage(path: Path) -> bool:
    """ELF files with the AppImage magic bytes (type 1 or 2) at offset 8."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(11)
    except OSError:
        return False
    return head[:4] == b"\x7fELF" and head[8:10] == b"AI" and head[10] in (1, 2)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-") or "app"


def parse_entry(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            section = line
        elif section == "[Desktop Entry]" and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip())
    return values


def desktop_entry(values: dict[str, str], name: str, exec_path: Path, icon: str,
                  extract_and_run: bool) -> str:
    """A menu entry for the installed AppImage; keeps field codes like %U."""
    args = values.get("Exec", "").split()[1:]
    command = f'"{exec_path}"' + (" " + " ".join(args) if args else "")
    if extract_and_run:
        command = "env APPIMAGE_EXTRACT_AND_RUN=1 " + command
    lines = ["[Desktop Entry]", "Type=Application", f"Name={name}",
             f"Exec={command}", f"Icon={icon}",
             f"Terminal={'true' if values.get('Terminal') == 'true' else 'false'}",
             f"X-AppImage-Path={exec_path}"]
    for key in ("Comment", "Categories", "MimeType", "StartupWMClass", "Keywords"):
        if values.get(key):
            lines.append(f"{key}={values[key]}")
    return "\n".join(lines) + "\n"


def _extract(source: Path, workdir: Path, pattern: str) -> None:
    subprocess.run([str(source), "--appimage-extract", pattern], cwd=workdir,
                   capture_output=True, timeout=120, check=False)


def _extract_file(source: Path, workdir: Path, name: str) -> Path | None:
    """Extract one file, following symlinks (.DirIcon and the root .desktop often are)."""
    root = workdir / "squashfs-root"
    path = root / name
    for _hop in range(5):
        if not path.is_symlink() and not path.exists():
            _extract(source, workdir, str(path.relative_to(root)))
        if not path.is_symlink():
            return path if path.is_file() else None
        link = Path(os.readlink(path))
        path = (root / link.relative_to("/")) if link.is_absolute() else path.parent / link
        path = Path(os.path.normpath(path))
        if root not in path.parents:
            return None
    return None


def install(source: Path, home: Path = Path.home(), fuse2=FUSE2) -> AppImage:
    """Copy, mark executable, and register an AppImage. Raises ValueError if not one."""
    source = source.resolve()
    if not is_appimage(source):
        raise ValueError(f"{source.name} is not an AppImage")
    apps_dir = home / "Applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    target = apps_dir / source.name
    if source != target:
        shutil.copy2(source, target)
    target.chmod(target.stat().st_mode | 0o111)

    values: dict[str, str] = {}
    icon = "application-x-executable"
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        _extract(target, work, "*.desktop")
        root = work / "squashfs-root"
        names = sorted(p.name for p in root.glob("*.desktop")) if root.is_dir() else []
        entry = _extract_file(target, work, names[0]) if names else None
        if entry:
            values = parse_entry(entry.read_text(encoding="utf-8", errors="replace"))
        name = values.get("Name") or source.stem.split("-")[0]
        key = slug(name)
        icon_name = values.get("Icon", "")
        for pattern in (f"{icon_name}.png", f"{icon_name}.svg", ".DirIcon"):
            if not icon_name and pattern != ".DirIcon":
                continue
            found = _extract_file(target, work, pattern)
            if found:
                suffix = found.suffix if found.suffix in (".png", ".svg") else ".png"
                icon_dir = home / ".local/share/icons/hicolor/256x256/apps"
                if suffix == ".svg":
                    icon_dir = home / ".local/share/icons/hicolor/scalable/apps"
                icon_dir.mkdir(parents=True, exist_ok=True)
                icon_file = icon_dir / f"{PREFIX}{key}{suffix}"
                shutil.copyfile(found, icon_file)
                icon = str(icon_file)
                break
    has_fuse = any(path.exists() for path in fuse2)
    desktop = home / ".local/share/applications" / f"{PREFIX}{key}.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(desktop_entry(values, name, target, icon, not has_fuse),
                       encoding="utf-8")
    return AppImage(name, target, desktop, icon)


def installed(home: Path = Path.home()) -> list[AppImage]:
    found = []
    for desktop in sorted((home / ".local/share/applications").glob(f"{PREFIX}*.desktop")):
        values = parse_entry(desktop.read_text(encoding="utf-8", errors="replace"))
        path = Path(values.get("X-AppImage-Path", ""))
        found.append(AppImage(values.get("Name", desktop.stem), path, desktop,
                              values.get("Icon", "")))
    return found


def remove(app: AppImage) -> None:
    for path in (app.path, app.desktop, Path(app.icon)):
        if path.is_absolute() and path.is_file():
            path.unlink()


def launch(app: AppImage) -> None:
    subprocess.Popen(["gtk-launch", app.desktop.stem], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
