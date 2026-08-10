"""Optional extraction of book-like sources into searchable text."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

EXTRACTABLE_EXTENSIONS = {".pdf", ".epub"}


@dataclass(frozen=True)
class ExtractionResult:
    source: Path
    target: Path | None
    status: str
    detail: str
    chars: int = 0


def is_extractable(path: Path) -> bool:
    return path.suffix.lower() in EXTRACTABLE_EXTENSIONS


def _absolute(path: Path) -> Path:
    """Return an absolute lexical path without following symlinks."""
    return Path(os.path.abspath(path.expanduser()))


def _relative_to(path: Path, root: Path) -> Path | None:
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def _is_linklike(path: Path) -> bool:
    """Detect symlinks and Windows reparse points such as junctions."""
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _has_linklike_ancestor(path: Path) -> bool:
    absolute = _absolute(path)
    return any(_is_linklike(component) for component in (absolute, *absolute.parents))


def _has_symlink_component(root: Path, path: Path) -> bool:
    """Check path components at and below root without leaving the boundary."""
    relative = _relative_to(path, root)
    if relative is None:
        return True
    current = root
    if _is_linklike(current):
        return True
    for part in relative.parts:
        current = current / part
        if _is_linklike(current):
            return True
    return False


def _validated_source(
    source: Path,
    source_root: Path | None,
) -> tuple[Path, Path | None, str | None]:
    source_path = _absolute(source)
    if _has_linklike_ancestor(source_path):
        return (
            source_path,
            None,
            f"refusing source path containing a symlink, junction, or reparse point: {source_path}",
        )
    if not source_path.is_file():
        return source_path, None, f"source file not found: {source_path}"

    if source_root is None:
        return source_path.resolve(strict=True), None, None

    root_path = _absolute(source_root)
    if _has_linklike_ancestor(root_path):
        return (
            source_path,
            None,
            f"refusing source root containing a symlink, junction, or reparse point: {root_path}",
        )
    if not root_path.is_dir():
        return source_path, None, f"source root not found or not a directory: {root_path}"

    lexical_relative = _relative_to(source_path, root_path)
    if lexical_relative is None:
        return source_path, None, f"source is outside source root: {source_path}"
    if _has_symlink_component(root_path, source_path):
        return source_path, None, f"refusing source path containing a symlink: {source_path}"

    resolved_root = root_path.resolve(strict=True)
    resolved_source = source_path.resolve(strict=True)
    if _relative_to(resolved_source, resolved_root) is None:
        return source_path, None, f"source resolves outside source root: {source_path}"
    return resolved_source, resolved_root, None


def _infer_source_root(source: Path, extracted_dir: Path) -> Path | None:
    candidate = _absolute(extracted_dir).parent
    if _has_linklike_ancestor(candidate) or not candidate.is_dir():
        return None
    try:
        source.resolve(strict=True).relative_to(candidate.resolve(strict=True))
    except (FileNotFoundError, ValueError):
        return None
    return candidate


def _source_identity(source: Path, source_root: Path | None) -> tuple[Path, str]:
    if source_root is not None:
        relative = source.relative_to(source_root)
        source_label = relative.as_posix()
    else:
        digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:12]
        relative = Path("external") / digest / source.name
        source_label = relative.as_posix()

    # Keep the original extension in the output name so foo.pdf and foo.epub
    # remain distinct identities even when they share a directory and stem.
    target_relative = relative.with_name(f"{relative.name}.txt")
    return target_relative, source_label


def _safe_target(extracted_dir: Path, target_relative: Path) -> tuple[Path | None, str | None]:
    output_root = _absolute(extracted_dir)
    if _has_linklike_ancestor(output_root):
        return (
            None,
            f"refusing extraction directory containing a symlink, junction, or reparse point: {output_root}",
        )
    if output_root.exists() and not output_root.is_dir():
        return None, f"extraction path is not a directory: {output_root}"

    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, f"could not create extraction directory {output_root}: {exc}"
    if _has_linklike_ancestor(output_root):
        return (
            None,
            f"refusing extraction directory containing a symlink, junction, or reparse point: {output_root}",
        )

    resolved_root = output_root.resolve(strict=True)
    target = output_root / target_relative
    if _relative_to(_absolute(target), output_root) is None:
        return None, f"extraction target escapes extraction directory: {target}"

    relative_parent = target_relative.parent
    current = output_root
    for part in relative_parent.parts:
        current = current / part
        if _is_linklike(current):
            return None, f"refusing symlink extraction target parent: {current}"
        if current.exists() and not current.is_dir():
            return None, f"extraction target parent is not a directory: {current}"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, f"could not create extraction target directory {target.parent}: {exc}"

    # Re-check after mkdir to reduce the opportunity for a symlink swap.
    if _has_symlink_component(output_root, target.parent):
        return None, f"refusing extraction target path containing a symlink: {target.parent}"
    try:
        target.parent.resolve(strict=True).relative_to(resolved_root)
    except ValueError:
        return None, f"extraction target resolves outside extraction directory: {target}"

    if _is_linklike(target):
        return None, f"refusing symlink extraction target: {target}"
    if target.exists() and not target.is_file():
        return None, f"extraction target is not a regular file: {target}"
    return target, None


def _yaml_string(value: str) -> str:
    """JSON strings are valid, safely quoted YAML scalars."""
    return json.dumps(value, ensure_ascii=False)


def _write_text(path: Path, text: str, *, overwrite: bool) -> None:
    """Atomically publish text without following a target symlink."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)

        if _is_linklike(path):
            raise OSError(f"refusing symlink extraction target: {path}")
        if overwrite:
            os.replace(temporary_path, path)
        else:
            # A hard-link publish is an atomic no-clobber operation: it fails
            # if another process created the target while extraction ran.
            os.link(temporary_path, path)
            temporary_path.unlink()
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF extraction requires: python -m pip install -e .[books]") from exc

    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page_index, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if text.strip():
            chunks.append(f"\n\n## Page {page_index}\n\n{text.strip()}")
    return "\n".join(chunks).strip()


def _epub_text(path: Path) -> str:
    try:
        import ebooklib
        from bs4 import BeautifulSoup
        from ebooklib import epub
    except ImportError as exc:
        raise RuntimeError("EPUB extraction requires: python -m pip install -e .[books]") from exc

    book = epub.read_epub(str(path))
    chunks: list[str] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text("\n", strip=True)
        if text:
            chunks.append(text)
    return "\n\n".join(chunks).strip()


def extract_source(
    source: Path,
    extracted_dir: Path,
    *,
    force: bool = False,
    source_root: Path | None = None,
) -> ExtractionResult:
    lexical_source = _absolute(source)
    effective_root = source_root
    if effective_root is None:
        effective_root = _infer_source_root(lexical_source, extracted_dir)

    validated_source, validated_root, validation_error = _validated_source(lexical_source, effective_root)
    if validation_error:
        return ExtractionResult(validated_source, None, "failed", validation_error)
    if not is_extractable(validated_source):
        return ExtractionResult(validated_source, None, "skipped", "not a supported PDF/EPUB source")

    target_relative, source_label = _source_identity(validated_source, validated_root)
    target, target_error = _safe_target(extracted_dir, target_relative)
    if target_error or target is None:
        return ExtractionResult(validated_source, None, "failed", target_error or "invalid extraction target")
    if target.exists() and not force:
        return ExtractionResult(validated_source, target, "skipped", "extracted target already exists")

    try:
        if validated_source.suffix.lower() == ".pdf":
            body = _pdf_text(validated_source)
        elif validated_source.suffix.lower() == ".epub":
            body = _epub_text(validated_source)
        else:
            return ExtractionResult(validated_source, None, "skipped", "not a supported PDF/EPUB source")
    except Exception as exc:  # noqa: BLE001 - surfaced to the CLI as an actionable status line.
        return ExtractionResult(validated_source, None, "failed", str(exc))

    timestamp = datetime.now(timezone.utc).isoformat()
    title = validated_source.stem.replace("\r", " ").replace("\n", " ").strip() or validated_source.name
    text = (
        f"---\n"
        f"title: {_yaml_string(title)}\n"
        f"category: {_yaml_string('extracted-source')}\n"
        f"tags:\n"
        f"  - {_yaml_string('source/extracted')}\n"
        f"sources:\n"
        f"  - {_yaml_string(source_label)}\n"
        f"created: {_yaml_string(timestamp)}\n"
        f"updated: {_yaml_string(timestamp)}\n"
        f"source_path: {_yaml_string(source_label)}\n"
        f"extracted: {_yaml_string(timestamp)}\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{body}\n"
    )
    # Extraction may be slow. Re-check containment after parsing in case a
    # target directory was replaced while the document was being processed.
    write_target, target_error = _safe_target(extracted_dir, target_relative)
    if target_error or write_target is None:
        return ExtractionResult(validated_source, None, "failed", target_error or "invalid extraction target")
    if write_target.exists() and not force:
        return ExtractionResult(validated_source, write_target, "skipped", "extracted target already exists")

    try:
        _write_text(write_target, text, overwrite=force)
    except FileExistsError:
        return ExtractionResult(validated_source, write_target, "skipped", "extracted target already exists")
    except OSError as exc:
        return ExtractionResult(validated_source, write_target, "failed", f"could not write extraction target: {exc}")

    if not body.strip():
        detail = "no extractable text found; the document may be scanned or image-only"
        return ExtractionResult(validated_source, write_target, "empty", detail, 0)
    return ExtractionResult(validated_source, write_target, "ok", "extracted", len(body))


def extract_all_sources(sources_dir: Path, *, force: bool = False) -> list[ExtractionResult]:
    lexical_root = _absolute(sources_dir)
    if _has_linklike_ancestor(lexical_root):
        return [
            ExtractionResult(
                lexical_root,
                None,
                "failed",
                f"refusing source root containing a symlink, junction, or reparse point: {lexical_root}",
            )
        ]
    if not lexical_root.is_dir():
        return [ExtractionResult(lexical_root, None, "failed", f"sources directory not found: {lexical_root}")]

    sources_root = lexical_root.resolve(strict=True)
    extracted_dir = lexical_root / "extracted"
    if _is_linklike(extracted_dir):
        return [
            ExtractionResult(
                sources_root,
                None,
                "failed",
                f"refusing symlink extraction directory: {extracted_dir}",
            )
        ]

    results: list[ExtractionResult] = []
    for path in sorted(lexical_root.rglob("*")):
        if _is_linklike(path):
            if is_extractable(path):
                results.append(ExtractionResult(path, None, "failed", f"refusing symlink source: {path}"))
            continue
        if not path.is_file() or not is_extractable(path):
            continue
        if _relative_to(path, extracted_dir) is not None:
            continue
        results.append(extract_source(path, extracted_dir, force=force, source_root=lexical_root))
    return results
