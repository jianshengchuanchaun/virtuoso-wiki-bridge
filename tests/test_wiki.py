from pathlib import Path

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


def test_copy_source_deduplicates(tmp_path: Path) -> None:
    src = tmp_path / "book.txt"
    src.write_text("noise matching offset", encoding="utf-8")
    target1 = copy_source(src, tmp_path / "sources")
    target2 = copy_source(src, tmp_path / "sources")
    assert target1.exists()
    assert target2.exists()
    assert target1 != target2
