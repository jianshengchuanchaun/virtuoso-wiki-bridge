"""Organize raw source files into analog-design source categories."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .text_safety import sanitize_untrusted_field
from .vault import DEFAULT_SOURCE_SUBFOLDERS
from .wiki import TEXT_EXTENSIONS, TEXT_FILENAMES, read_text_file

SKIP_FILENAMES = {"README.md", ".gitkeep", "INDEX.md", "ORGANIZE_PLAN.md"}
SKIP_SUFFIXES = {".tmp", ".bak", ".swp"}
INDEX_FILENAME = "INDEX.md"
PLAN_FILENAME = "ORGANIZE_PLAN.md"
MACHINE_PLAN_FILENAME = ".sources-plan.json"
MANIFEST_FILENAME = ".sources-manifest.json"
PLAN_VERSION = 1


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


def _digest(path: Path) -> str:
    """Return a full-file SHA-256 digest.

    The organizer uses this digest as part of the reviewed plan contract.  A
    prefix or bounded digest is not sufficient because changes after the
    sampled prefix must invalidate the plan too.
    """

    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
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
            return sanitize_untrusted_field(line[2:].strip())
        if line.lower().startswith("title:"):
            return sanitize_untrusted_field(line.split(":", 1)[1].strip().strip("'\""))
        if len(line) <= 90 and not line.startswith(("//", "*", ";")):
            return sanitize_untrusted_field(line)
    return sanitize_untrusted_field(path.stem)


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


def _is_link_or_reparse_stat(value: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(value, "st_file_attributes", 0)
    return stat.S_ISLNK(value.st_mode) or bool(file_attributes & reparse_flag)


def _lstat_or_none(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _assert_not_link_or_reparse(path: Path, *, label: str) -> os.stat_result:
    value = _lstat_or_none(path)
    if value is None:
        raise ValueError(f"{label} does not exist: {path}")
    if _is_link_or_reparse_stat(value):
        raise ValueError(f"{label} must not be a symlink, junction, or reparse point: {path}")
    return value


def _assert_no_link_components(path: Path, *, label: str) -> None:
    absolute = Path(os.path.abspath(path.expanduser()))
    for component in reversed((absolute, *absolute.parents)):
        value = _lstat_or_none(component)
        if value is not None and _is_link_or_reparse_stat(value):
            raise ValueError(
                f"{label} must not traverse a symlink, junction, or reparse point: {component}"
            )


def _path_key(path: Path, sources_dir: Path) -> str:
    relative = path.relative_to(sources_dir).as_posix()
    return unicodedata.normalize("NFC", relative).casefold()


def _scan_source_tree(sources_dir: Path) -> tuple[list[Path], set[str]]:
    """Scan without following links and return candidate files plus occupied paths."""

    root_stat = _assert_not_link_or_reparse(sources_dir, label="Sources directory")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError(f"Sources path is not a directory: {sources_dir}")

    files: list[Path] = []
    occupied: set[str] = set()
    stack: list[tuple[Path, bool]] = [(sources_dir, False)]

    while stack:
        directory, ignored_parent = stack.pop()
        try:
            with os.scandir(directory) as entries:
                ordered_entries = sorted(entries, key=lambda entry: entry.name.casefold())
        except OSError as exc:
            raise RuntimeError(f"Cannot scan sources directory {directory}: {exc}") from exc

        for entry in ordered_entries:
            path = Path(entry.path)
            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise RuntimeError(f"Cannot inspect source path {path}: {exc}") from exc

            if _is_link_or_reparse_stat(entry_stat):
                raise ValueError(
                    "Sources must not contain symlinks, junctions, or reparse points: "
                    f"{path}"
                )

            occupied.add(_path_key(path, sources_dir))
            relative = path.relative_to(sources_dir)
            ignored = ignored_parent or any(part.startswith(".") for part in relative.parts)

            if stat.S_ISDIR(entry_stat.st_mode):
                # Hidden directories are still traversed to ensure that a link cannot
                # hide inside the controlled source tree.
                stack.append((path, ignored))
                continue
            if not stat.S_ISREG(entry_stat.st_mode):
                raise ValueError(f"Sources must contain only regular files and directories: {path}")
            if ignored:
                continue
            if path.name in SKIP_FILENAMES:
                continue
            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            files.append(path)

    return sorted(files, key=lambda path: path.relative_to(sources_dir).as_posix()), occupied


def _unique_target(target: Path, sources_dir: Path, occupied: set[str]) -> Path:
    if _path_key(target, sources_dir) not in occupied:
        return target
    index = 2
    stem = target.stem
    suffix = target.suffix
    while True:
        candidate = target.with_name(f"{stem}-{index}{suffix}")
        if _path_key(candidate, sources_dir) not in occupied:
            return candidate
        index += 1


def iter_source_files(sources_dir: Path) -> list[Path]:
    _assert_no_link_components(sources_dir, label="Sources directory")
    sources_dir = sources_dir.expanduser().resolve()
    if not sources_dir.exists():
        return []
    files, _ = _scan_source_tree(sources_dir)
    return files


def build_plan(sources_dir: Path) -> list[SourceItem]:
    _assert_no_link_components(sources_dir, label="Sources directory")
    sources_dir = sources_dir.expanduser().resolve()
    items: list[SourceItem] = []
    files, occupied = _scan_source_tree(sources_dir)
    reserved_targets: set[str] = set()
    for path in files:
        category, reason, title = classify_source(path, sources_dir)
        existing = _existing_category(path, sources_dir)
        if existing:
            target = path
        else:
            target = _unique_target(
                sources_dir / category / path.name,
                sources_dir,
                occupied | reserved_targets,
            )
        target_key = _path_key(target, sources_dir)
        if target_key in reserved_targets:
            raise ValueError(
                "Source tree contains case-insensitive duplicate categorized paths; "
                f"cannot create a portable no-clobber plan for {target}"
            )
        reserved_targets.add(target_key)
        file_stat = path.stat()
        items.append(
            SourceItem(
                path=path,
                category=category,
                target=target,
                reason=reason,
                title=title,
                size_bytes=file_stat.st_size,
                digest=_digest(path),
            )
        )
    return items


def _copy_file_exclusive(item: SourceItem) -> None:
    """Copy a planned source to a newly-created target without clobbering."""

    source_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    target_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    source_fd: int | None = None
    target_fd: int | None = None
    target_created = False
    try:
        source_fd = os.open(item.path, source_flags)
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode):
            raise RuntimeError(f"Planned source is no longer a regular file: {item.path}")
        target_fd = os.open(item.target, target_flags, stat.S_IMODE(source_stat.st_mode) or 0o600)
        target_created = True

        hasher = hashlib.sha256()
        copied = 0
        with os.fdopen(source_fd, "rb", closefd=True) as source_handle:
            source_fd = None
            with os.fdopen(target_fd, "wb", closefd=True) as target_handle:
                target_fd = None
                while True:
                    chunk = source_handle.read(1024 * 1024)
                    if not chunk:
                        break
                    target_handle.write(chunk)
                    hasher.update(chunk)
                    copied += len(chunk)
                target_handle.flush()
                os.fsync(target_handle.fileno())

        if copied != item.size_bytes or hasher.hexdigest() != item.digest:
            raise RuntimeError(f"Source changed while being copied; apply aborted: {item.path}")
        shutil.copystat(item.path, item.target, follow_symlinks=False)
    except FileExistsError as exc:
        raise RuntimeError(f"Refusing to overwrite target created after preflight: {item.target}") from exc
    except Exception:
        if source_fd is not None:
            os.close(source_fd)
            source_fd = None
        if target_fd is not None:
            os.close(target_fd)
            target_fd = None
        if target_created:
            try:
                _remove_created_target(item.target)
            except Exception as cleanup_exc:
                raise RuntimeError(
                    f"Copy failed and target cleanup also failed for {item.target}: {cleanup_exc}"
                ) from cleanup_exc
        raise
    finally:
        if source_fd is not None:
            os.close(source_fd)
        if target_fd is not None:
            os.close(target_fd)


def _remove_created_target(path: Path) -> None:
    value = _lstat_or_none(path)
    if value is None:
        return
    if _is_link_or_reparse_stat(value) or not stat.S_ISREG(value.st_mode):
        raise RuntimeError(f"Cannot safely clean up unexpected target path: {path}")
    path.unlink()


def _assert_source_matches_item(item: SourceItem) -> None:
    value = _assert_not_link_or_reparse(item.path, label="Planned source")
    if not stat.S_ISREG(value.st_mode):
        raise ValueError(f"Planned source is not a regular file: {item.path}")
    if value.st_size != item.size_bytes:
        raise ValueError(
            f"Approved plan drift: size changed for {item.path} "
            f"({item.size_bytes} -> {value.st_size})"
        )
    digest = _digest(item.path)
    if digest != item.digest:
        raise ValueError(f"Approved plan drift: SHA-256 changed for {item.path}")


def _move_items(items: list[SourceItem]) -> list[SourceItem]:
    """Apply a fully preflighted plan with no-clobber, copy-then-delete moves."""

    to_move = [item for item in items if item.path != item.target]
    created: list[Path] = []
    try:
        # Keep all originals until every target has been copied and verified.
        for item in to_move:
            _copy_file_exclusive(item)
            created.append(item.target)
        # Close the copy/delete race: no original is removed if any source
        # changed while targets were being prepared.
        for item in items:
            _assert_source_matches_item(item)
    except Exception as apply_exc:
        cleanup_errors: list[str] = []
        for target in reversed(created):
            try:
                _remove_created_target(target)
            except Exception as cleanup_exc:  # pragma: no cover - exceptional recovery path
                cleanup_errors.append(f"{target}: {cleanup_exc}")
        if cleanup_errors:
            raise RuntimeError(
                "Apply failed and one or more temporary target copies could not be cleaned up: "
                + "; ".join(cleanup_errors)
            ) from apply_exc
        raise

    deleted: set[Path] = set()
    try:
        for item in to_move:
            item.path.unlink()
            deleted.add(item.path)
    except OSError as exc:
        # Targets are intentionally retained after deletion starts: removing a
        # target whose original was already deleted would cause data loss.
        raise RuntimeError(
            "Apply copied all targets safely but could not remove every original; "
            "both old and new paths may exist. No target was overwritten. "
            f"Failed at {item.path}: {exc}"
        ) from exc

    moved_items: list[SourceItem] = []
    for item in items:
        moved_items.append(
            SourceItem(
                path=item.path,
                category=item.category,
                target=item.target,
                reason=item.reason,
                title=item.title,
                size_bytes=item.size_bytes,
                digest=item.digest,
                moved=item.path in deleted,
            )
        )
    return moved_items


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _plan_record(item: SourceItem, sources_dir: Path) -> dict[str, Any]:
    return {
        "source": _relative(item.path, sources_dir),
        "target": _relative(item.target, sources_dir),
        "category": item.category,
        "reason": item.reason,
        "title": item.title,
        "size_bytes": item.size_bytes,
        "sha256": item.digest,
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _make_machine_plan(items: list[SourceItem], sources_dir: Path) -> dict[str, Any]:
    body: dict[str, Any] = {
        "version": PLAN_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources_dir": sources_dir.as_posix(),
        "items": [_plan_record(item, sources_dir) for item in items],
    }
    plan_id = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    return {**body, "plan_id": plan_id}


def _validate_machine_plan_document(document: Any, sources_dir: Path) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        raise ValueError("Approved sources plan must be a JSON object")
    expected_keys = {"version", "generated_at", "sources_dir", "items", "plan_id"}
    if set(document) != expected_keys:
        raise ValueError(
            "Approved sources plan has an invalid schema; regenerate it with a dry-run"
        )
    if document["version"] != PLAN_VERSION:
        raise ValueError(
            f"Unsupported sources plan version {document['version']!r}; "
            "regenerate it with a dry-run"
        )
    if document["sources_dir"] != sources_dir.as_posix():
        raise ValueError(
            "Approved sources plan belongs to a different sources directory: "
            f"{document['sources_dir']!r}"
        )
    if not isinstance(document["generated_at"], str) or not document["generated_at"]:
        raise ValueError("Approved sources plan has an invalid generated_at value")
    if not isinstance(document["items"], list):
        raise ValueError("Approved sources plan items must be a JSON array")
    if not isinstance(document["plan_id"], str):
        raise ValueError("Approved sources plan has an invalid plan_id")

    unsigned = {key: document[key] for key in document if key != "plan_id"}
    expected_id = hashlib.sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()
    if document["plan_id"] != expected_id:
        raise ValueError(
            "Approved sources plan was modified after generation; run a new dry-run and review it"
        )
    return document["items"]


def _path_from_plan(value: Any, sources_dir: Path, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Approved plan {label} must be a non-empty relative path")
    if "\\" in value:
        raise ValueError(f"Approved plan {label} must use '/' separators: {value!r}")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError(f"Approved plan {label} contains an unsafe path: {value!r}")
    if os.name == "nt" and any(":" in part for part in raw_parts):
        raise ValueError(f"Approved plan {label} contains an unsafe Windows path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute():
        raise ValueError(f"Approved plan {label} must be relative: {value!r}")

    candidate = sources_dir.joinpath(*pure.parts)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(sources_dir)
    except ValueError as exc:
        raise ValueError(
            f"Approved plan {label} escapes the sources directory: {value!r}"
        ) from exc
    return resolved


def _items_from_machine_plan(records: list[dict[str, Any]], sources_dir: Path) -> list[SourceItem]:
    expected_keys = {
        "source",
        "target",
        "category",
        "reason",
        "title",
        "size_bytes",
        "sha256",
    }
    items: list[SourceItem] = []
    source_keys: set[str] = set()
    target_keys: set[str] = set()

    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != expected_keys:
            raise ValueError(f"Approved sources plan item {index} has an invalid schema")
        if record["category"] not in DEFAULT_SOURCE_SUBFOLDERS:
            raise ValueError(
                f"Approved sources plan item {index} has an invalid category: "
                f"{record['category']!r}"
            )
        if not isinstance(record["reason"], str) or not isinstance(record["title"], str):
            raise ValueError(f"Approved sources plan item {index} has invalid text metadata")
        size_bytes = record["size_bytes"]
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
            raise ValueError(f"Approved sources plan item {index} has an invalid size")
        digest = record["sha256"]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"Approved sources plan item {index} has an invalid SHA-256")

        source = _path_from_plan(record["source"], sources_dir, label="source")
        target = _path_from_plan(record["target"], sources_dir, label="target")
        target_relative = target.relative_to(sources_dir)
        if (
            len(target_relative.parts) < 2
            or target_relative.parts[0] != record["category"]
        ):
            raise ValueError(
                f"Approved plan target is outside its category directory: {record['target']!r}"
            )

        source_key = _path_key(source, sources_dir)
        target_key = _path_key(target, sources_dir)
        if source_key in source_keys:
            raise ValueError(f"Approved plan contains duplicate source path: {record['source']!r}")
        if target_key in target_keys:
            raise ValueError(
                "Approved plan contains duplicate or case-conflicting target path: "
                f"{record['target']!r}"
            )
        source_keys.add(source_key)
        target_keys.add(target_key)
        items.append(
            SourceItem(
                path=source,
                category=record["category"],
                target=target,
                reason=record["reason"],
                title=record["title"],
                size_bytes=size_bytes,
                digest=digest,
            )
        )
    return items


def _load_machine_plan(path: Path, sources_dir: Path) -> list[SourceItem]:
    value = _lstat_or_none(path)
    if value is None:
        raise ValueError(
            f"No approved sources plan found at {path}. "
            "Run organize-sources without --apply, review the plan, then apply it."
        )
    if _is_link_or_reparse_stat(value) or not stat.S_ISREG(value.st_mode):
        raise ValueError(f"Approved sources plan must be a regular local file: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read approved sources plan {path}: {exc}") from exc
    records = _validate_machine_plan_document(document, sources_dir)
    return _items_from_machine_plan(records, sources_dir)


def _item_contract(item: SourceItem, sources_dir: Path) -> tuple[Any, ...]:
    return (
        _relative(item.path, sources_dir),
        _relative(item.target, sources_dir),
        item.category,
        item.reason,
        item.title,
        item.size_bytes,
        item.digest,
    )


def _validate_plan_against_sources(
    approved_items: list[SourceItem],
    sources_dir: Path,
) -> None:
    current_items = build_plan(sources_dir)
    approved_by_source = {
        _relative(item.path, sources_dir): item for item in approved_items
    }
    current_by_source = {
        _relative(item.path, sources_dir): item for item in current_items
    }
    approved_sources = set(approved_by_source)
    current_sources = set(current_by_source)
    if approved_sources != current_sources:
        added = sorted(current_sources - approved_sources)
        missing = sorted(approved_sources - current_sources)
        details: list[str] = []
        if added:
            details.append("added: " + ", ".join(added[:5]))
        if missing:
            details.append("missing: " + ", ".join(missing[:5]))
        raise ValueError(
            "Approved plan drift: source file set changed"
            + (f" ({'; '.join(details)})" if details else "")
        )

    for source in sorted(approved_sources):
        approved = approved_by_source[source]
        current = current_by_source[source]
        if _item_contract(approved, sources_dir) != _item_contract(current, sources_dir):
            if approved.size_bytes != current.size_bytes:
                field = "size"
            elif approved.digest != current.digest:
                field = "SHA-256"
            elif approved.target != current.target:
                field = "target"
            else:
                field = "classification metadata"
            raise ValueError(f"Approved plan drift: {field} changed for {source}")


def _assert_safe_directory(path: Path, sources_dir: Path, *, label: str) -> None:
    try:
        relative = path.relative_to(sources_dir)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the sources directory: {path}") from exc
    current = sources_dir
    _assert_not_link_or_reparse(current, label="Sources directory")
    for part in relative.parts:
        current = current / part
        value = _assert_not_link_or_reparse(current, label=label)
        if not stat.S_ISDIR(value.st_mode):
            raise ValueError(f"{label} is not a directory: {current}")


def _assert_safe_output_path(path: Path, sources_dir: Path) -> None:
    try:
        path.relative_to(sources_dir)
    except ValueError as exc:
        raise ValueError(f"Generated output escapes the sources directory: {path}") from exc
    _assert_safe_directory(path.parent, sources_dir, label="Generated output parent")
    value = _lstat_or_none(path)
    if value is not None:
        if _is_link_or_reparse_stat(value):
            raise ValueError(
                "Refusing to write generated output through a symlink, junction, "
                f"or reparse point: {path}"
            )
        if not stat.S_ISREG(value.st_mode):
            raise ValueError(f"Generated output path is not a regular file: {path}")

    wanted = unicodedata.normalize("NFC", path.name).casefold()
    with os.scandir(path.parent) as entries:
        for entry in entries:
            existing = unicodedata.normalize("NFC", entry.name).casefold()
            if existing == wanted and entry.name != path.name:
                raise ValueError(
                    "Generated output has a case-insensitive path conflict: "
                    f"{entry.path} vs {path}"
                )


def _atomic_write_text(path: Path, content: str, sources_dir: Path) -> None:
    _assert_safe_output_path(path, sources_dir)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        # Replacing a directory entry does not follow an existing symlink.  The
        # pre-check gives a clear error; replace also closes the write race.
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _preflight_apply(items: list[SourceItem], sources_dir: Path) -> None:
    _, occupied = _scan_source_tree(sources_dir)
    seen_targets: set[str] = set()
    for item in items:
        _assert_source_matches_item(item)
        target_key = _path_key(item.target, sources_dir)
        if target_key in seen_targets:
            raise ValueError(f"Approved plan has a duplicate target: {item.target}")
        seen_targets.add(target_key)
        _assert_safe_directory(
            item.target.parent,
            sources_dir,
            label="Approved target parent",
        )
        if item.path == item.target:
            continue
        if target_key in occupied or _lstat_or_none(item.target) is not None:
            raise ValueError(f"Approved target now exists; refusing to overwrite: {item.target}")


def render_plan(
    items: list[SourceItem],
    sources_dir: Path,
    *,
    apply: bool,
    plan_id: str | None = None,
) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Sources Organize Plan",
        "",
        f"Generated: {timestamp}",
        f"Mode: {'apply' if apply else 'dry-run'}",
        "",
        "This file is generated by `virtuoso-wiki-bridge organize-sources`.",
        "Dry-run mode does not move files. Use `--apply` to perform the moves.",
        f"Machine plan: `{MACHINE_PLAN_FILENAME}`",
        "",
    ]
    if plan_id:
        lines[4:4] = [f"Plan ID: `{plan_id}`", ""]
    if not items:
        lines.append("No source files found.")
        return "\n".join(lines) + "\n"
    for item in items:
        action = "move" if item.path != item.target else "keep"
        if item.moved:
            action = "moved"
        lines.extend(
            [
                f"## {sanitize_untrusted_field(_relative(item.target, sources_dir))}",
                "",
                f"- action: {action}",
                f"- category: {item.category}",
                f"- title: {sanitize_untrusted_field(item.title)}",
                f"- source: `{sanitize_untrusted_field(_relative(item.path, sources_dir))}`",
                f"- target: `{sanitize_untrusted_field(_relative(item.target, sources_dir))}`",
                f"- reason: {sanitize_untrusted_field(item.reason)}",
                f"- size_bytes: {item.size_bytes}",
                f"- sha256: {item.digest}",
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
        for item in sorted(
            category_items,
            key=lambda value: _relative(
                value.target if value.moved else value.path,
                sources_dir,
            ).lower(),
        ):
            actual_path = item.target if item.moved else item.path
            rel = sanitize_untrusted_field(_relative(actual_path, sources_dir))
            title = sanitize_untrusted_field(item.title)
            reason = sanitize_untrusted_field(item.reason)
            lines.append(f"- `{rel}` - {title} ({reason}; {item.size_bytes} bytes)")
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
                "path": _relative(item.target if item.moved else item.path, sources_dir),
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
    _atomic_write_text(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        sources_dir,
    )


def _prepare_sources_dir(path: Path, *, create: bool) -> Path:
    candidate = path.expanduser()
    _assert_no_link_components(candidate, label="Sources directory")
    value = _lstat_or_none(candidate)
    if value is None:
        if not create:
            raise ValueError(f"Cannot apply: sources directory does not exist: {candidate}")
        try:
            candidate.mkdir(parents=True)
        except OSError as exc:
            raise RuntimeError(f"Cannot create sources directory {candidate}: {exc}") from exc
        value = _assert_not_link_or_reparse(candidate, label="Sources directory")
        _assert_no_link_components(candidate, label="Sources directory")
    if _is_link_or_reparse_stat(value):
        raise ValueError(
            f"Sources directory must not be a symlink, junction, or reparse point: {candidate}"
        )
    if not stat.S_ISDIR(value.st_mode):
        raise ValueError(f"Sources path is not a directory: {candidate}")
    return candidate.resolve()


def _ensure_category_directories(sources_dir: Path) -> None:
    existing_names: dict[str, str] = {}
    with os.scandir(sources_dir) as entries:
        for entry in entries:
            key = unicodedata.normalize("NFC", entry.name).casefold()
            existing_names.setdefault(key, entry.name)

    for category in DEFAULT_SOURCE_SUBFOLDERS:
        key = unicodedata.normalize("NFC", category).casefold()
        conflicting_name = existing_names.get(key)
        if conflicting_name is not None and conflicting_name != category:
            raise ValueError(
                "Category directory has a case-insensitive name conflict: "
                f"{conflicting_name!r} vs {category!r}"
            )
        directory = sources_dir / category
        value = _lstat_or_none(directory)
        if value is None:
            try:
                directory.mkdir()
            except OSError as exc:
                raise RuntimeError(f"Cannot create category directory {directory}: {exc}") from exc
            value = _assert_not_link_or_reparse(directory, label="Category directory")
            existing_names[key] = category
        if _is_link_or_reparse_stat(value):
            raise ValueError(
                f"Category directory must not be a symlink, junction, or reparse point: {directory}"
            )
        if not stat.S_ISDIR(value.st_mode):
            raise ValueError(f"Category path is not a directory: {directory}")


def organize_sources(sources_dir: Path, *, apply: bool = False) -> OrganizeResult:
    sources_dir = _prepare_sources_dir(sources_dir, create=not apply)
    plan_path = sources_dir / PLAN_FILENAME
    index_path = sources_dir / INDEX_FILENAME
    machine_plan_path = sources_dir / MACHINE_PLAN_FILENAME
    manifest_path = sources_dir / MANIFEST_FILENAME

    if apply:
        approved_items = _load_machine_plan(machine_plan_path, sources_dir)
        _validate_plan_against_sources(approved_items, sources_dir)
        for output_path in (plan_path, index_path, manifest_path):
            _assert_safe_output_path(output_path, sources_dir)
        _preflight_apply(approved_items, sources_dir)
        items = _move_items(approved_items)

        # The reviewed machine plan remains byte-for-byte unchanged.  Human
        # outputs describe the paths that now actually exist.
        _atomic_write_text(
            plan_path,
            render_plan(items, sources_dir, apply=True),
            sources_dir,
        )
        _atomic_write_text(index_path, render_index(items, sources_dir), sources_dir)
        write_manifest(items, sources_dir, manifest_path)
    else:
        _ensure_category_directories(sources_dir)
        items = build_plan(sources_dir)
        machine_plan = _make_machine_plan(items, sources_dir)
        plan_id = machine_plan["plan_id"]
        for output_path in (plan_path, index_path, manifest_path, machine_plan_path):
            _assert_safe_output_path(output_path, sources_dir)

        _atomic_write_text(
            plan_path,
            render_plan(items, sources_dir, apply=False, plan_id=plan_id),
            sources_dir,
        )
        _atomic_write_text(index_path, render_index(items, sources_dir), sources_dir)
        write_manifest(items, sources_dir, manifest_path)
        _atomic_write_text(
            machine_plan_path,
            json.dumps(machine_plan, ensure_ascii=False, indent=2) + "\n",
            sources_dir,
        )

    return OrganizeResult(sources_dir, apply, tuple(items), index_path, plan_path, manifest_path)
