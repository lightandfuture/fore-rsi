# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Common lifecycle and input operations for one native agent conversation."""

from abc import ABC, abstractmethod


class AgentSession(ABC):
    """Base agent session to a workflow runner.

    Implementations bind configuration and native session references during
    construction, then acquire execution resources in start(). The native
    harness remains responsible for authentication and conversation storage.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start or attach to the bound agent without waiting for its task to finish."""
        ...

    @abstractmethod
    async def send_message(self, message: str) -> None:
        """Submit text through the native session input and return after submission."""
        ...

    @abstractmethod
    async def wait_until_idle(self) -> None:
        """Wait for active execution and queued or automatic continuation to settle."""
        ...

    @abstractmethod
    async def interrupt(self) -> None:
        """Request interruption of current work while keeping the conversation available."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Stop this agent and release its execution resources, preserving native history.

        Safe before start(), after a failed start(), and after an earlier close().
        """
        ...
