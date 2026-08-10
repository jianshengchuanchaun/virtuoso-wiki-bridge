from pathlib import Path

import pytest

from virtuoso_wiki_bridge.config import AppConfig, RemoteConfig, load_config, parse_env_file


def test_parse_env_file_preserves_quoted_hash(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "VWB_VAULT_PATH=/vault # comment\n"
        "VWB_VIRTUOSO_BRIDGE_CMD=\"C:/Tools/bridge # literal/virtuoso-bridge.exe\"\n",
        encoding="utf-8",
    )
    values = parse_env_file(env)
    assert values["VWB_VAULT_PATH"] == "/vault"
    assert values["VWB_VIRTUOSO_BRIDGE_CMD"] == "C:/Tools/bridge # literal/virtuoso-bridge.exe"


def test_parse_env_file_decodes_escaped_quote_and_backslash(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text('VALUE="C:/quoted \\"name\\"/back\\\\slash"\n', encoding="utf-8")

    values = parse_env_file(env)

    assert values["VALUE"] == 'C:/quoted "name"/back\\slash'


def test_app_config_defaults_sources() -> None:
    config = AppConfig.from_mapping({"VWB_VAULT_PATH": "/vault"})
    assert config.sources_dir.name == "sources"
    assert config.bridge_cmd == "virtuoso-bridge"


def test_relative_paths_are_resolved_from_env_directory(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    env = config_dir / ".env"
    env.write_text(
        "VWB_VAULT_PATH=./vault\n"
        "VWB_VIRTUOSO_BRIDGE_ENV=./bridge.env\n"
        "VWB_SSH_KEY=./keys/id_ed25519\n",
        encoding="utf-8",
    )

    config = load_config(env, cwd=tmp_path)

    assert config.vault_path == (config_dir / "vault").resolve()
    assert config.sources_dir == (config_dir / "vault" / "sources").resolve()
    assert config.bridge_env == (config_dir / "bridge.env").resolve()
    assert Path(config.remote.ssh_key) == (config_dir / "keys" / "id_ed25519").resolve()


def test_configured_path_variable_markers_are_literal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VWB_LITERAL_MARKER", "expanded-would-be-wrong")
    literal = tmp_path / "$VWB_LITERAL_MARKER" / "%VWB_LITERAL_MARKER%" / "vault"

    config = AppConfig.from_mapping({"VWB_VAULT_PATH": str(literal)})

    assert config.vault_path == literal.resolve()


def test_bridge_profile_is_loaded() -> None:
    config = AppConfig.from_mapping({"VWB_VIRTUOSO_BRIDGE_PROFILE": "gf22"})

    assert config.bridge_profile == "gf22"


def test_app_config_old_positional_constructor_remains_compatible(tmp_path: Path) -> None:
    remote = RemoteConfig()
    config = AppConfig(tmp_path, tmp_path / "sources", "~/work", "virtuoso-bridge", remote)

    assert config.remote is remote
    assert config.bridge_profile == ""
    assert config.bridge_env is None


@pytest.mark.parametrize("value", ["not-a-number", "0", "65536"])
def test_invalid_remote_port_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="VWB_REMOTE_PORT|integer"):
        AppConfig.from_mapping({"VWB_REMOTE_PORT": value})
