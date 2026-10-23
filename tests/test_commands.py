import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from glue_apps import commands
from glue_apps.commands import Command, action_plan, gl_extension_plan, run_commands, update_plan


class TestActionPlans(unittest.TestCase):
    def test_repo_uses_polkit_helper(self):
        command = action_plan("repo", "install", "vlc")[0]
        self.assertEqual(command.argv,
                         ("pkexec", "/usr/lib/glue-apps/pkg.sh", "install", "vlc"))

    def test_flatpak_adds_flathub_before_install(self):
        with mock.patch.object(commands, "NVIDIA_VERSION", Path("/nonexistent")):
            plan = action_plan("flatpak", "install", "org.videolan.VLC")
        self.assertEqual(len(plan), 2)
        self.assertIn("--if-not-exists", plan[0].argv)
        self.assertIn("--user", plan[1].argv)

    def test_aur_runs_as_user_and_delegates_only_sudo(self):
        argv = action_plan("aur", "install", "vesktop-bin")[0].argv
        self.assertEqual(argv[0], "yay")
        self.assertIn("--aur", argv)
        self.assertEqual(argv[argv.index("--sudo") + 1], "pkexec")
        self.assertNotEqual(argv[0], "pkexec")

    def test_remove_aur_uses_validating_helper(self):
        argv = action_plan("aur", "remove", "vesktop-bin")[0].argv
        self.assertEqual(argv[:2], ("pkexec", "/usr/lib/glue-apps/pkg.sh"))

    def test_rejects_injection(self):
        for ref in ("", "vlc;id", "$(id)", "../vlc", "vlc name"):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                action_plan("repo", "install", ref)

    def test_update_covers_repo_flatpak_and_aur(self):
        plan = update_plan(lambda name: f"/usr/bin/{name}")
        self.assertEqual([command.argv[0] for command in plan],
                         ["/usr/lib/glue-apps/update-check.sh", "pkexec", "flatpak", "yay"])


class TestNvidiaGlExtension(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.version = self.dir / "version"
        self.root = self.dir / "flatpak"

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, scope="--user"):
        return gl_extension_plan(scope, self.version, self.root)

    def test_no_nvidia_no_commands(self):
        self.assertEqual(self.plan(), ())

    def test_garbage_version_is_ignored(self):
        self.version.write_text("615.78;id\n")
        self.assertEqual(self.plan(), ())

    def test_installs_gl_and_gl32_for_the_driver(self):
        self.version.write_text("615.78.08\n")
        plan = self.plan()
        self.assertEqual([c.argv for c in plan], [
            ("flatpak", "install", "-y", "--noninteractive", "--user", "flathub",
             "org.freedesktop.Platform.GL.nvidia-615-78-08//1.4"),
            ("flatpak", "install", "-y", "--noninteractive", "--user", "flathub",
             "org.freedesktop.Platform.GL32.nvidia-615-78-08//1.4"),
        ])
        self.assertTrue(all(c.optional for c in plan))

    def test_same_scope_as_the_app(self):
        self.version.write_text("615.78.08\n")
        self.assertTrue(all("--system" in c.argv and "--user" not in c.argv
                            for c in self.plan("--system")))

    def test_skips_installed_refs(self):
        self.version.write_text("615.78.08\n")
        (self.root / "runtime/org.freedesktop.Platform.GL.nvidia-615-78-08/x86_64/1.4").mkdir(
            parents=True)
        plan = self.plan()
        self.assertEqual(len(plan), 1)
        self.assertIn("org.freedesktop.Platform.GL32.nvidia-615-78-08//1.4", plan[0].argv)

    def test_flatpak_install_plan_ends_with_the_extension(self):
        self.version.write_text("615.78.08\n")
        with mock.patch.object(commands, "NVIDIA_VERSION", self.version), \
                mock.patch.dict(commands.FLATPAK_ROOTS, {"--user": self.root}):
            plan = action_plan("flatpak", "install", "org.vinegarhq.Sober")
        self.assertEqual(plan[1].argv[-1], "org.vinegarhq.Sober")
        self.assertEqual(len(plan), 4)
        self.assertTrue(plan[2].optional and plan[3].optional)
        self.assertFalse(plan[1].optional)


class TestRunCommands(unittest.TestCase):
    def test_optional_failure_is_logged_not_fatal(self):
        out = []
        code = run_commands((Command(("true",), "App"),
                             Command(("false",), "Driver", optional=True),
                             Command(("sh", "-c", "echo after"), "Next")), out.append)
        self.assertEqual(code, 0)
        self.assertIn("Driver failed (exit 1), carrying on\n", out)
        self.assertIn("after\n", out)

    def test_optional_missing_binary_is_not_fatal(self):
        code = run_commands((Command(("/nonexistent/flatpak",), "Driver", optional=True),),
                            lambda _t: None)
        self.assertEqual(code, 0)

    def test_required_failure_stops_the_plan(self):
        out = []
        code = run_commands((Command(("false",), "App"),
                             Command(("sh", "-c", "echo after"), "Driver", optional=True)),
                            out.append)
        self.assertEqual(code, 1)
        self.assertNotIn("after\n", out)


if __name__ == "__main__":
    unittest.main()
