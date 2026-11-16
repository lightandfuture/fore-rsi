# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Agent execution quotas, scheduling priorities, and request bookkeeping."""

from asyncio import PriorityQueue
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import IntEnum
from itertools import count

from fore_rsi.rsi_workflows.base_agent import AgentState, BaseAgent


class SchedulingPriority(IntEnum):
    """Rank execution requests, with lower values taking precedence."""

    DEPENDENCY_READY = 0  # Continue work when a required result arrives.
    CONTINUATION = 1  # Resume unfinished work after yielding an execution slot.
    NEW_WORK = 2  # Begin new work, including replacement agents.


@dataclass
class AgentQuota:
    """Concurrent execution allowance for one role and model within a workflow."""

    agent_class: type[BaseAgent]
    model: str
    # None is unlimited; zero disables dispatch; positive values cap concurrent execution.
    limit: int | None


@dataclass(order=True)
class SchedulingRequest:
    """A quota-bound execution request ordered by priority and enqueue sequence."""

    priority: SchedulingPriority
    sequence: int
    agent: BaseAgent = field(compare=False)
    quota: AgentQuota = field(compare=False)


class AgentScheduler:
    """Own execution quotas and scheduling records for one workflow."""

    def __init__(self, quotas: Sequence[AgentQuota]) -> None:
        """Register declared quotas and initialize a workflow's scheduling state."""
        self.quotas: dict[tuple[type[BaseAgent], str], AgentQuota] = {}
        for quota in quotas:
            if quota.limit is not None and quota.limit < 0:
                raise ValueError("Agent quota limit must be nonnegative or None.")
            key = (quota.agent_class, quota.model)
            if key in self.quotas:
                raise ValueError(
                    f"Duplicate quota for {quota.agent_class.__name__!r} and model {quota.model!r}."
                )
            self.quotas[key] = quota

        self.waiting_queue: PriorityQueue[SchedulingRequest] = PriorityQueue()
        # Active requests include executions that are still pausing.
        self.active_requests: dict[BaseAgent, SchedulingRequest] = {}
        self._sequence = count()

    def enqueue(self, agent: BaseAgent, priority: SchedulingPriority, model: str) -> None:
        """Queue a ready agent under its declared role and model quota."""
        if agent.state is not AgentState.READY:
            raise ValueError(
                f"Cannot enqueue agent {agent.get_full_name()!r} in state {agent.state.value!r}."
            )

        quota = self.get_quota(type(agent), model)
        request = SchedulingRequest(
            priority=priority,
            sequence=next(self._sequence),
            agent=agent,
            quota=quota,
        )
        self.waiting_queue.put_nowait(request)
        agent.state = AgentState.QUEUED

    def get_quota(self, agent_class: type[BaseAgent], model: str) -> AgentQuota:
        """Return the declared quota for a role and model, raising KeyError if absent."""
        return self.quotas[(agent_class, model)]
