"""Glue Apps: the app store window (Discover, Apps, Games, Updates)."""

from __future__ import annotations

import concurrent.futures
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import appimage_ui
from .catalog import CatalogIndex, cached_appstream, system_appstream_paths
from .config import AppsConfig
from .curation import CATEGORIES, CREATE, ESSENTIALS, GAMES, seed_apps, split_by_category
from .detail import DetailView
from .i18n import _, set_language
from .model import App, AppSource, canonical_key
from .pages import settings_page
from .store_pages import InstalledView, UpdatesView
from .remote import SearchCache, aur_search, flathub_details, flathub_search
from .shell import use_adwaita_icons, ShellWindow
from .updates import check_updates
from .views import AppsView, discover_page, games_page
from .widgets import load_image, scrolled_page


def _installed(argv: list[str]) -> set[str]:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=10, check=False)
        return set(done.stdout.split()) if done.returncode == 0 else set()
    except (OSError, subprocess.TimeoutExpired):
        return set()


class AppsWindow(ShellWindow):
    NAV = (("discover", "Discover", "starred-symbolic"),
           ("apps", "Apps", "view-grid-symbolic"),
           ("games", "Games", "input-gaming-symbolic"),
           ("installed", "Installed", "drive-harddisk-symbolic"),
           ("updates", "Updates", "software-update-available-symbolic"))
    BOTTOM = ("installed", "updates")
    EXTRA_PAGES = ("settings",)
    BRAND = "Glue Apps"
    SEARCH = True

    def __init__(self, app, config: AppsConfig, config_path: Path, data_root: Path):
        super().__init__(app, config, config_path, data_root, 1240, 800)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        cache_dir = Path(GLib.get_user_cache_dir()) / "glue-apps"
        self.cache = SearchCache(cache_dir / "search.json")
        self.image_cache = cache_dir / "images"
        # the three package lists in parallel; the catalog parse is cached
        native, aur, flatpak = (self.pool.submit(_installed, argv) for argv in (
            ["pacman", "-Qq"], ["pacman", "-Qqm"],
            ["flatpak", "list", "--app", "--columns=application"]))
        self.native_installed = native.result()
        self.aur_installed = aur.result()
        self.flatpak_installed = flatpak.result()
        self.index = CatalogIndex(cached_appstream(system_appstream_paths(),
                                                   self.native_installed,
                                                   cache_dir / "appstream.pickle"))
        self.index.extend(seed_apps(self.flatpak_installed, self.native_installed,
                                    self.aur_installed))
        self.pending_updates = None
        self.search_serial = 0
        self.rebuild(os.environ.get("GLUE_APPS_START_PAGE", "discover"))
        if (wanted := os.environ.get("GLUE_APPS_OPEN_APP")) and (found := self.find_app(wanted)):
            self.open_app(found)
        appimage_ui.accept_drops(self, self._appimage_added)
        if config.store:
            self.check_updates()

    def install_file(self, path: Path) -> None:
        appimage_ui.confirm(self, path, self._appimage_added)

    def _appimage_added(self) -> None:
        self.show_page("installed")
        self.installed_view.load()

    def build_pages(self):
        self.search.connect("search-changed", self._search_changed)
        self.apps_view = AppsView(self)
        self.updates_view = UpdatesView(self)
        self.installed_view = InstalledView(self)
        return [("discover", discover_page(self)), ("apps", self.apps_view.widget),
                ("games", games_page(self)), ("installed", self.installed_view.widget),
                ("updates", self.updates_view.widget), ("settings", settings_page(self))]

    def show_page(self, key: str, sync_nav: bool = True) -> None:
        super().show_page(key, sync_nav)
        if key == "installed" and not self.installed_view.loaded:
            self.installed_view.load()

    def after_build(self) -> None:
        settings = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text=_("Settings"),
                              css_classes=["flat", "circular", "settings-button"])
        settings.connect("clicked", lambda _b: self.show_page("settings"))
        self.topbar.pack_end(settings)
        self.refresh_results()
        if self.pending_updates is not None:
            self.set_updates(self.pending_updates)

    def show_category(self, name: str) -> None:
        self.apps_view.select_category(name if name in CATEGORIES else "All")
        self.show_page("apps")

    def show_games(self) -> None:
        self.show_page("games")

    def open_app(self, app: App) -> None:
        if old := self.stack.get_child_by_name("detail"):
            self.stack.remove(old)
        current = self.stack.get_visible_child_name()
        if current and current != "detail":
            self.history.append(current)
        self.detail = DetailView(self, app)
        self.stack.add_named(scrolled_page(self.detail.widget), "detail")
        self.stack.set_visible_child_name("detail")
        self.back.set_visible(True)

    def get_app(self, app: App) -> None:
        self.open_app(app)
        if app.installed:
            self.detail.launch()

    def pick(self, names) -> list[App]:
        return self.index.featured(names)

    def find_app(self, name: str) -> App | None:
        found = self.index.featured([name])
        return found[0] if found else None

    def load(self, target, source: str) -> None:
        load_image(target, source, self.pool, self.image_cache)

    def load_screenshot(self, app: App, picture: Gtk.Picture) -> None:
        if app.screenshots:
            self.load(picture, app.screenshots[0])
            return
        ref = next((s.ref for s in app.sources if s.kind == "flatpak"), None)
        if not ref:
            return
        future = self.pool.submit(flathub_details, ref, self.cache, self.flatpak_installed)

        def loaded(f) -> bool:
            detail = None if f.exception() else f.result()
            if detail and detail.screenshots:
                self.merge_detail(app, detail)
                self.load(picture, detail.screenshots[0])
            return False
        future.add_done_callback(lambda f: GLib.idle_add(loaded, f))

    def _lookup(self, app: App) -> App:
        key = canonical_key(app)
        return next((item for item in self.index.apps if canonical_key(item) == key), app)

    def merge_detail(self, app: App, detail: App) -> App:
        self.index.extend([replace(detail, name=app.name)])
        return self._lookup(app)

    def mark_installed(self, app: App, source: AppSource, installed: bool) -> App:
        target = {"repo": self.native_installed, "flatpak": self.flatpak_installed,
                  "aur": self.aur_installed}[source.kind]
        (target.add if installed else target.discard)(source.ref)
        self.index.extend([replace(app, sources=(replace(source, installed=installed),))])
        return self._lookup(app)

    def _search_changed(self, entry: Gtk.SearchEntry) -> None:
        query = entry.get_text().strip()
        if query and self.stack.get_visible_child_name() != "apps":
            self.show_page("apps")
        # wait for a pause in typing: every run filters the whole catalog
        # and rebuilds the result cards
        if getattr(self, "_search_source", 0):
            GLib.source_remove(self._search_source)
        self._search_source = GLib.timeout_add(250, self._run_search)

    def _run_search(self) -> bool:
        self._search_source = 0
        query = self.search.get_text().strip()
        self.refresh_results()
        if len(query) < 2:
            return False
        self.search_serial += 1
        serial, source = self.search_serial, self.apps_view.source_key()
        future = self.pool.submit(self._remote_search, query, source)
        future.add_done_callback(lambda f: GLib.idle_add(self._merge_remote, serial, f))
        return False

    def _remote_search(self, query: str, source: str) -> list[App]:
        apps: list[App] = []
        if source in {"all", "flatpak"}:
            apps.extend(flathub_search(query, self.cache, self.flatpak_installed))
        if source in {"all", "aur"}:
            apps.extend(aur_search(query, self.cache, self.aur_installed))
        return apps

    def _merge_remote(self, serial: int, future) -> bool:
        if not future.exception():
            self.index.extend(future.result())
        if serial == self.search_serial:
            self.refresh_results()
        return False

    def refresh_results(self) -> None:
        if not getattr(self, "apps_view", None) or not self.apps_view.results:
            return
        query = self.search.get_text().strip()
        apps = self.index.search(query, self.apps_view.source_key(), limit=180)
        inside, others = split_by_category(apps, self.apps_view.category)
        if not query:
            featured = [app for app in self.pick(ESSENTIALS + GAMES + CREATE) if app in inside]
            inside, others = featured + [app for app in inside if app not in featured], []
        self.apps_view.render(inside[:120], query, others[:60])

    def check_updates(self) -> None:
        self.updates_view.checking()
        future = self.pool.submit(check_updates)
        future.add_done_callback(lambda f: GLib.idle_add(
            self.set_updates, None if f.exception() else f.result()))

    def set_updates(self, items) -> bool:
        if items is None:
            self.updates_view.failed()
            return False
        names = {s.ref: app.name for app in self.index.apps for s in app.sources
                 if s.kind == "flatpak"}
        items = [replace(item, title=names.get(item.ref, item.title)) if item.is_app
                 else item for item in items]
        self.pending_updates = items
        self.badge.set_text(str(len(items)))
        self.badge.set_visible(bool(items))
        self.updates_view.show(items)
        return False


class AppsApplication(Adw.Application):
    def __init__(self, config: AppsConfig, config_path: Path, data_root: Path):
        super().__init__(application_id="org.glue.Apps",
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.args = (config, config_path, data_root)

    def _window(self) -> AppsWindow:
        window = self.props.active_window or AppsWindow(self, *self.args)
        window.present()
        return window

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        use_adwaita_icons()

    def do_activate(self) -> None:
        self._window()

    def do_open(self, files, _count, _hint) -> None:
        window = self._window()
        path = files[0].get_path() if files else None
        if path:
            GLib.idle_add(lambda: window.install_file(Path(path)) or False)


def run(config: AppsConfig, config_path: Path, data_root: Path,
        files: tuple[str, ...] = ()) -> int:
    set_language(config.language)
    return AppsApplication(config, config_path, data_root).run(["glue-apps", *files])
