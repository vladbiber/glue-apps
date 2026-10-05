"""Window shell shared by Glue Apps and Glue Welcome: navigation, theme, compact mode."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from .config import AppsConfig, THEMES
from .i18n import _, set_language
from .theming import ThemeController
from .widgets import label, scrolled_page

COMPACT_WIDTH = 900


def use_adwaita_icons() -> None:
    """Our symbolic icons are Adwaita's; a desktop such as KDE may set breeze
    for every GTK app, and breeze lacks some of them (broken image icons)."""
    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.props.gtk_icon_theme_name = "Adwaita"


class ShellWindow(Adw.ApplicationWindow):
    NAV: tuple[tuple[str, str, str], ...] = ()
    BOTTOM: tuple[str, ...] = ()
    EXTRA_PAGES: tuple[str, ...] = ()
    BRAND = "Glue"
    ICON = "org.glue.Apps"
    SEARCH = False

    def __init__(self, app, config: AppsConfig, config_path: Path, data_root: Path,
                 width: int, height: int):
        super().__init__(application=app, title=self.BRAND, default_width=width,
                         default_height=height)
        self.config = config
        self.config_path = config_path
        self.timers: list[int] = []
        self.history: list[str] = []
        self.compact = False
        self.compact_hooks: list[Callable[[bool], None]] = []
        self.themes = ThemeController(data_root)
        Gtk.IconTheme.get_for_display(self.get_display()).add_search_path(
            str(data_root / "icons"))
        self.add_css_class("glue-apps")
        self.set_icon_name(self.ICON)
        self.connect("notify::default-width", lambda *_a: self._check_compact())
        self.monitor = Gio.File.new_for_path(str(config_path)).monitor_file(
            Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self._config_changed)

    def build_pages(self) -> list[tuple[str, Gtk.Widget]]:
        raise NotImplementedError

    def after_build(self) -> None:
        """Hook for subclasses once pages exist."""

    def rebuild(self, page: str) -> None:
        for timer in self.timers:
            GLib.source_remove(timer)
        self.timers = []
        self.compact_hooks = []
        self.layout = self.themes.apply(self.config.theme)
        for theme in THEMES:
            self.remove_css_class(f"theme-{theme}")
        self.add_css_class(f"theme-{self.config.theme}")
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                               hexpand=True, vexpand=True, css_classes=["shell-stack"])
        self.search = Gtk.SearchEntry(placeholder_text=_("Search apps, games and tools"),
                                      search_delay=300, css_classes=["shell-search"],
                                      hexpand=True)
        self.back = Gtk.Button(icon_name="go-previous-symbolic", visible=False,
                               tooltip_text=_("Back"), css_classes=["flat", "back-button"])
        self.back.connect("clicked", lambda _b: self.go_back())
        self.nav_buttons: dict[str, Gtk.ToggleButton] = {}
        self.nav_labels: list[Gtk.Label] = []
        self.badge = label("", "nav-badge", xalign=0.5)
        self.badge.set_visible(False)
        self.set_content({"rail": self._rail_shell}.get(self.layout["nav"],
                                                        self._sidebar_shell)())
        for key, widget in self.build_pages():
            self.stack.add_named(scrolled_page(widget), key)
        self.after_build()
        self._check_compact(force=True)
        keys = [key for key, _text, _icon in self.NAV] + list(self.EXTRA_PAGES)
        self.show_page(page if page in keys else keys[0])

    def _header(self, *classes: str) -> Adw.HeaderBar:
        header = Adw.HeaderBar(css_classes=["flat", *classes],
                               decoration_layout=":", show_start_title_buttons=False,
                               show_end_title_buttons=False)
        return header

    def _nav_button(self, key: str, text: str, icon: str, vertical: bool,
                    group: Gtk.ToggleButton | None) -> Gtk.ToggleButton:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical
                      else Gtk.Orientation.HORIZONTAL, spacing=4 if vertical else 12)
        image = Gtk.Image.new_from_icon_name(icon)
        image.add_css_class("nav-icon")
        overlay = Gtk.Overlay(child=image,
                              halign=Gtk.Align.CENTER if vertical else Gtk.Align.START)
        box.append(overlay)
        text_label = label(_(text), "nav-label", xalign=0.5 if vertical else 0)
        box.append(text_label)
        if not vertical:
            self.nav_labels.append(text_label)
        if key == "updates":
            self.badge.set_halign(Gtk.Align.END)
            self.badge.set_valign(Gtk.Align.START)
            self.badge.add_css_class("on-icon")
            overlay.add_overlay(self.badge)
        button = Gtk.ToggleButton(child=box, group=group, css_classes=["nav-item"],
                                  tooltip_text=_(text))
        button.connect("toggled", lambda b: b.get_active() and self.show_page(key, False))
        self.nav_buttons[key] = button
        return button

    def _nav_list(self, vertical: bool) -> Gtk.Box:
        nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, vexpand=True,
                      css_classes=["nav-list"])
        group = None
        for key, text, icon in self.NAV:
            if self.BOTTOM and key == self.BOTTOM[0]:
                nav.append(Gtk.Box(vexpand=True))
            button = self._nav_button(key, text, icon, vertical, group)
            group = group or button
            nav.append(button)
        return nav

    def _brand(self) -> Gtk.Widget:
        brand = Gtk.Box(spacing=10, css_classes=["brand"])
        logo = Gtk.Image.new_from_icon_name(self.ICON)
        logo.set_pixel_size(28)
        brand.append(logo)
        self.brand_name = label(self.BRAND, "brand-name")
        brand.append(self.brand_name)
        return brand

    def _content(self, *classes: str) -> Gtk.Widget:
        content = Gtk.Box(css_classes=["shell-content", *classes], hexpand=True, vexpand=True)
        content.set_overflow(Gtk.Overflow.HIDDEN)
        content.append(self.stack)
        return content

    def _sidebar_shell(self) -> Gtk.Widget:
        showcase = self.layout["nav"] == "search-sidebar"
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=False,
                       css_classes=["shell-nav", "sidebar"])
        side_header = self._header("nav-header")
        side_header.set_title_widget(Gtk.Box())
        side_header.pack_start(self._brand())
        side.append(side_header)
        if showcase and self.SEARCH:
            self.search.set_placeholder_text(_("Search apps"))
            self.search.set_margin_start(12); self.search.set_margin_end(12)
            self.search.set_margin_bottom(10)
            side.append(self.search)
        side.append(self._nav_list(False))
        header = self.topbar = self._header("shell-topbar")
        header.pack_start(self.back)
        if self.SEARCH and not showcase:
            clamp = Adw.Clamp(maximum_size=520, child=self.search, hexpand=True)
            header.set_title_widget(clamp)
        else:
            header.set_title_widget(Gtk.Box())
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True,
                       css_classes=["shell-main"])
        main.append(header)
        main.append(self._content())
        root = Gtk.Box(css_classes=["shell-root"])
        root.append(side)
        root.append(main)
        return root

    def _rail_shell(self) -> Gtk.Widget:
        header = self.topbar = self._header("shell-topbar", "wide")
        header.pack_start(self._brand())
        header.pack_start(self.back)
        if self.SEARCH:
            header.set_title_widget(Adw.Clamp(maximum_size=560, child=self.search,
                                              hexpand=True))
        else:
            header.set_title_widget(Gtk.Box())
        rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=False,
                       css_classes=["shell-nav", "rail"])
        rail.append(self._nav_list(True))
        body = Gtk.Box(vexpand=True)
        body.append(rail)
        body.append(self._content("layer"))
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["shell-root"])
        root.append(header)
        root.append(body)
        return root

    def on_compact(self, hook: Callable[[bool], None]) -> None:
        self.compact_hooks.append(hook)
        hook(self.compact)

    def _check_compact(self, force: bool = False) -> None:
        width = self.get_width() or self.get_default_size()[0]
        compact = 0 < width < COMPACT_WIDTH
        if compact == self.compact and not force:
            return
        self.compact = compact
        (self.add_css_class if compact else self.remove_css_class)("compact")
        for text in self.nav_labels:
            text.set_visible(not compact)
        if getattr(self, "brand_name", None) and self.layout["nav"] != "rail":
            self.brand_name.set_visible(not compact)
        for hook in self.compact_hooks:
            hook(compact)

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        Adw.ApplicationWindow.do_size_allocate(self, width, height, baseline)
        if (0 < width < COMPACT_WIDTH) != self.compact:
            GLib.idle_add(lambda: self._check_compact() or False)

    def show_page(self, key: str, sync_nav: bool = True) -> None:
        current = self.stack.get_visible_child_name()
        if current and current != key and current != "detail":
            self.history.append(current)
        self.stack.set_visible_child_name(key)
        self.back.set_visible(key == "detail" or bool(self.search.get_text()))
        if sync_nav and key in self.nav_buttons:
            self.nav_buttons[key].set_active(True)

    def go_back(self) -> None:
        if self.stack.get_visible_child_name() != "detail" and self.search.get_text():
            self.search.set_text("")
        target = self.history.pop() if self.history else self.NAV[0][0]
        self.show_page(target)
        self.back.set_visible(False)

    def add_timer(self, timer: int) -> None:
        self.timers.append(timer)

    def _config_changed(self, _monitor, _file, _other, event) -> None:
        """Another Glue window (Welcome or Glue Apps) changed the theme or language."""
        if event != Gio.FileMonitorEvent.CHANGES_DONE_HINT and \
                event != Gio.FileMonitorEvent.CREATED:
            return
        fresh = AppsConfig.load(self.config_path)
        if (fresh.theme, fresh.language) == (self.config.theme, self.config.language):
            self.config.autostart = fresh.autostart
            return
        self.config.theme, self.config.language = fresh.theme, fresh.language
        set_language(fresh.language)
        self.rebuild(self.stack.get_visible_child_name() or self.NAV[0][0])

    def save_config(self) -> None:
        self.config.save(self.config_path)

    def set_theme(self, theme: str) -> None:
        if theme != self.config.theme:
            self.config.theme = theme
            self.save_config()
            self.rebuild("settings")

    def set_language(self, code: str) -> None:
        if code != self.config.language:
            self.config.language = code
            self.save_config()
            set_language(code)
            self.rebuild("settings")

    def set_autostart(self, enabled: bool) -> None:
        self.config.autostart = enabled
        self.save_config()
