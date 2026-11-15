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

Quote values containing spaces. Relative task paths are relative to the working directory. With either task input method, you can continue sharing materials and refining requirements in the conversation.

To resume, use the same `--session` name without resubmitting `--task`. See [Exit and resume](../README.md#exit-and-resume) for the exit shortcut and recovery behavior.

`fore-rsi --help` lists available options; `fore-rsi --version` prints the installed version. Both commands exit after displaying their output.

### List sessions

List local sessions and their running or stopped status:

```bash
fore-rsi list
```

Use a name from the list with `fore-rsi --session NAME` to resume it. `list` does not accept `--session`.

### Delete a session

Delete a stopped named session and its ForeRSI data:

```bash
fore-rsi delete --session sglang-throughput
```

`delete` requires `--session NAME`. Running sessions must be exited first; the default session `default` is retained. Project files and agent-owned configuration and conversation history are preserved.

`--workflow`, `--harness`, and `--task` apply only to `run`.

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

值中有空格时加引号。任务文件的相对路径以工作目录为基准。两种任务输入方式都可以在后续对话中继续补充材料或调整要求。

恢复时使用相同的 `--session` 名称，无需重复提交 `--task`。退出快捷键和恢复行为见[退出与恢复](../README_zh.md#退出与恢复)。

`fore-rsi --help` 显示可用参数，`fore-rsi --version` 显示安装版本，输出后退出。

### 列出会话

列出本地会话，查看其运行或停止状态：

```bash
fore-rsi list
```

使用列表中的名称运行 `fore-rsi --session NAME` 即可恢复会话。`list` 不接受 `--session`。

### 删除会话

删除已停止的命名会话及其 ForeRSI 数据：

```bash
fore-rsi delete --session sglang-throughput
```

`delete` 必须提供 `--session NAME`。运行中的会话需要先退出；默认会话 `default` 保留。删除会保留项目文件以及 Agent 自行管理的配置和对话记录。

`--workflow`、`--harness` 和 `--task` 仅用于 `run`。

### 诊断日志

Python 诊断日志默认以 `INFO` 级别和文本格式写入 stderr。可以提高详细程度，或在 stderr 输出之外追加保存 JSON 日志：

```bash
fore-rsi --log-level DEBUG
fore-rsi --log-format json --log-file logs/fore-rsi.jsonl
```

`--log-format` 同时作用于 stderr 和指定文件。文件以 UTF-8 追加写入，缺少的父目录会自动创建；独立运行的进程应使用不同文件。帮助和版本命令不会创建日志文件，正式命令结果仍输出到 stdout。

Agent 对话和原生终端日志沿用各自的记录路径。
