"""Windows page: pick an .exe, run it with Wine or Proton, add what it installed to the menu."""

from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk

from . import windows
from .commands import action_plan
from .i18n import _
from .jobs import DONE, FAILED
from .store_pages import _app_row
from .views import page_heading
from .widgets import label, section_header

ENGINE = {"app": "Wine", "game": "Proton"}


def choose(win) -> None:
    dialog = Gtk.FileDialog(title=_("Choose a Windows program"))
    patterns = Gtk.FileFilter(name=_("Windows programs"))
    for pattern in ("*.exe", "*.EXE", "*.msi", "*.MSI"):
        patterns.add_pattern(pattern)
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
            confirm(win, Path(file.get_path()))
    dialog.open(win, None, picked)


def confirm(win, exe: Path) -> None:
    dialog = Adw.AlertDialog.new(
        _("Open {name}", name=exe.name),
        _("Is it a game or a program? Games run with Proton, everything else with Wine. "
          "Windows programs run with your permissions, so only open ones you trust."))
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("game", _("Game"))
    dialog.add_response("app", _("Program"))
    dialog.set_response_appearance("app", Adw.ResponseAppearance.SUGGESTED)
    dialog.connect("response", lambda _d, r: r in windows.MODES and _start(win, exe, r))
    dialog.present(win)


def install_engine(win, mode: str, then=None) -> None:
    """Queues the engine packages; `then` runs once all of them finished well."""
    jobs = [win.jobs.submit("repo", pkg, pkg, "install", action_plan("repo", "install", pkg))
            for pkg in windows.PACKAGES[mode]]

    def changed(job) -> None:
        if job not in jobs or not all(j.state in (DONE, FAILED) for j in jobs):
            return
        win.jobs.listeners.remove(changed)
        if getattr(win, "windows_view", None):
            win.windows_view.load()
        if then and windows.ready(mode):
            then()
    win.jobs.listeners.append(changed)


def _start(win, exe: Path, mode: str) -> None:
    if windows.ready(mode):
        _run(win, exe, mode)
        return
    win.toasts.add_toast(Adw.Toast(title=_("Installing {engine} first…", engine=ENGINE[mode])))
    install_engine(win, mode, lambda: _run(win, exe, mode))


def _run(win, exe: Path, mode: str) -> None:
    box = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
    box.append(Gtk.Spinner(spinning=True))
    box.append(label(_("Finish the installer, then close it."), "row-subtitle", wrap=True))
    wait = Adw.AlertDialog.new(
        _("{name} is running", name=exe.name),
        _("The first start can take a few minutes while {engine} gets ready.",
          engine=ENGINE[mode]))
    wait.set_extra_child(box)
    wait.set_can_close(False)
    wait.present(win)
    future = win.pool.submit(windows.run_install, mode, exe)

    def finished(f) -> bool:
        wait.set_can_close(True)
        wait.force_close()
        found = [] if f.exception() else f.result()
        if found:
            _pick(win, mode, found)
        elif exe.suffix.lower() != ".msi":
            _portable(win, exe, mode)
        else:
            _message(win, _("Nothing was installed"),
                     _("{name} closed without installing a program.", name=exe.name))
        return False
    future.add_done_callback(lambda f: GLib.idle_add(finished, f))


def _pick(win, mode: str, found: list[tuple[str, Path]]) -> None:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    checks = []
    for index, (name, exe) in enumerate(found):
        check = Gtk.CheckButton(label=name, active=index == 0, tooltip_text=exe.name)
        box.append(check)
        checks.append((check, name, exe))
    dialog = Adw.AlertDialog.new(_("Add to the app menu"),
                                 _("Pick what you want to open from the app menu."))
    dialog.set_extra_child(box)
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("add", _("Add"))
    dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)

    def respond(_d, response) -> None:
        if response == "add":
            _add(win, mode, [(n, e) for c, n, e in checks if c.get_active()])
    dialog.connect("response", respond)
    dialog.present(win)


def _portable(win, exe: Path, mode: str) -> None:
    dialog = Adw.AlertDialog.new(
        _("Add {name} to the app menu?", name=windows.pretty(exe.stem)),
        _("It did not install anything, so it is a program that runs as it is. "
          "Glue Apps can keep a copy and add it to the app menu."))
    dialog.add_response("cancel", _("No"))
    dialog.add_response("add", _("Add"))
    dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
    dialog.connect("response", lambda _d, r: r == "add" and _add(
        win, mode, [(windows.pretty(exe.stem), windows.keep_portable(mode, exe))]))
    dialog.present(win)


def _add(win, mode: str, picked: list[tuple[str, Path]]) -> None:
    for name, exe in picked:
        windows.add(name, mode, exe)
    if picked:
        win.toasts.add_toast(Adw.Toast(title=_("Added to the app menu"), timeout=6))
    win.show_page("windows")
    win.windows_view.load()


def _message(win, title: str, text: str) -> None:
    dialog = Adw.AlertDialog.new(title, text)
    dialog.add_response("ok", _("OK"))
    dialog.present(win)


class WindowsView:
    def __init__(self, win) -> None:
        self.win = win
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        self.widget.append(page_heading(
            _("Windows programs"),
            _("Open an .exe and it shows up in your app menu like any other app.")))
        pick = Gtk.Button(css_classes=["pill", "suggested-action", "appimage-button"],
                          halign=Gtk.Align.START)
        content = Gtk.Box(spacing=8)
        content.append(Gtk.Image.new_from_icon_name("document-open-symbolic"))
        content.append(Gtk.Label(label=_("Choose a .exe…")))
        pick.set_child(content)
        pick.connect("clicked", lambda _b: choose(win))
        self.widget.append(pick)
        self.widget.append(label(_("You can also drop a file here, or double-click "
                                   "an .exe in your file manager."), "row-subtitle", wrap=True))
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.widget.append(self.body)
        self.load()

    def load(self) -> None:
        while child := self.body.get_first_child():
            self.body.remove(child)
        self.body.append(section_header(_("Engines")))
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["panel", "rows"])
        for mode, text in (("app", _("For programs")), ("game", _("For games"))):
            if windows.ready(mode):
                state = label(_("Ready"), "row-subtitle")
            else:
                state = Gtk.Button(label=_("Install"), css_classes=["pill"])
                state.connect("clicked", lambda _b, m=mode: (
                    _b.set_sensitive(False), install_engine(self.win, m)))
            icon = "input-gaming-symbolic" if mode == "game" else "application-x-executable-symbolic"
            panel.append(_app_row(self.win, ENGINE[mode], icon, text, state))
        self.body.append(panel)
        apps = windows.installed()
        if not apps:
            return
        self.body.append(section_header(f"{_('In your app menu')}  ·  {len(apps)}"))
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["panel", "rows"])
        for app in apps:
            panel.append(self._row(app))
        self.body.append(panel)

    def _row(self, app: windows.WinApp) -> Gtk.Widget:
        open_button = Gtk.Button(label=_("Open"), css_classes=["pill"])
        open_button.connect("clicked", lambda _b: windows.launch(app))
        remove = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=_("Uninstall"),
                            css_classes=["flat", "circular", "remove-button"])
        remove.connect("clicked", lambda _b: self._remove(app))
        kind = _("Game") if app.mode == "game" else _("Program")
        return _app_row(self.win, app.name, app.icon, f"{kind} · {ENGINE[app.mode]}",
                        open_button, remove)

    def _remove(self, app: windows.WinApp) -> None:
        dialog = Adw.AlertDialog.new(_("Remove {name}?", name=app.name),
                                     _("It leaves the app menu and its files are deleted."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("remove", _("Remove"))
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda _d, r: r == "remove" and (
            windows.remove(app, files=True), self.load()))
        dialog.present(self.win)
