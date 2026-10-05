"""Full-page app details: Pacman, Flatpak and AUR options side by side."""

from __future__ import annotations

from gi.repository import Adw, GLib, Gtk

from . import aur
from .catalog import plain_text
from .commands import action_plan, run_commands
from .installed import open_installed
from .curation import category_of
from .i18n import _
from .model import App, AppSource
from .remote import aur_details, flathub_details
from .sources import SourceOption, probe_sources, recommended
from .widgets import grid, label, section_header

SOURCE_INFO = {
    "repo": ("Pacman", "Official repositories. Updated with the rest of the system.",
             "package-x-generic-symbolic"),
    "flatpak": ("Flatpak", "From Flathub. Sandboxed and always the newest version.",
                "application-x-addon-symbolic"),
    "aur": ("AUR", "Built on your PC from a community recipe.",
            "system-users-symbolic"),
}


def source_name(kind: str) -> str:
    return aur.label() if kind == "aur" else SOURCE_INFO[kind][0]


class DetailView:
    def __init__(self, win, app: App) -> None:
        self.win = win
        self.app = app
        self.options: list[SourceOption] = []
        self.busy = False
        self.pulse_id = 0
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30,
                              css_classes=["detail"])
        self.widget.append(self._header())
        self.widget.append(self._options_section())
        self.widget.append(self._screenshots())
        self.widget.append(self._about())
        self._fill()
        self._fetch_details()
        self._probe()

    def _header(self) -> Gtk.Widget:
        header = Gtk.Box(spacing=28, css_classes=["detail-header"])
        self.icon = Gtk.Image(pixel_size=128, css_classes=["app-icon", "detail-icon"])
        header.append(self.icon)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                       valign=Gtk.Align.CENTER, hexpand=True)
        self.name = label("", "detail-name", wrap=True)
        self.developer = label("", "detail-dev")
        self.summary = label("", "detail-summary", wrap=True)
        info.append(self.name); info.append(self.developer); info.append(self.summary)
        actions = Gtk.Box(spacing=12, css_classes=["detail-actions"])
        actions.set_margin_top(14)
        self.action = Gtk.Button(label=_("Checking…"), sensitive=False,
                                 css_classes=["action-button", "suggested-action", "pill"])
        self.action.connect("clicked", lambda _b: self.run(self.main_option()))
        self.open = Gtk.Button(label=_("Open"), visible=False,
                               css_classes=["action-button", "pill"])
        self.open.connect("clicked", lambda _b: self.launch())
        self.via = label("", "detail-via")
        self.via.set_valign(Gtk.Align.CENTER)
        for child in (self.action, self.open, self.via):
            actions.append(child)
        info.append(actions)
        self.progress = Gtk.ProgressBar(show_text=True, visible=False,
                                        css_classes=["action-progress"])
        self.status = label("", "detail-status", wrap=True)
        info.append(self.progress); info.append(self.status)
        header.append(info)
        self.win.on_compact(lambda compact: (
            self.icon.set_pixel_size(72 if compact else 128),
            header.set_spacing(16 if compact else 28)))
        return header

    def _options_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(section_header(_("Install options")))
        self.options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        spinner = Gtk.Box(spacing=10)
        spinner.append(Gtk.Spinner(spinning=True))
        spinner.append(label(_("Looking in Pacman, Flatpak and the AUR…"), "row-subtitle"))
        self.options_box.append(spinner)
        box.append(self.options_box)
        return box

    def _option_card(self, option: SourceOption, best: bool) -> Gtk.Widget:
        _name, blurb, icon = SOURCE_INFO[option.kind]
        title = source_name(option.kind)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       css_classes=["source-card"] + ([] if option.available else ["missing"]))
        top = Gtk.Box(spacing=10)
        image = Gtk.Image.new_from_icon_name(icon)
        image.set_pixel_size(20)
        image.add_css_class("source-icon")
        top.append(image)
        top.append(label(title, "row-title"))
        top.append(Gtk.Box(hexpand=True))
        if best and option.available:
            top.append(label(_("Installed") if option.installed else _("Recommended"),
                             "source-tag"))
        card.append(top)
        card.append(label(_(blurb), "row-subtitle", wrap=True, chars=22))
        if not option.available:
            card.append(label(_("Not available here"), "source-missing"))
            return card
        facts = Gtk.Grid(column_spacing=12, row_spacing=3, css_classes=["source-facts"])
        rows = [(_("Version"), option.version or _("Unknown"))] + \
               [(_(key), value) for key, value in option.details if value]
        for index, (key, value) in enumerate(rows):
            facts.attach(label(key, "info-key"), 0, index, 1, 1)
            facts.attach(label(value, "info-value-small", lines=1, chars=12), 1, index, 1, 1)
        card.append(facts)
        card.append(Gtk.Box(vexpand=True))
        button = Gtk.Button(label=_("Uninstall") if option.installed else _("Install"),
                            css_classes=["pill", "destructive-action" if option.installed
                                         else "suggested-action"])
        button.set_sensitive(not self.busy)
        button.connect("clicked", lambda _b: self.run(option))
        card.append(button)
        return card

    def _screenshots(self) -> Gtk.Widget:
        self.shots_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                                 visible=False)
        self.shots_box.append(section_header(_("Screenshots")))
        self.shots = Gtk.Box(spacing=14, css_classes=["shots"])
        scroll = Gtk.ScrolledWindow(vscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_propagate_natural_height(True)
        scroll.set_child(self.shots)
        self.shots_box.append(scroll)
        self.shown_shots: set[str] = set()
        self.shot_frames: list[Gtk.Widget] = []
        self.win.on_compact(lambda compact: [
            frame.set_size_request(300 if compact else 448, 169 if compact else 252)
            for frame in self.shot_frames])
        return self.shots_box

    def _about(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(section_header(_("About this app")))
        self.description = label("", "detail-description", wrap=True, chars=100)
        self.description.set_selectable(True)
        box.append(self.description)
        box.append(section_header(_("Information")))
        self.info = Gtk.Grid(column_spacing=40, row_spacing=4, column_homogeneous=True,
                             css_classes=["panel", "info-grid"])
        box.append(self.info)
        log_scroll = Gtk.ScrolledWindow(min_content_height=160)
        self.log = Gtk.TextView(editable=False, monospace=True,
                                wrap_mode=Gtk.WrapMode.WORD_CHAR, css_classes=["log"])
        log_scroll.set_child(self.log)
        self.log_expander = Gtk.Expander(label=_("Details"), visible=False)
        self.log_expander.set_child(log_scroll)
        box.append(self.log_expander)
        return box

    def _fill(self) -> None:
        app = self.app
        self.name.set_text(app.name)
        self.developer.set_text(app.developer or _(category_of(app)))
        self.summary.set_text(app.summary or _("No description."))
        self.description.set_text(plain_text(app.description) or app.summary
                                  or _("No description."))
        self.icon.set_from_icon_name("application-x-executable")
        self.win.load(self.icon, app.icon)
        while child := self.info.get_first_child():
            self.info.remove(child)
        rows = ((_("Developer"), app.developer or _("Unknown")),
                (_("License"), app.license or _("Unknown")),
                (_("Category"), _(category_of(app))))
        for index, (key, value) in enumerate(rows):
            self.info.attach(label(key, "info-key"), index, 0, 1, 1)
            self.info.attach(label(value, "info-value", wrap=True), index, 1, 1, 1)
        for url in app.screenshots[:4]:
            self._add_shot(url)

    def _add_shot(self, url: str) -> None:
        if url in self.shown_shots:
            return
        self.shown_shots.add(url)
        frame = Gtk.Box(css_classes=["shot"])
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        compact = self.win.compact
        frame.set_size_request(300 if compact else 448, 169 if compact else 252)
        picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True, hexpand=True)
        frame.append(picture)
        self.shots.append(frame)
        self.shot_frames.append(frame)
        self.shots_box.set_visible(True)
        self.win.load(picture, url)

    def _fetch_details(self) -> None:
        for source in self.app.sources:
            if source.kind == "flatpak":
                future = self.win.pool.submit(flathub_details, source.ref, self.win.cache,
                                              self.win.flatpak_installed)
            elif source.kind == "aur":
                future = self.win.pool.submit(aur_details, source.ref, self.win.cache,
                                              self.win.aur_installed)
            else:
                continue
            future.add_done_callback(lambda f: GLib.idle_add(self._details_loaded, f))

    def _details_loaded(self, future) -> bool:
        detail = None if future.exception() else future.result()
        if detail:
            self.app = self.win.merge_detail(self.app, detail)
            self._fill()
        return False

    def _probe(self) -> None:
        future = self.win.pool.submit(probe_sources, self.app, self.win.native_installed,
                                      self.win.aur_installed, self.win.flatpak_installed)
        future.add_done_callback(lambda f: GLib.idle_add(
            self._probed, [] if f.exception() else f.result()))

    def _probed(self, options: list[SourceOption]) -> bool:
        self.options = options
        self._render_options()
        return False

    def _render_options(self) -> None:
        while child := self.options_box.get_first_child():
            self.options_box.remove(child)
        best = self.main_option()
        cards = [self._option_card(option, option is best) for option in self.options]
        self.options_box.append(grid(cards, 3) if cards else label(
            _("Could not check the sources. Are you online?"), "row-subtitle"))
        if best:
            self.action.set_label(_("Uninstall") if best.installed else _("Install"))
            self.action.set_sensitive(not self.busy)
            self.action.remove_css_class("suggested-action" if best.installed
                                         else "destructive-action")
            self.action.add_css_class("destructive-action" if best.installed
                                      else "suggested-action")
            self.via.set_text(_("via {source}", source=source_name(best.kind)))
        else:
            self.action.set_label(_("Not available"))
            self.action.set_sensitive(False)
            self.via.set_text("")
        self.open.set_visible(bool(best and best.installed))

    def main_option(self) -> SourceOption | None:
        return recommended(self.options)

    def run(self, option: SourceOption | None) -> None:
        if not option or self.busy:
            return
        action = "remove" if option.installed else "install"
        if option.kind == "aur" and action == "install" and not self.win.config.aur_warning_seen:
            text = _("The AUR contains recipes written by the community. Glue Apps builds "
                     "them as your user, but check the source if the app handles sensitive "
                     "data.")
            if not aur.has_systemd():
                text += " " + _("Some recipes that need systemd will not work on this system.")
            dialog = Adw.AlertDialog.new(_("Community app"), text)
            dialog.add_response("cancel", _("Cancel"))
            dialog.add_response("continue", _("I understand, continue"))
            dialog.set_response_appearance("continue", Adw.ResponseAppearance.SUGGESTED)
            dialog.connect("response", lambda _d, r: self._aur_confirmed(option)
                           if r == "continue" else None)
            dialog.present(self.win)
            return
        self._start(option, action)

    def _aur_confirmed(self, option: SourceOption) -> None:
        self.win.config.aur_warning_seen = True
        self.win.save_config()
        self._start(option, "install")

    def launch(self) -> None:
        option = self.main_option()
        if option and option.installed:
            self.win.pool.submit(open_installed, option.kind, option.ref)

    def _start(self, option: SourceOption, action: str) -> None:
        self.busy = True
        self._render_options()
        self.action.set_sensitive(False)
        self.status.set_text(_("Working…"))
        self.log.get_buffer().set_text("")
        self.log_expander.set_visible(True)
        self.progress.set_visible(True)
        self.progress.set_text(_("Working…"))
        self.pulse_id = GLib.timeout_add(120, self._pulse)
        output = lambda text: GLib.idle_add(self._append, text)
        future = self.win.pool.submit(
            run_commands, action_plan(option.kind, action, option.ref), output)
        future.add_done_callback(lambda f: GLib.idle_add(self._done, f, option, action))

    def _pulse(self) -> bool:
        self.progress.pulse()
        return True

    def _append(self, text: str) -> bool:
        buffer = self.log.get_buffer()
        buffer.insert(buffer.get_end_iter(), text)
        return False

    def _done(self, future, option: SourceOption, action: str) -> bool:
        code = 1 if future.exception() else future.result()
        if self.pulse_id:
            GLib.source_remove(self.pulse_id)
            self.pulse_id = 0
        self.busy = False
        self.progress.set_fraction(1 if code == 0 else 0)
        self.progress.set_text(_("Done") if code == 0 else _("Failed"))
        self.status.set_text(_("Done.") if code == 0 else _("Failed with code {code}.", code=code))
        if code == 0:
            option.installed = action == "install"
            self.app = self.win.mark_installed(
                self.app, AppSource(option.kind, option.ref, option.version), option.installed)
        self._render_options()
        return False
