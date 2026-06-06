from pathlib import Path

from virtuoso_wiki_bridge.organize import classify_source, organize_sources


def test_classify_source_by_extension(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    skill = sources / "layout.il"
    skill.write_text("procedure(test() t)", encoding="utf-8")

    category, reason, title = classify_source(skill, sources)

    assert category == "skill"
    assert "extension" in reason
    assert title


def test_organize_sources_dry_run_writes_plan_and_index(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "tb_ota.scs").write_text("simulator lang=spectre\ntran tran stop=1u", encoding="utf-8")
    (sources / "ota_notes.md").write_text("# OTA Notes\nfolded cascode gm/Id", encoding="utf-8")

    result = organize_sources(sources, apply=False)

    assert result.plan_path.is_file()
    assert result.index_path.is_file()
    assert result.manifest_path.is_file()
    assert (sources / "tb_ota.scs").is_file()
    assert not (sources / "spectre" / "tb_ota.scs").exists()
    assert "tb_ota.scs" in result.index_path.read_text(encoding="utf-8")


def test_organize_sources_apply_moves_uncategorized_files(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "tb_ota.scs").write_text("simulator lang=spectre\n", encoding="utf-8")
    (sources / "layout.il").write_text("procedure(test() t)", encoding="utf-8")

    result = organize_sources(sources, apply=True)

    assert (sources / "spectre" / "tb_ota.scs").is_file()
    assert (sources / "skill" / "layout.il").is_file()
    assert not (sources / "tb_ota.scs").exists()
    assert sum(1 for item in result.items if item.moved) == 2
