import base64
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from virtuoso_wiki_bridge import cli
from virtuoso_wiki_bridge import setup as setup_api
from virtuoso_wiki_bridge.config import DEFAULT_VAULT_NAME, load_config
from virtuoso_wiki_bridge.setup import create_desktop_launcher, launcher_text, run_setup
from virtuoso_wiki_bridge.vault import DEFAULT_FOLDERS, DEFAULT_SOURCE_SUBFOLDERS
from virtuoso_wiki_bridge.virtuoso import RunSummary


def test_setup_default_complete_vault_and_repeat_preserves_user_content(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["setup", "--desktop", "no"]) == 0
    root = tmp_path / DEFAULT_VAULT_NAME
    config = load_config(tmp_path / ".env")
    assert config.vault_path == root
    assert all((root / name).is_dir() for name in DEFAULT_FOLDERS)
    assert all((root / "sources" / name).is_dir() for name in DEFAULT_SOURCE_SUBFOLDERS)
    assert (root / "START_HERE.md").is_file()
    assert len(list((root / ".agents/skills").glob("*/SKILL.md"))) == 3
    assert json.loads((root / ".manifest.json").read_text())["stats"]["total_sources_ingested"] == 0
    user_note = root / "concepts" / "mine.md"
    user_note.write_text("My own note", encoding="utf-8")
    (root / "START_HERE.md").write_text("Customized welcome", encoding="utf-8")
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    env_before = (tmp_path / ".env").read_bytes()
    assert cli.main(["setup", "--desktop", "no"]) == 0
    assert all(p.read_bytes() == value for p, value in before.items())
    assert (tmp_path / ".env").read_bytes() == env_before


def test_setup_uses_config_directory_and_preserves_old_vault_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env = tmp_path / "settings" / "vwb.env"
    result, _ = run_setup(None, env, desktop="no")
    assert result.vault_path == env.parent / DEFAULT_VAULT_NAME
    custom = tmp_path / "chosen"
    other_env = tmp_path / "other.env"
    run_setup(str(custom), other_env, desktop="no")
    result, _ = run_setup(None, other_env, desktop="no")
    assert result.vault_path == custom
    assert not (tmp_path / DEFAULT_VAULT_NAME).exists()


def test_setup_conflicting_path_fails_before_creating_other_vault(tmp_path):
    env = tmp_path / ".env"
    run_setup(None, env, desktop="no")
    before = env.read_bytes()
    with pytest.raises(ValueError, match="different vault"):
        run_setup(str(tmp_path / "different"), env, desktop="no")
    assert env.read_bytes() == before
    assert not (tmp_path / "different").exists()


def test_init_vault_path_is_optional_and_respects_existing_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["init-vault"]) == 0
    assert (tmp_path / DEFAULT_VAULT_NAME / "index.md").is_file()
    assert cli.main(["init-vault"]) == 0


@pytest.mark.parametrize(("answer", "created"), [("y", True), ("是", True), ("", False), ("no", False)])
def test_interactive_desktop_choice(tmp_path, monkeypatch, answer, created):
    monkeypatch.setattr(setup_api.sys, "platform", "win32")
    monkeypatch.setattr(setup_api.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("builtins.input", lambda prompt: answer)
    desktop = tmp_path / "redirected desktop"
    monkeypatch.setattr(setup_api, "windows_desktop", lambda: desktop)
    _, result = run_setup(None, tmp_path / ".env")
    assert bool(result) == created
    assert (desktop / "Start-VirtuosoWiki.cmd").exists() == created


def test_noninteractive_setup_never_prompts_or_creates_desktop(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_api.sys, "platform", "win32")
    monkeypatch.setattr(setup_api.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("Unexpected prompt"))
    _, result = run_setup(None, tmp_path / ".env")
    assert result is None


def test_desktop_yes_creates_launcher_and_preserves_same_named_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(setup_api.sys, "platform", "win32")
    env = tmp_path / ".env"
    desktop = tmp_path / "OneDrive Desktop"
    args = ["setup", "--env", str(env), "--desktop", "yes", "--desktop-dir", str(desktop)]
    assert cli.main(args) == 0
    target = desktop / "Start-VirtuosoWiki.cmd"
    assert target.read_text(encoding="ascii").startswith("@echo off")
    target.write_text("Existing custom launcher", encoding="ascii")
    assert cli.main(args) == 0
    assert target.read_text() == "Existing custom launcher"
    assert "existing file preserved" in capsys.readouterr().out


def test_desktop_unsupported_os_is_clear_and_has_no_setup_side_effects(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_api.sys, "platform", "linux")
    with pytest.raises(ValueError, match="Windows only"):
        run_setup(None, tmp_path / ".env", desktop="yes")
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError, match="Windows only"):
        create_desktop_launcher(tmp_path / ".env", tmp_path)
    with pytest.raises(ValueError, match="Windows only"):
        setup_api.windows_desktop()


def test_desktop_link_ancestor_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_api.sys, "platform", "win32")
    desktop = tmp_path / "desktop"
    def reject(path, *, label):
        raise ValueError("link ancestor")
    monkeypatch.setattr(setup_api, "_assert_no_link_components", reject)
    with pytest.raises(ValueError, match="link ancestor"):
        create_desktop_launcher(tmp_path / ".env", desktop)
    assert not desktop.exists()


def test_launcher_literal_paths_and_command_limit():
    path = Path("Chinese 个人 & %NAME% ! ' quote/.env")
    text = launcher_text(Path(sys.executable), path)
    encoded = text.split("-EncodedCommand ", 1)[1].strip()
    script = base64.b64decode(encoded).decode("utf-16le")
    assert "'' quote" in script
    assert "%NAME%" not in text
    assert str(path).replace("'", "''") in script
    with pytest.raises(ValueError, match="command length"):
        launcher_text(Path("x" * 4000), path)


@pytest.mark.skipif(sys.platform != "win32", reason="executes Windows launcher")
def test_generated_launcher_runs_with_unicode_shell_characters(tmp_path):
    env = tmp_path / "知识库 & %PATH% ! ' config" / ".env"
    result, _ = run_setup(None, env, desktop="no")
    text = launcher_text(Path(sys.executable), env)
    encoded = text.split("-EncodedCommand ", 1)[1].strip()
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-EncodedCommand", encoded],
        capture_output=True, timeout=30, check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    assert str(result.vault_path) in proc.stdout.decode("utf-8")
    assert b"Local mode" in proc.stdout


def test_start_local_and_offline_never_call_bridge(tmp_path, monkeypatch, capsys):
    env = tmp_path / ".env"
    run_setup(None, env, desktop="no")
    monkeypatch.setattr(cli, "run_bridge_command", lambda *a, **k: pytest.fail("Unexpected VM action"))
    assert cli.main(["start", "--env", str(env)]) == 0
    with env.open("a", encoding="utf-8") as handle:
        handle.write("\nVWB_VIRTUOSO_BRIDGE_PROFILE=my-vm\n")
    assert cli.main(["start", "--env", str(env), "--offline"]) == 0
    assert "Local mode" in capsys.readouterr().out


def test_start_configured_bridge_keeps_selector_timeout_and_return_code(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    run_setup(None, env, desktop="no")
    with env.open("a", encoding="utf-8") as handle:
        handle.write("\nVWB_VIRTUOSO_BRIDGE_PROFILE=my-vm\n")
    def fake_run(config, args, *, timeout):
        assert config.bridge_profile == "my-vm"
        assert args == ["start"]
        assert timeout == 12
        return RunSummary(7, "", "connection failed", .2)
    monkeypatch.setattr(cli, "run_bridge_command", fake_run)
    assert cli.main(["start", "--env", str(env), "--timeout", "12"]) == 7


def test_start_missing_vault_has_setup_hint(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text('VWB_VAULT_PATH="./missing"\n', encoding="utf-8")
    assert cli.main(["start", "--env", str(env)]) == 2
    assert "setup first" in capsys.readouterr().err
