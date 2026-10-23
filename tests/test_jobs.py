import re
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from glue_apps import i18n
from glue_apps.commands import Command
from glue_apps.jobs import DONE, FAILED, QUEUED, RUNNING, JobQueue


class Ui:
    """Collects posted callbacks; run() drains them like the GTK main loop."""

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def post(self, fn):
        with self.lock:
            self.calls.append(fn)

    def run(self):
        while True:
            with self.lock:
                if not self.calls:
                    return
                fn = self.calls.pop(0)
            fn()


def queue(runner):
    ui = Ui()
    return JobQueue(ui.post, runner), ui


def finish(q, ui):
    q.pool.shutdown(wait=True)
    ui.run()


class TestJobQueue(unittest.TestCase):
    def test_jobs_run_one_at_a_time_in_order(self):
        order, inside = [], []

        def runner(commands, out):
            inside.append(1)
            self.assertEqual(len(inside), 1)
            order.append(commands[0].label)
            inside.pop()
            return 0
        q, ui = queue(runner)
        for name in ("a", "b", "c"):
            q.submit("repo", name, name, "install", (Command(("true",), name),))
        finish(q, ui)
        self.assertEqual(order, ["a", "b", "c"])

    def test_same_app_twice_is_one_job(self):
        gate = threading.Event()
        q, ui = queue(lambda c, out: gate.wait(5) and 0)
        first = q.submit("flatpak", "org.x.X", "X", "install", ())
        second = q.submit("flatpak", "org.x.X", "X", "install", ())
        self.assertIs(first, second)
        gate.set()
        finish(q, ui)
        self.assertEqual(first.state, DONE)

    def test_a_new_page_finds_the_running_job_and_its_output(self):
        gate = threading.Event()

        def runner(commands, out):
            out("downloading 1/3\n")
            gate.wait(5)
            return 0
        q, ui = queue(runner)
        q.submit("repo", "gimp", "GIMP", "install", ())
        while not (q.find("repo", "gimp") and q.find("repo", "gimp").log):
            ui.run()
        job = q.find("repo", "gimp")
        self.assertEqual(job.state, RUNNING)
        self.assertEqual(job.last_line(), "downloading 1/3")
        gate.set()
        finish(q, ui)
        self.assertIsNone(q.find("repo", "gimp"))
        self.assertIs(q.latest("repo", "gimp"), job)

    def test_failure_and_crash_both_finish(self):
        def runner(commands, out):
            if commands and commands[0].label == "crash":
                raise RuntimeError("boom")
            return 3
        q, ui = queue(runner)
        bad = q.submit("aur", "x", "X", "install", ())
        crash = q.submit("aur", "y", "Y", "install", (Command(("x",), "crash"),))
        finish(q, ui)
        self.assertEqual((bad.state, bad.code), (FAILED, 3))
        self.assertEqual(crash.state, FAILED)
        self.assertIn("boom", "".join(crash.log))

    def test_window_hears_every_state_before_the_page(self):
        heard = []
        q, ui = queue(lambda c, out: 0)
        q.listeners.append(lambda job: heard.append(("window", job.state)))
        job = q.submit("repo", "vlc", "VLC", "install", ())
        job.listeners.append(lambda j: heard.append(("page", j.state)))
        finish(q, ui)
        self.assertEqual(heard[0], ("window", QUEUED))
        self.assertEqual(heard[-2:], [("window", DONE), ("page", DONE)])

    def test_custom_run_keeps_its_result(self):
        q, ui = queue(lambda c, out: 1)
        job = q.submit("system", "update", "System update", "update",
                       run=lambda out: (0, "summary"))
        finish(q, ui)
        self.assertEqual((job.state, job.result), (DONE, "summary"))


class TestJobStrings(unittest.TestCase):
    def test_new_strings_are_translated(self):
        for path in ("jobs.py", "detail.py", "ui.py", "store_pages.py"):
            text = (ROOT / "glue_apps" / path).read_text()
            for found in re.findall(r'_\("([^"]+)"', text):
                if "{name}" in found or found.endswith("…") or found in (
                        "Keep open", "Close", "System update", "The update is done",
                        "The update did not finish"):
                    with self.subTest(found):
                        self.assertIn(found, i18n.RO)


if __name__ == "__main__":
    unittest.main()
