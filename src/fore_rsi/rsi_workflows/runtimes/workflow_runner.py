# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Workflow runner lifecycle: startup, execution, cancellation, and cleanup."""

import asyncio
import json
from pathlib import Path
import tempfile

import psutil

from fore_rsi.config import WorkflowConfig
from fore_rsi.rsi_workflows.base_workflow import BaseWorkflow
from fore_rsi.rsi_workflows.runtimes.run_state import WorkflowState


class WorkflowRunner:
    """Manage the execution lifecycle of one workflow."""

    def __init__(
        self, workflow: BaseWorkflow, session_name: str | None, cache_dir: Path
    ) -> None:
        """Bind the workflow, session name, and resolved cache directory without starting execution."""
        self.workflow = workflow
        self.session_name = session_name
        self._sessions_dir = cache_dir / WorkflowConfig.SESSIONS_DIR_NAME

    async def run(self) -> None:
        """Record execution state and its final outcome after workflow cleanup, preserving exceptions."""
        # Keep one process identity across all state updates for this invocation.
        process = psutil.Process()
        self._write_session_record(WorkflowState.RUNNING, process)
        try:
            await self.workflow.run()
        except asyncio.CancelledError:
            self._write_session_record(WorkflowState.STOPPED, process)
            raise
        except BaseException:
            self._write_session_record(WorkflowState.FAILED, process)
            raise
        else:
            self._write_session_record(WorkflowState.COMPLETED, process)

    @staticmethod
    def list_workflow_sessions(cache_dir: Path) -> list[dict[str, str]]:
        """Return workflow identities and observed states, without modifying their saved records."""
        try:
            session_dirs = sorted((cache_dir / WorkflowConfig.SESSIONS_DIR_NAME).iterdir())
        except FileNotFoundError:
            return []

        sessions = []
        for session_dir in session_dirs:
            if not session_dir.is_dir():
                continue
            try:
                content = (session_dir / WorkflowConfig.SESSION_RECORD_NAME).read_text(encoding="utf-8")
            except FileNotFoundError:
                continue
            record = json.loads(content)
            session = {
                "session_name": record["session_name"],
                "workflow_name": record["workflow_name"],
            }
            if "state" in record:
                session["state"] = WorkflowRunner._observe_workflow_state(
                    WorkflowState(record["state"]),
                    record.get("pid"),
                    record.get("process_created_at"),
                ).value
            sessions.append(session)
        return sessions

    @staticmethod
    def _observe_workflow_state(
        state: WorkflowState, pid: int | None, process_created_at: float | None
    ) -> WorkflowState:
        """Check a recorded running state's local host while preserving final outcomes."""
        if state != WorkflowState.RUNNING:
            return state
        if pid is None or process_created_at is None:
            return WorkflowState.UNKNOWN
        try:
            process = psutil.Process(pid)
            if (
                process.create_time() == process_created_at
                and process.is_running()
                and process.status() not in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD)
            ):
                return WorkflowState.RUNNING
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            return WorkflowState.UNKNOWN
        return WorkflowState.INTERRUPTED

    def _write_session_record(self, state: WorkflowState, process: psutil.Process) -> None:
        """Publish the workflow identity, host process, and state as one complete session record."""
        session_name = self.session_name if self.session_name is not None else "default"
        if session_name in {"", ".", ".."} or Path(session_name).name != session_name:
            raise ValueError("Workflow session name must be a single directory name.")
        session_dir = self._sessions_dir / session_name
        session_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "session_name": session_name,
            "workflow_name": self.workflow.workflow_name,
            "state": state,
            "pid": process.pid,
            "process_created_at": process.create_time(),
        }
        # Publish only after the temporary file is closed, so readers see a
        # complete snapshot and Windows can replace the destination.
        temporary = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=session_dir, delete=False
        )
        temporary_path = Path(temporary.name)
        try:
            with temporary:
                json.dump(record, temporary, indent=2)
                temporary.write("\n")
            temporary_path.replace(session_dir / WorkflowConfig.SESSION_RECORD_NAME)
        finally:
            temporary_path.unlink(missing_ok=True)
