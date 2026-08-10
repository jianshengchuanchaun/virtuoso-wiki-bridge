"""Small SSH helpers for optional direct Spectre runs."""

from __future__ import annotations

import os
import posixpath
import shlex
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import RemoteConfig

DEFAULT_SSH_OPERATION_TIMEOUT = 300


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def _contains_unsafe_control(value: str) -> bool:
    return any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)


def _validate_remote_identity(value: str, label: str, *, allow_empty: bool = False) -> str:
    if not value:
        if allow_empty:
            return ""
        raise ValueError(f"{label} must not be empty")
    if value.startswith("-"):
        raise ValueError(f"{label} must not start with '-'")
    if _contains_unsafe_control(value):
        raise ValueError(f"{label} must not contain whitespace or control characters")
    return value


def remote_target(config: RemoteConfig) -> str:
    """Return a validated ``[user@]host`` target for ssh/scp."""

    host = _validate_remote_identity(config.remote_host, "remote host")
    user = _validate_remote_identity(config.remote_user, "remote user", allow_empty=True)
    return f"{user}@{host}" if user else host


def _validate_remote_path(value: str) -> str:
    if not value:
        raise ValueError("remote path must not be empty")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("remote path must not contain control characters")
    return value


def _is_link_or_reparse(path: Path) -> bool:
    try:
        value = path.lstat()
    except FileNotFoundError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(value, "st_file_attributes", 0)
    return stat.S_ISLNK(value.st_mode) or bool(reparse_flag and attributes & reparse_flag)


def _assert_no_link_components(path: Path, *, label: str) -> None:
    absolute = Path(os.path.abspath(path.expanduser()))
    for component in reversed((absolute, *absolute.parents)):
        if _is_link_or_reparse(component):
            raise ValueError(
                f"{label} must not traverse a symlink, junction, or reparse point: {component}"
            )


def quote_remote(value: str) -> str:
    return shlex.quote(value)


def quote_remote_path(value: str) -> str:
    value = _validate_remote_path(value)
    if value == "~":
        return value
    if value.startswith("~/"):
        rest = value[2:]
        return "~/" + quote_remote(rest) if rest else "~/"
    return quote_remote(value)


def remote_scp_target(config: RemoteConfig, remote_path: str) -> str:
    """Build an scp remote operand while preserving remote ``~`` expansion."""

    return f"{remote_target(config)}:{quote_remote_path(remote_path)}"


def ssh_base(config: RemoteConfig, *, batch: bool = False, connect_timeout: int | None = 10) -> list[str]:
    cmd = [config.ssh_cmd]
    if config.remote_port and config.remote_port != 22:
        cmd += ["-p", str(config.remote_port)]
    if config.ssh_key:
        cmd += ["-i", os.path.expanduser(os.path.expandvars(config.ssh_key))]
    if config.ssh_config:
        cmd += ["-F", os.path.expanduser(os.path.expandvars(config.ssh_config))]
    if batch:
        cmd += ["-o", "BatchMode=yes"]
    if connect_timeout is not None:
        cmd += ["-o", f"ConnectTimeout={connect_timeout}"]
    cmd += list(config.ssh_extra_args)
    cmd.append(remote_target(config))
    return cmd


def scp_base(config: RemoteConfig, *, batch: bool = False, connect_timeout: int | None = 10) -> list[str]:
    cmd = [config.scp_cmd]
    if config.remote_port and config.remote_port != 22:
        cmd += ["-P", str(config.remote_port)]
    if config.ssh_key:
        cmd += ["-i", os.path.expanduser(os.path.expandvars(config.ssh_key))]
    if config.ssh_config:
        cmd += ["-F", os.path.expanduser(os.path.expandvars(config.ssh_config))]
    if batch:
        cmd += ["-o", "BatchMode=yes"]
    if connect_timeout is not None:
        cmd += ["-o", f"ConnectTimeout={connect_timeout}"]
    cmd += list(config.ssh_extra_args)
    remote_target(config)
    return cmd


def remote_payload(config: RemoteConfig, command: str, *, workdir: str | None = None) -> str:
    parts = ["set -e"]
    if config.cadence_setup:
        parts.append(config.cadence_setup)
    if workdir:
        q_workdir = quote_remote_path(workdir)
        parts.append(f"mkdir -p {q_workdir}")
        parts.append(f"cd {q_workdir}")
    parts.append(command)
    return "\n".join(parts)


def run_remote(
    config: RemoteConfig,
    command: str,
    *,
    workdir: str | None = None,
    timeout: int | None = DEFAULT_SSH_OPERATION_TIMEOUT,
    batch: bool = False,
    connect_timeout: int | None = 10,
) -> CommandResult:
    """Run one remote command.

    Invalid remote identities and paths raise :class:`ValueError`. Executable
    lookup failures and operation timeouts propagate from ``subprocess.run``;
    a completed SSH process is represented by its exact return code.
    """

    if timeout is None:
        timeout = DEFAULT_SSH_OPERATION_TIMEOUT
    if timeout <= 0:
        raise ValueError("operation timeout must be a positive integer")
    payload = remote_payload(config, command, workdir=workdir)
    shell = config.remote_shell or "bash"
    remote_command = f"{quote_remote(shell)} -lc {quote_remote(payload)}"
    proc = subprocess.run(
        ssh_base(config, batch=batch, connect_timeout=connect_timeout) + [remote_command],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")


def upload(
    config: RemoteConfig,
    local_path: str | Path,
    remote_dir: str,
    *,
    batch: bool = True,
    connect_timeout: int | None = 10,
    timeout: int | None = DEFAULT_SSH_OPERATION_TIMEOUT,
) -> int:
    """Upload a file/directory and return the exact ssh/scp return code.

    Invalid inputs raise ``ValueError``/``FileNotFoundError``. Process startup
    errors and ``subprocess.TimeoutExpired`` are intentionally not converted to
    an ambiguous integer status.
    """

    if timeout is None:
        timeout = DEFAULT_SSH_OPERATION_TIMEOUT
    if timeout <= 0:
        raise ValueError("operation timeout must be a positive integer")
    local = Path(local_path).expanduser()
    if not local.exists():
        raise FileNotFoundError(f"local path not found: {local}")
    remote_dir = _validate_remote_path(remote_dir).rstrip("/")
    if not remote_dir:
        raise ValueError("remote directory must not be the filesystem root")
    remote_parent = posixpath.dirname(remote_dir) or "."
    mkdir = run_remote(
        config,
        "\n".join(
            [
                f"mkdir -p -- {quote_remote_path(remote_parent)}",
                f"mkdir -- {quote_remote_path(remote_dir)}",
            ]
        ),
        batch=batch,
        connect_timeout=connect_timeout,
        timeout=timeout,
    )
    if mkdir.returncode != 0:
        if mkdir.stdout:
            print(mkdir.stdout, end="")
        if mkdir.stderr:
            print(mkdir.stderr, end="")
        return mkdir.returncode
    cmd = scp_base(config, batch=batch, connect_timeout=connect_timeout) + [
        "-r",
        str(local.resolve()),
        remote_scp_target(config, remote_dir + "/"),
    ]
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode


def pull(
    config: RemoteConfig,
    remote_path: str,
    local_dir: str | Path,
    *,
    batch: bool = True,
    connect_timeout: int | None = 10,
    timeout: int | None = DEFAULT_SSH_OPERATION_TIMEOUT,
) -> int:
    """Pull a remote file/directory and return the exact scp return code."""

    if timeout is None:
        timeout = DEFAULT_SSH_OPERATION_TIMEOUT
    if timeout <= 0:
        raise ValueError("operation timeout must be a positive integer")
    remote_path = _validate_remote_path(remote_path)
    local = Path(os.path.abspath(Path(local_dir).expanduser()))
    _assert_no_link_components(local, label="Local pull destination")
    if local.exists() or local.is_symlink():
        raise FileExistsError(f"local pull destination already exists; choose a new directory: {local}")
    local.parent.mkdir(parents=True, exist_ok=True)
    local.mkdir(exist_ok=False)
    _assert_no_link_components(local, label="Local pull destination")
    cmd = scp_base(config, batch=batch, connect_timeout=connect_timeout) + [
        "-r",
        remote_scp_target(config, remote_path),
        str(local),
    ]
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode
