import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import virtuoso_wiki_bridge.ssh as ssh
import virtuoso_wiki_bridge.virtuoso as virtuoso
from virtuoso_wiki_bridge.config import RemoteConfig


def app_config(**overrides):
    values = {
        "bridge_cmd": "virtuoso-bridge",
        "bridge_profile": "",
        "bridge_env": "",
        "remote_workdir": "~/vwb-work",
        "remote": RemoteConfig(remote_host="eda.example", remote_user="designer"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "../escape",
        "escape/child",
        r"escape\child",
        "/absolute",
        r"C:\absolute",
        "-option",
        "run name",
        "run;touch-pwned",
        "run\nname",
    ],
)
def test_validate_run_name_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(ValueError, match="run name"):
        virtuoso.validate_run_name(name)


@pytest.mark.parametrize("name", ["ota", "ota-ac_1.2", ".hidden", "运行_一"])
def test_validate_run_name_accepts_safe_unicode_basename(name: str) -> None:
    assert virtuoso.validate_run_name(name) == name


def test_run_spectre_uses_confined_run_dir_and_preserves_spectre_status(tmp_path: Path, monkeypatch) -> None:
    netlist = tmp_path / "tb ota.scs"
    netlist.write_text("simulator lang=spectre", encoding="utf-8")
    config = app_config(remote_workdir="~/work dir")
    seen = {}

    def fake_upload(remote, local_path, remote_dir, **kwargs):
        seen["upload"] = (remote, local_path, remote_dir, kwargs)
        return 0

    def fake_run_remote(remote, command, **kwargs):
        seen["run"] = (remote, command, kwargs)
        return ssh.CommandResult(41, "spectre tail\n", "spectre error\n")

    monkeypatch.setattr(virtuoso, "upload", fake_upload)
    monkeypatch.setattr(virtuoso, "run_remote", fake_run_remote)

    summary = virtuoso.run_spectre_remote(config, netlist, name="ota-run", timeout=73)

    assert summary.returncode == 41
    assert summary.stdout == "spectre tail\n"
    assert summary.stderr == "spectre error\n"
    assert summary.remote_dir == "~/work dir/runs/ota-run"
    assert seen["upload"] == (
        config.remote,
        netlist.resolve(),
        "~/work dir/runs/ota-run",
        {"timeout": 73},
    )
    remote, command, run_kwargs = seen["run"]
    assert remote is config.remote
    assert "spectre './tb ota.scs' +log spectre.out" in command
    assert command.index("set +e") < command.index("spectre ")
    assert command.index("spectre ") < command.index("rc=$?")
    assert command.index("rc=$?") < command.index("tail -n 120")
    assert command.rstrip().endswith('exit "$rc"')
    assert run_kwargs == {
        "workdir": "~/work dir/runs/ota-run",
        "timeout": 73,
        "batch": True,
    }

    payload = ssh.remote_payload(config.remote, command, workdir=summary.remote_dir)
    assert payload.index("set -e") < payload.index("set +e")
    assert payload.index("set +e") < payload.index("spectre ")
    assert payload.rstrip().endswith('exit "$rc"')


def test_run_spectre_rejects_malicious_name_before_transfer(tmp_path: Path, monkeypatch) -> None:
    netlist = tmp_path / "tb.scs"
    netlist.write_text("", encoding="utf-8")

    def unexpected_upload(*args, **kwargs):
        raise AssertionError("unsafe run name must be rejected before upload")

    monkeypatch.setattr(virtuoso, "upload", unexpected_upload)

    with pytest.raises(ValueError, match="run name"):
        virtuoso.run_spectre_remote(app_config(), netlist, name="../../escape")


def test_run_spectre_rejects_unsafe_implicit_netlist_stem(tmp_path: Path, monkeypatch) -> None:
    netlist = tmp_path / "unsafe stem.scs"
    netlist.write_text("", encoding="utf-8")

    def unexpected_upload(*args, **kwargs):
        raise AssertionError("unsafe implicit run name must be rejected before upload")

    monkeypatch.setattr(virtuoso, "upload", unexpected_upload)

    with pytest.raises(ValueError, match="run name"):
        virtuoso.run_spectre_remote(app_config(), netlist)


def test_run_spectre_prefixes_option_like_netlist_basename(tmp_path: Path, monkeypatch) -> None:
    netlist = tmp_path / "+option.scs"
    netlist.write_text("simulator lang=spectre", encoding="utf-8")
    seen = {}

    monkeypatch.setattr(virtuoso, "upload", lambda *args, **kwargs: 0)

    def fake_run_remote(remote, command, **kwargs):
        seen["command"] = command
        return ssh.CommandResult(0, "", "")

    monkeypatch.setattr(virtuoso, "run_remote", fake_run_remote)

    virtuoso.run_spectre_remote(app_config(), netlist, name="safe-run")

    assert "spectre ./+option.scs +log spectre.out" in seen["command"]


def test_run_spectre_returns_upload_status_without_remote_execution(tmp_path: Path, monkeypatch) -> None:
    netlist = tmp_path / "tb.scs"
    netlist.write_text("", encoding="utf-8")
    monkeypatch.setattr(virtuoso, "upload", lambda *args, **kwargs: 12)

    def unexpected_run(*args, **kwargs):
        raise AssertionError("Spectre must not run after upload failure")

    monkeypatch.setattr(virtuoso, "run_remote", unexpected_run)

    summary = virtuoso.run_spectre_remote(app_config(), netlist, name="failed-run", timeout=9)

    assert summary.returncode == 12
    assert summary.stderr == "upload failed with return code 12"
    assert summary.remote_dir == "~/vwb-work/runs/failed-run"


def test_run_spectre_missing_host_returns_configuration_status(tmp_path: Path, monkeypatch) -> None:
    netlist = tmp_path / "tb.scs"
    netlist.write_text("", encoding="utf-8")
    config = app_config(remote=RemoteConfig())

    def unexpected_upload(*args, **kwargs):
        raise AssertionError("upload must not run without a remote host")

    monkeypatch.setattr(virtuoso, "upload", unexpected_upload)

    summary = virtuoso.run_spectre_remote(config, netlist, name="ota-run")

    assert summary.returncode == 2
    assert "VWB_REMOTE_HOST is empty" in summary.stderr
    assert summary.remote_dir == ""


def test_pull_remote_run_builds_path_from_safe_run_name(tmp_path: Path, monkeypatch) -> None:
    seen = {}

    def fake_pull(remote, remote_path, local_dir, **kwargs):
        seen["call"] = (remote, remote_path, local_dir, kwargs)
        return 6

    monkeypatch.setattr(virtuoso, "pull", fake_pull)
    config = app_config(remote_workdir="~/work dir/")
    local = tmp_path / "result"

    rc = virtuoso.pull_remote_run(config, "ota-run", local, timeout=27)

    assert rc == 6
    assert seen["call"] == (
        config.remote,
        "~/work dir/runs/ota-run/",
        local,
        {"timeout": 27},
    )


def test_pull_remote_run_rejects_path_instead_of_accepting_arbitrary_remote_dir(tmp_path: Path, monkeypatch) -> None:
    def unexpected_pull(*args, **kwargs):
        raise AssertionError("unsafe run name must be rejected before pull")

    monkeypatch.setattr(virtuoso, "pull", unexpected_pull)

    with pytest.raises(ValueError, match="run name"):
        virtuoso.pull_remote_run(app_config(), "~/other/path", tmp_path / "result")


def test_bridge_command_forwards_profile_and_env_after_subcommand_args(monkeypatch, tmp_path: Path) -> None:
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 4, stdout="out", stderr="err")

    monkeypatch.setattr(virtuoso.subprocess, "run", fake_run)
    bridge_env = tmp_path / "bridge.env"
    config = app_config(bridge_profile="lab", bridge_env=bridge_env)

    summary = virtuoso.run_bridge_command(config, ["status"], timeout=18)

    assert summary.returncode == 4
    assert summary.stdout == "out"
    assert summary.stderr == "err"
    assert seen["argv"] == [
        "virtuoso-bridge",
        "status",
        "--profile",
        "lab",
        "--env",
        str(bridge_env),
    ]
    assert seen["kwargs"] == {
        "text": True,
        "capture_output": True,
        "timeout": 18,
        "check": False,
    }


def test_bridge_command_remains_compatible_without_new_config_fields(monkeypatch) -> None:
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(virtuoso.subprocess, "run", fake_run)
    old_config = SimpleNamespace(bridge_cmd="virtuoso-bridge")

    virtuoso.run_bridge_command(old_config, ["status"])

    assert seen["argv"] == ["virtuoso-bridge", "status"]


def test_eval_and_load_forward_timeout_to_upstream_and_outer_process(tmp_path: Path, monkeypatch) -> None:
    skill = tmp_path / "probe.il"
    skill.write_text("getCurrentTime()", encoding="utf-8")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(virtuoso.subprocess, "run", fake_run)
    config = app_config(bridge_profile="lab", bridge_env="C:/configs/bridge.env")

    virtuoso.eval_skill(config, "getCurrentTime()", timeout=25)
    virtuoso.load_skill(config, skill, timeout=40)

    assert calls[0][0] == [
        "virtuoso-bridge",
        "eval",
        "getCurrentTime()",
        "--timeout",
        "25",
        "--profile",
        "lab",
        "--env",
        "C:/configs/bridge.env",
    ]
    assert calls[0][1]["timeout"] == 25 + virtuoso.UPSTREAM_TIMEOUT_GRACE
    assert calls[1][0] == [
        "virtuoso-bridge",
        "load",
        str(skill.resolve()),
        "--timeout",
        "40",
        "--profile",
        "lab",
        "--env",
        "C:/configs/bridge.env",
    ]
    assert calls[1][1]["timeout"] == 40 + virtuoso.UPSTREAM_TIMEOUT_GRACE


def test_bridge_timeout_exception_is_not_collapsed_to_return_code(monkeypatch) -> None:
    def timed_out(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(virtuoso.subprocess, "run", timed_out)

    with pytest.raises(subprocess.TimeoutExpired):
        virtuoso.eval_skill(app_config(), "getCurrentTime()", timeout=2)


def test_live_wrappers_use_finite_defaults(tmp_path: Path, monkeypatch) -> None:
    skill = tmp_path / "probe.il"
    skill.write_text("getCurrentTime()", encoding="utf-8")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(virtuoso.subprocess, "run", fake_run)
    config = app_config()

    virtuoso.eval_skill(config, "getCurrentTime()")
    virtuoso.load_skill(config, skill)
    virtuoso.snapshot(config)

    assert calls[0][0][-2:] == ["--timeout", str(virtuoso.DEFAULT_EVAL_TIMEOUT)]
    assert calls[0][1]["timeout"] == virtuoso.DEFAULT_EVAL_TIMEOUT + virtuoso.UPSTREAM_TIMEOUT_GRACE
    assert calls[1][0][-2:] == ["--timeout", str(virtuoso.DEFAULT_LOAD_TIMEOUT)]
    assert calls[1][1]["timeout"] == virtuoso.DEFAULT_LOAD_TIMEOUT + virtuoso.UPSTREAM_TIMEOUT_GRACE
    assert calls[2][1]["timeout"] == virtuoso.DEFAULT_SNAPSHOT_TIMEOUT


@pytest.mark.parametrize("command", ["eval", "load"])
def test_missing_upstream_command_gets_clear_compatibility_error(tmp_path: Path, monkeypatch, command: str) -> None:
    skill = tmp_path / "probe.il"
    skill.write_text("getCurrentTime()", encoding="utf-8")

    def fake_run(argv, **kwargs):
        stderr = f"argument command: invalid choice: '{command}' (choose from 'status', 'snapshot')"
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr=stderr)

    monkeypatch.setattr(virtuoso.subprocess, "run", fake_run)
    config = app_config()

    summary = (
        virtuoso.eval_skill(config, "getCurrentTime()")
        if command == "eval"
        else virtuoso.load_skill(config, skill)
    )

    assert summary.returncode == 2
    assert f"does not support the '{command}' command" in summary.stderr
    assert "current upstream main branch" in summary.stderr
    assert "upstream error:" in summary.stderr
