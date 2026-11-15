# Contributing to ForeRSI

English | [简体中文](CONTRIBUTING_zh.md)

## Local development

Install [Rustup](https://rustup.rs/) and the platform's C/C++ build tools, then install in editable mode from the repository root:

```bash
uv tool install --python 3.13 -e .
```

Changes under `src/` are used by the `fore-rsi` command without activating a virtual environment. Other installation options are in the [README](README.md#install).

Use `from loguru import logger` for Python diagnostics. Keep command results and parse-time usage errors on their CLI streams. Configure [logging.py](src/fore_rsi/logging.py) from the application entry point; Loguru closes synchronous sinks at process exit. Independently launched processes use separate log files. Conversations and experiment results stay with their respective recording modules.

The CLI reads the installed version through `importlib.metadata`; [pyproject.toml](pyproject.toml) is the source for package version metadata.

Keep English and Chinese documentation aligned. Update commands, examples, and configuration fields together. Keep credentials, private infrastructure details, and local runtime data outside the repository.

## Pre-commit

Install pre-commit with uv, enable the repository hooks, and run the complete check before submitting changes:

```bash
uv tool install pre-commit
pre-commit install
pre-commit run --all-files
```

The hooks run repository hygiene checks, Python syntax validation, terminal formatting, and strict terminal Clippy.

## Verify changes

```bash
fore-rsi --help
fore-rsi --version
```

Exercise the affected command paths and record the commands and actual results. See the [CLI reference](docs/cli.md) for available options.

## Build distributions

Build the source archive and platform wheel from the repository root:

```bash
uv build
```

Both are written to `dist/`. The wheel includes the compiled terminal; the source archive includes the inputs needed to rebuild it. Install the resulting wheel in a clean environment and verify it outside the source checkout before publishing.

## Pull requests

Keep changes focused and explain the problem, resulting behavior, and validation. Discuss major interface or responsibility changes with the maintainers first.

Use a short English PR title beginning with a tag such as `[Bugfix]`, `[Feature]`, `[Refactor]`, or `[Docs]`. Write commit messages in English.

Contributions are distributed under the [Apache License 2.0](LICENSE).
