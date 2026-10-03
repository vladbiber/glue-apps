"""Command-line entry point; GTK is imported only when the window is needed."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .config import AppsConfig, THEMES, validate_themes

PAGES = ("discover", "apps", "games", "installed", "updates", "settings")


def data_root() -> Path:
    override = os.environ.get("GLUE_APPS_DATA")
    if override:
        return Path(override)
    installed = Path("/usr/share/glue-apps")
    return installed if installed.exists() else Path(__file__).resolve().parent.parent / "data"


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "glue"


def user_config_path() -> Path:
    return config_dir() / "apps.conf"


def load_config(theme: str | None = None) -> AppsConfig:
    user = user_config_path()
    if not user.exists() and (config_dir() / "hub.conf").exists():
        user = config_dir() / "hub.conf"   # settings from before the rename
    config = AppsConfig.load(user, Path("/etc/glue/apps.conf"))
    if theme:
        config.theme = theme
    return config


def self_test() -> int:
    errors = validate_themes(data_root() / "themes")
    for name in ("base.css", "compact.css"):
        if not (data_root() / "themes" / name).is_file():
            errors.append(f"{name} missing")
    for error in errors:
        print(error)
    return int(bool(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="glue-apps")
    parser.add_argument("--self-test", action="store_true",
                        help="check the installed theme files and exit")
    parser.add_argument("--page", choices=PAGES, help="page to open")
    parser.add_argument("--theme", choices=THEMES, help=argparse.SUPPRESS)
    parser.add_argument("--app", help=argparse.SUPPRESS)
    parser.add_argument("file", nargs="?", help="an .AppImage to install")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.app:
        os.environ["GLUE_APPS_OPEN_APP"] = args.app
    if args.page:
        os.environ["GLUE_APPS_START_PAGE"] = args.page
    from .ui import run
    files = (str(Path(args.file).resolve()),) if args.file else ()
    return run(load_config(args.theme), user_config_path(), data_root(), files)


if __name__ == "__main__":
    raise SystemExit(main())
