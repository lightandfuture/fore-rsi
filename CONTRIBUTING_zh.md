# 为 ForeRSI 做贡献

[English](CONTRIBUTING.md) | 简体中文

## 本地开发

准备好 [Rustup](https://rustup.rs/) 与系统 C/C++ 构建工具后，在仓库根目录进行可编辑安装：

```bash
uv tool install --python 3.13 -e .
```

`src/` 下的修改会直接用于 `fore-rsi` 命令，无需激活虚拟环境。其他安装方式见 [README](README_zh.md#安装)。

## 配置与执行

- [src/fore_rsi/config.py](src/fore_rsi/config.py) 定义 `Config`、`WorkflowConfig`、`UIConfig` 和 `LoggingConfig`。任务与 harness 设置属于 `WorkflowConfig`，ForeRSI 会话名称属于 `UIConfig`。
- [src/fore_rsi/cli/](src/fore_rsi/cli/) 将 tyro 参数解析与参数组合校验分开。解析器调用校验后返回完整的 `Config`，并负责帮助、版本输出和参数使用错误。参数名称、默认值、类型和帮助说明随配置定义维护。
- [src/fore_rsi/main.py](src/fore_rsi/main.py) 是应用主入口。安装后的 `fore-rsi` 命令与 `python -m fore_rsi` 都调用其中的 `main()`。入口接收已校验的配置、初始化日志，再将会话操作交给 [ui/launch_ui.py](src/fore_rsi/ui/launch_ui.py)。

配置只保存数据。CLI 负责参数转换，workflow 负责业务校验、Agent 角色、调度和管理规则，harness 执行 Agent，终端 UI 展示进展与结果。避免另行维护一份字段类型清单，或为每个参数设置独立执行函数。

Python 诊断日志统一使用 `from loguru import logger`。命令结果和参数使用错误仍通过 CLI 输出。应用入口通过 [logging.py](src/fore_rsi/logging.py) 统一配置输出，同步日志由 Loguru 在进程退出时清理。使用 Loguru 的 `bind()` 或 `contextualize()` 关联任务与 Agent；独立启动的进程使用不同日志文件。对话和实验结果仍由各自的记录模块保存。

CLI 通过 `importlib.metadata` 读取安装版本；[pyproject.toml](pyproject.toml) 是包版本元数据的来源。

中英文文档保持一致。命令、示例和配置字段一起更新。凭据、私有基础设施信息和本地运行数据保留在仓库之外。

## Pre-commit

使用 uv 安装 pre-commit，启用仓库钩子，并在提交改动前运行完整检查：

```bash
uv tool install pre-commit
pre-commit install
pre-commit run --all-files
```

钩子会检查仓库文件规范、Python 语法、终端 Rust 格式以及严格 Clippy。

## 验证改动

```bash
fore-rsi --help
fore-rsi --version
```

实际执行受改动影响的命令路径，记录所用命令与真实结果。可用参数见 [CLI 参考](docs/cli.md)。

## 构建发行包

在仓库根目录构建源码包与平台 wheel：

```bash
uv build
```

产物写入 `dist/`。wheel 包含编译好的终端，源码包包含重新构建所需的输入。发布前，在干净环境中安装 wheel，并离开源码目录验证安装结果。

## 提交 Pull Request

保持改动集中，说明问题、结果和验证。涉及公开接口或职责的大改动，先与维护者讨论。

PR 使用简短英文标题，以 `[Bugfix]`、`[Feature]`、`[Refactor]` 或 `[Docs]` 等标签开头；提交信息使用英文。

贡献采用 [Apache License 2.0](LICENSE) 许可证。
