"""Manages codex exec-server child processes."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class HarnessProcess:
    session_id: str
    environment_id: str
    process: subprocess.Popen


class HarnessManager:
    def __init__(self) -> None:
        self._processes: dict[str, HarnessProcess] = {}  # keyed by session_id

    def start(self, session_id: str, remote_url: str, environment_id: str) -> HarnessProcess:
        if session_id in self._processes:
            raise RuntimeError(f"Harness already running for session {session_id!r}.")

        proc = subprocess.Popen(
            [
                "codex",
                "exec-server",
                "--remote", remote_url,
                "--environment-id", environment_id,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        harness = HarnessProcess(
            session_id=session_id,
            environment_id=environment_id,
            process=proc,
        )
        self._processes[session_id] = harness
        return harness

    def stop(self, session_id: str) -> None:
        harness = self._processes.pop(session_id, None)
        if harness is None:
            return
        harness.process.terminate()
        try:
            harness.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            harness.process.kill()

    def stop_all(self) -> None:
        for session_id in list(self._processes):
            self.stop(session_id)

    def list_active(self) -> list[HarnessProcess]:
        # Filter out any processes that have already exited
        dead = [sid for sid, h in self._processes.items() if h.process.poll() is not None]
        for sid in dead:
            self._processes.pop(sid)
        return list(self._processes.values())
