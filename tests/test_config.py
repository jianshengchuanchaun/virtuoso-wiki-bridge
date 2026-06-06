from pathlib import Path

from virtuoso_wiki_bridge.config import AppConfig, parse_env_file


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


def test_app_config_defaults_sources() -> None:
    config = AppConfig.from_mapping({"VWB_VAULT_PATH": "/vault"})
    assert config.sources_dir.name == "sources"
    assert config.bridge_cmd == "virtuoso-bridge"
