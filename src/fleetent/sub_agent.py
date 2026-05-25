"""Sub-agent executor: run multiple tasks in parallel via asyncio.gather."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from fleetent import agent_loop

logger = logging.getLogger(__name__)


@dataclass
class SubAgentResult:
    name: str
    result: Any
    error: str | None
    parent_session_id: str


class SubAgentExecutor:
    async def run(
        self,
        tasks: list[dict[str, str]],
        parent_user_id: str,
        parent_agent_id: int | None,
        parent_session_id: str,
    ) -> list[SubAgentResult]:
        coros = [
            self._run_one(task, parent_user_id, parent_agent_id, parent_session_id)
            for task in tasks
        ]
        return list(await asyncio.gather(*coros))

    async def _run_one(
        self,
        task: dict[str, str],
        parent_user_id: str,
        parent_agent_id: int | None,
        parent_session_id: str,
    ) -> SubAgentResult:
        name = task["name"]
        prompt = task["prompt"]
        try:
            result = await agent_loop.run(
                messages=[{"role": "user", "content": prompt}],
                user_id=parent_user_id,
                is_sub_agent=True,
            )
            return SubAgentResult(
                name=name, result=result, error=None, parent_session_id=parent_session_id
            )
        except Exception as exc:
            logger.warning("sub_agent_task_failed task=%s error=%s", name, exc)
            return SubAgentResult(
                name=name, result=None, error=str(exc), parent_session_id=parent_session_id
            )
