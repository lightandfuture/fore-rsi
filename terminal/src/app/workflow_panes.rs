// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: Copyright contributors to the Herdr and ForeRSI projects

//! Launch and close policies scoped to ForeRSI's workflow-owned panes.

use std::collections::BTreeSet;

use super::App;
use crate::terminal::WORK_PROGRESS_PANE_KEY;

pub(crate) const CLOSE_MESSAGE: &str = "This would close a workflow-managed pane.";

/// Resolve a saved progress invocation for this launch. Keep the module command in the
/// snapshot so the same pane can be restored from either an editable or a wheel install.
pub(crate) fn launch_argv<'a>(
    key: Option<&str>,
    argv: &'a [String],
) -> std::borrow::Cow<'a, [String]> {
    if cfg!(target_os = "macos")
        && key == Some(WORK_PROGRESS_PANE_KEY)
        && argv
            .get(1..5)
            .is_some_and(|args| args == ["-P", "-m", "fore_rsi", "workprogress"])
    {
        let app = crate::session::data_dir().join("work-progress.pyz");
        if app.is_file() {
            let mut command = argv.to_vec();
            command.splice(2..4, [app.to_string_lossy().into_owned()]);
            return command.into();
        }
    }
    argv.into()
}

pub(super) fn close_error(id: String) -> String {
    super::api::responses::encode_error(id, "workflow_pane_protected", CLOSE_MESSAGE)
}

impl App {
    /// Return canonical pane, tab and workspace IDs for menus and live close requests.
    /// Process exit and session shutdown do not use this user-action policy.
    pub(crate) fn protected_close_targets(&self) -> BTreeSet<String> {
        let mut targets = BTreeSet::new();
        for (ws_idx, ws) in self.state.workspaces.iter().enumerate() {
            for tab in &ws.tabs {
                let mut has_workflow_pane = false;
                for (pane_id, pane) in &tab.panes {
                    let key = self
                        .state
                        .terminals
                        .get(&pane.attached_terminal_id)
                        .and_then(|terminal| terminal.managed_key.as_deref());
                    if key.is_some_and(|key| {
                        key == WORK_PROGRESS_PANE_KEY || key.starts_with("fore-rsi.agent/")
                    }) {
                        has_workflow_pane = true;
                        targets.extend(self.public_pane_id(ws_idx, *pane_id));
                    }
                }
                if has_workflow_pane {
                    targets.insert(crate::workspace::public_tab_id_for_number(
                        &ws.id, tab.number,
                    ));
                    targets.insert(ws.id.clone());
                }
            }
        }

        // Closing the last tab or pane of a worktree parent can also close its children.
        if targets.is_empty() {
            return targets;
        }
        for (idx, ws) in self.state.workspaces.iter().enumerate() {
            if targets.contains(&ws.id)
                || ws
                    .worktree_space()
                    .is_none_or(|space| space.is_linked_worktree)
            {
                continue;
            }
            let closes_protected_child = self
                .state
                .workspace_close_indices(idx)
                .into_iter()
                .any(|i| targets.contains(&self.state.workspaces[i].id));
            if closes_protected_child {
                targets.insert(ws.id.clone());
                if let [tab] = ws.tabs.as_slice() {
                    targets.insert(crate::workspace::public_tab_id_for_number(
                        &ws.id, tab.number,
                    ));
                    if tab.layout.pane_count() == 1 {
                        targets.extend(self.public_pane_id(idx, tab.root_pane));
                    }
                }
            }
        }
        targets
    }
}
