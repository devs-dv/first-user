"""The worker's loop: claim queued runs one at a time, run them, and stop cleanly.

Kept apart from main.py (which initialises neatlogs on import) so it can be tested. It also
holds what a server needs:

  * a health line once a minute while idle, so `docker logs` shows the worker is alive and waiting;
  * a heartbeat file, touched while the process is alive, which the Docker HEALTHCHECK reads;
  * graceful shutdown on SIGTERM (what `docker stop` sends) and SIGINT: the run in progress is
    finished and saved first, then the process exits. A second signal stops immediately; the run is
    left "running" and a later stale-run sweep marks it failed.
"""

import asyncio
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

IDLE_SECONDS = 2
STALE_MINUTES = 15
STALE_SWEEP_SECONDS = 60
# A test login still in the database this long after it was queued is deleted unread.
SECRETS_MINUTES = 30
DB_ERROR_BACKOFF_SECONDS = 10
HEARTBEAT_SECONDS = 5


def _duration(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{secs:02d}s" if minutes else f"{secs}s"


class Worker:
    def __init__(self, agent_version: str, *, db, execute, brain_model: str, health_interval: float = 60,
                 health_file: str | None = None, idle_seconds: float = IDLE_SECONDS,
                 heartbeat_seconds: float = HEARTBEAT_SECONDS, clock=time.monotonic):
        self.agent_version, self.db, self.execute, self.brain_model = agent_version, db, execute, brain_model
        self.health_interval, self.health_file = health_interval, health_file
        self.idle_seconds, self.heartbeat_seconds, self.clock = idle_seconds, heartbeat_seconds, clock
        self.stop_requested = False
        self.state = "starting"  # starting | idle | running | stopping
        self.started_at = self.idle_since = clock()
        self.runs_done = self.runs_failed = self.db_errors = 0

    # ---------------------------------------------------------------- stopping
    def request_stop(self, why: str = "stop requested") -> None:
        if not self.stop_requested:
            self.stop_requested = True
            print(f"{why}: finishing the current run (if any), then exiting.", flush=True)

    def on_signal(self, signum, frame) -> None:
        """First signal: stop after the current run. Second: stop now."""
        if self.stop_requested:
            raise KeyboardInterrupt
        name = signal.Signals(signum).name if signum in signal.Signals._value2member_map_ else str(signum)
        self.request_stop(f"Received {name}")

    def install_signal_handlers(self) -> None:
        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):  # SIGBREAK is Windows' Ctrl+Break
            if hasattr(signal, name):
                signal.signal(getattr(signal, name), self.on_signal)

    async def _sleep_unless_stopping(self, seconds: float) -> None:
        deadline = self.clock() + seconds
        while not self.stop_requested and self.clock() < deadline:
            await asyncio.sleep(min(0.2, max(0.0, deadline - self.clock())))

    # ---------------------------------------------------------------- health
    def health_line(self) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        parts = [f"[health] {now}", self.state]
        if self.state == "idle":
            parts.append(f"for {_duration(self.clock() - self.idle_since)}, queue empty")
        parts.append(f"| {self.runs_done} runs since start ({self.runs_failed} failed)")
        parts.append(f"| up {_duration(self.clock() - self.started_at)}")
        parts.append(f"| agent {self.agent_version}")
        if self.db_errors:
            parts.append(f"| {self.db_errors} database errors in a row")
        return " ".join(parts)

    async def _heartbeat(self) -> None:
        """Touch the heartbeat file, and log a health line every health_interval while idle."""
        last_line = self.clock()
        while True:
            if self.health_file:
                try:
                    Path(self.health_file).touch()
                except OSError:
                    pass
            # Half a tick of tolerance, so a 60 s interval is 60 s and not 65.
            if self.state == "idle" and self.clock() - last_line >= self.health_interval - self.heartbeat_seconds / 2:
                print(self.health_line(), flush=True)
                last_line = self.clock()
            elif self.state != "idle":
                last_line = self.clock()
            await asyncio.sleep(self.heartbeat_seconds)

    # ---------------------------------------------------------------- the loop
    async def run(self) -> None:
        print(f"Worker started (agent {self.agent_version}, brain {self.brain_model}). "
              "Waiting for queued runs.", flush=True)
        heartbeat = asyncio.create_task(self._heartbeat())
        last_sweep = float("-inf")
        self.state = "idle"
        self.idle_since = self.clock()
        try:
            while not self.stop_requested:
                try:
                    if self.clock() - last_sweep >= STALE_SWEEP_SECONDS:
                        last_sweep = self.clock()
                        for stale in await self.db.fail_stale_runs(STALE_MINUTES):
                            print(f"Marked stale run {stale['id']} as failed", flush=True)
                        await self.db.delete_old_run_secrets(SECRETS_MINUTES)
                    run = await self.db.claim_run()
                    self.db_errors = 0
                except Exception as error:
                    self.db_errors += 1
                    print(f"Database error: {type(error).__name__}: {error}; "
                          f"retrying in {DB_ERROR_BACKOFF_SECONDS}s", flush=True)
                    await self._sleep_unless_stopping(DB_ERROR_BACKOFF_SECONDS)
                    continue

                if run is None:
                    if self.state != "idle":
                        self.state, self.idle_since = "idle", self.clock()
                    await self._sleep_unless_stopping(self.idle_seconds)
                    continue
                self.state = "running"
                try:
                    await self.execute(run, self.agent_version)
                    self.runs_done += 1
                except Exception as error:
                    # Saving the outcome failed; the stale-run sweep will mark the run failed later.
                    self.runs_failed += 1
                    print(f"Could not save run {run['id']}: {type(error).__name__}: {error}", flush=True)
                self.state, self.idle_since = "idle", self.clock()
        finally:
            self.state = "stopping"
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
