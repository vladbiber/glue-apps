"""Reusable GTK widgets: app cards, shelves, section headers and async images."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
from typing import Callable

from gi.repository import Gdk, GLib, Gtk, Pango

from .curation import category_of
from .i18n import _
from .media import cached_image
from .model import App
from .sources import BADGES, badge_kind


def label(text: str, *classes: str, wrap: bool = False, lines: int = 0,
          xalign: float = 0, chars: int = -1) -> Gtk.Label:
    widget = Gtk.Label(label=text, xalign=xalign, wrap=wrap, css_classes=list(classes),
                       max_width_chars=chars)
    if lines:
        widget.set_ellipsize(Pango.EllipsizeMode.END)
        widget.set_lines(lines)
        widget.set_wrap(lines > 1)
    return widget


def _texture(path: Path | str) -> Gdk.Texture | None:
    try:
        return Gdk.Texture.new_from_filename(str(path))
    except GLib.Error:
        return None


def load_image(target: Gtk.Image | Gtk.Picture, source: str,
               pool: concurrent.futures.Executor, cache: Path,
               done: Callable[[], None] | None = None) -> None:
    """Fill an Image or Picture from a path, an https URL or an icon name."""
    def apply(path) -> bool:
        texture = _texture(path) if path else None
        if texture:
            target.set_paintable(texture) if isinstance(target, Gtk.Picture) \
                else target.set_from_paintable(texture)
            if done:
                done()
        return False

    if source.startswith("/"):
        apply(source)
    elif source.startswith("https://"):
        future = pool.submit(cached_image, source, cache)
        future.add_done_callback(lambda f: GLib.idle_add(
            apply, f.result() if not f.exception() else None))
    elif source and isinstance(target, Gtk.Image):
        target.set_from_icon_name(source)


def app_icon(app: App, size: int, pool, cache: Path) -> Gtk.Image:
    icon = Gtk.Image.new_from_icon_name("application-x-executable")
    icon.set_pixel_size(size)
    icon.add_css_class("app-icon")
    load_image(icon, app.icon, pool, cache)
    return icon


def clickable(widget: Gtk.Widget, callback: Callable[[], None]) -> Gtk.Widget:
    gesture = Gtk.GestureClick()
    gesture.connect("released", lambda *_args: callback())
    widget.add_controller(gesture)
    widget.set_cursor_from_name("pointer")
    return widget


def pill(app: App, on_get: Callable[[App], None]) -> Gtk.Button:
    button = Gtk.Button(label=_("Open") if app.installed else _("Get"),
                        valign=Gtk.Align.CENTER, css_classes=["get-button"])
    button.connect("clicked", lambda _b: on_get(app))
    return button


def source_badge(app: App) -> Gtk.Widget | None:
    """Official / Flatpak / AUR: where Get would install the app from."""
    kind = badge_kind(app)
    if not kind:
        return None
    return label(_(BADGES[kind]), "source-badge", f"source-{kind}",
                 xalign=0.5)


def _meta_row(app: App) -> Gtk.Widget:
    row = Gtk.Box(spacing=6)
    row.append(label(_(category_of(app)), "app-meta", lines=1, chars=9))
    if badge := source_badge(app):
        badge.set_valign(Gtk.Align.CENTER)
        row.append(badge)
    return row


def app_card(app: App, style: str, pool, cache: Path,
             on_open: Callable[[App], None], on_get: Callable[[App], None]) -> Gtk.Widget:
    """A store card: 'row' (icon left, pill right) or 'tile' (vertical)."""
    if style == "tile":
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                       css_classes=["app-card", "tile"])
        card.set_size_request(176, 214)
        card.append(app_icon(app, 64, pool, cache))
        name = label(app.name, "app-name", lines=1)
        name.set_margin_top(10)
        card.append(name)
        card.append(label(_(category_of(app)), "app-meta", lines=1))
        if badge := source_badge(app):
            badge.set_halign(Gtk.Align.START)
            badge.set_margin_top(4)
            card.append(badge)
        spacer = Gtk.Box(vexpand=True)
        card.append(spacer)
        card.append(label(_("Installed") if app.installed else _("Free"), "app-price"))
        return clickable(card, lambda: on_open(app))

    card = Gtk.Box(spacing=14, css_classes=["app-card", "row"])
    card.append(app_icon(app, 56, pool, cache))
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                   valign=Gtk.Align.CENTER, hexpand=True)
    # small natural widths let the grid fit three cards per line; extra space is shared
    text.append(label(app.name, "app-name", lines=1, chars=9))
    text.append(label(app.summary or _(category_of(app)), "app-summary", lines=1, chars=9))
    text.append(_meta_row(app))
    card.append(text)
    card.append(pill(app, on_get))
    return clickable(card, lambda: on_open(app))


def section_header(title: str, action: Callable[[], None] | None = None) -> Gtk.Widget:
    box = Gtk.Box(css_classes=["section-header"])
    box.append(label(title, "section-title", xalign=0))
    box.append(Gtk.Box(hexpand=True))
    if action:
        link = Gtk.Button(label=_("See all"), css_classes=["flat", "section-link"])
        link.connect("clicked", lambda _b: action())
        box.append(link)
    return box


def grid(children: list[Gtk.Widget], columns: int) -> Gtk.FlowBox:
    flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                       min_children_per_line=1, max_children_per_line=columns,
                       column_spacing=12, row_spacing=12, css_classes=["card-grid"])
    for child in children:
        flow.append(child)
    return flow


def shelf(children: list[Gtk.Widget]) -> Gtk.Widget:
    """Horizontal scroller used by the tile layout."""
    box = Gtk.Box(spacing=12, css_classes=["shelf"])
    for child in children:
        box.append(child)
    scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                                vscrollbar_policy=Gtk.PolicyType.NEVER)
    scroll.set_child(box)
    scroll.set_propagate_natural_height(True)
    return scroll


def category_tile(name: str, icon: str, index: int,
                  on_click: Callable[[], None]) -> Gtk.Widget:
    tile = Gtk.Box(spacing=12, css_classes=["category-tile", f"cat-{index}"])
    tile.set_size_request(-1, 76)
    image = Gtk.Image.new_from_icon_name(icon)
    image.set_pixel_size(24)
    image.add_css_class("category-icon")
    tile.append(image)
    tile.append(label(_(name), "category-name"))
    return clickable(tile, on_click)


def empty_state(title: str, text: str, icon: str = "system-search-symbolic") -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                  halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, vexpand=True,
                  css_classes=["empty-state"])
    image = Gtk.Image.new_from_icon_name(icon)
    image.set_pixel_size(56)
    box.append(image)
    box.append(label(title, "title-2", xalign=0.5))
    box.append(label(text, "dim-label", xalign=0.5, wrap=True))
    return box


def scrolled_page(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
    clamp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["page"])
    clamp.append(child)
    scroll.set_child(clamp)
    return scroll
