import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from glue_apps.config import AppsConfig, THEMES, load_layout, validate_themes
from glue_apps.system import parse_checkupdates, parse_flatpak_updates


class TestConfig(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "apps.conf"
            expected = AppsConfig("mosaic", False, True, True, "ro")
            expected.save(path)
            self.assertEqual(AppsConfig.load(path), expected)

    def test_user_overrides_system(self):
        with tempfile.TemporaryDirectory() as tmp:
            system = Path(tmp) / "system.conf"
            user = Path(tmp) / "user.conf"
            system.write_text("[apps]\nstore=0\ntheme=glue\n")
            user.write_text("[apps]\nstore=1\ntheme=vitrina\n")
            loaded = AppsConfig.load(user, system)
            self.assertTrue(loaded.store)
            self.assertEqual(loaded.theme, "showcase")  # old Romanian id migrates

    def test_all_themes_have_valid_css_and_layout(self):
        theme_root = ROOT / "data" / "themes"
        self.assertEqual(validate_themes(theme_root), [])
        self.assertEqual(set(path.name for path in theme_root.iterdir() if path.is_dir()),
                         set(THEMES))
        self.assertEqual(load_layout(theme_root, "mosaic")["nav"], "rail")
        self.assertEqual(load_layout(theme_root, "showcase")["scheme"], "light")

    def test_language_defaults_to_english(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(AppsConfig.load(Path(tmp) / "missing.conf").language, "en")

    def test_bad_layout_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "glue"
            folder.mkdir()
            (folder / "layout.json").write_text('{"nav": "floating"}')
            self.assertEqual(load_layout(Path(tmp), "glue")["nav"], "sidebar")


class TestUpdateParsers(unittest.TestCase):
    def test_checkupdates(self):
        output = "linux-cachyos 6.1 -> 6.2\nmesa 1:2.0 -> 1:2.1\nnoise\n"
        self.assertEqual(parse_checkupdates(output), [
            ("linux-cachyos", "6.1", "6.2"), ("mesa", "1:2.0", "1:2.1")])

    def test_flatpak_updates(self):
        output = "org.videolan.VLC\tVLC\norg.gimp.GIMP\tGIMP\n"
        self.assertEqual(parse_flatpak_updates(output),
                         ["org.videolan.VLC", "org.gimp.GIMP"])


class TestHelpers(unittest.TestCase):
    def _run(self, script, *args):
        env = dict(os.environ, GLUE_APPS_DRY_RUN="1")
        return subprocess.run(["sh", str(ROOT / "helpers" / script), *args], env=env,
                              capture_output=True, text=True)

    def test_pkg_helper_dry_run(self):
        done = self._run("pkg.sh", "install", "vlc")
        self.assertEqual(done.returncode, 0)
        self.assertIn("pacman install vlc", done.stdout)

    def test_pkg_helper_rejects_bad_name(self):
        done = self._run("pkg.sh", "install", "vlc;id")
        self.assertNotEqual(done.returncode, 0)

    def test_update_helper_dry_run_without_pacman(self):
        done = self._run("update.sh")
        self.assertEqual(done.returncode, 0)
        self.assertIn("pacman -Syu", done.stdout)


if __name__ == "__main__":
    unittest.main()
