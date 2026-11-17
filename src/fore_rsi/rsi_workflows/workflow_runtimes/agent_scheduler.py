# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Agent execution quotas, scheduling priorities, and request bookkeeping."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import IntEnum
from heapq import heapify, heappop, heappush
from itertools import count
from typing import Literal

from fore_rsi.rsi_workflows.base_agent import AgentState, BaseAgent


type QuotaLimit = int | Literal["unlimited"]


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
    # "unlimited" removes the cap; zero disables dispatch; positive integers set the cap.
    limit: QuotaLimit


@dataclass(order=True)
class SchedulingRequest:
    """A quota-bound execution request ordered by priority and enqueue sequence."""

    priority: SchedulingPriority
    sequence: int
    agent: BaseAgent = field(compare=False)
    quota: AgentQuota = field(compare=False)


class AgentScheduler:
    """Own execution quotas and scheduling records for one workflow."""

    def __init__(self, agent_roles: Sequence[type[BaseAgent]]) -> None:
        """Bind available agent roles and initialize empty quotas and scheduling state."""
        self.agent_roles = tuple(agent_roles)
        self.quotas: dict[tuple[type[BaseAgent], str], AgentQuota] = {}
        self.priority_queue: list[SchedulingRequest] = []
        # Granted requests retain their slots through startup and pausing.
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
        heappush(self.priority_queue, request)
        agent.state = AgentState.QUEUED

    def set_queued_priority(self, agent: BaseAgent, priority: SchedulingPriority) -> bool:
        """Update a pending request's priority without changing its enqueue sequence.

        Return False if the agent has no queued request.
        """
        for request in self.priority_queue:
            if request.agent is agent:
                request.priority = priority
                heapify(self.priority_queue)
                return True
        return False

    def cancel_queued(self, agent: BaseAgent) -> bool:
        """Withdraw an agent's pending request, returning whether one was removed.

        A queued agent returns to READY; other lifecycle states are preserved.
        """
        for index, request in enumerate(self.priority_queue):
            if request.agent is not agent:
                continue

            del self.priority_queue[index]
            heapify(self.priority_queue)
            if agent.state is AgentState.QUEUED:
                agent.state = AgentState.READY
            return True
        return False

    def acquire_next(self) -> SchedulingRequest | None:
        """Reserve the highest-priority eligible request, or return None.

        The caller starts execution and releases the slot after native execution settles.
        """
        deferred: list[SchedulingRequest] = []
        try:
            while self.priority_queue:
                request = heappop(self.priority_queue)
                deferred.append(request)
                if request.agent.state is not AgentState.QUEUED:
                    continue
                if self.has_capacity(request.quota):
                    self.active_requests[request.agent] = request
                    deferred.pop()
                    return request
            return None
        finally:
            # Restore blocked requests with their original priority and enqueue sequence.
            for request in deferred:
                heappush(self.priority_queue, request)

    def find_preemption_candidate(
        self, request: SchedulingRequest
    ) -> SchedulingRequest | None:
        """Find a lower-priority running candidate for a waiting request, or None.

        Prefer the lowest priority, then the most recently enqueued request.
        """
        if request.agent.state is not AgentState.QUEUED:
            return None
        if not any(queued is request for queued in self.priority_queue):
            return None
        if request.quota.limit == 0 or self.has_capacity(request.quota):
            return None

        candidates = (
            active
            for active in self.active_requests.values()
            if active.quota is request.quota
            and active.agent.state is AgentState.RUNNING
            and active.priority > request.priority
        )
        return max(
            candidates,
            key=lambda active: (active.priority, active.sequence),
            default=None,
        )

    async def preempt(self, request: SchedulingRequest) -> bool:
        """Stop and requeue a running request outside native tool callbacks.

        Return False if the request is no longer active and running. While PAUSING,
        this operation owns release and requeue; failure before confirmed native
        idle leaves the slot held.
        """
        agent = request.agent
        if (
            self.active_requests.get(agent) is not request
            or agent.state is not AgentState.RUNNING
        ):
            return False

        agent.state = AgentState.PAUSING
        await agent.agent_runtime.interrupt()
        await agent.agent_runtime.wait_until_idle()
        self.release(request)
        agent.state = AgentState.READY
        self.enqueue(agent, SchedulingPriority.CONTINUATION, model=request.quota.model)
        return True

    async def finish(self, request: SchedulingRequest) -> bool:
        """Wait for native idle and finish a running request outside tool callbacks.

        Return True after releasing its slot and marking the agent SLEEPING.
        Return False if the request is stale or another lifecycle operation owns it.
        """
        agent = request.agent
        if (
            self.active_requests.get(agent) is not request
            or agent.state is not AgentState.RUNNING
        ):
            return False

        await agent.agent_runtime.wait_until_idle()
        # Preemption or a newer execution may have taken ownership while awaiting idle.
        if (
            self.active_requests.get(agent) is not request
            or agent.state is not AgentState.RUNNING
        ):
            return False

        self.release(request)
        agent.state = AgentState.SLEEPING
        return True

    def release(self, request: SchedulingRequest) -> None:
        """Release this request's slot after the caller confirms native execution has settled."""
        if self.active_requests.get(request.agent) is not request:
            raise ValueError(
                f"Execution request for agent {request.agent.get_full_name()!r} is not active."
            )
        del self.active_requests[request.agent]

    def set_quota(self, role_name: str, model: str, limit: QuotaLimit) -> AgentQuota:
        """Set a declared role's model quota and return its shared entry."""
        if limit != "unlimited" and (type(limit) is not int or limit < 0):
            raise ValueError('Agent quota limit must be a nonnegative integer or "unlimited".')

        for agent_class in self.agent_roles:
            if agent_class.role_name != role_name:
                continue

            key = (agent_class, model)
            current = self.quotas.get(key)
            if current is None:
                current = AgentQuota(agent_class=agent_class, model=model, limit=limit)
                self.quotas[key] = current
            else:
                # Queued and active requests retain this quota object for accounting.
                current.limit = limit
            return current
        raise ValueError(f"Unknown agent role {role_name!r}.")

    def get_quota(self, agent_class: type[BaseAgent], model: str) -> AgentQuota:
        """Return the declared quota for a role and model, raising KeyError if absent."""
        return self.quotas[(agent_class, model)]

    def has_capacity(self, quota: AgentQuota) -> bool:
        """Return whether a registered quota permits another active execution."""
        if quota.limit == "unlimited":
            return True

        active_count = sum(
            request.quota is quota for request in self.active_requests.values()
        )
        return active_count < quota.limit
