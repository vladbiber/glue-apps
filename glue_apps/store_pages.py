"""Pages backed by the package managers: Updates and Installed."""

from __future__ import annotations

from gi.repository import GLib, Gtk

from . import appimage, appimage_ui
from .commands import action_plan, run_commands, update_plan
from .i18n import _
from .installed import InstalledApp, installed_apps
from .updates import UpdateItem, counts
from .views import page_heading
from .widgets import empty_state, label, section_header

SOURCE_LABEL = {"repo": "Pacman", "flatpak": "Flatpak", "aur": "AUR"}
PACKAGE_PREVIEW = 40


def _icon(win, name: str, size: int) -> Gtk.Image:
    image = Gtk.Image.new_from_icon_name(name or "application-x-executable")
    image.set_pixel_size(size)
    image.add_css_class("app-icon")
    if name.startswith("/"):
        win.load(image, name)
    return image


def _app_row(win, title: str, icon: str, subtitle: str, *buttons: Gtk.Widget) -> Gtk.Widget:
    row = Gtk.Box(spacing=14, css_classes=["panel-row", "list-row"])
    row.append(_icon(win, icon, 40))
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
    text.append(label(title, "row-title", lines=1, chars=10))
    text.append(label(subtitle, "row-subtitle", lines=1, chars=10))
    row.append(text)
    for button in buttons:
        button.set_valign(Gtk.Align.CENTER)
        row.append(button)
    return row


def _version(item: UpdateItem) -> str:
    change = f"{item.old} → {item.new}" if item.old else item.new
    return f"{SOURCE_LABEL[item.source]} · {change}" if change else SOURCE_LABEL[item.source]


class UpdatesView:
    def __init__(self, win) -> None:
        self.win = win
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        self.widget.append(page_heading(
            _("Updates"), _("Update all brings the whole system up to date: the core system "
                            "and drivers first, then Flatpak and AUR apps.")))
        self.card = Gtk.Box(spacing=22, css_classes=["panel", "update-card"])
        self.icon = Gtk.Image.new_from_icon_name("software-update-available-symbolic")
        self.icon.set_pixel_size(52)
        self.icon.add_css_class("status-icon")
        self.card.append(self.icon)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                       hexpand=True, valign=Gtk.Align.CENTER)
        self.title = label(_("Checking…"), "update-title", wrap=True)
        self.subtitle = label(_("Steam updates itself when you open it."), "row-subtitle",
                              wrap=True)
        text.append(self.title); text.append(self.subtitle)
        self.card.append(text)
        self.buttons = Gtk.Box(spacing=10, valign=Gtk.Align.CENTER)
        self.check = Gtk.Button(label=_("Check again"), css_classes=["pill"])
        self.check.connect("clicked", lambda _b: win.check_updates())
        self.install = Gtk.Button(label=_("Update all"), sensitive=False,
                                  css_classes=["pill", "suggested-action"])
        self.install.connect("clicked", lambda _b: self.update_all())
        self.buttons.append(self.check); self.buttons.append(self.install)
        self.card.append(self.buttons)
        self.widget.append(self.card)
        win.on_compact(lambda compact: self.card.set_orientation(
            Gtk.Orientation.VERTICAL if compact else Gtk.Orientation.HORIZONTAL))
        self.progress = Gtk.ProgressBar(visible=False, css_classes=["action-progress"])
        self.widget.append(self.progress)
        self.log = Gtk.TextView(editable=False, monospace=True, css_classes=["log"])
        scroll = Gtk.ScrolledWindow(min_content_height=220)
        scroll.set_child(self.log)
        self.expander = Gtk.Expander(label=_("Update log"), visible=False)
        self.expander.set_child(scroll)
        self.widget.append(self.expander)
        self.lists = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        self.widget.append(self.lists)

    def checking(self) -> None:
        self.title.set_text(_("Checking…"))
        self.check.set_sensitive(False)

    def failed(self) -> None:
        self.check.set_sensitive(True)
        self.title.set_text(_("Could not check for updates."))

    def show(self, items: list[UpdateItem]) -> None:
        self.check.set_sensitive(True)
        system, flatpak, aur = counts(items)
        self.icon.set_from_icon_name("object-select-symbolic" if not items
                                     else "software-update-available-symbolic")
        self.title.set_text(_("Everything is up to date") if not items
                            else _("{count} updates available", count=len(items)))
        self.subtitle.set_text(_("{system} Pacman · {flatpak} Flatpak · {aur} AUR",
                                 system=system, flatpak=flatpak, aur=aur))
        self.install.set_sensitive(bool(items))
        while child := self.lists.get_first_child():
            self.lists.remove(child)
        apps = [item for item in items if item.is_app]
        packages = [item for item in items if not item.is_app]
        if apps:
            self.lists.append(section_header(_("Apps")))
            panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["panel", "rows"])
            for item in apps:
                panel.append(_app_row(self.win, item.title, item.icon, _version(item)))
            self.lists.append(panel)
        if packages:
            self.lists.append(section_header(
                _("System packages") + f"  ·  {len(packages)}"))
            self.lists.append(label(_("Parts of the system without a window: drivers, "
                                      "libraries and tools."), "row-subtitle", wrap=True))
            self._package_list(packages, PACKAGE_PREVIEW)

    def _package_list(self, packages: list[UpdateItem], limit: int) -> None:
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["panel", "rows"])
        for item in packages[:limit]:
            row = Gtk.Box(spacing=12, css_classes=["panel-row", "package-row"])
            name = label(item.ref, "package-name", lines=1, chars=10)
            name.set_hexpand(True)
            row.append(name)
            row.append(label(_version(item), "row-subtitle", lines=1, chars=10, xalign=1))
            panel.append(row)
        if len(packages) > limit:
            more = Gtk.Button(label=_("Show {count} more", count=len(packages) - limit),
                              css_classes=["flat", "section-link"])
            more.connect("clicked", lambda _b: self._expand(panel, packages))
            panel.append(more)
        self.lists.append(panel)

    def _expand(self, panel: Gtk.Box, packages: list[UpdateItem]) -> None:
        self.lists.remove(panel)
        self._package_list(packages, len(packages))

    def update_all(self) -> None:
        self.title.set_text(_("Updating…"))
        self.install.set_sensitive(False)
        self.progress.set_visible(True)
        self.expander.set_visible(True)
        self.expander.set_expanded(True)
        self.log.get_buffer().set_text("")
        pulse = GLib.timeout_add(120, lambda: self.progress.pulse() or True)

        def append(text: str) -> bool:
            buffer = self.log.get_buffer()
            buffer.insert(buffer.get_end_iter(), text)
            return False

        def finished(future) -> bool:
            GLib.source_remove(pulse)
            ok = not future.exception() and future.result() == 0
            self.progress.set_fraction(1 if ok else 0)
            self.title.set_text(_("Done.") if ok else _("Update failed."))
            if ok:
                self.win.check_updates()
            return False

        future = self.win.pool.submit(run_commands, update_plan(),
                                      lambda text: GLib.idle_add(append, text))
        future.add_done_callback(lambda f: GLib.idle_add(finished, f))


class InstalledView:
    def __init__(self, win) -> None:
        self.win = win
        self.loaded = False
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        heading = Gtk.Box(spacing=12)
        title = page_heading(_("Installed"), _("Apps with a window on this computer."))
        title.set_hexpand(True)
        heading.append(title)
        add = appimage_ui.pick_button(win, self.load)
        add.set_valign(Gtk.Align.CENTER)
        heading.append(add)
        self.widget.append(heading)
        win.on_compact(lambda compact: heading.set_orientation(
            Gtk.Orientation.VERTICAL if compact else Gtk.Orientation.HORIZONTAL))
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.widget.append(self.list)

    def load(self) -> None:
        self.loaded = True
        while child := self.list.get_first_child():
            self.list.remove(child)
        spinner = Gtk.Box(spacing=10)
        spinner.append(Gtk.Spinner(spinning=True))
        spinner.append(label(_("Loading…"), "row-subtitle"))
        self.list.append(spinner)
        future = self.win.pool.submit(
            lambda: (installed_apps(self.win.aur_installed), appimage.installed()))
        future.add_done_callback(lambda f: GLib.idle_add(
            self._show, *(([], []) if f.exception() else f.result())))

    def _show(self, apps: list[InstalledApp], images: list[appimage.AppImage]) -> bool:
        while child := self.list.get_first_child():
            self.list.remove(child)
        if images:
            self.list.append(section_header(f"AppImage  ·  {len(images)}"))
            panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["panel", "rows"])
            for image in images:
                panel.append(self._appimage_row(image))
            self.list.append(panel)
        if not apps and not images:
            self.list.append(empty_state(_("Nothing here yet"),
                                         _("Apps you install will show up here."),
                                         "view-grid-symbolic"))
            return False
        for kind in ("repo", "flatpak", "aur"):
            group = [app for app in apps if app.source == kind]
            if not group:
                continue
            self.list.append(section_header(f"{SOURCE_LABEL[kind]}  ·  {len(group)}"))
            panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["panel", "rows"])
            for app in group:
                panel.append(self._row(app))
            self.list.append(panel)
        return False

    def _appimage_row(self, image: appimage.AppImage) -> Gtk.Widget:
        open_button = Gtk.Button(label=_("Open"), css_classes=["pill"])
        open_button.connect("clicked", lambda _b: appimage.launch(image))
        remove = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=_("Uninstall"),
                            css_classes=["flat", "circular", "remove-button"])
        remove.connect("clicked", lambda _b: (appimage.remove(image), self.load()))
        return _app_row(self.win, image.name, image.icon, f"AppImage · {image.path.name}",
                        open_button, remove)

    def _row(self, app: InstalledApp) -> Gtk.Widget:
        open_button = Gtk.Button(label=_("Open"), css_classes=["pill"])
        open_button.connect("clicked", lambda _b: self.win.pool.submit(
            run_commands, action_plan(app.source, "open", app.launcher)))
        remove = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=_("Uninstall"),
                            css_classes=["flat", "circular", "remove-button"])
        remove.connect("clicked", lambda button: self._remove(app, button))
        subtitle = SOURCE_LABEL[app.source] + (f" · {app.version}" if app.version else
                                               f" · {app.ref}")
        return _app_row(self.win, app.title, app.icon, subtitle, open_button, remove)

    def _remove(self, app: InstalledApp, button: Gtk.Button) -> None:
        button.set_sensitive(False)
        future = self.win.pool.submit(run_commands, action_plan(app.source, "remove", app.ref))
        future.add_done_callback(lambda f: GLib.idle_add(self.load))
