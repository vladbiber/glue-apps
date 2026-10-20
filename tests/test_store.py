import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from glue_apps import i18n
from glue_apps.catalog import _best_size, plain_text
from glue_apps.curation import AI_APPS, CATEGORIES, GAMES, SEED, category_of, seed_apps, split_by_category
from glue_apps.installed import launcher_for, parse_flatpak_list, parse_owners
from glue_apps.model import App, AppSource
from glue_apps.sources import (aur_option, candidate_names, flatpak_option, human_size,
                              pacman_option, parse_aur_info, parse_pacman_si, recommended,
                              SourceOption)
from glue_apps.updates import (UpdateItem, classify, desktop_files, parse_desktop_entry,
                              parse_flatpak_remote_updates, sort_updates)

PACMAN_SI = """Repository      : world
Name            : vlc
Version         : 3.0.23_2-16
Description     : Free and open source cross-platform multimedia player
Optional Deps   : vlc-gui-ncurses: for ncurses TUI
                  vlc-plugins-all: for all plugins
Download Size   : 6.43 MiB
Installed Size  : 41.97 MiB

Repository      : world
Name            : obs-studio
Version         : 32.2.2-1
Download Size   : 6.74 MiB
Installed Size  : 24.82 MiB
"""


class TestUpdates(unittest.TestCase):
    def test_desktop_entry(self):
        self.assertEqual(parse_desktop_entry(
            "[Desktop Entry]\nName=VLC media player\nIcon=vlc\n[Desktop Action x]\nName=Other\n"),
            ("VLC media player", "vlc"))
        self.assertIsNone(parse_desktop_entry("[Desktop Entry]\nName=Hidden\nNoDisplay=true\n"))

    def test_apps_with_a_window_come_first(self):
        launchers = desktop_files("vlc /usr/share/applications/vlc.desktop\n"
                                  "mesa /usr/lib/libGL.so\n")
        items = classify([("mesa", "1", "2"), ("vlc", "3.0", "3.1")], "repo", launchers,
                         lambda _path: "[Desktop Entry]\nName=VLC\nIcon=vlc\n")
        ordered = sort_updates(items + [UpdateItem("zlib", "1", "2", "repo")])
        self.assertEqual([item.ref for item in ordered], ["vlc", "mesa", "zlib"])
        self.assertTrue(ordered[0].is_app)
        self.assertFalse(ordered[1].is_app)

    def test_flatpak_rows(self):
        self.assertEqual(parse_flatpak_remote_updates("org.videolan.VLC\tVLC\t3.0\n"),
                         [("org.videolan.VLC", "VLC", "3.0")])


class TestSources(unittest.TestCase):
    def test_candidates_use_aliases_and_plain_names(self):
        app = App("com.obsproject.Studio", "OBS Studio")
        self.assertEqual(candidate_names(app)[:2], ["obs-studio", "obsstudio"])

    def test_pacman_blocks(self):
        info = parse_pacman_si(PACMAN_SI)
        self.assertEqual(set(info), {"vlc", "obs-studio"})
        option = pacman_option(App("org.videolan.VLC", "VLC"), info, {"vlc"})
        self.assertTrue(option.available and option.installed)
        self.assertEqual(option.version, "3.0.23_2-16")
        self.assertIn(("Download", "6.43 MiB"), option.details)

    def test_aur_and_flatpak(self):
        info = parse_aur_info(json.dumps({"results": [
            {"Name": "vesktop", "Version": "1.6.7-1", "NumVotes": 95, "Maintainer": "x"}]}))
        option = aur_option(App("dev.vencord.Vesktop", "Vesktop"), info, set())
        self.assertEqual((option.available, option.ref), (True, "vesktop"))
        flat = flatpak_option("dev.vencord.Vesktop", "1.6.7", {"download_size": 135_500_000},
                              {"dev.vencord.Vesktop"})
        self.assertTrue(flat.installed)
        self.assertIn(("Download", "135.5 MB"), flat.details)
        self.assertEqual(human_size(950), "950 B")

    def test_recommended_prefers_installed_then_pacman(self):
        repo, flat = SourceOption("repo", True, "vlc"), SourceOption("flatpak", True, "x")
        self.assertIs(recommended([repo, flat]), repo)
        flat.installed = True
        self.assertIs(recommended([repo, flat]), flat)
        self.assertIsNone(recommended([SourceOption("aur")]))


class TestInstalled(unittest.TestCase):
    def test_owners(self):
        files = ["/usr/share/applications/vlc.desktop"]
        out = "/usr/share/applications/vlc.desktop is owned by vlc 3.0-1\n"
        self.assertEqual(parse_owners(files, out), {files[0]: "vlc"})

    def test_flatpak_list_and_launcher(self):
        self.assertEqual(parse_flatpak_list("a.b.C\tC\t1\n"), [("a.b.C", "C", "1")])
        self.assertEqual(launcher_for("vlc", "/usr/bin/vlc\n/usr/share/applications/vlc.desktop"),
                         "vlc")
        self.assertEqual(launcher_for("lib", "/usr/lib/x.so"), "lib")


class TestCuration(unittest.TestCase):
    def test_every_category_has_enough_apps(self):
        apps = seed_apps()
        for name, tags in CATEGORIES.items():
            if tags:
                shown = [app for app in apps if set(app.categories) & set(tags)]
                self.assertGreaterEqual(len(shown), 7, name)

    def test_seed_sources_cover_pacman_flatpak_and_aur(self):
        kinds = {app.name: app.sources[0].kind for app in seed_apps()}
        self.assertEqual(kinds["Ollama"], "repo")
        self.assertEqual(kinds["Claude Code"], "aur")
        self.assertEqual(kinds["LM Studio"], "flatpak")
        dev = [app.name for app in seed_apps() if "Development" in app.categories]
        self.assertTrue({"Claude Code", "Codex"} <= set(dev))

    def test_requested_apps_are_listed(self):
        ids = {app_id for app_id, *_rest in SEED}
        self.assertIn("aur:claude-desktop", ids)
        self.assertIn("aur:codex-app-unofficial", ids)
        self.assertTrue({"Claude Desktop", "Codex Desktop"} <= set(AI_APPS))
        self.assertIn("dev.vencord.Vesktop", ids)
        self.assertIn("org.vinegarhq.Sober", ids)
        self.assertIn("Sober", GAMES)
        self.assertEqual(len(ids), len(SEED))

    def test_category_matches_come_first(self):
        apps = [App("a", "Kdenlive", categories=("AudioVideo",)),
                App("b", "Blender", categories=("Graphics",)),
                App("c", "VLC", categories=("AudioVideo", "Video"))]
        inside, others = split_by_category(apps, "Media")
        self.assertEqual([app.name for app in inside], ["Kdenlive", "VLC"])
        self.assertEqual([app.name for app in others], ["Blender"])
        self.assertEqual(split_by_category(apps, "All"), (apps, []))

    def test_flathub_search_categories(self):
        from glue_apps.catalog import parse_flathub_search
        app = parse_flathub_search({"hits": [{
            "app_id": "org.openshot.OpenShot", "name": "OpenShot",
            "main_categories": "audiovideo", "sub_categories": ["Video"]}]})[0]
        self.assertEqual(app.categories, ("AudioVideo", "Video"))

    def test_text_helpers(self):
        self.assertEqual(plain_text("<p>A &amp; B</p><ul><li>one</li></ul>"), "A & B\n\n• one")
        self.assertEqual(_best_size([{"src": "s", "width": "224"}, {"src": "b", "width": "1248"}]),
                         "b")


class TestLanguage(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_english_is_default_and_romanian_optional(self):
        self.assertEqual(i18n._("Install"), "Install")
        i18n.set_language("ro")
        self.assertEqual(i18n._("Install"), "Instalează")
        self.assertEqual(i18n._("via {source}", source="AUR"), "prin AUR")
        i18n.set_language("xx")
        self.assertEqual(i18n.language(), "en")


if __name__ == "__main__":
    unittest.main()


class InstalledFilterTest(unittest.TestCase):
    def test_matches_every_word_in_title_or_package(self):
        from glue_apps.installed import matches
        self.assertTrue(matches("", "Firefox", "firefox"))
        self.assertTrue(matches("fire", "Firefox", "firefox"))
        self.assertTrue(matches("FIREFOX", "Firefox", "firefox"))
        self.assertTrue(matches("obs stu", "OBS Studio", "obs-studio"))
        self.assertTrue(matches("com.valve", "Steam", "com.valvesoftware.Steam"))
        self.assertFalse(matches("steam", "Firefox", "firefox"))
        self.assertFalse(matches("obs gimp", "OBS Studio", "obs-studio"))
