"""AppImage install flow: file picker, drag and drop, confirm and result dialogs."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import appimage
from .i18n import _


def pick_button(win, on_done: Callable[[], None] | None = None) -> Gtk.Button:
    button = Gtk.Button(css_classes=["pill", "appimage-button"])
    content = Gtk.Box(spacing=8)
    content.append(Gtk.Image.new_from_icon_name("document-open-symbolic"))
    content.append(Gtk.Label(label=_("Install an AppImage…")))
    button.set_child(content)
    button.connect("clicked", lambda _b: choose(win, on_done))
    return button


def choose(win, on_done=None) -> None:
    dialog = Gtk.FileDialog(title=_("Choose an AppImage"))
    patterns = Gtk.FileFilter(name="AppImage")
    patterns.add_pattern("*.AppImage")
    patterns.add_pattern("*.appimage")
    patterns.add_mime_type("application/vnd.appimage")
    filters = Gio.ListStore.new(Gtk.FileFilter)
    filters.append(patterns)
    dialog.set_filters(filters)
    downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
    if downloads:
        dialog.set_initial_folder(Gio.File.new_for_path(downloads))

    def picked(source, result) -> None:
        try:
            file = source.open_finish(result)
        except GLib.Error:
            return
        if file and file.get_path():
            confirm(win, Path(file.get_path()), on_done)
    dialog.open(win, None, picked)


def confirm(win, path: Path, on_done=None) -> None:
    if not appimage.is_appimage(path):
        _message(win, _("Not an AppImage"),
                 _("{name} is not an AppImage file.", name=path.name))
        return
    dialog = Adw.MessageDialog.new(
        win, _("Install {name}?", name=path.name),
        _("It will be copied to your Applications folder and added to the app menu. "
          "AppImages run with your permissions, so only install ones from sites you trust."))
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("install", _("Install"))
    dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
    dialog.connect("response", lambda _d, r: r == "install" and _install(win, path, on_done))
    dialog.present()


def _install(win, path: Path, on_done) -> None:
    future = win.pool.submit(appimage.install, path)

    def finished(f) -> bool:
        if f.exception():
            _message(win, _("Could not install"), str(f.exception()))
        else:
            app = f.result()
            _message(win, _("{name} is installed", name=app.name),
                     _("Find it in your app menu or under Installed."))
            if on_done:
                on_done()
        return False
    future.add_done_callback(lambda f: GLib.idle_add(finished, f))


def _message(win, title: str, text: str) -> None:
    dialog = Adw.MessageDialog.new(win, title, text)
    dialog.add_response("ok", _("OK"))
    dialog.present()


def accept_drops(win, on_done=None) -> None:
    """Dropping an .AppImage anywhere on the window starts the install."""
    target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)

    def dropped(_target, value, _x, _y) -> bool:
        files = value.get_files() if value else []
        for file in files[:1]:
            if file.get_path():
                confirm(win, Path(file.get_path()), on_done)
                return True
        return False
    target.connect("drop", dropped)
    win.add_controller(target)
