"""Settings page and the panel rows shared with Glue Welcome."""

from __future__ import annotations

from gi.repository import Gtk

from .config import THEME_NAMES, THEMES
from .i18n import LANGUAGES, _
from .views import page_heading
from .widgets import clickable, grid, label, section_header

THEME_BLURBS = {"glue": "Light, with white cards and violet accents.",
                "showcase": "Light and airy, with a search sidebar.",
                "mosaic": "Dark tiles with a navigation rail."}


def panel_row(title: str, value: Gtk.Widget | str, subtitle: str = "") -> Gtk.Widget:
    row = Gtk.Box(spacing=16, css_classes=["panel-row"])
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True,
                   valign=Gtk.Align.CENTER)
    text.append(label(title, "row-title"))
    if subtitle:
        text.append(label(subtitle, "row-subtitle", wrap=True))
    row.append(text)
    row.append(label(value, "row-value", xalign=1) if isinstance(value, str) else value)
    return row


def panel(*rows: Gtk.Widget) -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["panel", "rows"])
    for row in rows:
        box.append(row)
    return box


def _theme_preview(theme: str) -> Gtk.Widget:
    preview = Gtk.Box(css_classes=["theme-preview", f"preview-{theme}"],
                      valign=Gtk.Align.START)
    preview.set_size_request(180, -1)
    preview.set_overflow(Gtk.Overflow.HIDDEN)
    nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, css_classes=["pv-nav"])
    for _index in range(4):
        nav.append(Gtk.Box(css_classes=["pv-dot"]))
    preview.append(nav)
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True,
                   css_classes=["pv-body"])
    body.append(Gtk.Box(css_classes=["pv-hero"]))
    cards = Gtk.Box(spacing=6, homogeneous=True)
    for _index in range(3):
        cards.append(Gtk.Box(css_classes=["pv-card"]))
    body.append(cards)
    preview.append(body)
    return preview


def settings_page(win, extra: tuple[tuple[str, Gtk.Widget], ...] = ()) -> Gtk.Widget:
    """Appearance and language; extra adds titled panels (Welcome adds startup)."""
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    page.append(page_heading(_("Settings")))
    page.append(section_header(_("Appearance")))
    cards = []
    for theme in THEMES:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       css_classes=["theme-card"] + (["selected"] if theme == win.config.theme else []))
        card.append(_theme_preview(theme))
        card.append(label(THEME_NAMES[theme], "row-title"))
        card.append(label(_(THEME_BLURBS[theme]), "row-subtitle", wrap=True))
        cards.append(clickable(card, lambda t=theme: win.set_theme(t)))
    page.append(grid(cards, 3))

    language = Gtk.DropDown.new_from_strings(list(LANGUAGES.values()))
    language.set_selected(list(LANGUAGES).index(win.config.language))
    language.set_valign(Gtk.Align.CENTER)
    language.connect("notify::selected",
                     lambda d, _p: win.set_language(list(LANGUAGES)[d.get_selected()]))
    page.append(section_header(_("Language")))
    page.append(panel(panel_row(_("Language"), language)))
    for title, widget in extra:
        page.append(section_header(title))
        page.append(widget)
    return page
