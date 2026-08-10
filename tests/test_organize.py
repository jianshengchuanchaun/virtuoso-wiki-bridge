import hashlib
import json
import os
from pathlib import Path

import pytest

from virtuoso_wiki_bridge.organize import (
    MACHINE_PLAN_FILENAME,
    classify_source,
    organize_sources,
)


def test_classify_source_by_extension(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    skill = sources / "layout.il"
    skill.write_text("procedure(test() t)", encoding="utf-8")

    category, reason, title = classify_source(skill, sources)

    assert category == "skill"
    assert "extension" in reason
    assert title


def test_generated_plan_and_index_escape_terminal_controls(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "unsafe.md").write_text(
        "# \x1b]52;c;UkVEVEVBTV9DTElQQk9BUkQ=\x07\nphase margin",
        encoding="utf-8",
    )

    result = organize_sources(sources, apply=False)
    rendered = result.plan_path.read_text(encoding="utf-8") + result.index_path.read_text(encoding="utf-8")

    assert "\x1b" not in rendered
    assert "\x07" not in rendered
    assert "\\u001b" in rendered
    assert "\\u0007" in rendered


def test_organize_sources_dry_run_writes_plan_and_index(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    drop = sources / "incoming"
    drop.mkdir()
    (drop / "tb_ota.scs").write_text(
        "simulator lang=spectre\ntran tran stop=1u",
        encoding="utf-8",
    )
    (sources / "ota_notes.md").write_text("# OTA Notes\nfolded cascode gm/Id", encoding="utf-8")

    result = organize_sources(sources, apply=False)

    assert result.plan_path.is_file()
    assert result.index_path.is_file()
    assert result.manifest_path.is_file()
    assert (sources / MACHINE_PLAN_FILENAME).is_file()
    assert (drop / "tb_ota.scs").is_file()
    assert not (sources / "spectre" / "tb_ota.scs").exists()
    index = result.index_path.read_text(encoding="utf-8")
    assert "`incoming/tb_ota.scs`" in index
    assert "`spectre/tb_ota.scs`" not in index


def test_organize_sources_apply_moves_uncategorized_files(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "tb_ota.scs").write_text("simulator lang=spectre\n", encoding="utf-8")
    (sources / "layout.il").write_text("procedure(test() t)", encoding="utf-8")

    organize_sources(sources, apply=False)
    machine_plan = (sources / MACHINE_PLAN_FILENAME).read_bytes()
    result = organize_sources(sources, apply=True)

    assert (sources / "spectre" / "tb_ota.scs").is_file()
    assert (sources / "skill" / "layout.il").is_file()
    assert not (sources / "tb_ota.scs").exists()
    assert sum(1 for item in result.items if item.moved) == 2
    assert (sources / MACHINE_PLAN_FILENAME).read_bytes() == machine_plan
    index = result.index_path.read_text(encoding="utf-8")
    assert "`spectre/tb_ota.scs`" in index


def test_batch_duplicate_and_case_conflicting_names_never_clobber(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    first_drop = sources / "drop-a"
    second_drop = sources / "drop-b"
    first_drop.mkdir(parents=True)
    second_drop.mkdir()
    (first_drop / "same.txt").write_text("first content", encoding="utf-8")
    (second_drop / "SAME.TXT").write_text("second content", encoding="utf-8")

    dry_run = organize_sources(sources, apply=False)
    targets = [item.target for item in dry_run.items]

    assert len(targets) == 2
    assert len({str(path).casefold() for path in targets}) == 2

    organize_sources(sources, apply=True)

    kept_contents = {
        path.read_text(encoding="utf-8")
        for path in (sources / "notes").iterdir()
        if path.is_file()
    }
    assert kept_contents == {"first content", "second content"}
    assert not (first_drop / "same.txt").exists()
    assert not (second_drop / "SAME.TXT").exists()


def test_apply_without_reviewed_machine_plan_is_rejected(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    raw = sources / "tb.scs"
    raw.write_text("simulator lang=spectre\n", encoding="utf-8")

    with pytest.raises(ValueError, match="No approved sources plan"):
        organize_sources(sources, apply=True)

    assert raw.read_text(encoding="utf-8") == "simulator lang=spectre\n"
    assert not (sources / "spectre" / "tb.scs").exists()


def test_apply_rejects_added_source_and_moves_nothing(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    reviewed = sources / "reviewed.scs"
    reviewed.write_text("simulator lang=spectre\n", encoding="utf-8")
    organize_sources(sources, apply=False)
    added = sources / "unreviewed.il"
    added.write_text("procedure(unreviewed() t)", encoding="utf-8")

    with pytest.raises(ValueError, match="file set changed"):
        organize_sources(sources, apply=True)

    assert reviewed.is_file()
    assert added.is_file()
    assert not (sources / "spectre" / reviewed.name).exists()
    assert not (sources / "skill" / added.name).exists()


def test_apply_rejects_content_drift_and_moves_nothing(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    unchanged = sources / "unchanged.il"
    changed = sources / "changed.scs"
    unchanged.write_text("procedure(stays() t)", encoding="utf-8")
    changed.write_text("simulator lang=spectre\nvalue=1", encoding="utf-8")
    organize_sources(sources, apply=False)
    changed.write_text("simulator lang=spectre\nvalue=2", encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256 changed"):
        organize_sources(sources, apply=True)

    assert unchanged.is_file()
    assert changed.is_file()
    assert not (sources / "skill" / unchanged.name).exists()
    assert not (sources / "spectre" / changed.name).exists()


def test_apply_rejects_existing_target_without_overwriting(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    raw = sources / "tb.scs"
    raw.write_text("reviewed source", encoding="utf-8")
    dry_run = organize_sources(sources, apply=False)
    target = next(item.target for item in dry_run.items if item.path == raw)
    target.write_text("pre-existing target", encoding="utf-8")

    with pytest.raises(ValueError, match="plan drift|target now exists"):
        organize_sources(sources, apply=True)

    assert raw.read_text(encoding="utf-8") == "reviewed source"
    assert target.read_text(encoding="utf-8") == "pre-existing target"


def test_full_sha256_detects_change_after_old_two_megabyte_boundary(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    raw = sources / "large.txt"
    original = b"a" * 2_000_000 + b"x"
    raw.write_bytes(original)

    organize_sources(sources, apply=False)
    document = json.loads((sources / MACHINE_PLAN_FILENAME).read_text(encoding="utf-8"))
    assert document["items"][0]["sha256"] == hashlib.sha256(original).hexdigest()

    raw.write_bytes(original[:-1] + b"y")
    with pytest.raises(ValueError, match="SHA-256 changed"):
        organize_sources(sources, apply=True)

    assert raw.is_file()
    assert not (sources / "notes" / raw.name).exists()


def test_modified_machine_plan_is_rejected(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    raw = sources / "notes.txt"
    raw.write_text("review this", encoding="utf-8")
    organize_sources(sources, apply=False)
    plan_path = sources / MACHINE_PLAN_FILENAME
    document = json.loads(plan_path.read_text(encoding="utf-8"))
    document["items"][0]["target"] = "notes/other.txt"
    plan_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="modified after generation"):
        organize_sources(sources, apply=True)

    assert raw.is_file()
    assert not (sources / "notes" / "other.txt").exists()


def test_source_symlink_is_rejected_without_touching_external_file(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("outside", encoding="utf-8")
    link = sources / "linked.txt"
    try:
        link.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(ValueError, match="symlinks, junctions, or reparse points"):
        organize_sources(sources, apply=False)

    assert external.read_text(encoding="utf-8") == "outside"


def test_generated_output_symlink_is_not_followed(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    external = tmp_path / "external-index.md"
    external.write_text("outside", encoding="utf-8")
    output_link = sources / "INDEX.md"
    try:
        output_link.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(ValueError, match="symlinks, junctions, or reparse points"):
        organize_sources(sources, apply=False)

    assert external.read_text(encoding="utf-8") == "outside"


def test_sources_path_with_link_like_ancestor_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    sources = outside / "sources"
    sources.mkdir(parents=True)
    raw = sources / "ota.txt"
    raw.write_text("folded cascode", encoding="utf-8")
    carrier = tmp_path / "carrier"
    carrier.mkdir()
    linked_parent = carrier / "linked-parent"
    try:
        os.symlink(outside, linked_parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")

    with pytest.raises(ValueError, match="traverse.*symlink"):
        organize_sources(linked_parent / "sources", apply=False)

    assert raw.read_text(encoding="utf-8") == "folded cascode"
    assert not (sources / "INDEX.md").exists()
