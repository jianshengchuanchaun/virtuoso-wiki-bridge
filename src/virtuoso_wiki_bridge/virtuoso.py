"""Virtuoso and Spectre bridge commands."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .ssh import pull, quote_remote, run_remote, upload


@dataclass(frozen=True)
class RunSummary:
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    remote_dir: str = ""


def bridge_available(config: AppConfig) -> bool:
    return shutil.which(config.bridge_cmd) is not None or Path(config.bridge_cmd).is_file()


def run_bridge_command(config: AppConfig, args: list[str], *, timeout: int | None = None) -> RunSummary:
    start = time.monotonic()
    proc = subprocess.run(
        [config.bridge_cmd] + args,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return RunSummary(proc.returncode, proc.stdout or "", proc.stderr or "", time.monotonic() - start)


def status(config: AppConfig) -> RunSummary:
    return run_bridge_command(config, ["status"], timeout=60)


def eval_skill(config: AppConfig, expr: str, *, timeout: int | None = None) -> RunSummary:
    return run_bridge_command(config, ["eval", expr], timeout=timeout)


def load_skill(config: AppConfig, path: Path, *, timeout: int | None = None) -> RunSummary:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SKILL file not found: {path}")
    return run_bridge_command(config, ["load", str(path)], timeout=timeout)


def snapshot(config: AppConfig, output_dir: Path | None = None, *, timeout: int | None = None) -> RunSummary:
    args = ["snapshot"]
    if output_dir is not None:
        args += ["-o", str(output_dir)]
    return run_bridge_command(config, args, timeout=timeout)


def run_spectre_remote(
    config: AppConfig,
    netlist: Path,
    *,
    name: str | None = None,
    timeout: int | None = None,
) -> RunSummary:
    netlist = netlist.expanduser().resolve()
    if not netlist.is_file():
        raise FileNotFoundError(f"Spectre netlist not found: {netlist}")
    if not config.remote.remote_host:
        return RunSummary(2, "", "VWB_REMOTE_HOST is empty; configure SSH or use virtuoso-bridge spectre support.", 0.0)
    run_name = name or netlist.stem
    remote_dir = f"{config.remote_workdir.rstrip('/')}/runs/{run_name}"
    rc = upload(config.remote, netlist, remote_dir)
    if rc != 0:
        return RunSummary(rc, "", f"upload failed with return code {rc}", 0.0, remote_dir)
    start = time.monotonic()
    q_netlist = quote_remote(netlist.name)
    command = f"rm -f spectre.out; spectre {q_netlist} +log spectre.out; rc=$?; tail -120 spectre.out; exit $rc"
    result = run_remote(config.remote, command, workdir=remote_dir, timeout=timeout, batch=True)
    return RunSummary(result.returncode, result.stdout, result.stderr, time.monotonic() - start, remote_dir)


def pull_remote_run(config: AppConfig, remote_dir: str, local_dir: Path) -> int:
    return pull(config.remote, remote_dir.rstrip("/") + "/", local_dir)


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
