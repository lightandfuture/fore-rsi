// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: Copyright contributors to the Herdr and ForeRSI projects

//! Workspace, workflow-group, and pane navigation for the ForeRSI terminal.
//!
//! The workflow supplies group metadata; this client only arranges existing panes.
//! A progress view is an ordinary pane, so selecting it uses the same focus path
//! as selecting an agent. Terminal contents and process ownership stay in Herdr.

use std::collections::BTreeMap;

use super::super::agent_sidebar::ordered_agent_pane_ids;
use super::sidebar::{
    displayed_workspace_status, render_parent_group_toggle, render_workspace_rows,
    workspace_entries, workspace_rows,
};
use super::*;
use crate::protocol::{ClientShellAgent, ClientShellPane};

const GROUP_TOKEN: &str = "fore_rsi_group";
const GROUP_ORDER_TOKEN: &str = "fore_rsi_group_order";
const MEMBER_TOKEN: &str = "fore_rsi_member";
const ENTRY_TOKEN: &str = "fore_rsi_entry";
const VIEW_TOKEN: &str = "fore_rsi_view";
const STATE_TOKEN: &str = "fore_rsi_state";

/// Fixed labels owned by the ForeRSI client; pane and role names remain workflow data.
pub(crate) struct SidebarLabels {
    pub(crate) progress: &'static str,
    pub(crate) terminal: &'static str,
    pub(crate) new: &'static str,
    pub(crate) menu: &'static str,
}

/// Pane identity is available before the harness has been detected as an agent.
#[derive(Clone, Copy)]
struct Member<'a> {
    pane: &'a ClientShellPane,
    agent: Option<&'a ClientShellAgent>,
}

impl<'a> Member<'a> {
    fn token(self, key: &str) -> Option<&'a str> {
        token(&self.pane.tokens, key).or_else(|| token(&self.agent?.tokens, key))
    }
}

#[derive(Default)]
struct ForeRsiGroup<'a> {
    order: Option<u64>,
    has_entry: bool,
    members: Vec<Member<'a>>,
}

/// Rows in the unified workspace → group → pane tree.
enum NavigationRow<'a> {
    Workspace {
        entry: WorkspaceEntry,
        workspace: &'a ClientShellWorkspace,
    },
    Group {
        label: &'a str,
        depth: u16,
    },
    Member {
        member: Member<'a>,
        depth: u16,
    },
}

enum EndpointNavigationRow<'a> {
    Endpoint {
        endpoint: &'a ClientShellEndpoint,
    },
    Content {
        endpoint: &'a ClientShellEndpoint,
        row: NavigationRow<'a>,
    },
}

impl SidebarLabels {
    /// Use the process locale without adding a second global language setting.
    pub(crate) fn from_environment() -> Self {
        let chinese = ["LC_ALL", "LC_MESSAGES", "LANG"]
            .into_iter()
            .filter_map(|key| std::env::var(key).ok())
            .find(|value| !value.is_empty())
            .is_some_and(|value| value.to_ascii_lowercase().starts_with("zh"));
        if chinese {
            Self {
                progress: "工作进展",
                terminal: "终端",
                new: "新建",
                menu: "菜单",
            }
        } else {
            Self {
                progress: "Work progress",
                terminal: "Terminal",
                new: "new",
                menu: "menu",
            }
        }
    }
}

fn token<'a>(tokens: &'a [(String, String)], key: &str) -> Option<&'a str> {
    tokens
        .iter()
        .find(|(name, _)| name == key)
        .map(|(_, value)| value.as_str())
}

/// Find the progress view independently of whether a harness is detected in its pane.
pub(in crate::client::shell) fn progress_pane(
    snapshot: &ClientShellSnapshot,
) -> Option<&ClientShellPane> {
    snapshot
        .panes
        .iter()
        .find(|pane| token(&pane.tokens, VIEW_TOKEN) == Some("progress"))
        .or_else(|| {
            // Older endpoints expose tokens on detected agents only.
            let agent = snapshot
                .agents
                .iter()
                .find(|agent| token(&agent.tokens, VIEW_TOKEN) == Some("progress"))?;
            snapshot
                .panes
                .iter()
                .find(|pane| pane.pane_id == agent.pane_id)
        })
}

/// Reserve the progress row outside the scrollable workspace tree and register its real focus target.
pub(super) fn render_progress_shortcut(
    buffer: &mut Buffer,
    area: Rect,
    snapshot: &ClientShellSnapshot,
    config: &ClientShellConfig,
    state: &ShellRenderState<'_>,
    hits: &mut ShellHitMap,
) -> Rect {
    let Some(pane) = progress_pane(snapshot) else {
        return area;
    };
    if area.width <= 1 || area.height <= 1 {
        return area;
    }
    let height = if area.height >= 4 { 2 } else { 1 };
    render_sidebar_background(
        buffer,
        Rect::new(area.x, area.y, area.width, height),
        &config.palette,
    );
    let row = Rect::new(area.x, area.y, area.width - 1, 1);
    if pane.focused {
        buffer.set_style(row, Style::default().bg(config.palette.active_row_bg));
    }
    put_text(
        buffer,
        row.x,
        row.y,
        row.width,
        config.fore_rsi_labels.progress,
        Style::default()
            .fg(config.palette.text)
            .add_modifier(Modifier::BOLD),
    );
    if height == 2 {
        put_text(
            buffer,
            row.x,
            row.y + 1,
            row.width,
            &"─".repeat(row.width as usize),
            Style::default().fg(config.palette.surface_dim),
        );
    }
    if state.endpoints.len() > 1 {
        hits.endpoint_agents
            .push((row, state.active_endpoint_id.clone(), pane.pane_id.clone()));
    } else {
        hits.agents.push((row, pane.pane_id.clone()));
    }
    Rect::new(area.x, area.y + height, area.width, area.height - height)
}

/// Project each pane into its actual workspace and group once. The entry reference only
/// affects ordering; it never replaces the member's name or creates a second row.
fn navigation_rows<'a>(
    snapshot: &'a ClientShellSnapshot,
    config: &ClientShellConfig,
    collapsed_groups: &HashSet<String>,
) -> Vec<NavigationRow<'a>> {
    let agents: HashMap<_, _> = snapshot
        .agents
        .iter()
        .map(|a| (a.pane_id.as_str(), a))
        .collect();
    let ranks: HashMap<_, _> = ordered_agent_pane_ids(snapshot, config.agent_panel_sort)
        .into_iter()
        .enumerate()
        .map(|(rank, id)| (id, rank))
        .collect();
    let entries: HashSet<_> = snapshot
        .workspaces
        .iter()
        .filter_map(|w| token(&w.tokens, ENTRY_TOKEN))
        .collect();
    let mut by_workspace = HashMap::<&str, BTreeMap<Option<&str>, ForeRsiGroup>>::new();
    for pane in &snapshot.panes {
        let member = Member {
            pane,
            agent: agents.get(pane.pane_id.as_str()).copied(),
        };
        let label = member.token(GROUP_TOKEN);
        let entry = entries.contains(pane.terminal_id.as_str());
        let declared_member = label.is_some() && snapshot.agent_view_label.is_none();
        let visible = entry || declared_member || ranks.contains_key(&pane.pane_id);
        if !visible || member.token(VIEW_TOKEN) == Some("progress") {
            continue;
        }
        let group = by_workspace
            .entry(&pane.workspace_id)
            .or_default()
            .entry(label)
            .or_default();
        group.has_entry |= entry;
        if let Some(order) = member
            .token(GROUP_ORDER_TOKEN)
            .and_then(|s| s.parse::<u64>().ok())
        {
            group.order = Some(group.order.map_or(order, |current| current.min(order)));
        }
        group.members.push(member);
    }

    let mut rows = Vec::new();
    for entry in workspace_entries(snapshot, collapsed_groups) {
        let Some(workspace) = snapshot.workspaces.get(entry.index) else {
            continue;
        };
        let depth = u16::from(entry.indented) + 1;
        rows.push(NavigationRow::Workspace { entry, workspace });
        let Some(groups) = by_workspace.remove(workspace.workspace_id.as_str()) else {
            continue;
        };
        let mut groups = groups.into_iter().collect::<Vec<_>>();
        groups.sort_by_key(|(label, g)| (!g.has_entry, g.order.unwrap_or(u64::MAX), *label));
        for (label, mut group) in groups {
            if let Some(label) = label {
                rows.push(NavigationRow::Group { label, depth });
            }
            group.members.sort_by_key(|m| {
                (
                    !entries.contains(m.pane.terminal_id.as_str()),
                    ranks.get(&m.pane.pane_id).copied().unwrap_or(usize::MAX),
                )
            });
            rows.extend(
                group
                    .members
                    .into_iter()
                    .map(|member| NavigationRow::Member {
                        member,
                        depth: depth + u16::from(label.is_some()),
                    }),
            );
        }
    }
    rows
}

fn endpoint_navigation_rows<'a>(
    endpoints: &'a [ClientShellEndpoint],
    collapsed_endpoints: &HashSet<ClientEndpointId>,
    collapsed_groups: &HashSet<String>,
    remote_collapsed_groups: &HashMap<ClientEndpointId, HashSet<String>>,
    config: &ClientShellConfig,
) -> Vec<EndpointNavigationRow<'a>> {
    let empty_collapsed_groups = HashSet::new();
    let mut rows = Vec::new();
    for endpoint in endpoints {
        rows.push(EndpointNavigationRow::Endpoint { endpoint });
        if collapsed_endpoints.contains(&endpoint.endpoint_id) {
            continue;
        }
        let Some(snapshot) = endpoint.snapshot.as_deref() else {
            continue;
        };
        let endpoint_groups = if endpoint.endpoint_id.is_local() {
            collapsed_groups
        } else {
            remote_collapsed_groups
                .get(&endpoint.endpoint_id)
                .unwrap_or(&empty_collapsed_groups)
        };
        rows.extend(
            navigation_rows(snapshot, config, endpoint_groups)
                .into_iter()
                .map(|row| EndpointNavigationRow::Content { endpoint, row }),
        );
    }
    rows
}

/// Expand the owning navigation scopes and return a pane's row in the unified tree.
///
/// Focus actions use this same projection path as rendering so a pane hidden by a
/// collapsed endpoint or worktree group becomes visible before its row is revealed.
pub(crate) fn reveal_endpoint_pane(
    endpoints: &[ClientShellEndpoint],
    collapsed_endpoints: &mut HashSet<ClientEndpointId>,
    collapsed_groups: &mut HashSet<String>,
    remote_collapsed_groups: &mut HashMap<ClientEndpointId, HashSet<String>>,
    config: &ClientShellConfig,
    endpoint_id: &ClientEndpointId,
    pane_id: &str,
) -> Option<usize> {
    collapsed_endpoints.remove(endpoint_id);
    let worktree_key = endpoints
        .iter()
        .find(|endpoint| &endpoint.endpoint_id == endpoint_id)
        .and_then(|endpoint| endpoint.snapshot.as_deref())
        .and_then(|snapshot| {
            let pane = snapshot.panes.iter().find(|pane| pane.pane_id == pane_id)?;
            let workspace = snapshot
                .workspaces
                .iter()
                .find(|workspace| workspace.workspace_id == pane.workspace_id)?;
            workspace
                .worktree
                .as_ref()
                .filter(|worktree| worktree.is_linked_worktree)
                .map(|worktree| worktree.key.clone())
        });
    if let Some(worktree_key) = worktree_key {
        if endpoint_id.is_local() {
            collapsed_groups.remove(&worktree_key);
        } else {
            remote_collapsed_groups
                .entry(endpoint_id.clone())
                .or_default()
                .remove(&worktree_key);
        }
    }
    endpoint_navigation_rows(
        endpoints,
        collapsed_endpoints,
        collapsed_groups,
        remote_collapsed_groups,
        config,
    )
    .iter()
    .position(|row| {
        matches!(
            row,
            EndpointNavigationRow::Content {
                endpoint,
                row: NavigationRow::Member { member, .. },
            } if &endpoint.endpoint_id == endpoint_id && member.pane.pane_id == pane_id
        )
    })
}

struct RowRenderContext<'a> {
    endpoint_id: &'a ClientEndpointId,
    endpoint_active: bool,
    multi_endpoint: bool,
    snapshot: &'a ClientShellSnapshot,
    config: &'a ClientShellConfig,
    collapsed_groups: &'a HashSet<String>,
    navigating: bool,
    selected_workspace: bool,
    dragged_workspace: bool,
}

/// Draw one tree row and register its existing Herdr interaction target.
fn render_row(
    buffer: &mut Buffer,
    rect: Rect,
    row: &NavigationRow<'_>,
    context: &RowRenderContext<'_>,
    hits: &mut ShellHitMap,
    palette: &Palette,
) {
    match row {
        NavigationRow::Workspace { entry, workspace } => {
            let status =
                displayed_workspace_status(context.snapshot, workspace, context.collapsed_groups);
            let workspace_rows =
                workspace_rows(workspace, status, entry.indented, &context.config.spaces);
            render_workspace_rows(
                buffer,
                rect,
                status,
                context.config.status_indicators,
                entry,
                workspace_rows,
                context.endpoint_active && workspace.focused,
                context.selected_workspace,
                context.navigating,
                context.dragged_workspace,
                palette,
            );
            let group_toggle = render_parent_group_toggle(
                buffer,
                rect,
                context.snapshot,
                entry.index,
                context.collapsed_groups,
                palette,
            );
            hits.workspaces.push(WorkspaceHit {
                rect,
                endpoint_id: context.endpoint_id.clone(),
                workspace_id: workspace.workspace_id.clone(),
                indented: entry.indented,
                group_toggle,
            });
        }
        NavigationRow::Group { label, depth } => {
            let x = rect.x.saturating_add(depth.saturating_mul(2));
            put_text(
                buffer,
                x,
                rect.y,
                rect.width.saturating_sub(x.saturating_sub(rect.x)),
                label,
                Style::default()
                    .fg(palette.overlay1)
                    .add_modifier(Modifier::BOLD),
            );
        }
        NavigationRow::Member { member, depth } => {
            let Member { pane, agent } = *member;
            let x = rect.x.saturating_add(depth.saturating_mul(2));
            let content = Rect::new(
                x,
                rect.y,
                rect.width.saturating_sub(x.saturating_sub(rect.x)),
                rect.height,
            );
            let label = member
                .token(MEMBER_TOKEN)
                .or_else(|| {
                    agent.and_then(|agent| {
                        agent
                            .display_agent
                            .as_deref()
                            .or(agent.name.as_deref())
                            .or(agent.agent.as_deref())
                            .or(agent.title.as_deref())
                    })
                })
                .or(pane.label.as_deref())
                .unwrap_or(context.config.fore_rsi_labels.terminal);
            let state_style = match member.token(STATE_TOKEN) {
                Some("retired") => Style::default().fg(palette.overlay0),
                Some("working") => Style::default().fg(palette.green),
                Some("sleeping") => Style::default().fg(palette.overlay1),
                _ => Style::default().fg(palette.subtext0),
            };
            if context.endpoint_active && pane.focused {
                buffer.set_style(rect, Style::default().bg(palette.active_row_bg));
            }
            let status = agent
                .map(|agent| agent.agent_status)
                .unwrap_or(crate::api::schema::AgentStatus::Unknown);
            let status_icon = status_icon(status, context.config.status_indicators);
            let status_icon_width = display_width(status_icon);
            put_text(
                buffer,
                content.x,
                content.y,
                status_icon_width,
                status_icon,
                Style::default().fg(status_color(status, palette)),
            );
            put_text(
                buffer,
                content.x.saturating_add(status_icon_width + 1),
                content.y,
                content
                    .width
                    .saturating_sub(status_icon_width.saturating_add(1)),
                label,
                state_style,
            );
            if context.multi_endpoint {
                hits.endpoint_agents.push((
                    rect,
                    context.endpoint_id.clone(),
                    pane.pane_id.clone(),
                ));
            } else {
                hits.agents.push((rect, pane.pane_id.clone()));
            }
        }
    }
}

/// Render the unified tree and keep Herdr's existing pane and workspace hit paths.
pub(crate) fn render_sidebar(
    buffer: &mut Buffer,
    area: Rect,
    snapshot: &ClientShellSnapshot,
    config: &ClientShellConfig,
    state: &mut ShellRenderState<'_>,
    hits: &mut ShellHitMap,
) {
    render_sidebar_background(buffer, area, &config.palette);
    if area.height == 0 || area.width <= 1 {
        return;
    }
    let palette = &config.palette;
    hits.sidebar_divider = Rect::new(area.right() - 1, area.y, 1, area.height);
    hits.sidebar_section_divider = Rect::default();
    let body = Rect::new(area.x, area.y, area.width - 1, area.height - 1);
    hits.workspace_body = body;
    hits.agent_body = Rect::default();
    hits.workspace_scrollbar = Rect::default();
    hits.agent_scrollbar = Rect::default();
    hits.workspace_scroll_metrics = None;
    hits.agent_scroll_metrics = None;
    hits.workspace_max_scroll = 0;

    let rows = navigation_rows(snapshot, config, state.collapsed_groups);
    let heights = rows
        .iter()
        .map(|row| match row {
            NavigationRow::Workspace { entry, workspace } => workspace_rows(
                workspace,
                displayed_workspace_status(snapshot, workspace, state.collapsed_groups),
                entry.indented,
                &config.spaces,
            )
            .len()
            .max(1),
            NavigationRow::Group { .. } | NavigationRow::Member { .. } => 1,
        })
        .map(|height| height.min(u16::MAX as usize) as u16)
        .collect::<Vec<_>>();
    let gaps = rows
        .iter()
        .enumerate()
        .map(|(index, _)| {
            u16::from(matches!(
                rows.get(index + 1),
                Some(NavigationRow::Workspace { .. } | NavigationRow::Group { .. })
            ))
        })
        .collect::<Vec<_>>();
    let can_reveal = body.height > 1;
    let reveal_focused = can_reveal && std::mem::take(state.reveal_focused_workspace);
    let reveal_navigation = can_reveal && std::mem::take(state.reveal_navigation_workspace);
    if reveal_focused || reveal_navigation {
        let target = rows.iter().position(|row| match row {
            NavigationRow::Workspace { workspace, .. } => {
                if reveal_navigation {
                    state.selected_workspace_id.is_some_and(|target| {
                        target.matches(state.active_endpoint_id, &workspace.workspace_id)
                    })
                } else {
                    workspace.focused
                }
            }
            NavigationRow::Member { member, .. } => reveal_focused && member.pane.focused,
            NavigationRow::Group { .. } => false,
        });
        if let Some(target) = target {
            *state.workspace_scroll = super::scroll::list_scroll_start_to_reveal(
                &heights,
                &gaps,
                body.height,
                *state.workspace_scroll,
                target,
            );
        }
    }
    let metrics =
        super::scroll::list_scroll_metrics(&heights, &gaps, body.height, *state.workspace_scroll);
    *state.workspace_scroll = metrics
        .max_offset_from_bottom
        .saturating_sub(metrics.offset_from_bottom);
    *state.agent_scroll = 0;
    hits.workspace_scroll_metrics = Some(metrics);
    hits.workspace_max_scroll = metrics.max_offset_from_bottom;
    let show_scrollbar = metrics.max_offset_from_bottom > 0 && body.width > 1;
    let content_width = body.width.saturating_sub(u16::from(show_scrollbar));
    let mut y = body.y;
    for (index, row) in rows.iter().enumerate().skip(*state.workspace_scroll) {
        let height = heights[index].min(body.height);
        if y >= body.bottom() || y.saturating_add(height) > body.bottom() {
            break;
        }
        let (selected_workspace, dragged_workspace) = match row {
            NavigationRow::Workspace { workspace, .. } => (
                state.selected_workspace_id.is_some_and(|target| {
                    target.matches(state.active_endpoint_id, &workspace.workspace_id)
                }),
                state.dragged_workspace_id == Some(workspace.workspace_id.as_str()),
            ),
            NavigationRow::Group { .. } | NavigationRow::Member { .. } => (false, false),
        };
        let context = RowRenderContext {
            endpoint_id: &ClientEndpointId::Local,
            endpoint_active: true,
            multi_endpoint: false,
            snapshot,
            config,
            collapsed_groups: state.collapsed_groups,
            navigating: state.selected_workspace_id.is_some(),
            selected_workspace,
            dragged_workspace,
        };
        render_row(
            buffer,
            Rect::new(body.x, y, content_width, height),
            row,
            &context,
            hits,
            palette,
        );
        y = y.saturating_add(height).saturating_add(gaps[index]);
    }
    if show_scrollbar {
        hits.workspace_scrollbar = Rect::new(body.right() - 1, body.y, 1, body.height);
        super::scroll::render_list_scrollbar(buffer, hits.workspace_scrollbar, metrics, palette);
    }
    if let Some(row) = state
        .workspace_drop_indicator_row
        .filter(|row| *row >= body.y && *row < body.bottom())
    {
        put_text(
            buffer,
            body.x,
            row,
            content_width,
            &"─".repeat(content_width as usize),
            Style::default().fg(palette.accent),
        );
    }
    let footer_y = area.bottom() - 1;
    render_footer(
        buffer,
        Rect::new(area.x, footer_y, body.width.saturating_sub(1), 1),
        config,
        super::super::global_menu::global_menu_attention(snapshot),
        hits,
    );
    hits.sidebar_toggle = Rect::new(
        area.right().saturating_sub(2),
        footer_y,
        u16::from(area.width > 1),
        u16::from(area.height > 0),
    );
    put_text(
        buffer,
        hits.sidebar_toggle.x,
        hits.sidebar_toggle.y,
        hits.sidebar_toggle.width,
        "«",
        Style::default().fg(palette.overlay0),
    );
}

/// Render all endpoint roots, workspaces, workflow groups, and Agent panes in one tree.
pub(crate) fn render_endpoint_sidebar(
    buffer: &mut Buffer,
    area: Rect,
    config: &ClientShellConfig,
    state: &mut ShellRenderState<'_>,
    hits: &mut ShellHitMap,
) {
    render_sidebar_background(buffer, area, &config.palette);
    if area.height == 0 || area.width <= 1 {
        return;
    }
    let palette = &config.palette;
    let empty_collapsed_groups = HashSet::new();
    let rows = endpoint_navigation_rows(
        state.endpoints,
        state.collapsed_endpoints,
        state.collapsed_groups,
        state.remote_collapsed_groups,
        config,
    );
    hits.sidebar_divider = Rect::new(area.right() - 1, area.y, 1, area.height);
    hits.sidebar_section_divider = Rect::default();
    hits.workspace_body = Rect::new(area.x, area.y, area.width - 1, area.height - 1);
    hits.agent_body = Rect::default();
    hits.workspace_scrollbar = Rect::default();
    hits.agent_scrollbar = Rect::default();
    hits.workspace_scroll_metrics = None;
    hits.agent_scroll_metrics = None;
    hits.workspace_max_scroll = 0;

    let heights = rows
        .iter()
        .map(|row| match row {
            EndpointNavigationRow::Endpoint { .. } => 1,
            EndpointNavigationRow::Content { endpoint, row } => match row {
                NavigationRow::Workspace { entry, workspace } => {
                    let collapsed_groups =
                        super::super::endpoint_sidebar::collapsed_groups_for_endpoint(
                            state,
                            &endpoint.endpoint_id,
                        )
                        .unwrap_or(&empty_collapsed_groups);
                    workspace_rows(
                        workspace,
                        displayed_workspace_status(
                            snapshot_for(endpoint),
                            workspace,
                            collapsed_groups,
                        ),
                        entry.indented,
                        &config.spaces,
                    )
                    .len()
                    .max(1)
                    .min(u16::MAX as usize) as u16
                }
                NavigationRow::Group { .. } | NavigationRow::Member { .. } => 1,
            },
        })
        .collect::<Vec<_>>();
    let gaps = rows
        .iter()
        .enumerate()
        .map(|(index, row)| match (row, rows.get(index + 1)) {
            (
                EndpointNavigationRow::Content {
                    endpoint,
                    row: NavigationRow::Workspace { .. },
                },
                Some(EndpointNavigationRow::Content {
                    endpoint: next_endpoint,
                    row: NavigationRow::Workspace { entry, .. },
                }),
            ) if endpoint.endpoint_id == next_endpoint.endpoint_id => {
                u16::from(!entry.indented) * config.spaces.row_gap
            }
            _ => 0,
        })
        .collect::<Vec<_>>();
    let body = hits.workspace_body;
    let can_reveal = body.height > 1;
    let reveal_focused = can_reveal && std::mem::take(state.reveal_focused_workspace);
    let reveal_navigation = can_reveal && std::mem::take(state.reveal_navigation_workspace);
    if reveal_focused || reveal_navigation {
        let target = rows.iter().position(|row| match row {
            EndpointNavigationRow::Endpoint { .. } => false,
            EndpointNavigationRow::Content { endpoint, row } => match row {
                NavigationRow::Workspace { workspace, .. } => {
                    if reveal_navigation {
                        state.selected_workspace_id.is_some_and(|target| {
                            target.matches(&endpoint.endpoint_id, &workspace.workspace_id)
                        })
                    } else {
                        endpoint.endpoint_id == *state.active_endpoint_id && workspace.focused
                    }
                }
                NavigationRow::Group { .. } | NavigationRow::Member { .. } => false,
            },
        });
        if let Some(target) = target {
            *state.workspace_scroll = super::scroll::list_scroll_start_to_reveal(
                &heights,
                &gaps,
                body.height,
                *state.workspace_scroll,
                target,
            );
        }
    }
    let metrics =
        super::scroll::list_scroll_metrics(&heights, &gaps, body.height, *state.workspace_scroll);
    *state.workspace_scroll = metrics
        .max_offset_from_bottom
        .saturating_sub(metrics.offset_from_bottom);
    *state.agent_scroll = 0;
    hits.workspace_scroll_metrics = Some(metrics);
    hits.workspace_max_scroll = metrics.max_offset_from_bottom;
    let show_scrollbar = metrics.max_offset_from_bottom > 0 && body.width > 1;
    let content_width = body.width.saturating_sub(u16::from(show_scrollbar));
    let mut y = body.y;
    for (index, row) in rows.iter().enumerate().skip(*state.workspace_scroll) {
        let height = heights[index].min(body.height);
        if y >= body.bottom() || y.saturating_add(height) > body.bottom() {
            break;
        }
        match row {
            EndpointNavigationRow::Endpoint { endpoint } => {
                let rect = Rect::new(body.x, y, content_width, height);
                let collapsed = state.collapsed_endpoints.contains(&endpoint.endpoint_id);
                let status_badge = super::super::endpoint_sidebar::render_endpoint_row(
                    buffer,
                    rect,
                    if collapsed { "▸" } else { "▾" },
                    endpoint,
                    &endpoint.endpoint_id == state.active_endpoint_id && collapsed,
                    state.machine_diagnostics,
                    palette,
                );
                hits.machines.push(MachineHit {
                    rect,
                    status_badge,
                    collapse_toggle: Rect::new(
                        rect.x.saturating_add(1),
                        rect.y,
                        u16::from(rect.width > 1),
                        1,
                    ),
                    endpoint_id: endpoint.endpoint_id.clone(),
                });
            }
            EndpointNavigationRow::Content { endpoint, row } => {
                let Some(snapshot) = endpoint.snapshot.as_deref() else {
                    continue;
                };
                let collapsed_groups =
                    super::super::endpoint_sidebar::collapsed_groups_for_endpoint(
                        state,
                        &endpoint.endpoint_id,
                    )
                    .unwrap_or(&empty_collapsed_groups);
                let selected = match row {
                    NavigationRow::Workspace { workspace, .. } => {
                        state.selected_workspace_id.is_some_and(|target| {
                            target.matches(&endpoint.endpoint_id, &workspace.workspace_id)
                        })
                    }
                    NavigationRow::Group { .. } | NavigationRow::Member { .. } => false,
                };
                let context = RowRenderContext {
                    endpoint_id: &endpoint.endpoint_id,
                    endpoint_active: &endpoint.endpoint_id == state.active_endpoint_id,
                    multi_endpoint: true,
                    snapshot,
                    config,
                    collapsed_groups,
                    navigating: state.selected_workspace_id.is_some(),
                    selected_workspace: selected,
                    dragged_workspace: false,
                };
                render_row(
                    buffer,
                    Rect::new(body.x, y, content_width, height),
                    row,
                    &context,
                    hits,
                    palette,
                );
                if endpoint.status != ClientEndpointStatus::Online {
                    buffer.set_style(
                        Rect::new(body.x, y, content_width, height),
                        Style::default()
                            .fg(palette.overlay0)
                            .add_modifier(Modifier::DIM),
                    );
                }
            }
        }
        y = y.saturating_add(height).saturating_add(gaps[index]);
    }
    if show_scrollbar {
        hits.workspace_scrollbar = Rect::new(body.right() - 1, body.y, 1, body.height);
        super::scroll::render_list_scrollbar(buffer, hits.workspace_scrollbar, metrics, palette);
    }
    let footer_y = area.bottom() - 1;
    render_footer(
        buffer,
        Rect::new(area.x, footer_y, body.width.saturating_sub(1), 1),
        config,
        state
            .endpoints
            .iter()
            .find(|endpoint| &endpoint.endpoint_id == state.active_endpoint_id)
            .and_then(|endpoint| endpoint.snapshot.as_deref())
            .is_some_and(super::super::global_menu::global_menu_attention),
        hits,
    );
    hits.sidebar_toggle = Rect::new(
        area.right().saturating_sub(2),
        footer_y,
        u16::from(area.width > 1),
        u16::from(area.height > 0),
    );
    put_text(
        buffer,
        hits.sidebar_toggle.x,
        hits.sidebar_toggle.y,
        hits.sidebar_toggle.width,
        "«",
        Style::default().fg(palette.overlay0),
    );
}

fn snapshot_for(endpoint: &ClientShellEndpoint) -> &ClientShellSnapshot {
    endpoint
        .snapshot
        .as_deref()
        .expect("endpoint navigation content requires a snapshot")
}

fn render_footer(
    buffer: &mut Buffer,
    area: Rect,
    config: &ClientShellConfig,
    attention: bool,
    hits: &mut ShellHitMap,
) {
    if area.width == 0 || !config.mouse_capture {
        return;
    }
    hits.new_workspace = Rect::new(area.x, area.y, 5.min(area.width), 1);
    put_text(
        buffer,
        area.x + 1,
        area.y,
        area.width.saturating_sub(1),
        config.fore_rsi_labels.new,
        Style::default().fg(config.palette.overlay0),
    );
    let menu_width = display_width(config.fore_rsi_labels.menu)
        .saturating_add(if attention { 4 } else { 2 })
        .min(area.width);
    hits.global_launcher = Rect::new(
        area.right().saturating_sub(menu_width),
        area.y,
        menu_width,
        1,
    );
    if attention {
        put_text(
            buffer,
            hits.global_launcher.x + 1,
            area.y,
            2.min(menu_width.saturating_sub(1)),
            "● ",
            Style::default()
                .fg(config.palette.accent)
                .add_modifier(Modifier::BOLD),
        );
        put_text(
            buffer,
            hits.global_launcher.x + 3,
            area.y,
            menu_width.saturating_sub(3),
            config.fore_rsi_labels.menu,
            Style::default().fg(config.palette.overlay0),
        );
    } else {
        put_text(
            buffer,
            hits.global_launcher.x + 1,
            area.y,
            menu_width.saturating_sub(1),
            config.fore_rsi_labels.menu,
            Style::default().fg(config.palette.overlay0),
        );
    }
}
