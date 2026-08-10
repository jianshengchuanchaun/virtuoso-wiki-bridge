"""Initialize an Obsidian-style analog design knowledge vault."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CONTENT_FOLDERS = (
    "concepts",
    "entities",
    "journal",
    "Obsidian",
    "projects",
    "references",
    "skills",
    "sources",
    "synthesis",
)
SYSTEM_FOLDERS = (
    "_archives",
    "_raw",
    "_staging",
    ".obsidian",
)
DEFAULT_FOLDERS = CONTENT_FOLDERS + SYSTEM_FOLDERS
DEFAULT_SOURCE_SUBFOLDERS = (
    "books",
    "papers",
    "manuals",
    "datasheets",
    "circuits",
    "spectre",
    "skill",
    "logs",
    "notes",
    "extracted",
)


README_TEXT = {
    "sources": "# sources\n\nRaw books, papers, manuals, datasheets, netlists, SKILL scripts, simulation logs, and notes live here.\n",
    "projects": "# projects\n\nAnalog design projects, cells, testbenches, and run histories live here.\n",
    "concepts": "# concepts\n\nReusable analog concepts live here: gm/Id, noise, mismatch, stability, compensation, biasing, and layout effects.\n",
    "entities": "# entities\n\nEntity pages live here: tools, PDKs, devices, libraries, people, and organizations.\n",
    "journal": "# journal\n\nDaily working notes live here.\n",
    "Obsidian": "# Obsidian\n\nObsidian-specific dashboards, templates, and vault notes live here.\n",
    "references": "# references\n\nDistilled notes from analog books, papers, manuals, and examples live here.\n",
    "skills": "# skills\n\nReusable operating procedures and agent skills live here.\n",
    "synthesis": "# synthesis\n\nCross-topic analog design synthesis notes live here.\n",
    "_archives": "# _archives\n\nArchived wiki snapshots live here before rebuilds or major reorganizations.\n",
    "_raw": "# _raw\n\nUnprocessed notes and rough captures can be staged here before distillation.\n",
    "_staging": "# _staging\n\nReview queue for generated wiki pages when staged writes are enabled.\n",
    ".obsidian": "# .obsidian\n\nMinimal Obsidian configuration for this vault.\n",
}

SOURCE_README_TEXT = {
    "books": "# books\n\nPut private analog IC design book PDFs, EPUBs, or extracted text files here. Do not commit copyrighted books.\n",
    "papers": "# papers\n\nPut analog and mixed-signal papers, app notes, and preprints here.\n",
    "manuals": "# manuals\n\nPut Cadence, Virtuoso, Spectre, PDK, and process manual excerpts here.\n",
    "datasheets": "# datasheets\n\nPut device, IP, and measurement equipment datasheets here.\n",
    "circuits": "# circuits\n\nPut schematics notes, CDL/SPICE netlists, and circuit examples here.\n",
    "spectre": "# spectre\n\nPut Spectre netlists, ADE exports, run setup notes, and reusable testbenches here.\n",
    "skill": "# skill\n\nPut SKILL and OCEAN scripts here. Files here are knowledge until explicitly executed.\n",
    "logs": "# logs\n\nPut simulation logs, operating point summaries, and measurement outputs here.\n",
    "notes": "# notes\n\nPut your own analog design notes and copied book excerpts here.\n",
    "extracted": "# extracted\n\nText extracted from PDFs or EPUBs is written here so local search can use it.\n",
}

GITIGNORE_TEXT = """# Local configuration and secrets
.env
.env.*
!.env.example

# Raw source material is private by default. Keep only generated folder guides.
sources/**
!sources/**/
!sources/**/README.md
!sources/**/.gitkeep

# Virtuoso, Spectre, and simulator run products
runs/
virtuoso-results/
spectre-results/
**/psf/
**/*.raw
**/*.psf
**/*.trn
**/*.ac
**/*.dc
**/*.tran
**/*.sweep
**/*.stb
**/*.noise
**/*.info
**/*.log
**/spectre.out
**/logFile
**/*.ahdlSimDB/

# Local Obsidian UI state
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/cache/
"""

@dataclass(frozen=True)
class VaultInitResult:
    vault_path: Path
    env_path: Path
    created: tuple[Path, ...]
    skipped: tuple[Path, ...]
    env_written: bool


def _is_link_or_reparse(path: Path) -> bool:
    try:
        value = path.lstat()
    except FileNotFoundError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(value, "st_file_attributes", 0)
    return stat.S_ISLNK(value.st_mode) or bool(reparse_flag and attributes & reparse_flag)


def _assert_no_link_components(path: Path, *, label: str) -> None:
    """Reject an existing link/reparse point anywhere in an absolute path."""

    absolute = Path(os.path.abspath(path.expanduser()))
    for component in reversed((absolute, *absolute.parents)):
        if _is_link_or_reparse(component):
            raise ValueError(
                f"{label} must not traverse a symlink, junction, or reparse point: {component}"
            )


def _assert_plain_directory(path: Path, *, label: str) -> None:
    _assert_no_link_components(path, label=label)
    if _is_link_or_reparse(path):
        raise ValueError(f"{label} must not be a symlink, junction, or reparse point: {path}")
    if not path.is_dir():
        raise ValueError(f"{label} is not a directory: {path}")


def _validate_existing_gitignore(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    _assert_no_link_components(path, label="Vault .gitignore")
    if not path.is_file():
        raise ValueError(f"Vault .gitignore is not a regular file: {path}")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Cannot validate existing vault .gitignore {path}: {exc}") from exc
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").rstrip()
    required = GITIGNORE_TEXT.rstrip()
    if normalized != required and not normalized.endswith("\n" + required):
        raise ValueError(
            "Existing vault .gitignore must end with the exact generated private-data safety block. "
            "Keep custom rules before that block, then rerun initialization."
        )


def _validate_existing_sources_tree(sources: Path) -> None:
    if not sources.exists() and not sources.is_symlink():
        return
    _assert_plain_directory(sources, label="Existing sources directory")
    stack = [sources]
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as entries:
                current_entries = list(entries)
        except OSError as exc:
            raise ValueError(f"Cannot validate existing sources directory {directory}: {exc}") from exc
        for entry in current_entries:
            path = Path(entry.path)
            try:
                value = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise ValueError(f"Cannot inspect existing source path {path}: {exc}") from exc
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            attributes = getattr(value, "st_file_attributes", 0)
            if stat.S_ISLNK(value.st_mode) or bool(reparse_flag and attributes & reparse_flag):
                raise ValueError(
                    "Existing sources tree must not contain a symlink, junction, or reparse point: "
                    f"{path}"
                )
            if entry.name.casefold() == ".gitignore":
                raise ValueError(
                    "Nested .gitignore files under sources can override private-data rules; "
                    f"remove or relocate this file before initialization: {path}"
                )
            if stat.S_ISDIR(value.st_mode):
                stack.append(path)


def _mkdir(path: Path, created: list[Path], skipped: list[Path]) -> None:
    _assert_no_link_components(path, label="Vault directory")
    if path.exists() or path.is_symlink():
        _assert_plain_directory(path, label="Vault directory")
        skipped.append(path)
        return
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        _assert_plain_directory(path, label="Vault directory")
        skipped.append(path)
        return
    _assert_plain_directory(path, label="Vault directory")
    created.append(path)


def _write_if_missing(path: Path, text: str, created: list[Path], skipped: list[Path], *, force: bool = False) -> None:
    _assert_no_link_components(path, label="Generated file path")
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_plain_directory(path.parent, label="Generated file parent")
    exists = path.exists() or path.is_symlink()
    if exists:
        if _is_link_or_reparse(path):
            raise ValueError(f"Generated file must not be a symlink or reparse point: {path}")
        if not path.is_file():
            raise ValueError(f"Generated file path is not a regular file: {path}")
        if not force:
            skipped.append(path)
            return

    if not force:
        try:
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        except FileExistsError:
            if _is_link_or_reparse(path) or not path.is_file():
                raise ValueError(f"Generated file was replaced by an unsafe path: {path}") from None
            skipped.append(path)
            return
    else:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            if _is_link_or_reparse(path):
                raise ValueError(f"Generated file must not be a symlink or reparse point: {path}")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    created.append(path)


def _yaml_string(value: str) -> str:
    """JSON strings are valid, safely quoted YAML scalars."""
    return json.dumps(value, ensure_ascii=False)


def _wiki_page(
    *,
    title: str,
    category: str,
    tags: tuple[str, ...],
    timestamp: str,
    body: str,
    sources: tuple[str, ...] = (),
) -> str:
    lines = [
        "---",
        f"title: {_yaml_string(title)}",
        f"category: {_yaml_string(category)}",
        "tags:",
    ]
    lines.extend(f"  - {_yaml_string(tag)}" for tag in tags)
    if sources:
        lines.append("sources:")
        lines.extend(f"  - {_yaml_string(source)}" for source in sources)
    else:
        lines.append("sources: []")
    lines.extend(
        [
            f"created: {_yaml_string(timestamp)}",
            f"updated: {_yaml_string(timestamp)}",
            "---",
            "",
            body.rstrip(),
            "",
        ]
    )
    return "\n".join(lines)


def _env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def env_text(vault_path: Path, *, remote_workdir: str = "~/virtuoso-work/virtuoso-wiki-bridge") -> str:
    vault = vault_path.resolve().as_posix()
    sources = (vault_path / "sources").resolve().as_posix()
    return (
        "# Virtuoso Wiki Bridge local configuration\n"
        "# Edit VWB_* values for your Virtuoso bridge and Cadence environment.\n\n"
        f"VWB_VAULT_PATH={_env_value(vault)}\n"
        f"VWB_SOURCES_DIR={_env_value(sources)}\n"
        f"OBSIDIAN_VAULT_PATH={_env_value(vault)}\n"
        f"OBSIDIAN_SOURCES_DIR={_env_value(sources)}\n"
        f"VWB_REMOTE_WORKDIR={_env_value(remote_workdir)}\n"
        "VWB_VIRTUOSO_BRIDGE_CMD=virtuoso-bridge\n"
        "VWB_VIRTUOSO_BRIDGE_PROFILE=\n"
        "VWB_VIRTUOSO_BRIDGE_ENV=\n\n"
        "VWB_REMOTE_HOST=\n"
        "VWB_REMOTE_USER=\n"
        "VWB_REMOTE_PORT=22\n"
        "VWB_SSH_KEY=\n"
        "VWB_SSH_CONFIG=\n"
        "VWB_SSH_EXTRA_ARGS=\n"
        "VWB_CADENCE_SETUP=\n"
        "VWB_REMOTE_SHELL=bash\n"
        "VWB_SSH_CMD=ssh\n"
        "VWB_SCP_CMD=scp\n"
    )


def init_vault(
    vault_path: str | Path,
    *,
    env_path: str | Path | None = None,
    force_env: bool = False,
    remote_workdir: str = "~/virtuoso-work/virtuoso-wiki-bridge",
) -> VaultInitResult:
    vault = Path(os.path.abspath(Path(vault_path).expanduser()))
    env = (
        Path(os.path.abspath(Path(env_path).expanduser()))
        if env_path
        else Path(os.path.abspath(Path.cwd() / ".env"))
    )
    created: list[Path] = []
    skipped: list[Path] = []
    timestamp = datetime.now(timezone.utc).isoformat()

    _assert_no_link_components(vault, label="Vault path")
    _assert_no_link_components(env, label="Environment path")
    _validate_existing_gitignore(vault / ".gitignore")
    _validate_existing_sources_tree(vault / "sources")
    _mkdir(vault, created, skipped)
    for folder in DEFAULT_FOLDERS:
        folder_path = vault / folder
        _mkdir(folder_path, created, skipped)
        _write_if_missing(
            folder_path / "README.md",
            _wiki_page(
                title=folder,
                category="folder-index",
                tags=("vault/index", f"folder/{folder.lower()}"),
                timestamp=timestamp,
                body=README_TEXT[folder],
            ),
            created,
            skipped,
        )
        _write_if_missing(folder_path / ".gitkeep", "", created, skipped)
    for subfolder in DEFAULT_SOURCE_SUBFOLDERS:
        subfolder_path = vault / "sources" / subfolder
        _mkdir(subfolder_path, created, skipped)
        _write_if_missing(
            subfolder_path / "README.md",
            _wiki_page(
                title=subfolder,
                category="source-index",
                tags=("vault/index", f"sources/{subfolder}"),
                timestamp=timestamp,
                body=SOURCE_README_TEXT[subfolder],
            ),
            created,
            skipped,
        )
        _write_if_missing(subfolder_path / ".gitkeep", "", created, skipped)

    _write_if_missing(vault / ".gitignore", GITIGNORE_TEXT, created, skipped)
    _write_if_missing(
        vault / "index.md",
        _wiki_page(
            title="Wiki Index",
            category="index",
            tags=("vault/index",),
            timestamp=timestamp,
            body=(
                "# Wiki Index\n\n"
                f"*Automatically initialized: {timestamp}*\n\n"
                "## Concepts\n\n"
                "*No pages yet. Add source material, then distill notes into this vault.*\n\n"
                "## Entities\n\n"
                "## Skills\n\n"
                "## References\n\n"
                "## Synthesis\n\n"
                "## Projects\n"
            ),
        ),
        created,
        skipped,
    )
    _write_if_missing(
        vault / "log.md",
        _wiki_page(
            title="Wiki Log",
            category="journal",
            tags=("vault/log",),
            timestamp=timestamp,
            body=(
                "# Wiki Log\n\n"
                f"- [{timestamp}] INIT vault_path=\".\" sources=\"sources\"\n"
            ),
        ),
        created,
        skipped,
    )
    _write_if_missing(
        vault / "hot.md",
        _wiki_page(
            title="Hot Cache",
            category="synthesis",
            tags=("vault/hot-cache",),
            timestamp=timestamp,
            body=(
                "# Hot Cache\n\n"
                "*Short rolling summary of recent analog design knowledge. Update after major ingest or simulation work.*\n\n"
                "## Recent Activity\n\n"
                f"- [{timestamp}] Vault initialized.\n\n"
                "## Active Threads\n\n"
                "*None yet.*\n\n"
                "## Key Takeaways\n\n"
                "*None yet.*\n\n"
                "## Flagged Contradictions\n\n"
                "*None yet.*\n"
            ),
        ),
        created,
        skipped,
    )
    _write_if_missing(
        vault / ".manifest.json",
        json.dumps({"version": 1, "created_at": timestamp, "sources": {}, "extractions": {}}, indent=2) + "\n",
        created,
        skipped,
    )
    _write_if_missing(
        vault / ".obsidian" / "app.json",
        json.dumps(
            {
                "strictLineBreaks": False,
                "showFrontmatter": False,
                "defaultViewMode": "preview",
                "livePreview": True,
            },
            indent=2,
        )
        + "\n",
        created,
        skipped,
    )
    _write_if_missing(vault / ".obsidian" / "appearance.json", json.dumps({"baseFontSize": 16}, indent=2) + "\n", created, skipped)

    env_already_exists = env.exists()
    _write_if_missing(env, env_text(vault, remote_workdir=remote_workdir), created, skipped, force=force_env)
    return VaultInitResult(vault, env, tuple(created), tuple(skipped), force_env or not env_already_exists)
