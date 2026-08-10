import shutil
import subprocess
from pathlib import Path

import pytest

import virtuoso_wiki_bridge.vault as vault_module
from virtuoso_wiki_bridge.config import load_config
from virtuoso_wiki_bridge.vault import (
    DEFAULT_FOLDERS,
    DEFAULT_SOURCE_SUBFOLDERS,
    GITIGNORE_TEXT,
    init_vault,
)

REQUIRED_FRONTMATTER_FIELDS = ("title:", "category:", "tags:", "sources:", "created:", "updated:")


def assert_has_required_frontmatter(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, frontmatter, _ = text.split("---", 2)
    for field in REQUIRED_FRONTMATTER_FIELDS:
        assert any(line.startswith(field) for line in frontmatter.splitlines()), f"{path} is missing {field}"


def test_init_vault_creates_obsidian_style_structure(tmp_path: Path) -> None:
    result = init_vault(tmp_path / "vault", env_path=tmp_path / ".env")

    for folder in DEFAULT_FOLDERS:
        assert (result.vault_path / folder).is_dir()
        readme = result.vault_path / folder / "README.md"
        assert readme.is_file()
        assert_has_required_frontmatter(readme)

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
        readme = result.vault_path / "sources" / subfolder / "README.md"
        assert readme.is_file()
        assert_has_required_frontmatter(readme)
    assert (result.vault_path / "index.md").is_file()
    assert (result.vault_path / "hot.md").is_file()
    assert (result.vault_path / ".gitignore").is_file()
    assert (result.vault_path / ".obsidian" / "app.json").is_file()
    assert (result.vault_path / ".manifest.json").is_file()
    for page_name in ("index.md", "log.md", "hot.md"):
        assert_has_required_frontmatter(result.vault_path / page_name)

    env_text = result.env_path.read_text(encoding="utf-8")
    assert "VWB_VAULT_PATH=" in env_text
    assert "VWB_SOURCES_DIR=" in env_text
    assert "OBSIDIAN_VAULT_PATH=" in env_text
    assert "OBSIDIAN_SOURCES_DIR=" in env_text
    assert "VWB_VIRTUOSO_BRIDGE_PROFILE=" in env_text
    assert "VWB_VIRTUOSO_BRIDGE_ENV=" in env_text
    assert "VWB_SSH_CONFIG=" in env_text
    assert "VWB_SSH_EXTRA_ARGS=" in env_text

    log_text = (result.vault_path / "log.md").read_text(encoding="utf-8")
    assert result.vault_path.as_posix() not in log_text


def test_generated_env_round_trips_spaces_hash_unicode_and_variable_markers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VWB_LITERAL_MARKER", "expanded-would-be-wrong")
    vault = tmp_path / "模拟 Research #1 $VWB_LITERAL_MARKER %VWB_LITERAL_MARKER%" / "vault"
    env = tmp_path / "config #1.env"
    remote_workdir = "~/runs #1/$VWB_LITERAL_MARKER/%VWB_LITERAL_MARKER%"

    init_vault(vault, env_path=env, remote_workdir=remote_workdir)
    config = load_config(env)

    assert config.vault_path == vault.resolve()
    assert config.sources_dir == (vault / "sources").resolve()
    assert config.remote_workdir == remote_workdir


def test_generated_gitignore_protects_private_sources_and_run_products(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        return

    result = init_vault(tmp_path / "vault", env_path=tmp_path / ".env")
    vault = result.vault_path
    subprocess.run(["git", "init", "-q"], cwd=vault, check=True)

    private_source = vault / "sources" / "books" / "private-manual.pdf"
    local_env = vault / ".env"
    run_output = vault / "virtuoso-results" / "ota" / "run.raw"
    private_source.write_bytes(b"private")
    local_env.write_text("SECRET=value\n", encoding="utf-8")
    run_output.parent.mkdir(parents=True)
    run_output.write_bytes(b"simulation")

    for path in (private_source, local_env, run_output):
        relative = path.relative_to(vault)
        ignored = subprocess.run(["git", "check-ignore", "--quiet", str(relative)], cwd=vault, check=False)
        assert ignored.returncode == 0, f"{relative} should be ignored"

    generated_readme = Path("sources") / "books" / "README.md"
    tracked_guide = subprocess.run(["git", "check-ignore", "--quiet", str(generated_readme)], cwd=vault, check=False)
    assert tracked_guide.returncode == 1


def test_init_vault_preserves_existing_env_without_force(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("KEEP=this-value\n", encoding="utf-8")

    result = init_vault(tmp_path / "vault", env_path=env)

    assert result.env_written is False
    assert env.read_text(encoding="utf-8") == "KEEP=this-value\n"
    assert env in result.skipped


def test_init_vault_force_env_atomically_replaces_regular_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("OLD=value\n", encoding="utf-8")

    result = init_vault(tmp_path / "vault", env_path=env, force_env=True)

    assert result.env_written is True
    assert "OLD=value" not in env.read_text(encoding="utf-8")
    assert "VWB_VAULT_PATH=" in env.read_text(encoding="utf-8")


def test_init_vault_rejects_incomplete_existing_gitignore_before_writing(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    gitignore = vault / ".gitignore"
    gitignore.write_text("# existing but unsafe\n", encoding="utf-8")
    env = tmp_path / ".env"

    with pytest.raises(ValueError, match="exact generated private-data safety block"):
        init_vault(vault, env_path=env)

    assert list(vault.iterdir()) == [gitignore]
    assert not env.exists()


def test_init_vault_rejects_gitignore_negation_after_safety_block(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    gitignore = vault / ".gitignore"
    gitignore.write_text(GITIGNORE_TEXT + "\n!sources/**\n!.env\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must end with the exact generated"):
        init_vault(vault, env_path=tmp_path / ".env")

    assert not (vault / "index.md").exists()


def test_init_vault_rejects_nested_sources_gitignore(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    nested = vault / "sources" / "books"
    nested.mkdir(parents=True)
    (vault / ".gitignore").write_text(GITIGNORE_TEXT, encoding="utf-8")
    nested_gitignore = nested / ".gitignore"
    nested_gitignore.write_text("!private.pdf\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Nested .gitignore"):
        init_vault(vault, env_path=tmp_path / ".env")

    assert nested_gitignore.read_text(encoding="utf-8") == "!private.pdf\n"
    assert not (vault / "index.md").exists()


def test_init_vault_rejects_file_as_vault_root(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError, match="not a directory"):
        init_vault(vault, env_path=tmp_path / ".env")


def test_force_env_refuses_symlink_without_touching_external_file(tmp_path: Path) -> None:
    external = tmp_path / "external.env"
    external.write_text("SECRET=keep\n", encoding="utf-8")
    env_link = tmp_path / ".env"
    try:
        env_link.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(ValueError, match="symlink|reparse"):
        init_vault(tmp_path / "vault", env_path=env_link, force_env=True)

    assert external.read_text(encoding="utf-8") == "SECRET=keep\n"


def test_init_vault_refuses_linked_generated_folder(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    linked_sources = vault / "sources"
    try:
        linked_sources.symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")

    with pytest.raises(ValueError, match="symlink|junction|reparse"):
        init_vault(vault, env_path=tmp_path / ".env")

    assert list(external.iterdir()) == []


def test_init_vault_rejects_link_like_ancestor_before_writing(tmp_path: Path, monkeypatch) -> None:
    carrier = tmp_path / "carrier"
    carrier.mkdir()
    original = vault_module._is_link_or_reparse

    def fake_link_check(path: Path) -> bool:
        return path == carrier or original(path)

    monkeypatch.setattr(vault_module, "_is_link_or_reparse", fake_link_check)

    with pytest.raises(ValueError, match="traverse.*junction"):
        init_vault(carrier / "vault", env_path=tmp_path / ".env")

    assert list(carrier.iterdir()) == []
