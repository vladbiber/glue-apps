import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from glue_apps import appimage, aur
from glue_apps.commands import action_plan, update_plan


def which_only(*names):
    return lambda name: f"/usr/bin/{name}" if name in names else None


class TestAurHelpers(unittest.TestCase):
    def test_prefers_yay_then_paru(self):
        self.assertEqual(aur.helper(which_only("yay", "paru")), "yay")
        self.assertEqual(aur.helper(which_only("paru")), "paru")
        self.assertIsNone(aur.helper(which_only()))
        self.assertEqual(aur.label(which_only("paru")), "AUR (paru)")

    def test_paru_and_yay_never_prompt(self):
        paru = aur.install_argv("paru", "vesktop")
        self.assertEqual(paru[:2], ("paru", "-S"))
        self.assertIn("--skipreview", paru)
        yay = aur.upgrade_argv("yay")
        self.assertIn("--answerdiff", yay)
        self.assertEqual(yay[yay.index("--sudo") + 1], "pkexec")

    def test_update_plan_skips_missing_tools(self):
        plan = update_plan(which_only())
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0].argv, ("/usr/lib/glue-apps/update-check.sh",))
        self.assertEqual(plan[1].argv[:3], ("pkexec", "pacman", "-Syu"))
        full = update_plan(which_only("flatpak", "paru"))
        self.assertEqual([c.argv[0] for c in full],
                         ["/usr/lib/glue-apps/update-check.sh", "pkexec", "flatpak", "paru"])

    def test_install_plan_never_runs_aur_as_root(self):
        argv = action_plan("aur", "install", "vesktop")[0].argv
        self.assertNotEqual(argv[0], "pkexec")


class TestAppImage(unittest.TestCase):
    def test_magic_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "a.AppImage"
            good.write_bytes(b"\x7fELF\x02\x01\x01\x00AI\x02rest")
            bad = Path(tmp) / "b.AppImage"
            bad.write_bytes(b"#!/bin/sh\n")
            self.assertTrue(appimage.is_appimage(good))
            self.assertFalse(appimage.is_appimage(bad))

    def test_desktop_entry_keeps_field_codes(self):
        entry = appimage.desktop_entry({"Exec": "tool %U", "Categories": "Utility;"},
                                       "Tool", Path("/home/u/Applications/Tool.AppImage"),
                                       "/icons/tool.png", extract_and_run=True)
        self.assertIn('Exec=env APPIMAGE_EXTRACT_AND_RUN=1 "/home/u/Applications/Tool.AppImage" %U',
                      entry)
        self.assertIn("Categories=Utility;", entry)

    def test_install_list_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            downloads = Path(tmp) / "dl"
            downloads.mkdir()
            source = downloads / "Tool-1.0-x86_64.AppImage"
            script = ("#!/bin/sh\nmkdir -p squashfs-root\n"
                      "printf '[Desktop Entry]\\nName=Tool\\nExec=tool %%U\\nIcon=tool\\n' "
                      "> squashfs-root/tool.desktop\nprintf png > squashfs-root/tool.png\n")
            source.write_text(script)
            source.chmod(source.stat().st_mode | stat.S_IXUSR)
            original = appimage.is_appimage
            appimage.is_appimage = lambda _path: True
            try:
                app = appimage.install(source, home, fuse2=())
            finally:
                appimage.is_appimage = original
            self.assertEqual(app.name, "Tool")
            self.assertTrue(os.access(app.path, os.X_OK))
            self.assertEqual(app.path.parent, home / "Applications")
            text = app.desktop.read_text()
            self.assertIn("APPIMAGE_EXTRACT_AND_RUN=1", text)
            self.assertTrue(Path(app.icon).is_file())
            listed = appimage.installed(home)
            self.assertEqual([item.name for item in listed], ["Tool"])
            appimage.remove(listed[0])
            self.assertFalse(app.path.exists() or app.desktop.exists())
            self.assertEqual(appimage.installed(home), [])


if __name__ == "__main__":
    unittest.main()
