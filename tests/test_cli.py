from pathlib import Path
from types import SimpleNamespace

import pytest

import virtuoso_wiki_bridge.cli as cli
from virtuoso_wiki_bridge.extract import ExtractionResult


def write_env(path: Path, vault: Path) -> None:
    path.write_text(
        f"VWB_VAULT_PATH={vault.as_posix()}\n"
        f"VWB_SOURCES_DIR={(vault / 'sources').as_posix()}\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--env", "before.env", "doctor"], "before.env"),
        (["doctor", "--env", "after.env"], "after.env"),
        (["--env", "before.env", "init-vault", "vault"], "before.env"),
        (["init-vault", "vault", "--env", "after.env"], "after.env"),
    ],
)
def test_env_option_works_before_or_after_subcommand(argv: list[str], expected: str) -> None:
    args = cli.build_parser().parse_args(argv)

    assert args.env == expected


def test_env_before_subcommand_is_not_silently_overwritten(tmp_path: Path, capsys) -> None:
    vault = tmp_path / "selected-vault"
    sources = vault / "sources"
    sources.mkdir(parents=True)
    env = tmp_path / "selected.env"
    write_env(env, vault)

    rc = cli.main(["--env", str(env), "extract-sources"])

    output = capsys.readouterr().out
    assert rc == 0
    assert f"env: {env.resolve()}" in output
    assert f"vault: {vault.resolve()}" in output
    assert f"sources: {sources.resolve()}" in output


def test_init_vault_uses_env_option_as_generated_env_path(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    env = tmp_path / "config" / "vwb.env"

    rc = cli.main(["init-vault", str(vault), "--env", str(env)])

    assert rc == 0
    assert vault.is_dir()
    assert env.is_file()


def test_init_vault_rejects_conflicting_env_aliases(tmp_path: Path, capsys) -> None:
    rc = cli.main(
        [
            "init-vault",
            str(tmp_path / "vault"),
            "--env",
            str(tmp_path / "one.env"),
            "--env-path",
            str(tmp_path / "two.env"),
        ]
    )

    assert rc == 2
    assert "must refer to the same file" in capsys.readouterr().err


@pytest.mark.parametrize("category", ["../escape", "custom", "extracted"])
def test_ingest_rejects_category_outside_allowed_input_folders(category: str) -> None:
    with pytest.raises(SystemExit) as error:
        cli.build_parser().parse_args(["ingest-source", "source.txt", "--category", category])

    assert error.value.code == 2


def test_ingest_empty_extraction_returns_nonzero(tmp_path: Path, monkeypatch, capsys) -> None:
    vault = tmp_path / "vault"
    sources = vault / "sources"
    sources.mkdir(parents=True)
    env = tmp_path / ".env"
    write_env(env, vault)
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-test")

    def fake_extract(
        copied: Path,
        extracted_dir: Path,
        *,
        force: bool,
        source_root: Path,
    ) -> ExtractionResult:
        assert copied.parent == sources / "books"
        assert extracted_dir == sources / "extracted"
        assert source_root == sources
        assert force is False
        return ExtractionResult(copied, extracted_dir / "books" / "scan.pdf.txt", "empty", "scanned", 0)

    monkeypatch.setattr(cli, "extract_source", fake_extract)

    rc = cli.main(["ingest-source", str(source), "--env", str(env)])

    assert rc == 1
    assert "extraction: empty scanned" in capsys.readouterr().out


def test_expected_operational_error_has_no_traceback(capsys, tmp_path: Path) -> None:
    rc = cli.main(["ingest-source", str(tmp_path / "missing.txt")])

    captured = capsys.readouterr()
    assert rc == 2
    assert "error:" in captured.err
    assert "missing.txt" in captured.err
    assert "Traceback" not in captured.err


def test_pull_run_passes_safe_run_name_and_timeout(tmp_path: Path, monkeypatch, capsys) -> None:
    seen = {}
    config = SimpleNamespace()
    monkeypatch.setattr(cli, "load_config", lambda env: config)

    def fake_pull(received_config, run_name, local_dir, *, timeout):
        seen["call"] = (received_config, run_name, local_dir, timeout)
        return 7

    monkeypatch.setattr(cli, "pull_remote_run", fake_pull)
    local_dir = tmp_path / "results"

    rc = cli.main(["pull-run", "ota-safe", str(local_dir), "--timeout", "30"])

    assert rc == 7
    assert seen["call"] == (config, "ota-safe", local_dir, 30)
    assert "returncode: 7" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["0", "-1"])
def test_timeout_must_be_positive(value: str) -> None:
    with pytest.raises(SystemExit) as error:
        cli.build_parser().parse_args(["run-spectre", "tb.scs", "--timeout", value])

    assert error.value.code == 2


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["eval-skill", "1+1"], cli.DEFAULT_EVAL_TIMEOUT),
        (["load-skill", "probe.il"], cli.DEFAULT_LOAD_TIMEOUT),
        (["snapshot"], cli.DEFAULT_SNAPSHOT_TIMEOUT),
        (["run-spectre", "tb.scs"], cli.DEFAULT_SPECTRE_TIMEOUT),
        (["pull-run", "ota", "results"], cli.DEFAULT_PULL_TIMEOUT),
    ],
)
def test_live_commands_have_finite_default_timeout(argv: list[str], expected: int) -> None:
    assert cli.build_parser().parse_args(argv).timeout == expected


def test_version_matches_package(capsys) -> None:
    rc = cli.main(["--version"])

    assert rc == 0
    assert capsys.readouterr().out.strip() == f"virtuoso-wiki-bridge {cli.__version__}"


@pytest.mark.parametrize("command", ["search", "ask-pack"])
def test_retrieval_cli_escapes_terminal_control_sequences(tmp_path: Path, monkeypatch, capsys, command: str) -> None:
    vault = tmp_path / "vault"
    sources = vault / "sources"
    sources.mkdir(parents=True)
    (sources / "malicious.md").write_text(
        "# \x1b]52;c;UkVEVEVBTV9DTElQQk9BUkQ=\x07\nneedle phase margin",
        encoding="utf-8",
    )
    config = SimpleNamespace(vault_path=vault, sources_dir=sources)
    monkeypatch.setattr(cli, "load_config", lambda env: config)

    rc = cli.main([command, "needle phase margin"])

    output = capsys.readouterr().out
    assert rc == 0
    assert "\x1b" not in output
    assert "\x07" not in output
    assert "\\u001b" in output
    assert "\\u0007" in output


def test_child_process_summary_escapes_terminal_controls(capsys) -> None:
    summary = SimpleNamespace(
        stdout="stdout \x1b[31mred\x1b[0m\n",
        stderr="stderr \x07\u202e\n",
        remote_dir="run\x1bdir",
        elapsed_seconds=1.25,
        returncode=7,
    )

    rc = cli._print_summary(summary)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert rc == 7
    assert "\x1b" not in combined
    assert "\x07" not in combined
    assert "\u202e" not in combined
    assert "\\u001b" in combined
    assert "\\u0007" in combined
    assert "\\u202e" in combined
