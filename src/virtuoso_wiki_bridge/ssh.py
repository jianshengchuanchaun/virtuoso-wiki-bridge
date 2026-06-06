"""Small SSH helpers for optional direct Spectre runs."""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import RemoteConfig


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def quote_remote(value: str) -> str:
    return shlex.quote(value)


def quote_remote_path(value: str) -> str:
    if value == "~":
        return value
    if value.startswith("~/"):
        rest = value[2:]
        return "~/" + quote_remote(rest) if rest else "~/"
    return quote_remote(value)


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
    cmd.append(config.target)
    return cmd


def scp_base(config: RemoteConfig) -> list[str]:
    cmd = [config.scp_cmd]
    if config.remote_port and config.remote_port != 22:
        cmd += ["-P", str(config.remote_port)]
    if config.ssh_key:
        cmd += ["-i", os.path.expanduser(os.path.expandvars(config.ssh_key))]
    if config.ssh_config:
        cmd += ["-F", os.path.expanduser(os.path.expandvars(config.ssh_config))]
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
    timeout: int | None = None,
    batch: bool = False,
) -> CommandResult:
    payload = remote_payload(config, command, workdir=workdir)
    shell = config.remote_shell or "bash"
    remote_command = f"{shell} -lc {quote_remote(payload)}"
    proc = subprocess.run(
        ssh_base(config, batch=batch) + [remote_command],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")


def upload(config: RemoteConfig, local_path: str | Path, remote_dir: str) -> int:
    mkdir = run_remote(config, f"mkdir -p {quote_remote_path(remote_dir)}", batch=True)
    if mkdir.returncode != 0:
        if mkdir.stdout:
            print(mkdir.stdout, end="")
        if mkdir.stderr:
            print(mkdir.stderr, end="")
        return mkdir.returncode
    cmd = scp_base(config) + [
        "-r",
        str(Path(local_path).expanduser()),
        f"{config.target}:{remote_dir.rstrip('/')}/",
    ]
    return subprocess.call(cmd)


def pull(config: RemoteConfig, remote_path: str, local_dir: str | Path) -> int:
    local = Path(local_dir).expanduser()
    local.mkdir(parents=True, exist_ok=True)
    cmd = scp_base(config) + ["-r", f"{config.target}:{remote_path}", str(local)]
    return subprocess.call(cmd)
