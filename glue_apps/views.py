"""Store views: Discover, Apps (browse + search) and Games, per theme layout."""

from __future__ import annotations

from gi.repository import Adw, GLib, Gtk

from .curation import (AI_APPS, CATEGORIES, CATEGORY_ICONS, CREATE, ESSENTIALS, FEATURED,
                       GAMES, Feature)
from . import aur
from .i18n import _
from .widgets import (app_card, category_tile, clickable, empty_state, grid, label,
                      section_header, shelf)


def _cards(win, apps) -> list[Gtk.Widget]:
    return [app_card(app, win.layout["card"], win.pool, win.image_cache,
                     win.open_app, win.get_app) for app in apps]


def app_section(win, title: str, apps, action=None, rows: int = 2) -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.append(section_header(title, action))
    if win.layout["card"] == "tile":
        box.append(shelf(_cards(win, apps)))
    else:
        box.append(grid(_cards(win, apps[:win.layout["columns"] * rows]),
                        win.layout["columns"]))
    return box


def _hero_text(win, feature: Feature, app, compact: bool) -> Gtk.Widget:
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                   css_classes=["hero-text"], valign=Gtk.Align.END,
                   halign=Gtk.Align.START)
    text.append(label(_(feature.eyebrow).upper(), "hero-eyebrow"))
    text.append(label(_(feature.title), "hero-title", wrap=True))
    if not compact:
        text.append(label(_(feature.blurb), "hero-blurb", wrap=True))
    if app:
        row = Gtk.Box(spacing=12, css_classes=["hero-app"])
        row.set_margin_top(10)
        icon = Gtk.Image(pixel_size=40, css_classes=["app-icon"])
        win.load(icon, app.icon)
        row.append(icon)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        names.append(label(app.name, "hero-app-name"))
        names.append(label(app.summary, "hero-app-summary", lines=1))
        row.append(names)
        button = Gtk.Button(label=_("Open") if app.installed else _("Get"),
                            valign=Gtk.Align.CENTER, css_classes=["get-button", "hero-get"])
        button.connect("clicked", lambda _b: win.get_app(app))
        row.append(button)
        text.append(row)
    return text


def hero_card(win, feature: Feature, index: int, height: int,
              compact: bool = False) -> Gtk.Widget:
    """Full-bleed feature card: screenshot (when online) under a scrim."""
    app = win.find_app(feature.app)
    overlay = Gtk.Overlay(css_classes=["hero", f"hero-bg-{index}"], hexpand=True)
    overlay.set_overflow(Gtk.Overflow.HIDDEN)
    overlay.set_size_request(-1, height)
    picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True,
                          css_classes=["hero-picture"])
    overlay.set_child(picture)
    overlay.add_overlay(Gtk.Box(css_classes=["hero-scrim"]))
    overlay.add_overlay(_hero_text(win, feature, app, compact))
    if app:
        win.load_screenshot(app, picture)
        clickable(overlay, lambda: win.open_app(app))
    return overlay


def hero_banner(win, feature: Feature) -> Gtk.Widget:
    """Glue layout: text on the left, framed screenshot on the right."""
    app = win.find_app(feature.app)
    banner = Gtk.Box(spacing=32, css_classes=["hero", "banner"])
    text = _hero_text(win, feature, app, False)
    text.set_valign(Gtk.Align.CENTER)
    text.set_hexpand(True)
    banner.append(text)
    frame = Gtk.Box(css_classes=["banner-shot"], valign=Gtk.Align.CENTER, hexpand=True)
    frame.set_overflow(Gtk.Overflow.HIDDEN)
    frame.set_size_request(-1, 248)   # no fixed width, so small windows can go compact
    picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True, hexpand=True)
    frame.append(picture)
    banner.append(frame)
    if app:
        win.load_screenshot(app, picture)
    win.on_compact(lambda compact: frame.set_visible(not compact))
    return banner


def carousel(win, features) -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    pages = Adw.Carousel(allow_scroll_wheel=False, spacing=12, css_classes=["hero-carousel"])
    cards = [hero_card(win, feature, index, 330) for index, feature in enumerate(features)]
    for card in cards:
        pages.append(card)
    win.on_compact(lambda compact: [card.set_size_request(-1, 260 if compact else 330)
                                    for card in cards])
    dots = Adw.CarouselIndicatorLines(carousel=pages)
    box.append(pages)
    box.append(dots)

    def advance() -> bool:
        if not pages.get_root():
            return False
        position = (round(pages.get_position()) + 1) % pages.get_n_pages()
        pages.scroll_to(pages.get_nth_page(position), True)
        return True
    win.add_timer(GLib.timeout_add_seconds(7, advance))
    return box


def categories_section(win) -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.append(section_header(_("Browse by category")))
    names = [name for name in CATEGORIES if name != "All"]
    tiles = [category_tile(name, CATEGORY_ICONS[name], index,
                           lambda name=name: win.show_category(name))
             for index, name in enumerate(names)]
    tiles_grid = grid(tiles, 4)
    win.on_compact(lambda compact: tiles_grid.set_max_children_per_line(2 if compact else 4))
    box.append(tiles_grid)
    return box


def page_heading(title: str, subtitle: str = "") -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                  css_classes=["page-heading"])
    box.append(label(title, "page-title"))
    if subtitle:
        box.append(label(subtitle, "page-subtitle", wrap=True))
    return box


def discover_page(win) -> Gtk.Widget:
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=34)
    hero = win.layout["hero"]
    if hero == "editorial":
        page.append(page_heading(_("Discover")))
        pair = Gtk.Box(spacing=18, homogeneous=True)
        for index, feature in enumerate(FEATURED[:2]):
            pair.append(hero_card(win, feature, index, 300))
        win.on_compact(lambda compact: pair.set_orientation(
            Gtk.Orientation.VERTICAL if compact else Gtk.Orientation.HORIZONTAL))
        page.append(pair)
    elif hero == "carousel":
        page.append(carousel(win, FEATURED))
    else:
        page.append(hero_banner(win, FEATURED[0]))
    page.append(app_section(win, _("Essential apps"), win.pick(ESSENTIALS),
                            lambda: win.show_category("All")))
    page.append(app_section(win, _("Top games"), win.pick(GAMES), win.show_games))
    page.append(app_section(win, _("Create"), win.pick(CREATE),
                            lambda: win.show_category("Graphics"), rows=1))
    page.append(app_section(win, _("AI tools"), win.pick(AI_APPS),
                            lambda: win.show_category("AI"), rows=1))
    page.append(categories_section(win))
    return page


def games_page(win) -> Gtk.Widget:
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30)
    page.append(page_heading(_("Games")))
    page.append(hero_card(win, FEATURED[0], 0, 300))
    games = win.pick(GAMES)
    more = [app for app in win.index.search("", limit=400)
            if "Game" in app.categories and app not in games]
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.append(section_header(_("Top games")))
    box.append(grid(_cards(win, games + more[:30]),
                    win.layout["columns"] if win.layout["card"] == "row" else 5))
    page.append(box)
    return page


class AppsView:
    """Category chips, source filter and a result grid that refreshes in place."""

    SOURCES = ("all", "repo", "flatpak", "aur")

    def __init__(self, win) -> None:
        self.win = win
        self.category = "All"
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.heading = page_heading(_("Apps"))
        self.widget.append(self.heading)
        if not win.config.store:
            self.widget.append(empty_state(_("Apps"),
                               _("The app store is not installed on this system."),
                               "system-software-install-symbolic"))
            self.results = None
            return
        bar = Gtk.Box(spacing=8)
        chips = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, hexpand=True,
                            max_children_per_line=12, column_spacing=6, row_spacing=6)
        self.chips: dict[str, Gtk.ToggleButton] = {}
        group = None
        for name in CATEGORIES:
            chip = Gtk.ToggleButton(label=_(name), css_classes=["chip"], group=group)
            group = group or chip
            chip.connect("toggled", self._chip_toggled, name)
            self.chips[name] = chip
            chips.append(chip)
        bar.append(chips)
        self.source = Gtk.DropDown.new_from_strings(
            [_("All sources"), "Pacman", "Flatpak", aur.label()])
        self.source.set_valign(Gtk.Align.START)
        self.source.connect("notify::selected", lambda *_a: win.refresh_results())
        bar.append(self.source)
        self.widget.append(bar)
        self.status = label("", "dim-label")
        self.widget.append(self.status)
        self.results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.widget.append(self.results)
        self.chips["All"].set_active(True)

    def source_key(self) -> str:
        return self.SOURCES[self.source.get_selected()] if self.results else "all"

    def select_category(self, name: str) -> None:
        if self.results and name in self.chips:
            self.chips[name].set_active(True)

    def _chip_toggled(self, chip: Gtk.ToggleButton, name: str) -> None:
        if chip.get_active():
            self.category = name
            self.win.refresh_results()

    def render(self, apps, query: str, others=()) -> None:
        """Matches in the chosen category, then matches from the other categories."""
        if not self.results:
            return
        while child := self.results.get_first_child():
            self.results.remove(child)
        title = self.heading.get_first_child()
        title.set_text(f"{_('Results')} · “{query}”" if query else _("Apps"))
        columns = self.win.layout["columns"] if self.win.layout["card"] == "row" else 5
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        if apps:
            if others:
                box.append(section_header(_("In {category}", category=_(self.category))))
            box.append(grid(_cards(self.win, apps), columns))
        elif others:
            box.append(label(_("Nothing in {category} matches. Here is what the other "
                               "categories have:", category=_(self.category)), "row-subtitle",
                             wrap=True))
        if others:
            if apps:
                box.append(Gtk.Box(css_classes=["section-gap"]))
            box.append(section_header(_("In other categories")))
            box.append(grid(_cards(self.win, list(others)), columns))
        if not apps and not others:
            box.append(empty_state(_("No apps found"),
                                   _("Try another word, like “video” or “photo”.")))
        self.results.append(box)
