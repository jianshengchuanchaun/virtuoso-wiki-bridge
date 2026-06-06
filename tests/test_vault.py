from pathlib import Path

from virtuoso_wiki_bridge.vault import DEFAULT_FOLDERS, DEFAULT_SOURCE_SUBFOLDERS, init_vault


def test_init_vault_creates_obsidian_style_structure(tmp_path: Path) -> None:
    result = init_vault(tmp_path / "vault", env_path=tmp_path / ".env")

    for folder in DEFAULT_FOLDERS:
        assert (result.vault_path / folder).is_dir()
        assert (result.vault_path / folder / "README.md").is_file()

    assert (result.vault_path / "sources" / "books").is_dir()
    assert (result.vault_path / "sources" / "papers").is_dir()
    assert (result.vault_path / "sources" / "manuals").is_dir()
    assert (result.vault_path / "sources" / "datasheets").is_dir()
    assert (result.vault_path / "sources" / "circuits").is_dir()
    assert (result.vault_path / "sources" / "spectre").is_dir()
    assert (result.vault_path / "sources" / "skill").is_dir()
    assert (result.vault_path / "sources" / "logs").is_dir()
    assert (result.vault_path / "sources" / "notes").is_dir()
    assert (result.vault_path / "sources" / "extracted").is_dir()
    for subfolder in DEFAULT_SOURCE_SUBFOLDERS:
        assert (result.vault_path / "sources" / subfolder / "README.md").is_file()
    assert (result.vault_path / "index.md").is_file()
    assert (result.vault_path / "hot.md").is_file()
    assert (result.vault_path / ".obsidian" / "app.json").is_file()
    assert (result.vault_path / ".manifest.json").is_file()

    env_text = result.env_path.read_text(encoding="utf-8")
    assert "VWB_VAULT_PATH=" in env_text
    assert "VWB_SOURCES_DIR=" in env_text
    assert "OBSIDIAN_VAULT_PATH=" in env_text
    assert "OBSIDIAN_SOURCES_DIR=" in env_text
