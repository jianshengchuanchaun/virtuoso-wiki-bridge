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
        quote = value[0]
        inner = value[1:-1]
        decoded: list[str] = []
        index = 0
        while index < len(inner):
            char = inner[index]
            if char == "\\" and index + 1 < len(inner) and inner[index + 1] in ("\\", quote):
                index += 1
                char = inner[index]
            decoded.append(char)
            index += 1
        return "".join(decoded)
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
    except ValueError as exc:
        raise ValueError(f"expected an integer, got {value!r}") from exc


def _split(value: str | None) -> tuple[str, ...]:
    if value is None or value.strip() == "":
        return ()
    return tuple(shlex.split(value, posix=os.name != "nt"))


def _local_path(value: str | Path, *, base: Path) -> Path:
    # Treat configured path text literally (apart from ``~``). Automatic
    # ``$NAME``/``%NAME%`` expansion corrupts legitimate filenames and makes a
    # generated .env fail to round-trip.
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


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
    bridge_profile: str = ""
    bridge_env: Path | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, str], env_path: Path | None = None) -> "AppConfig":
        base = env_path.parent.resolve() if env_path is not None else Path.cwd().resolve()
        vault = _local_path(
            values.get("VWB_VAULT_PATH") or values.get("OBSIDIAN_VAULT_PATH") or ".",
            base=base,
        )
        sources_value = values.get("VWB_SOURCES_DIR") or values.get("OBSIDIAN_SOURCES_DIR")
        sources = _local_path(sources_value, base=base) if sources_value else (vault / "sources").resolve()
        try:
            remote_port = _int(values.get("VWB_REMOTE_PORT"), 22)
        except ValueError as exc:
            raise ValueError(f"VWB_REMOTE_PORT {exc}") from exc
        if not 1 <= remote_port <= 65535:
            raise ValueError(f"VWB_REMOTE_PORT must be between 1 and 65535, got {remote_port}")
        bridge_env_value = values.get("VWB_VIRTUOSO_BRIDGE_ENV", "").strip()
        bridge_env = _local_path(bridge_env_value, base=base) if bridge_env_value else None
        ssh_key_value = values.get("VWB_SSH_KEY", "").strip()
        ssh_config_value = values.get("VWB_SSH_CONFIG", "").strip()
        remote = RemoteConfig(
            remote_host=values.get("VWB_REMOTE_HOST", "").strip(),
            remote_user=values.get("VWB_REMOTE_USER", "").strip(),
            remote_port=remote_port,
            ssh_key=str(_local_path(ssh_key_value, base=base)) if ssh_key_value else "",
            ssh_config=str(_local_path(ssh_config_value, base=base)) if ssh_config_value else "",
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
            bridge_profile=values.get("VWB_VIRTUOSO_BRIDGE_PROFILE", "").strip(),
            bridge_env=bridge_env,
            remote=remote,
            env_path=env_path,
        )


def load_config(explicit_env: str | Path | None = None, cwd: Path | None = None) -> AppConfig:
    env_path = resolve_env_path(explicit_env, cwd=cwd)
    values = dict(os.environ)
    if env_path is not None:
        values.update(parse_env_file(env_path))
    return AppConfig.from_mapping(values, env_path=env_path)
