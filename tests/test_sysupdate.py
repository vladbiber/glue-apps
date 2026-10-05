"""sysupdate: the system update works around single broken packages."""

import tempfile
import unittest
from pathlib import Path

from glue_apps import sysupdate
from glue_apps.sysupdate import blockers, summary, update_system


class FakeRunner:
    """Answers commands from a list of (prefix, code, text); records calls."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, argv, output):
        self.calls.append(argv)
        for prefix, code, text in self.answers:
            if argv[:len(prefix)] == prefix:
                if isinstance(code, list):
                    code, text = code.pop(0), text.pop(0)
                return code, text
        return 0, ""


DEP_ERROR = ("error: failed to prepare transaction (could not satisfy dependencies)\n"
             ":: installing libfoo (2.0-1) breaks dependency 'libfoo=1.0' required by bar-git\n")
CONFLICT = ":: geocode-glib-3.26.4-6 and geocode-glib-common-3.26.4-5 are in conflict\n"
FILES = "error: failed to commit transaction (conflicting files)\nbaz: /usr/bin/baz exists in filesystem\n"


class TestBlockers(unittest.TestCase):
    def test_names_only_pending_upgrades(self):
        self.assertEqual(blockers(DEP_ERROR, ["libfoo", "zsh"]), ["libfoo"])
        self.assertEqual(blockers(CONFLICT, ["geocode-glib"]), ["geocode-glib"])
        self.assertEqual(blockers(FILES, ["baz"]), ["baz"])
        self.assertEqual(blockers(DEP_ERROR, []), [])


class TestUpdateSystem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lock = Path(self.tmp.name) / "db.lck"

    def tearDown(self):
        self.tmp.cleanup()

    def test_retries_without_the_broken_package(self):
        runner = FakeRunner([
            (["pacman", "-Qq"], 0, "artix-keyring\n"),
            (["pacman", "-Qu"], 0, "libfoo 1.0-1 -> 2.0-1\nzsh 5.9-1 -> 5.9-2\n"),
            (["pkexec", "pacman", "-Su"], [1, 0], [DEP_ERROR, "ok"]),
        ])
        result = update_system(lambda _l: None, runner, self.lock, lambda: False)
        self.assertTrue(result.ok)
        self.assertEqual(result.skipped, ["libfoo"])
        last = runner.calls[-1]
        self.assertIn("--ignore", last)
        self.assertEqual(last[last.index("--ignore") + 1], "libfoo")
        self.assertIn("--ask=20", last)
        self.assertIn("libfoo", summary(result))

    def test_one_password_action_for_every_root_step(self):
        runner = FakeRunner([(["pacman", "-Qq"], 0, "artix-keyring\n")])
        update_system(lambda _l: None, runner, self.lock, lambda: False)
        root = [c for c in runner.calls if c[0] == "pkexec"]
        self.assertTrue(root)
        self.assertTrue(all(c[1] == "pacman" for c in root))

    def test_stale_lock_is_cleared_only_when_pacman_is_idle(self):
        self.lock.write_text("")
        runner = FakeRunner([])
        update_system(lambda _l: None, runner, self.lock, lambda: False)
        self.assertIn(["pkexec", sysupdate.UNLOCK], runner.calls)
        runner = FakeRunner([])
        update_system(lambda _l: None, runner, self.lock, lambda: True)
        self.assertNotIn(["pkexec", sysupdate.UNLOCK], runner.calls)

    def test_network_failure_is_reported_plainly(self):
        runner = FakeRunner([(["pkexec", "pacman"], 1,
                              "error: failed retrieving file 'x' from mirror\n")])
        result = update_system(lambda _l: None, runner, self.lock, lambda: False)
        self.assertFalse(result.ok)
        self.assertIn("internet", result.problems[0])

    def test_driver_check_stops_before_root(self):
        runner = FakeRunner([([sysupdate.CHECK], 3, "linux-cachyos-headers is not installed")])
        result = update_system(lambda _l: None, runner, self.lock, lambda: False)
        self.assertFalse(result.ok)
        self.assertFalse([c for c in runner.calls if c[0] == "pkexec"])


if __name__ == "__main__":
    unittest.main()
