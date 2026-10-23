"""Glue Apps configuration and theme validation."""

from __future__ import annotations

import configparser
import json
from dataclasses import dataclass
from pathlib import Path


THEMES = ("glue", "showcase", "mosaic")
THEME_NAMES = {"glue": "Glue", "showcase": "Showcase", "mosaic": "Mosaic"}
LEGACY_THEMES = {"vitrina": "showcase", "mozaic": "mosaic"}
LANGUAGES = ("en", "ro")

LAYOUT_CHOICES = {
    "nav": ("sidebar", "search-sidebar", "rail"),
    "scheme": ("dark", "light"),
    "card": ("row", "tile"),
    "hero": ("banner", "editorial", "carousel"),
}
DEFAULT_LAYOUT = {"nav": "sidebar", "scheme": "dark", "card": "row",
                  "hero": "banner", "columns": 3}


def _flag(section, key: str, default: str) -> bool:
    return str(section.get(key, default)).lower() in {"1", "true", "yes"}


@dataclass
class AppsConfig:
    theme: str = "glue"
    autostart: bool = True
    store: bool = True
    aur_warning_seen: bool = False  # unused: every AUR install asks; kept for old configs
    language: str = "en"

    @classmethod
    def load(cls, user_path: Path, system_path: Path | None = None) -> "AppsConfig":
        parser = configparser.ConfigParser()
        paths = [str(path) for path in (system_path, user_path) if path and path.exists()]
        parser.read(paths, encoding="utf-8")
        name = next((n for n in ("apps", "hub") if parser.has_section(n)), None)
        section = parser[name] if name else {}
        theme = str(section.get("theme", "glue"))
        theme = LEGACY_THEMES.get(theme, theme)
        language = str(section.get("language", "en"))
        return cls(
            theme=theme if theme in THEMES else "glue",
            autostart=_flag(section, "autostart", "1"),
            store=_flag(section, "store", "1"),
            aur_warning_seen=_flag(section, "aur_warning_seen", "0"),
            language=language if language in LANGUAGES else "en",
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = (
            "[apps]\n"
            f"theme={self.theme}\n"
            f"autostart={int(self.autostart)}\n"
            f"store={int(self.store)}\n"
            f"aur_warning_seen={int(self.aur_warning_seen)}\n"
            f"language={self.language}\n"
        )
        temp = path.with_suffix(".tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)


def _layout_errors(theme: str, data: dict) -> list[str]:
    errors = [f"{theme}: layout.json missing {key}"
              for key in DEFAULT_LAYOUT if key not in data]
    for key, allowed in LAYOUT_CHOICES.items():
        if key in data and data[key] not in allowed:
            errors.append(f"{theme}: layout.json {key}={data[key]!r} not in {allowed}")
    if "columns" in data and data["columns"] not in range(1, 7):
        errors.append(f"{theme}: layout.json columns must be 1..6")
    return errors


def validate_themes(root: Path) -> list[str]:
    errors: list[str] = []
    for theme in THEMES:
        folder = root / theme
        css = folder / "theme.css"
        if not css.is_file() or not css.read_text(encoding="utf-8").strip():
            errors.append(f"{theme}: theme.css missing or empty")
        try:
            data = json.loads((folder / "layout.json").read_text(encoding="utf-8"))
            errors.extend(_layout_errors(theme, data))
        except (OSError, ValueError):
            errors.append(f"{theme}: invalid layout.json")
    return errors


def load_layout(root: Path, theme: str) -> dict:
    try:
        data = json.loads((root / theme / "layout.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT_LAYOUT)
    if _layout_errors(theme, data):
        return dict(DEFAULT_LAYOUT)
    return {**DEFAULT_LAYOUT, **{key: data[key] for key in DEFAULT_LAYOUT}}
