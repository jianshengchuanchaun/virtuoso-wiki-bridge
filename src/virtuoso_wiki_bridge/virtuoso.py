"""Virtuoso and Spectre bridge commands."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .ssh import pull, quote_remote, run_remote, upload

DEFAULT_BRIDGE_TIMEOUT = 60
DEFAULT_EVAL_TIMEOUT = 30
DEFAULT_LOAD_TIMEOUT = 60
DEFAULT_SNAPSHOT_TIMEOUT = 120
DEFAULT_SPECTRE_TIMEOUT = 300
DEFAULT_PULL_TIMEOUT = 120
UPSTREAM_TIMEOUT_GRACE = 5


@dataclass(frozen=True)
class RunSummary:
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    remote_dir: str = ""


def validate_run_name(value: str) -> str:
    """Validate a single safe remote run-directory component."""

    if not value:
        raise ValueError("run name must not be empty")
    if value in {".", ".."}:
        raise ValueError("run name must not be '.' or '..'")
    if "/" in value or "\\" in value:
        raise ValueError("run name must be a basename without path separators")
    if value.startswith("-"):
        raise ValueError("run name must not start with '-'")
    if any(not (char.isalnum() or char in "._-") for char in value):
        raise ValueError("run name may contain only letters, numbers, '.', '_', and '-'")
    return value


def _remote_runs_root(config: AppConfig) -> str:
    configured = str(config.remote_workdir)
    if not configured.strip():
        raise ValueError("remote work directory must not be empty")
    root = configured.rstrip("/")
    if not root:
        return "/runs"
    return f"{root}/runs"


def _remote_run_dir(config: AppConfig, run_name: str) -> str:
    return f"{_remote_runs_root(config)}/{validate_run_name(run_name)}"


def _bridge_selector_args(config: AppConfig) -> list[str]:
    args: list[str] = []
    profile = getattr(config, "bridge_profile", None)
    env_path = getattr(config, "bridge_env", None)
    if profile:
        args += ["--profile", str(profile)]
    if env_path:
        args += ["--env", str(env_path)]
    return args


def bridge_available(config: AppConfig) -> bool:
    return shutil.which(config.bridge_cmd) is not None or Path(config.bridge_cmd).is_file()


def _bounded_timeout(timeout: int | None, default: int) -> int:
    selected = default if timeout is None else timeout
    if selected <= 0:
        raise ValueError("operation timeout must be a positive integer")
    return selected


def _explain_missing_upstream_command(summary: RunSummary, command: str) -> RunSummary:
    diagnostic = f"{summary.stdout}\n{summary.stderr}".lower()
    if summary.returncode != 2 or "invalid choice" not in diagnostic or command.lower() not in diagnostic:
        return summary
    compatibility = (
        f"installed upstream virtuoso-bridge does not support the '{command}' command; "
        "upgrade to a build that exposes this command (the current upstream main branch does)."
    )
    original = summary.stderr.strip()
    stderr = f"{compatibility}\nupstream error: {original}\n" if original else f"{compatibility}\n"
    return RunSummary(summary.returncode, summary.stdout, stderr, summary.elapsed_seconds, summary.remote_dir)


def run_bridge_command(
    config: AppConfig,
    args: list[str],
    *,
    timeout: int | None = DEFAULT_BRIDGE_TIMEOUT,
) -> RunSummary:
    timeout = _bounded_timeout(timeout, DEFAULT_BRIDGE_TIMEOUT)
    start = time.monotonic()
    command = [config.bridge_cmd] + list(args) + _bridge_selector_args(config)
    proc = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return RunSummary(proc.returncode, proc.stdout or "", proc.stderr or "", time.monotonic() - start)


def status(config: AppConfig) -> RunSummary:
    return run_bridge_command(config, ["status"], timeout=DEFAULT_BRIDGE_TIMEOUT)


def eval_skill(config: AppConfig, expr: str, *, timeout: int | None = DEFAULT_EVAL_TIMEOUT) -> RunSummary:
    timeout = _bounded_timeout(timeout, DEFAULT_EVAL_TIMEOUT)
    args = ["eval", expr]
    args += ["--timeout", str(timeout)]
    summary = run_bridge_command(config, args, timeout=timeout + UPSTREAM_TIMEOUT_GRACE)
    return _explain_missing_upstream_command(summary, "eval")


def load_skill(config: AppConfig, path: Path, *, timeout: int | None = DEFAULT_LOAD_TIMEOUT) -> RunSummary:
    timeout = _bounded_timeout(timeout, DEFAULT_LOAD_TIMEOUT)
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SKILL file not found: {path}")
    args = ["load", str(path)]
    args += ["--timeout", str(timeout)]
    summary = run_bridge_command(config, args, timeout=timeout + UPSTREAM_TIMEOUT_GRACE)
    return _explain_missing_upstream_command(summary, "load")


def snapshot(
    config: AppConfig,
    output_dir: Path | None = None,
    *,
    timeout: int | None = DEFAULT_SNAPSHOT_TIMEOUT,
) -> RunSummary:
    timeout = _bounded_timeout(timeout, DEFAULT_SNAPSHOT_TIMEOUT)
    args = ["snapshot"]
    if output_dir is not None:
        args += ["-o", str(output_dir)]
    return run_bridge_command(config, args, timeout=timeout)


def run_spectre_remote(
    config: AppConfig,
    netlist: Path,
    *,
    name: str | None = None,
    timeout: int | None = DEFAULT_SPECTRE_TIMEOUT,
) -> RunSummary:
    timeout = _bounded_timeout(timeout, DEFAULT_SPECTRE_TIMEOUT)
    netlist = netlist.expanduser().resolve()
    if not netlist.is_file():
        raise FileNotFoundError(f"Spectre netlist not found: {netlist}")
    run_name = validate_run_name(name if name is not None else netlist.stem)
    remote_dir = _remote_run_dir(config, run_name)
    if not config.remote.remote_host:
        return RunSummary(2, "", "VWB_REMOTE_HOST is empty; configure SSH or use virtuoso-bridge spectre support.", 0.0)
    rc = upload(config.remote, netlist, remote_dir, timeout=timeout)
    if rc != 0:
        return RunSummary(rc, "", f"upload failed with return code {rc}", 0.0, remote_dir)
    start = time.monotonic()
    # Prefix the uploaded basename so Spectre cannot parse a leading '-' or '+'
    # in the filename as an option. Shell quoting still protects whitespace and
    # punctuation in the basename itself.
    q_netlist = quote_remote("./" + netlist.name)
    command = "\n".join(
        [
            "rm -f -- spectre.out",
            "set +e",
            f"spectre {q_netlist} +log spectre.out",
            "rc=$?",
            'if [ -f spectre.out ]; then tail -n 120 -- spectre.out; fi',
            'exit "$rc"',
        ]
    )
    result = run_remote(config.remote, command, workdir=remote_dir, timeout=timeout, batch=True)
    return RunSummary(result.returncode, result.stdout, result.stderr, time.monotonic() - start, remote_dir)


def pull_remote_run(
    config: AppConfig,
    run_name: str,
    local_dir: Path,
    *,
    timeout: int | None = DEFAULT_PULL_TIMEOUT,
) -> int:
    timeout = _bounded_timeout(timeout, DEFAULT_PULL_TIMEOUT)
    remote_dir = _remote_run_dir(config, run_name)
    return pull(config.remote, remote_dir + "/", local_dir, timeout=timeout)


def doctor(config: AppConfig) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("vault", config.vault_path.exists(), str(config.vault_path)))
    checks.append(("sources", config.sources_dir.exists(), str(config.sources_dir)))
    checks.append(("virtuoso_bridge_cmd", bridge_available(config), config.bridge_cmd))
    if bridge_available(config):
        result = status(config)
        checks.append(("virtuoso_bridge_status", result.returncode == 0, (result.stdout + result.stderr).strip()))
    if config.remote.remote_host:
        probe = run_remote(config.remote, "printf 'ssh-ok\\n'; uname -srm", batch=True, timeout=20)
        checks.append(("ssh", probe.returncode == 0, (probe.stdout + probe.stderr).strip()))
    return checks
