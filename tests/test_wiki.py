from pathlib import Path

import pytest

from virtuoso_wiki_bridge.wiki import build_context, copy_source, read_text_file, search, tokenize


def test_tokenize_analog_terms() -> None:
    tokens = tokenize("gm/Id folded-cascode pnoise Spectre")
    assert "gm/id" in tokens
    assert "gmid" in tokens
    assert "folded-cascode" in tokens
    assert "foldedcascode" in tokens
    assert "pnoise" in tokens


def test_search_finds_spectre_netlist(tmp_path: Path) -> None:
    netlist = tmp_path / "tb_ota.scs"
    netlist.write_text("simulator lang=spectre\n// folded cascode OTA noise testbench\n", encoding="utf-8")
    hits = search(tmp_path, "folded cascode noise", limit=3)
    assert hits
    assert hits[0].path == netlist


def test_search_finds_overlapping_chinese_phrase(tmp_path: Path) -> None:
    note = tmp_path / "ota.txt"
    note.write_text(
        "\u8fd9\u662f\u6298\u53e0\u5171\u6e90\u5171\u6805\u653e\u5927\u5668\u7684\u8bbe\u8ba1\u7b14\u8bb0",
        encoding="utf-8",
    )

    hits = search(tmp_path, "\u6298\u53e0\u5171\u6e90\u5171\u6805", limit=3)

    assert hits
    assert hits[0].path == note


def test_build_context_can_exclude_sources(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    sources = vault / "sources"
    concepts = vault / "concepts"
    sources.mkdir(parents=True)
    concepts.mkdir()
    (sources / "book.txt").write_text("folded cascode noise from source", encoding="utf-8")
    (concepts / "ota.md").write_text("# OTA\nfolded cascode noise from wiki", encoding="utf-8")

    context = build_context(vault, "folded cascode noise", exclude_roots=(sources,))

    assert "from wiki" in context
    assert "from source" not in context


def test_build_context_includes_source_index(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "INDEX.md").write_text("# Sources Index\n\n- `notes/ota.md` - OTA noise map", encoding="utf-8")
    (sources / "note.txt").write_text("folded cascode pnoise details", encoding="utf-8")

    context = build_context(sources, "folded cascode", limit=1)

    assert "[source-index]" in context
    assert "OTA noise map" in context
    assert "folded cascode pnoise" in context


def test_build_context_uses_relative_identities_without_absolute_path(tmp_path: Path) -> None:
    sources = tmp_path / "private-user" / "sources"
    note = sources / "notes" / "ota.txt"
    note.parent.mkdir(parents=True)
    note.write_text("folded cascode pnoise details", encoding="utf-8")

    context = build_context(sources, "folded cascode", limit=1)

    assert "path: notes/ota.txt" in context
    assert str(tmp_path) not in context


def test_build_context_escapes_terminal_control_sequences(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    payload = "# \x1b]52;c;UkVEVEVBTV9DTElQQk9BUkQ=\x07\nneedle phase margin"
    (sources / "malicious.md").write_text(payload, encoding="utf-8")
    (sources / "INDEX.md").write_text("index \x1b[31mred\x1b[0m\x07", encoding="utf-8")

    context = build_context(sources, "needle phase margin", limit=1)

    assert "\x1b" not in context
    assert "\x07" not in context
    assert "\\u001b" in context
    assert "\\u0007" in context


def test_search_skips_generated_source_index(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "INDEX.md").write_text("# Sources Index\nfolded cascode", encoding="utf-8")
    note = sources / "note.txt"
    note.write_text("folded cascode pnoise details", encoding="utf-8")

    hits = search(sources, "folded cascode", limit=5)

    assert hits
    assert all(hit.path.name != "INDEX.md" for hit in hits)
    assert hits[0].path == note


def test_search_allows_hidden_parent_directory(tmp_path: Path) -> None:
    vault = tmp_path / ".tmp" / "vault"
    notes = vault / "sources" / "notes"
    notes.mkdir(parents=True)
    source = notes / "ota.txt"
    source.write_text("folded cascode OTA source-first note", encoding="utf-8")

    hits = search(vault / "sources", "folded cascode OTA", limit=2)

    assert hits
    assert hits[0].path == source


def test_read_text_file_strips_utf8_bom(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_bytes("\ufefffolded cascode".encode("utf-8"))

    assert read_text_file(source) == "folded cascode"


def test_read_text_file_keeps_utf8_when_limit_splits_character(tmp_path: Path) -> None:
    source = tmp_path / "large-chinese.txt"
    character = "\u4e2d"
    source.write_bytes(character.encode("utf-8") * 266_667)

    text = read_text_file(source)

    assert text.count(character) == 266_666
    assert "\u6d93" not in text


def test_copy_source_deduplicates(tmp_path: Path) -> None:
    src = tmp_path / "book.txt"
    src.write_text("noise matching offset", encoding="utf-8")
    target1 = copy_source(src, tmp_path / "sources")
    target2 = copy_source(src, tmp_path / "sources")
    assert target1.exists()
    assert target2.exists()
    assert target1 != target2


def test_copy_source_avoids_case_insensitive_name_conflict(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    books = sources / "books"
    books.mkdir(parents=True)
    existing = books / "same.txt"
    existing.write_text("existing", encoding="utf-8")
    source = tmp_path / "SAME.TXT"
    source.write_text("new", encoding="utf-8")

    target = copy_source(source, sources)

    assert target.name.casefold() != existing.name.casefold()
    assert existing.read_text(encoding="utf-8") == "existing"
    assert target.read_text(encoding="utf-8") == "new"


@pytest.mark.parametrize("category", ["../outside", "../../escaped", "custom", "extracted"])
def test_copy_source_rejects_invalid_or_unsafe_category(tmp_path: Path, category: str) -> None:
    source = tmp_path / "book.txt"
    source.write_text("private source", encoding="utf-8")

    with pytest.raises(ValueError, match="category"):
        copy_source(source, tmp_path / "vault" / "sources", category=category)

    assert not (tmp_path / "outside" / "book.txt").exists()
    assert not (tmp_path / "escaped" / "book.txt").exists()


def test_copy_source_rejects_symlink_input(tmp_path: Path) -> None:
    source = tmp_path / "book.txt"
    source.write_text("private source", encoding="utf-8")
    link = tmp_path / "book-link.txt"
    try:
        link.symlink_to(source)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(ValueError, match="symlink|reparse"):
        copy_source(link, tmp_path / "sources")


def test_copy_source_rejects_linked_category_without_touching_external_directory(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    linked_books = sources / "books"
    try:
        linked_books.symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")
    source = tmp_path / "book.txt"
    source.write_text("private source", encoding="utf-8")

    with pytest.raises(ValueError, match="symlink|reparse"):
        copy_source(source, sources)

    assert list(external.iterdir()) == []


def test_copy_source_rejects_link_like_sources_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    carrier = tmp_path / "carrier"
    carrier.mkdir()
    linked_parent = carrier / "linked-parent"
    try:
        linked_parent.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")
    source = tmp_path / "book.txt"
    source.write_text("private source", encoding="utf-8")

    with pytest.raises(ValueError, match="traverse.*symlink"):
        copy_source(source, linked_parent / "sources")

    assert list(outside.iterdir()) == []
