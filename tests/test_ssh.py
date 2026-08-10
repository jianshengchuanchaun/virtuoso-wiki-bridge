import subprocess
from pathlib import Path

import pytest

import virtuoso_wiki_bridge.ssh as ssh
from virtuoso_wiki_bridge.config import RemoteConfig


def remote_config(**overrides) -> RemoteConfig:
    values = {
        "remote_host": "eda.example",
        "remote_user": "designer",
        "remote_port": 2222,
        "ssh_key": "",
        "ssh_config": "",
        "remote_shell": "bash",
        "ssh_cmd": "ssh",
        "scp_cmd": "scp",
        "ssh_extra_args": ("-J", "jump@example", "-o", "StrictHostKeyChecking=yes"),
    }
    values.update(overrides)
    return RemoteConfig(**values)


@pytest.mark.parametrize("host", ["", "-proxy", "eda host", "eda\thost", "eda\nhost", "eda\x7fhost"])
def test_remote_host_rejects_unsafe_argv_values(host: str) -> None:
    with pytest.raises(ValueError, match="remote host"):
        ssh.ssh_base(remote_config(remote_host=host))


@pytest.mark.parametrize("user", ["-root", "bad user", "bad\tuser", "bad\nuser", "bad\x7fuser"])
def test_remote_user_rejects_unsafe_argv_values(user: str) -> None:
    with pytest.raises(ValueError, match="remote user"):
        ssh.scp_base(remote_config(remote_user=user))


def test_empty_remote_user_is_allowed() -> None:
    config = remote_config(remote_user="")
    assert ssh.remote_target(config) == "eda.example"
    assert ssh.ssh_base(config)[-1] == "eda.example"


def test_ssh_and_scp_base_include_safe_connection_options() -> None:
    config = remote_config()

    ssh_argv = ssh.ssh_base(config, batch=True, connect_timeout=7)
    scp_argv = ssh.scp_base(config, batch=True, connect_timeout=7)

    assert ssh_argv == [
        "ssh",
        "-p",
        "2222",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=7",
        "-J",
        "jump@example",
        "-o",
        "StrictHostKeyChecking=yes",
        "designer@eda.example",
    ]
    assert scp_argv == [
        "scp",
        "-P",
        "2222",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=7",
        "-J",
        "jump@example",
        "-o",
        "StrictHostKeyChecking=yes",
    ]


def test_remote_scp_target_shell_quotes_remote_path() -> None:
    config = remote_config()
    remote_path = "~/runs/OTA run/it's ready/"

    operand = ssh.remote_scp_target(config, remote_path)

    assert operand == f"designer@eda.example:{ssh.quote_remote_path(remote_path)}"
    assert operand.startswith("designer@eda.example:~/")
    assert "OTA run" in operand
    assert "'\"'\"'" in operand


def test_run_remote_passes_batch_connect_and_operation_timeouts(monkeypatch) -> None:
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 17, stdout="out", stderr="err")

    monkeypatch.setattr(ssh.subprocess, "run", fake_run)

    result = ssh.run_remote(
        remote_config(),
        "printf ok",
        workdir="~/work dir",
        timeout=31,
        batch=True,
        connect_timeout=6,
    )

    assert result == ssh.CommandResult(17, "out", "err")
    assert seen["argv"][:-1] == ssh.ssh_base(remote_config(), batch=True, connect_timeout=6)
    payload = ssh.remote_payload(remote_config(), "printf ok", workdir="~/work dir")
    assert seen["argv"][-1] == f"bash -lc {ssh.quote_remote(payload)}"
    assert "set -e" in payload
    assert "mkdir -p ~/'work dir'" in payload
    assert seen["kwargs"] == {
        "text": True,
        "capture_output": True,
        "timeout": 31,
        "check": False,
    }


def test_run_remote_quotes_configured_shell_as_one_executable(monkeypatch) -> None:
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(ssh.subprocess, "run", fake_run)

    ssh.run_remote(remote_config(remote_shell="bash; printf INJECTED"), "printf ok")

    assert seen["argv"][-1].startswith("'bash; printf INJECTED' -lc ")
    assert seen["argv"][-1].count("printf INJECTED") == 1


def test_upload_uses_quoted_scp_target_and_returns_child_status(tmp_path: Path, monkeypatch) -> None:
    local = tmp_path / "net list.scs"
    local.write_text("simulator lang=spectre", encoding="utf-8")
    seen = {}

    def fake_run_remote(config, command, **kwargs):
        seen["mkdir"] = (config, command, kwargs)
        return ssh.CommandResult(0, "", "")

    def fake_run(argv, **kwargs):
        seen["scp"] = (argv, kwargs)
        return subprocess.CompletedProcess(argv, 9, stdout="", stderr="copy failed")

    monkeypatch.setattr(ssh, "run_remote", fake_run_remote)
    monkeypatch.setattr(ssh.subprocess, "run", fake_run)

    rc = ssh.upload(
        remote_config(),
        local,
        "~/work dir/runs/ota-run",
        batch=True,
        connect_timeout=8,
        timeout=42,
    )

    assert rc == 9
    _, mkdir_command, mkdir_kwargs = seen["mkdir"]
    assert mkdir_command == (
        "mkdir -p -- ~/'work dir/runs'\n"
        "mkdir -- ~/'work dir/runs/ota-run'"
    )
    assert mkdir_kwargs == {"batch": True, "connect_timeout": 8, "timeout": 42}
    scp_argv, scp_kwargs = seen["scp"]
    assert scp_argv[-3] == "-r"
    assert scp_argv[-2] == str(local.resolve())
    assert scp_argv[-1] == "designer@eda.example:~/'work dir/runs/ota-run/'"
    assert "-J" in scp_argv
    assert scp_kwargs == {
        "text": True,
        "capture_output": True,
        "timeout": 42,
        "check": False,
    }


def test_upload_returns_mkdir_status_without_starting_scp(tmp_path: Path, monkeypatch) -> None:
    local = tmp_path / "tb.scs"
    local.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        ssh,
        "run_remote",
        lambda *args, **kwargs: ssh.CommandResult(23, "", "mkdir failed"),
    )

    def unexpected_run(*args, **kwargs):
        raise AssertionError("scp must not run after mkdir failure")

    monkeypatch.setattr(ssh.subprocess, "run", unexpected_run)

    assert ssh.upload(remote_config(), local, "~/runs/test") == 23


def test_pull_uses_quoted_remote_operand_and_timeout(tmp_path: Path, monkeypatch) -> None:
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 5, stdout="", stderr="pull failed")

    monkeypatch.setattr(ssh.subprocess, "run", fake_run)

    local = tmp_path / "download"
    rc = ssh.pull(
        remote_config(),
        "~/work dir/runs/ota-run/",
        local,
        batch=True,
        connect_timeout=4,
        timeout=55,
    )

    assert rc == 5
    assert local.is_dir()
    assert seen["argv"][-2] == "designer@eda.example:~/'work dir/runs/ota-run/'"
    assert seen["argv"][-1] == str(local.resolve())
    assert seen["kwargs"]["timeout"] == 55


def test_pull_refuses_existing_local_destination_before_scp(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "download"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    def unexpected_run(*args, **kwargs):
        raise AssertionError("scp must not run for an existing destination")

    monkeypatch.setattr(ssh.subprocess, "run", unexpected_run)

    with pytest.raises(FileExistsError, match="already exists"):
        ssh.pull(remote_config(), "~/runs/ota-run/", destination)

    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_pull_propagates_operation_timeout(tmp_path: Path, monkeypatch) -> None:
    def timed_out(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(ssh.subprocess, "run", timed_out)

    with pytest.raises(subprocess.TimeoutExpired):
        ssh.pull(remote_config(), "~/runs/ota-run/", tmp_path / "download", timeout=3)


def test_upload_rejects_missing_local_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="local path not found"):
        ssh.upload(remote_config(), tmp_path / "missing.scs", "~/runs/test")


@pytest.mark.parametrize("remote_path", ["", "bad\npath", "bad\x7fpath"])
def test_remote_path_rejects_control_characters(remote_path: str) -> None:
    with pytest.raises(ValueError, match="remote path"):
        ssh.remote_scp_target(remote_config(), remote_path)
