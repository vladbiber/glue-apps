import os
import struct
import tempfile
import unittest
from pathlib import Path

from glue_apps import windows


def lnk(target: str) -> bytes:
    """Minimal Shell Link with only LinkInfo/LocalBasePath (ANSI)."""
    header = b"L\0\0\0" + b"\0" * 16 + struct.pack("<I", 2) + b"\0" * (0x4C - 24)
    base = target.encode("cp1252") + b"\0"
    info = struct.pack("<IIIIIII", 28 + len(base), 28, 1, 0, 28, 0, 0) + base
    return header + info


class WindowsTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_lnk_target(self):
        self.assertEqual(windows.lnk_target(lnk("C:\\Program Files\\Foo\\foo.exe")),
                         "C:\\Program Files\\Foo\\foo.exe")
        self.assertIsNone(windows.lnk_target(b"nope"))

    def test_install_finds_shortcut_and_new_exe(self):
        pfx = windows.prefix("app", self.home)
        before = windows._scan(pfx)
        app = pfx / "drive_c/Program Files/Foo"
        app.mkdir(parents=True)
        (app / "Foo.exe").write_bytes(b"MZ" + b"\0" * 100)
        (app / "unins000.exe").write_bytes(b"MZ")
        menu = pfx / "drive_c/users/me/AppData/Roaming/Microsoft/Windows/Start Menu"
        menu.mkdir(parents=True)
        (menu / "Foo Studio.lnk").write_bytes(lnk("c:\\program files\\foo\\foo.exe"))
        found = windows.candidates(pfx, before)
        self.assertEqual(found, [("Foo Studio", app / "Foo.exe")])

    def test_add_list_remove(self):
        exe = windows.keep_portable("game", self._exe("cool_game.exe"), self.home)
        app = windows.add("Cool game", "game", exe, self.home)
        text = app.desktop.read_text()
        self.assertIn("umu-run", text)
        self.assertIn("Categories=Game;", text)
        [listed] = windows.installed(self.home)
        self.assertEqual((listed.name, listed.mode, listed.exe), ("Cool game", "game", exe))
        windows.remove(listed, files=True, home=self.home)
        self.assertEqual(windows.installed(self.home), [])
        self.assertFalse(exe.exists())
        self.assertTrue(windows.prefix("game", self.home).is_dir())

    def test_exec_quoting(self):
        exe = self.home / "My Apps" / "a.exe"
        line = next(l for l in windows.desktop_entry("A", "app", exe, "x", self.home).splitlines()
                    if l.startswith("Exec="))
        self.assertIn('wine "' + str(exe) + '"', line)
        self.assertIn("WINEDLLOVERRIDES=winemenubuilder.exe=d", line)

    def test_icon_from_real_exe(self):
        exes = [p for p in Path("/usr/lib").glob("python3*/site-packages/distlib/w64.exe")]
        if not exes:
            self.skipTest("no sample exe")
        png = windows.exe_icon(exes[0].read_bytes())
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_is_exe(self):
        self.assertTrue(windows.is_exe(self._exe("a.exe")))
        other = self.home / "x.AppImage"
        other.write_bytes(b"\x7fELF")
        self.assertFalse(windows.is_exe(other))

    def _exe(self, name):
        path = self.home / "Downloads" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"MZ" + os.urandom(64))
        return path


if __name__ == "__main__":
    unittest.main()
