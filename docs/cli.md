# CLI reference / 命令行参考

## English

### Start or resume

Run `fore-rsi` or `fore-rsi run` in the project directory to start a ForeRSI session and describe the task in the conversation. Both forms accept the same options. You can select a workflow, choose an agent backend, name the session, and supply a task file:

```bash
fore-rsi --workflow inference \
  --harness pi \
  --session sglang-throughput \
  --task tasks/inference-optimization/sglang-throughput.md
```

This example uses the task file from the ForeRSI repository root. All startup options are optional:

- `--workflow NAME` selects `default` for general tasks, `inference` for inference optimization, or a custom workflow by name. Omitting it selects `default`.
- `--harness NAME` selects the backend that runs agents, such as `pi`.
- `--session NAME` names the ForeRSI session to create or resume.
- `--task FILE` provides a Markdown task file. Omit it to describe the task in the conversation.
- `--cache-dir PATH` sets the root directory for local ForeRSI runtime data (default: `./cache`). Relative paths use the current project's Git repository root, or the startup directory outside Git; absolute paths are used directly. Workflow session records are stored in its `workflows/` subdirectory.

Quote values containing spaces. Relative task paths are relative to the working directory. With either task input method, you can continue sharing materials and refining requirements in the conversation.

To resume, use the same `--session` name without resubmitting `--task`. See [Exit and resume](../README.md#exit-and-resume) for the exit shortcut and recovery behavior.

`fore-rsi --help` lists available options; `fore-rsi --version` prints the installed version. Both commands exit after displaying their output.

### List sessions

List the workflows registered in the selected cache and local terminal sessions:

```bash
fore-rsi list
```

`WORKFLOW` shows the registered workflow name. `WORKFLOW_STATE` preserves recorded `completed`, `stopped`, and `failed` outcomes. For a `running` record, it checks the local host's PID and creation time: a matching live process remains `running`, an exited host or reused PID shows `interrupted`, and missing identity or unavailable process information shows `unknown`. These observations do not change the saved record.

`TERMINAL_SERVER` independently shows `running`, `stopped`, or `unavailable`. A dash (`—`) marks a missing record or a workflow record that has no saved state.

If startup used a custom cache, pass the same `--cache-dir PATH` to `list`.

Use a name from the list with `fore-rsi --session NAME` to resume it. `list` does not accept `--session`.

### Delete a session

Stop and delete a named terminal session:

```bash
fore-rsi delete --session sglang-throughput
```

`delete` requires `--session NAME`. It stops the terminal server before deleting its session data; the default session `default` is retained. Workflow records in the cache, project files, and agent-owned configuration and conversation history are preserved.

`--workflow`, `--harness`, and `--task` apply only to `run`. `--cache-dir` applies to `run` and `list`.

### Diagnostic logs

Python diagnostics use `INFO` level and readable text on stderr by default. Increase detail or keep a JSON log alongside stderr:

```bash
fore-rsi --log-level DEBUG
fore-rsi --log-format json --log-file logs/fore-rsi.jsonl
```

`--log-format` applies to stderr and the optional file. File output appends in UTF-8 and creates missing parent directories. Use separate files for independently running processes. Help and version commands do not create log files, and normal command results remain on stdout.

Agent conversations and native terminal logs retain their own recording paths.

## 中文

### 启动与恢复

在项目目录运行 `fore-rsi` 或 `fore-rsi run`，进入终端界面后直接描述任务。两种写法接受相同的参数，可以选择工作流、指定 Agent 后端、命名会话，并提供任务文件：

```bash
fore-rsi --workflow inference \
  --harness pi \
  --session sglang-throughput \
  --task tasks/inference-optimization/sglang-throughput.md
```

示例使用 ForeRSI 仓库根目录下的任务文件。启动参数均可按需省略：

- `--workflow NAME` 选择通用工作流 `default`、推理优化工作流 `inference`，或按名称选择自定义工作流。省略时使用 `default`。
- `--harness NAME` 选择执行 Agent 的后端，例如 `pi`。
- `--session NAME` 指定要创建或恢复的 ForeRSI 会话名称。
- `--task FILE` 提供 Markdown 任务文件。省略时，在对话中直接描述任务。
- `--cache-dir PATH` 指定 ForeRSI 本地运行数据的根目录，默认 `./cache`。相对路径以当前项目的 Git 仓库根目录为基准；不在 Git 仓库中时使用启动目录，绝对路径直接使用。工作流会话记录保存在其中的 `workflows/` 子目录。

值中有空格时加引号。任务文件的相对路径以工作目录为基准。两种任务输入方式都可以在后续对话中继续补充材料或调整要求。

恢复时使用相同的 `--session` 名称，无需重复提交 `--task`。退出快捷键和恢复行为见[退出与恢复](../README_zh.md#退出与恢复)。

`fore-rsi --help` 显示可用参数，`fore-rsi --version` 显示安装版本，输出后退出。

### 列出会话

汇总所选缓存中登记的工作流和本地终端会话：

```bash
fore-rsi list
```

`WORKFLOW` 显示登记的工作流名称。`WORKFLOW_STATE` 保留已记录的 `completed`、`stopped` 和 `failed` 结果；对于 `running` 记录，会核对本机宿主进程的 PID 和创建时间。同一进程仍存活时显示 `running`，宿主已退出或 PID 已被复用时显示 `interrupted`，缺少身份信息或无法查询进程信息时显示 `unknown`。查询结果不会回写记录文件。

`TERMINAL_SERVER` 独立显示终端服务器的 `running`、`stopped` 或 `unavailable` 状态。缺少某一侧记录，或工作流记录尚未保存状态时，显示 `—`。

启动时如果指定了自定义缓存目录，查询时也传入相同的 `--cache-dir PATH`。

使用列表中的名称运行 `fore-rsi --session NAME` 即可恢复会话。`list` 不接受 `--session`。

### 删除会话

停止并删除命名终端会话：

```bash
fore-rsi delete --session sglang-throughput
```

`delete` 必须提供 `--session NAME`，命令会先停止终端服务器，再删除其会话数据。默认会话 `default` 保留。缓存中的工作流记录、项目文件，以及 Agent 自行管理的配置和对话记录会保留。

`--workflow`、`--harness` 和 `--task` 仅用于 `run`。`--cache-dir` 用于 `run` 和 `list`。

### 诊断日志

Python 诊断日志默认以 `INFO` 级别和文本格式写入 stderr。可以提高详细程度，或在 stderr 输出之外追加保存 JSON 日志：

```bash
fore-rsi --log-level DEBUG
fore-rsi --log-format json --log-file logs/fore-rsi.jsonl
```

`--log-format` 同时作用于 stderr 和指定文件。文件以 UTF-8 追加写入，缺少的父目录会自动创建；独立运行的进程应使用不同文件。帮助和版本命令不会创建日志文件，正式命令结果仍输出到 stdout。

Agent 对话和原生终端日志沿用各自的记录路径。
