# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Open or resume a member's conversation when its PTY is created or its layout is replayed."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile
from uuid import UUID, uuid4


def _write_record(path: Path, value: str) -> None:
    """Publish the native binding before a launcher or a future host can use it."""
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete_on_close=False) as tmp:
        tmp.write(value + "\n")
        tmp.close()
        Path(tmp.name).replace(path)


def _link_directory(link: Path, target: Path) -> None:
    """Expose the member's transcript directory at its native location without replacing existing data."""
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    link.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
    except FileExistsError:
        if not link.is_symlink() or link.resolve() != target.resolve():
            raise RuntimeError(f"Native conversation directory is already in use: {link}") from None


def codex_profiles(state_directory: Path, session_name: str) -> Path:
    """Locate the session's private Codex databases outside the project and its transcript cache."""
    return state_directory / "codex-profiles" / session_name.encode().hex()


def _prepare_codex_profile(profile: Path) -> None:
    """Reference the native user's configuration and file-based login without copying either."""
    origin = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()
    origin.mkdir(mode=0o700, parents=True, exist_ok=True)
    if profile.resolve() == origin:
        return
    names = ("config.toml", "auth.json", "AGENTS.md", "AGENTS.override.md", "rules", "skills", "hooks.json",
             "hooks", "plugins", "agents", *(p.name for p in origin.glob("*.config.toml")))
    for name in names:
        source, link = origin / name, profile / name
        if link.is_symlink():
            if link.readlink() != source:
                raise ValueError("This Codex conversation belongs to a different CODEX_HOME.")
        elif not link.exists() and (source.exists() or name == "auth.json"):
            # Codex also writes a fresh file-based login through this link, outside ForeRSI.
            link.symlink_to(source, target_is_directory=source.is_dir())


def codex_thread(record: Path, sessions: Path) -> str | None:
    """Pin the root thread of this member's private rollout directory; never select by recency."""
    if record.exists():
        return str(UUID(record.read_text(encoding="utf-8").strip()))
    roots = set()
    for path in sessions.glob("*/*/*/rollout-*.jsonl"):
        with path.open(encoding="utf-8") as stream:
            line = stream.readline()
        if line:
            first = json.loads(line)
            meta = first.get("payload", {})
            if (first.get("type") == "session_meta" and meta.get("source") == "cli"
                    and not meta.get("forked_from_id") and not meta.get("parent_thread_id")):
                roots.add(str(UUID(meta["id"])))
    if len(roots) > 1:
        raise RuntimeError(f"Cannot identify one root Codex conversation in {sessions}.")
    if roots:
        thread = roots.pop()
        _write_record(record, thread)
        return thread
    return None  # Codex may defer creating its rollout until the first turn.


def _claude_project_link(home: Path, conversation: str) -> Path:
    return home / "projects" / f"fore-rsi-{UUID(conversation)}"


def _unlink_project(link: Path, target: Path) -> None:
    # Never remove a real user directory, or a link that has been repurposed.
    if link.is_symlink() and link.readlink() == target:
        link.unlink()


def _claude_session(member: Path, home: Path) -> tuple[str, str, str]:
    """Bind the UUID and project alias to this member's native settings, preserving sign-in and history."""
    record = member.with_suffix(".session")
    projects = member.parent / "projects" / "agents" / member.name
    try:
        binding = json.loads(record.read_bytes())
    except FileNotFoundError:
        binding = {"id": str(uuid4()), "home": None}
    conversation = str(UUID(binding["id"]))
    if binding["home"] != str(home):
        if binding["home"] is not None:
            _unlink_project(_claude_project_link(Path(binding["home"]), conversation), projects)
        _write_record(record, json.dumps({"id": conversation, "home": str(home)}))
    link = _claude_project_link(home, conversation)
    _link_directory(link, projects)
    flag = "--resume" if (projects / f"{conversation}.jsonl").is_file() else "--session-id"
    return link.name, flag, conversation


def remove_native_storage(session_directory: Path, state_directory: Path) -> None:
    """Remove external profile state and owned Claude project links before deleting the stopped session."""
    codex = codex_profiles(state_directory, session_directory.name)
    for profile in codex.glob("member-*"):
        sessions = profile / "sessions"
        expected = session_directory / "harnesses" / "codex" / "sessions" / profile.name
        if not profile.is_symlink() and sessions.is_symlink() and sessions.resolve() == expected.resolve():
            shutil.rmtree(profile)  # Only the links to user settings and credentials are removed.
    if codex.is_dir() and not any(codex.iterdir()):
        codex.rmdir()
    claude = session_directory / "harnesses" / "claude"
    for record in claude.glob("member-*.session"):
        binding = json.loads(record.read_bytes())
        link = _claude_project_link(Path(binding["home"]), binding["id"])
        _unlink_project(link, claude / "projects" / "agents" / record.stem)


def _windows_command(executable: str, kind: str) -> list[str]:
    """Resolve standard npm shims to argv without passing prompts or paths through cmd.exe."""
    shim = Path(executable)
    if shim.suffix.lower() not in (".cmd", ".bat"):
        return [executable]
    if native := shutil.which(f"{kind}.exe"):
        return [native]
    modules = shim.parent.parent if shim.parent.name == ".bin" else shim.parent / "node_modules"
    package = modules / ("@openai/codex" if kind == "codex" else "@anthropic-ai/claude-code")
    manifest = package / "package.json"
    if manifest.is_file():
        bins = json.loads(manifest.read_bytes())["bin"]
        entry = package / (bins if isinstance(bins, str) else bins[kind])
        if entry.suffix.lower() == ".exe":
            return [str(entry)]
        if entry.is_file() and (node := shutil.which("node.exe")):
            return [node, str(entry)]
    raise OSError(f"Cannot resolve {shim.name} to its native or npm executable.")


def launch(arguments: list[str]) -> None:
    """Replace the installed helper with the native interactive CLI, preserving its controlling PTY."""
    kind, executable, member_path, native_home, instructions, *options = arguments
    member, profile = Path(member_path), Path(native_home)
    env = dict(os.environ)
    if kind == "codex":
        env["CODEX_HOME"] = str(profile)
        sessions = member.parent / "sessions" / member.name
        _link_directory(profile / "sessions", sessions)
        _prepare_codex_profile(profile)
        thread = codex_thread(member.with_suffix(".id"), sessions)
        command = [executable, "--no-daemon", "-c", f"sqlite_home={json.dumps(str(profile), ensure_ascii=False)}", *options]
        if instructions:
            prompt = Path(instructions).read_text(encoding="utf-8")
            command.extend(["-c", f"developer_instructions={json.dumps(prompt, ensure_ascii=False)}"])
        if thread is not None:
            command.extend(["resume", thread])
    elif kind == "claude":
        project_name, flag, conversation = _claude_session(member, profile)
        env["CLAUDE_CODE_PROJECT_DIR_NAME"] = project_name
        command = [executable, flag, conversation, *options]
        if instructions:
            command.extend(["--append-system-prompt-file", instructions])
    else:
        raise ValueError(f"Unknown native launcher: {kind}")
    if os.name == "nt":
        # ConPTY monitors the launcher process; keep it alive for the child's full lifetime.
        command[:1] = _windows_command(executable, kind)
        raise SystemExit(subprocess.run(command, env=env).returncode)
    os.execve(executable, command, env)


if __name__ == "__main__":
    launch(sys.argv[1:])
