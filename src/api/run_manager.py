from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from application.correlation import UsageContext, reset_usage_context, set_usage_context
from application.use_cases.orchestrator import CopilotOrchestrator

log = logging.getLogger("api.runs")

# Once a run has published one of these, the stream for it is complete.
FINAL_EVENTS = {"awaiting_approval", "refused", "degraded", "failed", "rejected", "dispatched"}


@dataclass
class _Channel:
    history: list[dict[str, Any]] = field(default_factory=list)
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    finished: bool = False


class RunManager:
    """Runs workflows as background tasks so `POST /runs` can answer at once,
    fans progress events out to any number of SSE subscribers, and supports
    server-side cancellation. The orchestrator publishes into `publish`
    (its `emit` hook); events are keyed by run id.

    State lives in process memory only for live progress. The durable record
    is the hash-chained log in the database, so after a restart a client
    still gets the run's state and full trace, just not a live feed."""

    def __init__(self, orchestrator: CopilotOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator
        self._channels: dict[str, _Channel] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def bind(self, orchestrator: CopilotOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def publish(self, event: dict[str, Any]) -> None:
        channel = self._channels.setdefault(event["run_id"], _Channel())
        channel.history.append(event)
        for queue in channel.subscribers:
            queue.put_nowait(event)

    async def submit(self, symptom: str, created_by: str) -> str:
        assert self._orchestrator is not None
        run = await self._orchestrator.begin(created_by)
        self._channels[run.run_id] = _Channel()
        task = asyncio.create_task(
            self._run(run, symptom, created_by), name=f"run-{run.run_id}"
        )
        self._tasks[run.run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run.run_id, None))
        return run.run_id

    async def _run(self, run, symptom: str, created_by: str) -> None:
        assert self._orchestrator is not None
        # The task copies the request's contextvars, so the correlation id is
        # already the one from POST /runs; add who and which run, so every model
        # call the workflow makes is attributed in the accounting table.
        usage_token = set_usage_context(
            UsageContext(user_id=created_by, run_id=run.run_id, purpose="run")
        )
        try:
            await self._orchestrator.execute(run, symptom)
        except asyncio.CancelledError:
            pass  # the orchestrator already closed the run as failed/cancelled
        except Exception:  # noqa: BLE001 - already recorded as a failed step
            log.exception("run %s failed", run.run_id)
        finally:
            reset_usage_context(usage_token)
            await self.publish({"run_id": run.run_id, "state": run.state.value,
                                "event": "stream_end"})
            channel = self._channels.get(run.run_id)
            if channel:
                channel.finished = True

    def is_running(self, run_id: str) -> bool:
        return run_id in self._tasks

    def cancel(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        if task is None:
            return False
        task.cancel()
        return True

    async def events(self, run_id: str) -> AsyncIterator[dict[str, Any]] | None:
        """History first, then live events, ending at `stream_end`. Returns
        None for a run this process has no channel for."""
        channel = self._channels.get(run_id)
        if channel is None:
            return None
        return self._stream(channel)

    async def _stream(self, channel: _Channel) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue()
        backlog = list(channel.history)
        channel.subscribers.append(queue)
        try:
            for event in backlog:
                yield event
                if event["event"] == "stream_end":
                    return
            while True:
                event = await queue.get()
                yield event
                if event["event"] == "stream_end":
                    return
        finally:
            channel.subscribers.remove(queue)
