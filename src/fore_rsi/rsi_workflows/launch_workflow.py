# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Discover named workflows and construct the selected workflow's runner."""

from importlib import import_module
from inspect import getmembers, isabstract, isclass
from pkgutil import walk_packages

from fore_rsi.config import Config
from fore_rsi.rsi_workflows import custom_workflows
from fore_rsi.rsi_workflows.base_workflow import BaseWorkflow
from fore_rsi.rsi_workflows.workflow_runtimes.workflow_runner import WorkflowRunner


def create_workflow_runner(config: Config) -> WorkflowRunner:
    """Return an unstarted runner for the workflow selected by the resolved application configuration."""
    all_available_workflows = _discover_workflows()
    workflow_name = config.workflow.workflow_name
    workflow_class = all_available_workflows.get(workflow_name)
    if workflow_class is None:
        available = ", ".join(sorted(all_available_workflows)) or "(none)"
        raise ValueError(f"Unknown workflow {workflow_name!r}. Available workflows: {available}.")

    return WorkflowRunner(
        workflow_class=workflow_class,
        workflow_config=config.workflow,
        session_name=config.session,
        cache_dir=config.cache_dir,
    )


def _discover_workflows() -> dict[str, type[BaseWorkflow]]:
    """Index concrete workflows in custom_workflows by their declared names for the launcher."""
    workflows: dict[str, type[BaseWorkflow]] = {}
    for module_info in walk_packages(custom_workflows.__path__, f"{custom_workflows.__name__}."):
        module = import_module(module_info.name)
        for _, workflow_class in getmembers(module, isclass):
            if (
                workflow_class.__module__ != module.__name__
                or not issubclass(workflow_class, BaseWorkflow)
                or isabstract(workflow_class)
            ):
                continue

            workflow_name = workflow_class.workflow_name
            if not isinstance(workflow_name, str) or not workflow_name:
                raise ValueError(
                    f"{module.__name__}.{workflow_class.__name__} must declare a nonempty workflow_name."
                )
            if workflow_name in workflows and workflows[workflow_name] is not workflow_class:
                raise ValueError(f"Duplicate workflow name {workflow_name!r}.")
            workflows[workflow_name] = workflow_class

    return workflows
