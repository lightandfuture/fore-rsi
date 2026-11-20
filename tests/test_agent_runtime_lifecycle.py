# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Regression tests for startup ownership and prompt settlement."""

import asyncio
import json
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fore_rsi.config import AgentConfig
from fore_rsi.rsi_workflows.agent_runtimes import base


class Runtime(base.AgentRuntime):
    harness_name = "test"

    @classmethod
    async def ensure_installed(cls) -> Path:
        return Path("/native/test")

    def build_launch_command(self, executable, arguments=(), *, system_prompt=None):
        return [str(executable), *arguments]

    def _tool_mcp_args(self):
        return []


class RuntimeLifecycleTest(IsolatedAsyncioTestCase):
    def setUp(self):
        self.host = AsyncMock()
        directory = Path(self.enterContext(TemporaryDirectory())) / "session"
        self.runtime = Runtime(
            AgentConfig(), directory, workgroup_name="group", agent_name="worker",
            tool_mcp_host=self.host,
        )
        self.ensure = self.enterContext(patch.object(base, "ensure_terminal_pane"))
        self.metadata = self.enterContext(patch.object(base, "report_terminal_metadata"))
        self.run = self.enterContext(patch.object(base, "run_terminal"))

    @staticmethod
    def agent(state="idle", sequence=10, completion=9):
        return {
            "terminal_id": "term-test", "name": "term-test", "agent": "test",
            "interactive_ready": True, "agent_status": state,
            "state_change_seq": sequence, "completion_seq": completion,
        }

    @staticmethod
    def result(**result):
        return CompletedProcess([], 0, stdout=json.dumps({"result": result}))

    def set_pane(self, *, created=False):
        self.ensure.return_value = {
            "workspace_id": "w1", "pane_id": "w1:p1", "terminal_id": "term-test",
            "created": created,
        }

    async def test_launch_failure_releases_only_the_pane_created_by_this_start(self):
        self.set_pane(created=True)

        async def terminal(args, *other, **options):
            if args[:2] == ["agent", "start"]:
                raise RuntimeError("cannot start native editor")
            self.assertEqual(args, [
                "pane", "remove", "--key", "fore-rsi.agent/group/worker",
                "--terminal-id", "term-test",
            ])
            return self.result()

        self.run.side_effect = terminal
        with self.assertRaisesRegex(RuntimeError, "cannot start"):
            await self.runtime.start("w1")
        self.assertEqual(self.run.await_count, 2)
        self.assertIsNone(self.runtime.terminal_id)
        self.host.unpublish.assert_awaited_once()

    async def test_failed_attach_preserves_existing_pane(self):
        self.set_pane()
        self.run.return_value = self.result(agent=self.agent())
        self.metadata.side_effect = RuntimeError("metadata rejected")
        with self.assertRaisesRegex(RuntimeError, "metadata rejected"):
            await self.runtime.start("w1")
        self.assertEqual(self.run.await_count, 1)
        self.assertEqual(self.run.await_args.args[0][:2], ["agent", "start"])
        self.assertIsNone(self.runtime.terminal_id)
        self.host.unpublish.assert_awaited_once()

    async def test_cancelled_claim_still_removes_created_pane(self):
        self.set_pane(created=True)
        submitting = asyncio.Event()
        release = asyncio.Event()

        async def terminal(args, *other, **options):
            if args[:2] == ["agent", "start"]:
                submitting.set()
                await release.wait()
                return self.result(agent=self.agent())
            self.assertEqual(args[:2], ["pane", "remove"])
            return self.result()

        self.run.side_effect = terminal
        start = asyncio.create_task(self.runtime.start("w1"))
        await asyncio.wait_for(submitting.wait(), timeout=2)
        start.cancel()
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await start
        self.assertEqual(self.run.await_count, 2)
        self.assertIsNone(self.runtime.terminal_id)

    async def test_old_idle_does_not_settle_a_new_prompt(self):
        self.runtime.terminal_id = "term-test"
        self.run.return_value = self.result(agent=self.agent())
        await self.runtime.send_message("--a literal prompt")
        self.run.assert_awaited_once_with(
            ["agent", "prompt", "--require-idle", "--", "term-test", "--a literal prompt"],
            "session", capture_output=True,
        )
        with patch.object(self.runtime, "_bound_agent", new=AsyncMock()) as read:
            read.return_value = self.agent()
            awaiting = asyncio.create_task(self.runtime.wait_until_idle())
            try:
                await asyncio.sleep(0)
                self.assertFalse(awaiting.done())
                read.return_value = self.agent("done", sequence=12, completion=12)
                await asyncio.wait_for(awaiting, timeout=2)
            finally:
                awaiting.cancel()

    async def test_interrupt_acknowledgement_does_not_reuse_last_idle(self):
        self.runtime.terminal_id = "term-test"
        self.run.return_value = self.result(agent=self.agent())
        await self.runtime.send_message("start")
        with patch.object(self.runtime, "_bound_agent", new=AsyncMock()) as read:
            read.return_value = self.agent()
            await self.runtime.interrupt()
            awaiting = asyncio.create_task(self.runtime.wait_until_idle())
            try:
                await asyncio.sleep(0)
                self.assertFalse(awaiting.done())
                read.return_value = self.agent("idle", sequence=12)
                await asyncio.wait_for(awaiting, timeout=2)
            finally:
                awaiting.cancel()

    async def test_overlapping_prompt_cannot_replace_pending_input(self):
        self.runtime.terminal_id = "term-test"
        self.run.return_value = self.result(agent=self.agent())
        await self.runtime.send_message("first")
        working = self.agent("working", sequence=11)
        with patch.object(self.runtime, "_bound_agent", new=AsyncMock(return_value=working)) as read:
            with self.assertRaisesRegex(RuntimeError, "previous input has not settled"):
                await self.runtime.send_message("second")
            self.run.assert_awaited_once()
            read.return_value = self.agent("done", sequence=12, completion=12)
            await self.runtime.send_message("second")
        self.assertEqual(self.run.await_count, 2)

    async def test_failed_rollback_can_be_retried_by_close(self):
        self.set_pane(created=True)
        self.run.side_effect = [RuntimeError("start failed"), RuntimeError("remove failed"), self.result()]
        with self.assertRaisesRegex(RuntimeError, "start failed") as caught:
            await self.runtime.start("w1")
        self.assertIn("Terminal rollback failed: remove failed", caught.exception.__notes__)
        await self.runtime.close()
        attempts = [call.args[0] for call in self.run.await_args_list]
        self.assertEqual(attempts[1], attempts[2])
        self.assertEqual(attempts[2][-1], "term-test")
