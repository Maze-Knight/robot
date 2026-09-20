"""Side-effect-limited helpers shared by the Windows management terminal."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


ENVIRONMENT_KEYS = (
    "QQ_APP_ID",
    "QQ_APP_SECRET",
    "GIFT_API_BASE_URL",
    "TRICKCAL_MODE",
    "TRICKCAL_API_BASE_URL",
    "TRICKCAL_BOT_API_KEY",
    # Legacy local-only fallback settings.
    "TRICKCAL_WEB_PUBLIC_URL",
    "TRICKCAL_WEB_SECURE_COOKIE",
    "TRICKCAL_WEB_SESSION_DAYS",
    "TRICKCAL_LOGIN_TICKET_MINUTES",
)


def application_directory() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def default_runtime_directory(base: Path | None = None) -> Path:
    root = base or application_directory()
    return root if (root / "ElenaBot.exe").is_file() else root / "dist"


def find_repository(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def load_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text("utf-8-sig").splitlines()
    except FileNotFoundError:
        return values
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in ENVIRONMENT_KEYS:
            values[key] = value.strip()
    return values


def save_environment(path: Path, values: dict[str, str]) -> None:
    """Update managed keys while preserving comments and unrelated deployment settings."""
    try:
        original = path.read_text("utf-8-sig").splitlines()
    except FileNotFoundError:
        original = []
    remaining = dict(values)
    result: list[str] = []
    for line in original:
        if "=" not in line or line.lstrip().startswith("#"):
            result.append(line)
            continue
        key, _old = line.split("=", 1)
        key = key.strip()
        if key not in remaining:
            result.append(line)
            continue
        result.append(f"{key}={remaining.pop(key).strip()}")
    if remaining:
        if result and result[-1]:
            result.append("")
        result.append("# Managed by ElenaManager; do not commit this file.")
        result.extend(f"{key}={value.strip()}" for key, value in remaining.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(result).rstrip() + "\n", "utf-8")
    os.replace(temporary, path)


def bot_command(runtime_directory: Path) -> tuple[list[str], Path]:
    exe = runtime_directory / "ElenaBot.exe"
    if exe.is_file():
        return [str(exe)], runtime_directory
    source_root = runtime_directory if (runtime_directory / "main.py").is_file() else runtime_directory.parent
    python = source_root / ".venv" / "Scripts" / "python.exe"
    if python.is_file() and (source_root / "main.py").is_file():
        return [str(python), "main.py"], source_root
    raise FileNotFoundError("未找到 ElenaBot.exe，也没有可用的源码虚拟环境。")


def launch_bot(runtime_directory: Path) -> subprocess.Popen[bytes]:
    command, cwd = bot_command(runtime_directory)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)


def run_git(repository: Path, arguments: Iterable[str], *, timeout: int = 90) -> tuple[int, str]:
    command = ["git", "-C", str(repository), *arguments]
    completed = subprocess.run(command, text=True, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode, output or "（没有输出）"


def git_status(repository: Path) -> tuple[bool, str]:
    code, output = run_git(repository, ["status", "--short", "--branch"])
    return code == 0, output


def git_pull_fast_forward(repository: Path) -> tuple[bool, str]:
    code, status = run_git(repository, ["status", "--porcelain"])
    if code != 0:
        return False, status
    # run_git supplies a user-facing placeholder for genuinely empty output.
    # `git status --porcelain` is intentionally empty in a clean worktree.
    if status != "（没有输出）":
        return False, "工作区存在未提交修改。为避免覆盖，请先提交或处理这些修改。"
    code, output = run_git(repository, ["pull", "--ff-only"], timeout=180)
    return code == 0, output


def build_distribution(
    repository: Path, *, stage_manager: bool = False
) -> tuple[bool, str]:
    """Build a deployment distribution without exposing command output elsewhere."""
    script = repository / "build_exe.ps1"
    if not script.is_file():
        return False, "未找到 build_exe.ps1，无法构建部署文件。"
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-SkipInstall",
    ]
    if stage_manager:
        command.extend(["-ManagerName", "ElenaManager.next"])
    try:
        completed = subprocess.run(
            command,
            cwd=repository,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"构建未完成：{exc}"
    output = (completed.stdout + completed.stderr).strip()
    if completed.returncode:
        return False, output or "构建失败。"
    return True, output or "构建完成。"


def stop_managed_process(process: Any, *, timeout: int = 15) -> bool:
    """Stop only the process explicitly launched by this manager, including children."""
    if process is None or process.poll() is not None:
        return True
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        else:
            process.terminate()
        process.wait(timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return process.poll() is not None
    return process.poll() is not None


def git_commit_and_push(repository: Path, message: str) -> tuple[bool, str]:
    message = message.strip()
    if not message:
        return False, "请输入提交说明。"
    code, output = run_git(repository, ["add", "-A"])
    if code != 0:
        return False, output
    code, output = run_git(repository, ["commit", "-m", message])
    if code != 0:
        return False, output
    code, output = run_git(repository, ["push"], timeout=180)
    return code == 0, output
