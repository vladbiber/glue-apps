"""Install/remove jobs owned by the window, run one at a time.

Pages come and go; a job does not. Any page can ask whether an app is being
installed, replay its output so far and follow it to the end. One worker
thread runs them in order, so pacman, flatpak and the AUR helper never fight
over the package lock.
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from typing import Callable

from .commands import Command, run_commands

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"


@dataclass(eq=False)
class Job:
    kind: str
    ref: str
    name: str
    action: str
    commands: tuple[Command, ...]
    # instead of commands: run(on_output) -> (code, result), e.g. the system update
    run: Callable | None = None
    result: object = None
    state: str = QUEUED
    code: int | None = None
    log: list[str] = field(default_factory=list)
    listeners: list[Callable[["Job"], None]] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind, self.ref)

    @property
    def active(self) -> bool:
        return self.state in (QUEUED, RUNNING)

    def last_line(self) -> str:
        for line in reversed(self.log):
            if line.strip():
                return line.strip()
        return ""


class JobQueue:
    """post(fn) hands a callback to the UI thread (GLib.idle_add in the app)."""

    def __init__(self, post: Callable[[Callable[[], None]], None],
                 runner: Callable = run_commands) -> None:
        self.post = post
        self.runner = runner
        self.jobs: list[Job] = []
        self.listeners: list[Callable[[Job], None]] = []
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def find(self, kind: str, ref: str) -> Job | None:
        return next((j for j in reversed(self.jobs) if j.key == (kind, ref) and j.active), None)

    def active(self) -> list[Job]:
        return [j for j in self.jobs if j.active]

    def running(self) -> Job | None:
        return next((j for j in self.jobs if j.state == RUNNING), None)

    def submit(self, kind: str, ref: str, name: str, action: str,
               commands: tuple[Command, ...] = (), run: Callable | None = None) -> Job:
        if job := self.find(kind, ref):
            return job
        job = Job(kind, ref, name, action, commands, run)
        self.jobs.append(job)
        self._changed(job)
        self.pool.submit(self._run, job)
        return job

    def _run(self, job: Job) -> None:
        self.post(lambda: self._set(job, RUNNING))
        output = lambda text: self.post(lambda: self._log(job, text))
        try:
            if job.run is not None:
                code, job.result = job.run(output)
            else:
                code = self.runner(job.commands, output)
        except Exception as exc:  # noqa: BLE001 - a crashed job must still finish
            message = f"{exc}\n"
            self.post(lambda: self._log(job, message))
            code = 1
        self.post(lambda: self._finish(job, code))

    def _log(self, job: Job, text: str) -> None:
        job.log.append(text)
        for listener in list(job.listeners):
            listener(job)

    def _set(self, job: Job, state: str) -> None:
        job.state = state
        self._changed(job)

    def _finish(self, job: Job, code: int) -> None:
        job.code = code
        self._set(job, DONE if code == 0 else FAILED)
        # finished jobs are kept only until the next change, enough for pages to see the end
        self.jobs = [j for j in self.jobs if j.active or j is job]

    def latest(self, kind: str, ref: str) -> Job | None:
        """The active job, else the one that just finished (pages show its result)."""
        return self.find(kind, ref) or next(
            (j for j in reversed(self.jobs) if j.key == (kind, ref)), None)

    def _changed(self, job: Job) -> None:
        # the window first (installed state), then the pages following the job
        for listener in list(self.listeners):
            listener(job)
        for listener in list(job.listeners):
            listener(job)
