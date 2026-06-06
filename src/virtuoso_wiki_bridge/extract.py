"""Optional extraction of book-like sources into searchable text."""

from __future__ import annotations

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


def _unique_target(source: Path, extracted_dir: Path) -> Path:
    target = extracted_dir / f"{source.stem}.txt"
    if not target.exists():
        return target
    index = 2
    while True:
        candidate = extracted_dir / f"{source.stem}-{index}.txt"
        if not candidate.exists():
            return candidate
        index += 1


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


def extract_source(source: Path, extracted_dir: Path, *, force: bool = False) -> ExtractionResult:
    source = source.expanduser().resolve()
    extracted_dir = extracted_dir.expanduser().resolve()
    if not source.is_file():
        return ExtractionResult(source, None, "failed", f"source file not found: {source}")
    if not is_extractable(source):
        return ExtractionResult(source, None, "skipped", "not a supported PDF/EPUB source")

    extracted_dir.mkdir(parents=True, exist_ok=True)
    target = extracted_dir / f"{source.stem}.txt" if force else _unique_target(source, extracted_dir)
    if target.exists() and not force:
        return ExtractionResult(source, target, "skipped", "target already exists")

    try:
        if source.suffix.lower() == ".pdf":
            body = _pdf_text(source)
        elif source.suffix.lower() == ".epub":
            body = _epub_text(source)
        else:
            return ExtractionResult(source, None, "skipped", "not a supported PDF/EPUB source")
    except Exception as exc:  # noqa: BLE001 - surfaced to the CLI as an actionable status line.
        return ExtractionResult(source, None, "failed", str(exc))

    timestamp = datetime.now(timezone.utc).isoformat()
    text = (
        f"---\n"
        f"title: {source.stem}\n"
        f"source_path: {source.as_posix()}\n"
        f"extracted: {timestamp}\n"
        f"---\n\n"
        f"# {source.stem}\n\n"
        f"{body}\n"
    )
    target.write_text(text, encoding="utf-8", newline="\n")
    return ExtractionResult(source, target, "ok", "extracted", len(body))


def extract_all_sources(sources_dir: Path, *, force: bool = False) -> list[ExtractionResult]:
    sources_dir = sources_dir.expanduser().resolve()
    extracted_dir = sources_dir / "extracted"
    if not sources_dir.exists():
        return [ExtractionResult(sources_dir, None, "failed", f"sources directory not found: {sources_dir}")]

    results: list[ExtractionResult] = []
    for path in sources_dir.rglob("*"):
        if not path.is_file() or not is_extractable(path):
            continue
        try:
            path.resolve().relative_to(extracted_dir.resolve())
            continue
        except ValueError:
            pass
        results.append(extract_source(path, extracted_dir, force=force))
    return results
