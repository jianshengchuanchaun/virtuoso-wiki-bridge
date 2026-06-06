"""Organize raw source files into analog-design source categories."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .vault import DEFAULT_SOURCE_SUBFOLDERS
from .wiki import TEXT_EXTENSIONS, TEXT_FILENAMES, read_text_file


SKIP_FILENAMES = {"README.md", ".gitkeep", "INDEX.md", "ORGANIZE_PLAN.md"}
SKIP_SUFFIXES = {".tmp", ".bak", ".swp"}
INDEX_FILENAME = "INDEX.md"
PLAN_FILENAME = "ORGANIZE_PLAN.md"


CATEGORY_EXTENSIONS: dict[str, set[str]] = {
    "books": {".epub", ".mobi", ".azw", ".azw3"},
    "papers": set(),
    "manuals": set(),
    "datasheets": set(),
    "circuits": {".cdl", ".cir", ".sp", ".spi"},
    "spectre": {".scs", ".mdl", ".ocn"},
    "skill": {".il", ".ils", ".skill"},
    "logs": {".log", ".out", ".lis", ".info", ".measure", ".mt0", ".ms0"},
    "notes": {".md", ".txt", ".rst", ".tex", ".csv"},
    "extracted": set(),
}


CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "datasheets": ("datasheet", "data sheet", "electrical characteristics", "absolute maximum ratings"),
    "manuals": ("manual", "user guide", "reference guide", "spectre circuit simulator", "virtuoso", "cadence"),
    "papers": ("abstract", "ieee", "references", "doi", "proceedings", "journal"),
    "books": ("chapter", "isbn", "textbook", "edition", "publisher"),
    "spectre": ("simulator lang=spectre", "include", "parameters", "analysis", "tran", "ac", "dcop", "pnoise"),
    "skill": ("procedure(", "defun", "let(", "hiCreate", "dbOpenCellViewByType", "geGetEditCellView"),
    "logs": ("spectre.out", "warning", "error", "cpu time", "elapsed time", "simulation started"),
    "circuits": (".subckt", ".ends", "subckt", "ends", "mos", "pmos", "nmos"),
    "notes": ("gm/id", "folded cascode", "phase margin", "noise", "mismatch"),
}


@dataclass(frozen=True)
class SourceItem:
    path: Path
    category: str
    target: Path
    reason: str
    title: str
    size_bytes: int
    digest: str
    moved: bool = False


@dataclass(frozen=True)
class OrganizeResult:
    sources_dir: Path
    apply: bool
    items: tuple[SourceItem, ...]
    index_path: Path
    plan_path: Path
    manifest_path: Path


def _digest(path: Path, *, max_bytes: int = 2_000_000) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        remaining = max_bytes
        while remaining > 0:
            chunk = handle.read(min(65536, remaining))
            if not chunk:
                break
            hasher.update(chunk)
            remaining -= len(chunk)
    return hasher.hexdigest()


def _existing_category(path: Path, sources_dir: Path) -> str | None:
    try:
        relative = path.relative_to(sources_dir)
    except ValueError:
        return None
    if len(relative.parts) >= 2 and relative.parts[0] in DEFAULT_SOURCE_SUBFOLDERS:
        return relative.parts[0]
    return None


def _read_sample(path: Path, *, max_chars: int = 80_000) -> str:
    if path.suffix.lower() in TEXT_EXTENSIONS or path.name in TEXT_FILENAMES:
        try:
            return read_text_file(path, limit_chars=max_chars)
        except OSError:
            return ""
    return ""


def _title_from_sample(path: Path, sample: str) -> str:
    for line in sample.splitlines()[:40]:
        line = line.strip()
        if not line:
            continue
        if line.startswith("# "):
            return line[2:].strip()
        if line.lower().startswith("title:"):
            return line.split(":", 1)[1].strip().strip("'\"")
        if len(line) <= 90 and not line.startswith(("//", "*", ";")):
            return line
    return path.stem


def _score_keywords(sample: str, filename: str) -> tuple[str, int, str]:
    haystack = f"{filename.lower()}\n{sample[:8000].lower()}"
    best_category = "notes"
    best_score = 0
    best_terms: list[str] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        terms = [keyword for keyword in keywords if keyword in haystack]
        score = len(terms)
        if score > best_score:
            best_category = category
            best_score = score
            best_terms = terms[:4]
    return best_category, best_score, ", ".join(best_terms)


def classify_source(path: Path, sources_dir: Path) -> tuple[str, str, str]:
    suffix = path.suffix.lower()
    existing = _existing_category(path, sources_dir)
    sample = _read_sample(path)
    title = _title_from_sample(path, sample)

    if existing:
        return existing, f"already under sources/{existing}", title

    if suffix == ".pdf":
        category, score, terms = _score_keywords(sample, path.name)
        if category in {"papers", "manuals", "datasheets", "books"} and score > 0:
            return category, f"PDF keyword match: {terms}", title
        name = path.name.lower()
        if "datasheet" in name:
            return "datasheets", "PDF filename contains datasheet", title
        if "manual" in name or "guide" in name or "spectre" in name or "virtuoso" in name:
            return "manuals", "PDF filename suggests manual", title
        if "paper" in name or "ieee" in name:
            return "papers", "PDF filename suggests paper", title
        return "books", "PDF default category", title

    for category, suffixes in CATEGORY_EXTENSIONS.items():
        if suffix in suffixes:
            return category, f"extension {suffix}", title

    category, score, terms = _score_keywords(sample, path.name)
    if score > 0:
        return category, f"keyword match: {terms}", title
    return "notes", "default text/source category", title


def _unique_target(target: Path) -> Path:
    if not target.exists():
        return target
    index = 2
    stem = target.stem
    suffix = target.suffix
    while True:
        candidate = target.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def iter_source_files(sources_dir: Path) -> list[Path]:
    sources_dir = sources_dir.expanduser().resolve()
    if not sources_dir.exists():
        return []
    files: list[Path] = []
    for path in sources_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.name in SKIP_FILENAMES:
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if any(part.startswith(".") for part in path.relative_to(sources_dir).parts):
            continue
        files.append(path.resolve())
    return sorted(files)


def build_plan(sources_dir: Path) -> list[SourceItem]:
    sources_dir = sources_dir.expanduser().resolve()
    items: list[SourceItem] = []
    for path in iter_source_files(sources_dir):
        category, reason, title = classify_source(path, sources_dir)
        existing = _existing_category(path, sources_dir)
        if existing:
            target = path
        else:
            target = _unique_target(sources_dir / category / path.name)
        stat = path.stat()
        items.append(
            SourceItem(
                path=path,
                category=category,
                target=target,
                reason=reason,
                title=title,
                size_bytes=stat.st_size,
                digest=_digest(path),
            )
        )
    return items


def _move_items(items: list[SourceItem]) -> list[SourceItem]:
    moved_items: list[SourceItem] = []
    for item in items:
        if item.path == item.target:
            moved_items.append(item)
            continue
        item.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(item.path), str(item.target))
        moved_items.append(
            SourceItem(
                path=item.path,
                category=item.category,
                target=item.target,
                reason=item.reason,
                title=item.title,
                size_bytes=item.size_bytes,
                digest=item.digest,
                moved=True,
            )
        )
    return moved_items


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def render_plan(items: list[SourceItem], sources_dir: Path, *, apply: bool) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Sources Organize Plan",
        "",
        f"Generated: {timestamp}",
        f"Mode: {'apply' if apply else 'dry-run'}",
        "",
        "This file is generated by `virtuoso-wiki-bridge organize-sources`.",
        "Dry-run mode does not move files. Use `--apply` to perform the moves.",
        "",
    ]
    if not items:
        lines.append("No source files found.")
        return "\n".join(lines) + "\n"
    for item in items:
        action = "move" if item.path != item.target else "keep"
        if item.moved:
            action = "moved"
        lines.extend(
            [
                f"## {_relative(item.target, sources_dir)}",
                "",
                f"- action: {action}",
                f"- category: {item.category}",
                f"- title: {item.title}",
                f"- source: `{_relative(item.path, sources_dir)}`",
                f"- target: `{_relative(item.target, sources_dir)}`",
                f"- reason: {item.reason}",
                f"- size_bytes: {item.size_bytes}",
                f"- sha256_prefix: {item.digest[:16]}",
                "",
            ]
        )
    return "\n".join(lines)


def render_index(items: list[SourceItem], sources_dir: Path) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Sources Index",
        "",
        f"Updated: {timestamp}",
        "",
        "This index summarizes raw local sources for source-first analog reasoning.",
        "Private books, manuals, PDK files, netlists, and logs should stay local and out of git.",
        "",
    ]
    if not items:
        lines.append("*No source files found.*")
        return "\n".join(lines) + "\n"
    by_category: dict[str, list[SourceItem]] = {}
    for item in items:
        by_category.setdefault(item.category, []).append(item)
    for category in DEFAULT_SOURCE_SUBFOLDERS:
        category_items = by_category.get(category, [])
        if not category_items:
            continue
        lines.extend([f"## {category}", ""])
        for item in sorted(category_items, key=lambda value: _relative(value.target, sources_dir).lower()):
            rel = _relative(item.target, sources_dir)
            lines.append(f"- `{rel}` - {item.title} ({item.reason}; {item.size_bytes} bytes)")
        lines.append("")
    return "\n".join(lines)


def write_manifest(items: list[SourceItem], sources_dir: Path, manifest_path: Path) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    manifest = {
        "version": 1,
        "updated_at": timestamp,
        "sources_dir": sources_dir.as_posix(),
        "sources": [
            {
                "path": _relative(item.target, sources_dir),
                "original_path": _relative(item.path, sources_dir),
                "category": item.category,
                "title": item.title,
                "reason": item.reason,
                "size_bytes": item.size_bytes,
                "sha256": item.digest,
            }
            for item in items
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def organize_sources(sources_dir: Path, *, apply: bool = False) -> OrganizeResult:
    sources_dir = sources_dir.expanduser().resolve()
    sources_dir.mkdir(parents=True, exist_ok=True)
    for category in DEFAULT_SOURCE_SUBFOLDERS:
        (sources_dir / category).mkdir(parents=True, exist_ok=True)

    items = build_plan(sources_dir)
    if apply:
        items = _move_items(items)

    plan_path = sources_dir / PLAN_FILENAME
    index_path = sources_dir / INDEX_FILENAME
    manifest_path = sources_dir / ".sources-manifest.json"
    plan_path.write_text(render_plan(items, sources_dir, apply=apply), encoding="utf-8", newline="\n")
    index_path.write_text(render_index(items, sources_dir), encoding="utf-8", newline="\n")
    write_manifest(items, sources_dir, manifest_path)
    return OrganizeResult(sources_dir, apply, tuple(items), index_path, plan_path, manifest_path)
