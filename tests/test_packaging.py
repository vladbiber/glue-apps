import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from glue_apps.app import self_test


class TestPackaging(unittest.TestCase):
    def test_required_files(self):
        for rel in ("PKGBUILD", "Makefile", "LICENSE", "README.md", "glue-apps",
                    "helpers/pkg.sh", "helpers/update.sh", "polkit/org.glue.apps.policy",
                    "data/applications/org.glue.Apps.desktop", "data/icons/org.glue.Apps.svg",
                    "data/apps.conf", "data/themes/base.css", "data/themes/compact.css"):
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_pkgbuild_dependencies(self):
        text = (ROOT / "PKGBUILD").read_text()
        for dependency in ("python-gobject", "gtk4", "libadwaita", "polkit", "pacman-contrib"):
            self.assertIn(dependency, text)
        for optional in ("yay", "paru", "flatpak", "archlinux-appstream-data",
                         "artixlinux-appstream-data", "fuse2"):
            self.assertIn(f"'{optional}:", text)

    def test_desktop_entry_opens_appimages(self):
        text = (ROOT / "data/applications/org.glue.Apps.desktop").read_text()
        self.assertIn("Exec=glue-apps %f", text)
        self.assertIn("application/vnd.appimage", text)

    def test_polkit_paths_match_install(self):
        policy = (ROOT / "polkit/org.glue.apps.policy").read_text()
        makefile = (ROOT / "Makefile").read_text()
        self.assertIn("/usr/lib/glue-apps/pkg.sh", policy)
        self.assertIn("/usr/lib/glue-apps/update.sh", policy)
        self.assertIn("$(LIBDIR)/pkg.sh", makefile)

    def test_no_proprietary_names_in_themes(self):
        for path in (ROOT / "data" / "themes").rglob("*"):
            if path.is_file():
                text = path.read_text().casefold()
                for word in ("apple", "macos", "microsoft", "windows 11", "segoe", "sf pro"):
                    self.assertNotIn(word, text, f"{word} in {path}")

    def test_self_test(self):
        self.assertEqual(self_test(), 0)

    def test_source_files_stay_under_500_lines(self):
        for path in (ROOT / "glue_apps").glob("*.py"):
            with self.subTest(path=path.name):
                self.assertLessEqual(len(path.read_text().splitlines()), 500)


if __name__ == "__main__":
    unittest.main()
