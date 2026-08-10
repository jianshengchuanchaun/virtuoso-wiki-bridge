import os
from pathlib import Path

import pytest

import virtuoso_wiki_bridge.extract as extract_module
from virtuoso_wiki_bridge.extract import extract_all_sources, extract_source


def _source(path: Path, body: bytes = b"placeholder") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def test_extract_source_uses_stable_relative_identity_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = tmp_path / "sources"
    books = _source(sources / "books" / "same.pdf")
    papers = _source(sources / "papers" / "same.pdf")
    extracted = sources / "extracted"
    monkeypatch.setattr(extract_module, "_pdf_text", lambda path: f"text from {path.parent.name}")

    book_result = extract_source(books, extracted, source_root=sources)
    paper_result = extract_source(papers, extracted, source_root=sources)

    assert book_result.status == "ok"
    assert paper_result.status == "ok"
    assert book_result.target == extracted / "books" / "same.pdf.txt"
    assert paper_result.target == extracted / "papers" / "same.pdf.txt"
    assert book_result.target != paper_result.target

    repeated = extract_source(books, extracted, source_root=sources)
    assert repeated.status == "skipped"
    assert repeated.target == book_result.target
    assert sorted(path.relative_to(extracted).as_posix() for path in extracted.rglob("*.txt")) == [
        "books/same.pdf.txt",
        "papers/same.pdf.txt",
    ]


def test_force_only_overwrites_the_same_source_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = tmp_path / "sources"
    books = _source(sources / "books" / "same.pdf")
    papers = _source(sources / "papers" / "same.pdf")
    extracted = sources / "extracted"
    monkeypatch.setattr(extract_module, "_pdf_text", lambda path: f"initial {path.parent.name}")

    book_result = extract_source(books, extracted, source_root=sources)
    paper_result = extract_source(papers, extracted, source_root=sources)
    paper_before = paper_result.target.read_text(encoding="utf-8")

    monkeypatch.setattr(extract_module, "_pdf_text", lambda path: f"updated {path.parent.name}")
    forced = extract_source(books, extracted, source_root=sources, force=True)

    assert forced.status == "ok"
    assert forced.target == book_result.target
    assert "updated books" in forced.target.read_text(encoding="utf-8")
    assert paper_result.target.read_text(encoding="utf-8") == paper_before


def test_pdf_and_epub_with_same_stem_have_distinct_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = tmp_path / "sources"
    pdf = _source(sources / "books" / "same.pdf")
    epub = _source(sources / "books" / "same.epub")
    extracted = sources / "extracted"
    monkeypatch.setattr(extract_module, "_pdf_text", lambda _path: "pdf body")
    monkeypatch.setattr(extract_module, "_epub_text", lambda _path: "epub body")

    pdf_result = extract_source(pdf, extracted, source_root=sources)
    epub_result = extract_source(epub, extracted, source_root=sources)

    assert pdf_result.status == "ok"
    assert epub_result.status == "ok"
    assert pdf_result.target == extracted / "books" / "same.pdf.txt"
    assert epub_result.target == extracted / "books" / "same.epub.txt"
    assert pdf_result.target != epub_result.target


def test_extract_all_sources_is_idempotent_for_same_stems(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = tmp_path / "sources"
    _source(sources / "books" / "same.pdf")
    _source(sources / "papers" / "same.pdf")
    monkeypatch.setattr(extract_module, "_pdf_text", lambda path: f"text from {path.parent.name}")

    first = extract_all_sources(sources)
    second = extract_all_sources(sources)
    forced = extract_all_sources(sources, force=True)

    assert [result.status for result in first] == ["ok", "ok"]
    assert [result.status for result in second] == ["skipped", "skipped"]
    assert [result.status for result in forced] == ["ok", "ok"]
    assert len({result.target for result in first}) == 2
    assert {result.target for result in first} == {result.target for result in forced}


def test_empty_pdf_reports_scanned_or_image_only_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = tmp_path / "sources"
    source = _source(sources / "books" / "scanned.pdf")
    extracted = sources / "extracted"
    monkeypatch.setattr(extract_module, "_pdf_text", lambda _path: " \n")

    result = extract_source(source, extracted, source_root=sources)

    assert result.status == "empty"
    assert result.chars == 0
    assert "scanned or image-only" in result.detail
    assert result.target is not None and result.target.is_file()
    assert extract_source(source, extracted, source_root=sources).status == "skipped"


def test_extracted_frontmatter_quotes_relative_source_path_without_absolute_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = tmp_path / "sources"
    source = _source(sources / "books" / "report # draft.pdf")
    extracted = sources / "extracted"
    monkeypatch.setattr(extract_module, "_pdf_text", lambda _path: "body")

    result = extract_source(source, extracted, source_root=sources)

    text = result.target.read_text(encoding="utf-8")
    assert 'title: "report # draft"' in text
    assert 'source_path: "books/report # draft.pdf"' in text
    assert '  - "books/report # draft.pdf"' in text
    assert sources.as_posix() not in text
    for field in ("category:", "tags:", "sources:", "created:", "updated:"):
        assert field in text.split("---", 2)[1]


def test_source_root_is_inferred_for_existing_cli_call_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = tmp_path / "sources"
    source = _source(sources / "books" / "book.pdf")
    extracted = sources / "extracted"
    monkeypatch.setattr(extract_module, "_pdf_text", lambda _path: "body")

    result = extract_source(source, extracted)

    assert result.status == "ok"
    assert result.target == extracted / "books" / "book.pdf.txt"
    text = result.target.read_text(encoding="utf-8")
    assert 'source_path: "books/book.pdf"' in text
    assert sources.as_posix() not in text


def test_external_source_uses_opaque_relative_identity_without_path_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(tmp_path / "incoming" / "book.pdf")
    extracted = tmp_path / "output" / "extracted"
    monkeypatch.setattr(extract_module, "_pdf_text", lambda _path: "body")

    result = extract_source(source, extracted)

    assert result.status == "ok"
    assert result.target is not None
    assert result.target.is_relative_to(extracted / "external")
    text = result.target.read_text(encoding="utf-8")
    assert 'source_path: "external/' in text
    assert source.parent.as_posix() not in text


def test_explicit_source_root_rejects_source_outside_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    outside = _source(tmp_path / "outside.pdf")
    extracted = sources / "extracted"
    monkeypatch.setattr(extract_module, "_pdf_text", lambda _path: "must not run")

    result = extract_source(outside, extracted, source_root=sources)

    assert result.status == "failed"
    assert result.target is None
    assert "outside source root" in result.detail
    assert not extracted.exists()


def test_source_symlink_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    outside = _source(tmp_path / "outside.pdf")
    link = sources / "linked.pdf"
    try:
        os.symlink(outside, link)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    monkeypatch.setattr(extract_module, "_pdf_text", lambda _path: "must not run")

    result = extract_source(link, sources / "extracted", source_root=sources)

    assert result.status == "failed"
    assert result.target is None
    assert "symlink" in result.detail


def test_symlink_extraction_directory_is_rejected_without_touching_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = tmp_path / "sources"
    source = _source(sources / "books" / "book.pdf")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    extracted = sources / "extracted"
    try:
        os.symlink(outside, extracted, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    monkeypatch.setattr(extract_module, "_pdf_text", lambda _path: "must not run")

    result = extract_source(source, extracted, source_root=sources)

    assert result.status == "failed"
    assert result.target is None
    assert "symlink" in result.detail
    assert sentinel.read_text(encoding="utf-8") == "unchanged"


def test_source_root_with_link_like_ancestor_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path / "outside"
    source = _source(outside / "sources" / "books" / "book.pdf")
    carrier = tmp_path / "carrier"
    carrier.mkdir()
    linked_parent = carrier / "linked-parent"
    try:
        os.symlink(outside, linked_parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")
    monkeypatch.setattr(extract_module, "_pdf_text", lambda _path: "must not run")
    linked_sources = linked_parent / "sources"

    result = extract_source(
        linked_sources / "books" / source.name,
        linked_sources / "extracted",
        source_root=linked_sources,
    )

    assert result.status == "failed"
    assert "symlink" in result.detail
    assert not (outside / "sources" / "extracted").exists()
