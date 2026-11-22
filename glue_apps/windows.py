"""Windows programs: Wine for apps, Proton (umu) for games, one shared prefix per mode."""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import zlib
from dataclasses import dataclass
from pathlib import Path

PREFIX = "glue-windows-"
MODES = ("app", "game")
PACKAGES = {"app": ("wine", "wine-mono", "wine-gecko"), "game": ("umu-launcher",)}
PROTON_DIRS = (Path("/usr/share/steam/compatibilitytools.d"),
               Path.home() / ".local/share/Steam/compatibilitytools.d")
SKIP = re.compile(r"unins|uninst|setup|install|update|crash|report|helper|redist|vcredist|"
                  r"dotnet|directx|dxsetup|launcherpatcher", re.I)


@dataclass(frozen=True)
class WinApp:
    name: str
    mode: str
    exe: Path
    desktop: Path
    icon: str


def root(home: Path = Path.home()) -> Path:
    return home / ".local/share/glue-windows"


def prefix(mode: str, home: Path = Path.home()) -> Path:
    return root(home) / ("games" if mode == "game" else "apps")


def is_exe(path: Path) -> bool:
    """PE programs (MZ) and Windows Installer packages (OLE compound file)."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(8)
    except OSError:
        return False
    return head[:2] == b"MZ" or head == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def ready(mode: str) -> bool:
    return shutil.which("umu-run" if mode == "game" else "wine") is not None


def proton() -> str:
    """Newest GE-Proton already on disk, else the name umu downloads it by."""
    found = [d for base in PROTON_DIRS if base.is_dir()
             for d in base.iterdir() if d.name.startswith("GE-Proton") and (d / "proton").exists()]
    found.sort(key=lambda d: [int(n) for n in re.findall(r"\d+", d.name)])
    return str(found[-1]) if found else "GE-Proton"


def env(mode: str, home: Path = Path.home()) -> dict[str, str]:
    # our own menu entries only; wine would add a second one for every shortcut
    values = {"WINEPREFIX": str(prefix(mode, home)), "WINEDEBUG": "-all",
              "WINEDLLOVERRIDES": "winemenubuilder.exe=d"}
    if mode == "game":
        values.update(PROTONPATH=proton(), GAMEID="umu-default")
    return values


def argv(mode: str, exe: Path) -> list[str]:
    runner = "umu-run" if mode == "game" else "wine"
    if exe.suffix.lower() == ".msi":
        return [runner, "msiexec", "/i", str(exe)]
    return [runner, str(exe)]


def _scan(pfx: Path) -> set[Path]:
    drive = pfx / "drive_c"
    found: set[Path] = set()
    if not drive.is_dir():
        return found
    for top in drive.iterdir():
        if top.name.lower() == "windows" or not top.is_dir():
            continue
        for base, _dirs, files in os.walk(top):
            found.update(Path(base, f) for f in files if f.lower().endswith((".exe", ".lnk")))
    return found


def lnk_target(data: bytes) -> str | None:
    """LocalBasePath of a Shell Link (.lnk), e.g. C:\\Program Files\\App\\app.exe."""
    if len(data) < 0x4C or data[:4] != b"L\0\0\0":
        return None
    flags = struct.unpack_from("<I", data, 0x14)[0]
    pos = 0x4C
    if flags & 1:
        pos += 2 + struct.unpack_from("<H", data, pos)[0]
    if not flags & 2 or pos + 28 > len(data):
        return None
    head, info_flags, base_off = struct.unpack_from("<I", data, pos + 4)[0], \
        struct.unpack_from("<I", data, pos + 8)[0], struct.unpack_from("<I", data, pos + 16)[0]
    if not info_flags & 1:
        return None
    if head >= 0x24:
        uni = struct.unpack_from("<I", data, pos + 28)[0]
        if uni:
            raw = data[pos + uni:]
            end = next((i for i in range(0, len(raw) - 1, 2) if raw[i:i + 2] == b"\0\0"), len(raw))
            return raw[:end].decode("utf-16-le", "replace")
    raw = data[pos + base_off:]
    return raw[:raw.find(b"\0")].decode("cp1252", "replace") if b"\0" in raw else None


def unix_path(pfx: Path, win_path: str) -> Path | None:
    """C:\\a\\b.exe inside the prefix, matching names case-insensitively like Windows."""
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", win_path)
    if not match or match.group(1).lower() != "c":
        return None
    path = pfx / "drive_c"
    for part in filter(None, re.split(r"[\\/]", match.group(2))):
        if not path.is_dir():
            return None
        hit = next((p for p in path.iterdir() if p.name.lower() == part.lower()), None)
        if hit is None:
            return None
        path = hit
    return path if path.is_file() else None


def candidates(pfx: Path, before: set[Path]) -> list[tuple[str, Path]]:
    """(name, exe) the install added: Start menu/desktop shortcuts first, then new programs."""
    new = _scan(pfx) - before
    out: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for lnk in sorted(p for p in new if p.suffix.lower() == ".lnk"):
        try:
            target = lnk_target(lnk.read_bytes())
        except OSError:
            continue
        exe = unix_path(pfx, target) if target else None
        if exe and exe.suffix.lower() == ".exe" and exe not in seen and not SKIP.search(lnk.stem):
            seen.add(exe)
            out.append((lnk.stem, exe))
    exes = sorted((p for p in new if p.suffix.lower() == ".exe" and p not in seen
                   and not SKIP.search(p.name)), key=lambda p: -p.stat().st_size)
    out += [(pretty(p.stem), p) for p in exes[:8]]
    return out


def pretty(stem: str) -> str:
    words = re.sub(r"[_\-.]+", " ", stem).strip()
    return words[:1].upper() + words[1:] if words else "Windows app"


def run_install(mode: str, exe: Path, home: Path = Path.home()) -> list[tuple[str, Path]]:
    """Runs the installer (or the program) and waits; returns what it added."""
    pfx = prefix(mode, home)
    pfx.mkdir(parents=True, exist_ok=True)
    before = _scan(pfx)
    subprocess.run(argv(mode, exe), env={**os.environ, **env(mode, home)}, cwd=str(exe.parent),
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=False)
    return candidates(pfx, before)


def keep_portable(mode: str, exe: Path, home: Path = Path.home()) -> Path:
    """A program that installed nothing: copy it into the prefix so Downloads can be cleaned.
    shortcut: copies only the .exe, portable apps with side files need their folder."""
    target = prefix(mode, home) / "drive_c/Programs" / exe.stem / exe.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if exe.resolve() != target.resolve():
        shutil.copy2(exe, target)
    return target


# ---- icons: the biggest image of the exe's first icon group, saved as PNG ----

def _png(width: int, height: int, rgba: bytes) -> bytes:
    rows = b"".join(b"\0" + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def _dib_png(dib: bytes) -> bytes | None:
    size, width, height2, _planes, bits = struct.unpack_from("<IiiHH", dib, 0)
    height = height2 // 2
    if width <= 0 or height <= 0 or bits not in (4, 8, 24, 32):
        return None
    colors = struct.unpack_from("<I", dib, 32)[0] or (1 << bits if bits <= 8 else 0)
    palette = dib[size:size + colors * 4]
    pixels = size + colors * 4
    stride = ((width * bits + 31) // 32) * 4
    mask_stride = ((width + 31) // 32) * 4
    mask = pixels + stride * height
    out = bytearray(width * height * 4)
    has_alpha = bits == 32 and any(dib[pixels + i * 4 + 3] for i in range(width * height))
    for y in range(height):
        row = pixels + (height - 1 - y) * stride
        mrow = mask + (height - 1 - y) * mask_stride
        for x in range(width):
            if bits == 32:
                b, g, r, a = dib[row + x * 4:row + x * 4 + 4]
            elif bits == 24:
                b, g, r = dib[row + x * 3:row + x * 3 + 3]
                a = 255
            else:
                byte = dib[row + x * bits // 8]
                index = byte if bits == 8 else (byte >> 4 if x % 2 == 0 else byte & 15)
                b, g, r = palette[index * 4:index * 4 + 3]
                a = 255
            if not has_alpha and mrow + x // 8 < len(dib):
                a = 0 if dib[mrow + x // 8] & (0x80 >> (x % 8)) else 255
            out[(y * width + x) * 4:(y * width + x) * 4 + 4] = bytes((r, g, b, a))
    return _png(width, height, bytes(out))


def exe_icon(data: bytes) -> bytes | None:
    """PNG bytes of the program's icon, or None. Pure PE resource walk, no tools needed."""
    try:
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe:pe + 4] != b"PE\0\0":
            return None
        nsec, optsize = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
        opt = pe + 24
        dirs = opt + (112 if struct.unpack_from("<H", data, opt)[0] == 0x20B else 96)
        res_rva = struct.unpack_from("<I", data, dirs + 16)[0]
        sections = [struct.unpack_from("<IIII", data, opt + optsize + i * 40 + 8) for i in range(nsec)]

        def off(rva: int) -> int:
            for vsize, vaddr, rsize, raw in sections:
                if vaddr <= rva < vaddr + max(vsize, rsize):
                    return rva - vaddr + raw
            raise ValueError("rva outside sections")
        base = off(res_rva)

        def entries(at: int):
            named, ids = struct.unpack_from("<HH", data, at + 12)
            for i in range(named + ids):
                name, target = struct.unpack_from("<II", data, at + 16 + i * 8)
                yield name, target

        def leaf(target: int) -> bytes:
            while target & 0x80000000:
                target = next(entries(base + (target & 0x7FFFFFFF)))[1]
            rva, size = struct.unpack_from("<II", data, base + target)
            return data[off(rva):off(rva) + size]
        types = dict(entries(base))
        if 14 not in types or 3 not in types:
            return None
        group = leaf(types[14])
        count = struct.unpack_from("<H", group, 4)[0]
        best = max((struct.unpack_from("<BBBBHHIH", group, 6 + i * 14) for i in range(count)),
                   key=lambda e: ((e[0] or 256) * (e[1] or 256), e[5]))
        icons = dict(entries(base + (types[3] & 0x7FFFFFFF)))
        image = leaf(icons[best[7]])
        return image if image.startswith(b"\x89PNG") else _dib_png(image)
    except (struct.error, ValueError, KeyError, IndexError, StopIteration):
        return None


# ---- menu entries ----

def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-") or "app"


def _quote(arg: str) -> str:
    """Desktop Entry Exec quoting."""
    arg = arg.replace("%", "%%")
    if not re.search(r'[\s"\'\\`$<>~|&;*?#()]', arg):
        return arg
    return '"' + re.sub(r'(["`$\\])', r"\\\1", arg) + '"'


def desktop_entry(name: str, mode: str, exe: Path, icon: str, home: Path = Path.home()) -> str:
    command = " ".join(["env", *(f"{k}={_quote(v)}" for k, v in env(mode, home).items()),
                        *(_quote(a) for a in argv(mode, exe))])
    return "\n".join([
        "[Desktop Entry]", "Type=Application", f"Name={name}", f"Exec={command}",
        f"Path={exe.parent}", f"Icon={icon}", "Terminal=false",
        f"Categories={'Game;' if mode == 'game' else 'Utility;'}",
        f"StartupWMClass={exe.name.lower()}",
        f"X-Glue-Windows-Mode={mode}", f"X-Glue-Windows-Exe={exe}"]) + "\n"


def add(name: str, mode: str, exe: Path, home: Path = Path.home()) -> WinApp:
    key = slug(f"{name}-{mode}")
    icon = "application-x-executable"
    try:
        png = exe_icon(exe.read_bytes())
    except OSError:
        png = None
    if png:
        icon_file = home / ".local/share/icons/hicolor/256x256/apps" / f"{PREFIX}{key}.png"
        icon_file.parent.mkdir(parents=True, exist_ok=True)
        icon_file.write_bytes(png)
        icon = str(icon_file)
    desktop = home / ".local/share/applications" / f"{PREFIX}{key}.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(desktop_entry(name, mode, exe, icon, home), encoding="utf-8")
    return WinApp(name, mode, exe, desktop, icon)


def _values(desktop: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in desktop.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line and not line.startswith(("#", "[")):
            key, value = line.split("=", 1)
            values.setdefault(key, value)
    return values


def installed(home: Path = Path.home()) -> list[WinApp]:
    apps = []
    for desktop in sorted((home / ".local/share/applications").glob(f"{PREFIX}*.desktop")):
        v = _values(desktop)
        apps.append(WinApp(v.get("Name", desktop.stem), v.get("X-Glue-Windows-Mode", "app"),
                           Path(v.get("X-Glue-Windows-Exe", "")), desktop, v.get("Icon", "")))
    return apps


def app_folder(app: WinApp, home: Path = Path.home()) -> Path | None:
    """The program's own folder (Program Files\\Vendor or Programs\\Name), never a shared one."""
    drive = prefix(app.mode, home) / "drive_c"
    try:
        parts = app.exe.relative_to(drive).parts
    except ValueError:
        return None
    if len(parts) >= 3 and parts[0].lower() in ("program files", "program files (x86)", "programs"):
        return drive / parts[0] / parts[1]
    return None


def remove(app: WinApp, files: bool, home: Path = Path.home()) -> None:
    folder = app_folder(app, home) if files else None
    if folder and folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
    for path in (app.desktop, Path(app.icon)):
        if path.is_absolute() and path.is_file():
            path.unlink()


def launch(app: WinApp) -> None:
    subprocess.Popen(["gtk-launch", app.desktop.stem], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
