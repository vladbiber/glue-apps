import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from glue_apps import i18n
from glue_apps.model import App, AppSource
from glue_apps.sources import (BADGES, SourceOption, aur_warning, badge_kind, recommended,
                               safer_alternative)


def opts(*kinds):
    return [SourceOption(k, k in kinds, ref=k) for k in ("repo", "flatpak", "aur")]


class TestSourceChoice(unittest.TestCase):
    def test_get_prefers_official_then_flatpak_then_aur(self):
        self.assertEqual(recommended(opts("repo", "flatpak", "aur")).kind, "repo")
        self.assertEqual(recommended(opts("flatpak", "aur")).kind, "flatpak")
        self.assertEqual(recommended(opts("aur")).kind, "aur")

    def test_safer_alternative_to_the_aur(self):
        self.assertEqual(safer_alternative(opts("flatpak", "aur")).kind, "flatpak")
        self.assertEqual(safer_alternative(opts("repo", "flatpak", "aur")).kind, "repo")
        self.assertIsNone(safer_alternative(opts("aur")))

    def test_badge_follows_the_preferred_source(self):
        app = App("x", "X", sources=(AppSource("aur", "x-bin"), AppSource("flatpak", "org.x.X")))
        self.assertEqual(badge_kind(app), "flatpak")
        self.assertEqual(badge_kind(App("y", "Y")), "")
        self.assertEqual(BADGES, {"repo": "Official", "flatpak": "Flatpak", "aur": "AUR"})


class TestAurWarning(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_says_root_and_unreviewed(self):
        text = aur_warning(True)
        self.assertIn("run as root", text)
        self.assertIn("nobody reviews", text)
        self.assertNotIn("systemd", text)

    def test_mentions_the_alternative(self):
        self.assertIn("sandboxed", aur_warning(True, SourceOption("flatpak", True)))
        self.assertIn("official repositories", aur_warning(True, SourceOption("repo", True)))
        self.assertIn("systemd", aur_warning(False))

    def test_romanian(self):
        i18n.set_language("ro")
        self.assertIn("ca root", aur_warning(True, SourceOption("flatpak", True)))
        for text in ("I trust this package", "Install the Flatpak instead",
                     "Install the official package instead", "Install from the AUR?",
                     "Official", "Official (Pacman)"):
            self.assertIn(text, i18n.RO)


class TestDetailAlwaysAsks(unittest.TestCase):
    def test_no_seen_once_shortcut(self):
        src = (ROOT / "glue_apps" / "detail.py").read_text()
        self.assertNotIn("aur_warning_seen", src)
        self.assertIn('if option.kind == "aur" and action == "install":', src)
        self.assertIn("ResponseAppearance.DESTRUCTIVE", src)


if __name__ == "__main__":
    unittest.main()
