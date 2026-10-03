"""Live theme loading: shared base CSS, per-theme CSS and the light/dark scheme."""

from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gdk, GLib, Gtk

from .config import load_layout
from .curation import CATEGORY_COLORS, FEATURED


def _generated_css() -> str:
    rules = [f".hero-bg-{index} {{ background-image: linear-gradient(135deg, {a}, {b}); }}"
             for index, (a, b) in enumerate(feature.colors for feature in FEATURED)]
    rules += [f".theme-mosaic .cat-{index}, .theme-showcase .cat-{index} .category-icon "
              f"{{ background-image: linear-gradient(135deg, {a}, {b}); }}"
              for index, (a, b) in enumerate(CATEGORY_COLORS.values())]
    return "\n".join(rules)


class ThemeController:
    def __init__(self, data_root: Path) -> None:
        self.root = data_root / "themes"
        self.providers = [Gtk.CssProvider() for _index in range(4)]
        display = Gdk.Display.get_default()
        for offset, provider in enumerate(self.providers):
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + offset)
        self.providers[2].load_from_string(_generated_css())
        try:
            self.providers[3].load_from_path(str(self.root / "compact.css"))
        except GLib.Error:
            pass

    def apply(self, theme: str) -> dict:
        layout = load_layout(self.root, theme)
        Adw.StyleManager.get_default().set_color_scheme(
            Adw.ColorScheme.FORCE_LIGHT if layout["scheme"] == "light"
            else Adw.ColorScheme.FORCE_DARK)
        for provider, path in zip(self.providers,
                                  (self.root / "base.css", self.root / theme / "theme.css")):
            try:
                provider.load_from_path(str(path))
            except GLib.Error:
                pass
        return layout
