"""Configuration for Virtuoso Wiki Bridge."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def _strip_inline_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char in ("'", '"'):
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            continue
        if char == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.strip()


def _unquote(value: str) -> str:
    value = _strip_inline_comment(value.strip())
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_env_file(path: str | Path) -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = Path(path).expanduser()
    if not env_path.is_file():
        raise FileNotFoundError(f".env file not found: {env_path}")
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = _unquote(value)
    return values


def resolve_env_path(explicit: str | Path | None = None, cwd: Path | None = None) -> Path | None:
    base = (cwd or Path.cwd()).resolve()
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = base / path
        return path.resolve()
    local = base / ".env"
    if local.is_file():
        return local
    user = Path.home() / ".virtuoso-wiki-bridge" / ".env"
    if user.is_file():
        return user
    return None


def _int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _split(value: str | None) -> tuple[str, ...]:
    if value is None or value.strip() == "":
        return ()
    return tuple(shlex.split(value, posix=os.name != "nt"))


@dataclass(frozen=True)
class RemoteConfig:
    remote_host: str = ""
    remote_user: str = ""
    remote_port: int = 22
    ssh_key: str = ""
    ssh_config: str = ""
    cadence_setup: str = ""
    remote_shell: str = "bash"
    ssh_cmd: str = "ssh"
    scp_cmd: str = "scp"
    ssh_extra_args: tuple[str, ...] = ()

    @property
    def target(self) -> str:
        if self.remote_user:
            return f"{self.remote_user}@{self.remote_host}"
        return self.remote_host


@dataclass(frozen=True)
class AppConfig:
    vault_path: Path
    sources_dir: Path
    remote_workdir: str
    bridge_cmd: str
    remote: RemoteConfig
    env_path: Path | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, str], env_path: Path | None = None) -> "AppConfig":
        vault = Path(values.get("VWB_VAULT_PATH") or values.get("OBSIDIAN_VAULT_PATH") or ".").expanduser()
        sources = Path(
            values.get("VWB_SOURCES_DIR")
            or values.get("OBSIDIAN_SOURCES_DIR")
            or str(vault / "sources")
        ).expanduser()
        remote = RemoteConfig(
            remote_host=values.get("VWB_REMOTE_HOST", "").strip(),
            remote_user=values.get("VWB_REMOTE_USER", "").strip(),
            remote_port=_int(values.get("VWB_REMOTE_PORT"), 22),
            ssh_key=values.get("VWB_SSH_KEY", "").strip(),
            ssh_config=values.get("VWB_SSH_CONFIG", "").strip(),
            cadence_setup=values.get("VWB_CADENCE_SETUP", "").strip(),
            remote_shell=values.get("VWB_REMOTE_SHELL", "bash").strip() or "bash",
            ssh_cmd=values.get("VWB_SSH_CMD", "ssh").strip() or "ssh",
            scp_cmd=values.get("VWB_SCP_CMD", "scp").strip() or "scp",
            ssh_extra_args=_split(values.get("VWB_SSH_EXTRA_ARGS")),
        )
        return cls(
            vault_path=vault,
            sources_dir=sources,
            remote_workdir=values.get("VWB_REMOTE_WORKDIR", "~/virtuoso-work/virtuoso-wiki-bridge").strip()
            or "~/virtuoso-work/virtuoso-wiki-bridge",
            bridge_cmd=values.get("VWB_VIRTUOSO_BRIDGE_CMD", "virtuoso-bridge").strip() or "virtuoso-bridge",
            remote=remote,
            env_path=env_path,
        )


def load_config(explicit_env: str | Path | None = None, cwd: Path | None = None) -> AppConfig:
    env_path = resolve_env_path(explicit_env, cwd=cwd)
    values = dict(os.environ)
    if env_path is not None:
        values.update(parse_env_file(env_path))
    return AppConfig.from_mapping(values, env_path=env_path)
