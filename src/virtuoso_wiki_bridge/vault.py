"""Initialize an Obsidian-style analog design knowledge vault."""

from __future__ import annotations

import json
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


@dataclass(frozen=True)
class VaultInitResult:
    vault_path: Path
    env_path: Path
    created: tuple[Path, ...]
    skipped: tuple[Path, ...]
    env_written: bool


def _mkdir(path: Path, created: list[Path], skipped: list[Path]) -> None:
    if path.exists():
        skipped.append(path)
        return
    path.mkdir(parents=True, exist_ok=True)
    created.append(path)


def _write_if_missing(path: Path, text: str, created: list[Path], skipped: list[Path], *, force: bool = False) -> None:
    if path.exists() and not force:
        skipped.append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    created.append(path)


def env_text(vault_path: Path, *, remote_workdir: str = "~/virtuoso-work/virtuoso-wiki-bridge") -> str:
    vault = vault_path.resolve().as_posix()
    sources = (vault_path / "sources").resolve().as_posix()
    return (
        "# Virtuoso Wiki Bridge local configuration\n"
        "# Edit VWB_* values for your Virtuoso bridge and Cadence environment.\n\n"
        f"VWB_VAULT_PATH={vault}\n"
        f"VWB_SOURCES_DIR={sources}\n"
        f"OBSIDIAN_VAULT_PATH={vault}\n"
        f"OBSIDIAN_SOURCES_DIR={sources}\n"
        f"VWB_REMOTE_WORKDIR={remote_workdir}\n"
        "VWB_VIRTUOSO_BRIDGE_CMD=virtuoso-bridge\n\n"
        "VWB_REMOTE_HOST=\n"
        "VWB_REMOTE_USER=\n"
        "VWB_REMOTE_PORT=22\n"
        "VWB_SSH_KEY=\n"
        "VWB_CADENCE_SETUP=\n"
        "VWB_REMOTE_SHELL=bash\n"
    )


def init_vault(
    vault_path: str | Path,
    *,
    env_path: str | Path | None = None,
    force_env: bool = False,
    remote_workdir: str = "~/virtuoso-work/virtuoso-wiki-bridge",
) -> VaultInitResult:
    vault = Path(vault_path).expanduser().resolve()
    env = Path(env_path).expanduser().resolve() if env_path else (Path.cwd() / ".env").resolve()
    created: list[Path] = []
    skipped: list[Path] = []
    timestamp = datetime.now(timezone.utc).isoformat()

    _mkdir(vault, created, skipped)
    for folder in DEFAULT_FOLDERS:
        folder_path = vault / folder
        _mkdir(folder_path, created, skipped)
        _write_if_missing(folder_path / "README.md", README_TEXT[folder], created, skipped)
        _write_if_missing(folder_path / ".gitkeep", "", created, skipped)
    for subfolder in DEFAULT_SOURCE_SUBFOLDERS:
        subfolder_path = vault / "sources" / subfolder
        _mkdir(subfolder_path, created, skipped)
        _write_if_missing(subfolder_path / "README.md", SOURCE_README_TEXT[subfolder], created, skipped)
        _write_if_missing(subfolder_path / ".gitkeep", "", created, skipped)

    _write_if_missing(
        vault / "index.md",
        "---\n"
        "title: Wiki Index\n"
        "---\n\n"
        "# Wiki Index\n\n"
        f"*Automatically initialized: {timestamp}*\n\n"
        "## Concepts\n\n"
        "*No pages yet. Add source material, then distill notes into this vault.*\n\n"
        "## Entities\n\n"
        "## Skills\n\n"
        "## References\n\n"
        "## Synthesis\n\n"
        "## Projects\n",
        created,
        skipped,
    )
    _write_if_missing(
        vault / "log.md",
        "---\n"
        "title: Wiki Log\n"
        "---\n\n"
        "# Wiki Log\n\n"
        f"- [{timestamp}] INIT vault_path=\"{vault.as_posix()}\" sources=\"{(vault / 'sources').as_posix()}\"\n",
        created,
        skipped,
    )
    _write_if_missing(
        vault / "hot.md",
        "---\n"
        "title: Hot Cache\n"
        f"updated: {timestamp}\n"
        "---\n\n"
        "# Hot Cache\n\n"
        "*Short rolling summary of recent analog design knowledge. Update after major ingest or simulation work.*\n\n"
        "## Recent Activity\n\n"
        f"- [{timestamp}] Vault initialized.\n\n"
        "## Active Threads\n\n"
        "*None yet.*\n\n"
        "## Key Takeaways\n\n"
        "*None yet.*\n\n"
        "## Flagged Contradictions\n\n"
        "*None yet.*\n",
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
