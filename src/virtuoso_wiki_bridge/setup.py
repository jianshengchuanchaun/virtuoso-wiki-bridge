"""First-run setup and an opt-in Windows desktop launcher."""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

from .config import DEFAULT_VAULT_NAME, AppConfig, parse_env_file
from .vault import _assert_no_link_components, _write_if_missing, init_vault


def setup_vault_path(path: str | None, env: Path) -> Path:
    if path:
        return Path(path).expanduser().absolute()
    if env.is_file():
        # Existing local selection wins over the new default. Do not switch an
        # existing installation to an empty vault during an upgrade.
        return AppConfig.from_mapping(parse_env_file(env), env_path=env).vault_path
    return env.parent / DEFAULT_VAULT_NAME


def windows_desktop() -> Path:
    """Resolve the user's redirected Desktop (including OneDrive) via Windows."""
    if sys.platform != "win32":
        raise ValueError("Desktop CMD creation is supported on Windows only; use vwb start in your terminal.")
    import ctypes

    buffer = ctypes.create_unicode_buffer(32768)
    # CSIDL_DESKTOPDIRECTORY; unlike ~/Desktop, honors folder redirection.
    result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buffer)
    if result != 0 or not buffer.value:
        raise OSError("Windows could not resolve the Desktop; pass --desktop-dir explicitly.")
    return Path(buffer.value)


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def launcher_text(python: Path, env: Path) -> str:
    # Encoding avoids cmd.exe re-expanding Unicode, %, &, !, and spaces in the
    # configured paths. No user-supplied text is evaluated as PowerShell code.
    script = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        "$env:PYTHONUTF8 = '1'",
        "$env:PYTHONIOENCODING = 'utf-8'",
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new()",
        "$OutputEncoding = [Console]::OutputEncoding",
        f"$global:VwbPython = {_ps_literal(str(python))}",
        f"$global:VwbEnv = {_ps_literal(str(env))}",
        "$env:Path = (Split-Path -Parent $global:VwbPython) + ';' + $env:Path",
        "function global:vwb { & $global:VwbPython -m virtuoso_wiki_bridge.cli --env $global:VwbEnv @args }",
        "Set-Location -LiteralPath (Split-Path -Parent $global:VwbEnv)",
        "vwb start",
    ])
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    command = "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -NoExit -EncodedCommand " + encoded
    if len(command) > 8000:
        raise ValueError("Launcher paths exceed the Windows command length limit.")
    return "@echo off\nsetlocal DisableDelayedExpansion\n" + command + "\n"


def create_desktop_launcher(env: Path, desktop: Path | None = None) -> tuple[Path, bool]:
    if sys.platform != "win32":
        raise ValueError("Desktop CMD creation is supported on Windows only.")
    folder = desktop if desktop is not None else windows_desktop()
    folder = Path(os.path.abspath(folder.expanduser()))
    _assert_no_link_components(folder, label="Desktop directory")
    target = folder / "Start-VirtuosoWiki.cmd"
    created: list[Path] = []
    skipped: list[Path] = []
    _write_if_missing(target, launcher_text(Path(sys.executable), env), created, skipped)
    return target, bool(created)


def run_setup(path: str | None, env: Path, *, desktop: str = "ask", desktop_dir: Path | None = None):
    env = Path(os.path.abspath(env.expanduser()))
    _assert_no_link_components(env, label="Environment path")
    vault = setup_vault_path(path, env)
    if env.is_file() and path:
        configured = AppConfig.from_mapping(parse_env_file(env), env_path=env).vault_path
        if configured != vault.resolve():
            raise ValueError(
                "Existing .env selects a different vault. Use a new --env file for the new vault; "
                "setup does not replace your existing configuration."
            )
    if desktop == "yes" and sys.platform != "win32":
        raise ValueError("--desktop yes is supported on Windows only; use --desktop no.")
    result = init_vault(vault, env_path=env)
    want_desktop = desktop == "yes"
    if desktop == "ask" and sys.platform == "win32" and sys.stdin.isatty():
        try:
            answer = input("是否在桌面创建 Start-VirtuosoWiki.cmd，方便启动知识库和已配置的桥接？[y/N] ")
        except EOFError:
            answer = ""
        want_desktop = answer.strip().lower() in {"y", "yes", "是"}
    launcher = create_desktop_launcher(env, desktop_dir) if want_desktop else None
    return result, launcher
