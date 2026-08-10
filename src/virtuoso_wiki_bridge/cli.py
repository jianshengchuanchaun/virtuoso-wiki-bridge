"""Command line interface for Virtuoso Wiki Bridge."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from . import __version__
from .analog import ANALOG_CHECKLIST, suggested_instruction
from .config import AppConfig, load_config
from .extract import extract_all_sources, extract_source, is_extractable
from .organize import organize_sources
from .text_safety import sanitize_untrusted_field, sanitize_untrusted_text
from .vault import DEFAULT_SOURCE_SUBFOLDERS, init_vault
from .virtuoso import (
    DEFAULT_EVAL_TIMEOUT,
    DEFAULT_LOAD_TIMEOUT,
    DEFAULT_PULL_TIMEOUT,
    DEFAULT_SNAPSHOT_TIMEOUT,
    DEFAULT_SPECTRE_TIMEOUT,
    doctor,
    eval_skill,
    load_skill,
    pull_remote_run,
    run_spectre_remote,
    snapshot,
    status,
)
from .wiki import build_context, copy_source, search

INGEST_CATEGORIES = tuple(category for category in DEFAULT_SOURCE_SUBFOLDERS if category != "extracted")


def _print_result(name: str, ok: bool, detail: str) -> None:
    print(f"[{'ok' if ok else 'fail'}] {sanitize_untrusted_field(name)}: {sanitize_untrusted_text(detail)}")


def _print_config_context(config: AppConfig) -> None:
    env_label = config.env_path if config.env_path is not None else "<process environment and defaults>"
    print(f"env: {sanitize_untrusted_field(env_label)}")
    print(f"vault: {sanitize_untrusted_field(config.vault_path)}")
    print(f"sources: {sanitize_untrusted_field(config.sources_dir)}")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def cmd_init_vault(args: argparse.Namespace) -> int:
    env_option = getattr(args, "env", None)
    if args.env_path and env_option:
        env_path = Path(args.env_path).expanduser().resolve()
        env_option_path = Path(env_option).expanduser().resolve()
        if env_path != env_option_path:
            raise ValueError("--env and --env-path must refer to the same file when both are provided")
    selected_env_path = args.env_path or env_option or ".env"
    result = init_vault(
        args.path,
        env_path=selected_env_path,
        force_env=args.force_env,
        remote_workdir=args.remote_workdir,
    )
    print(f"vault: {sanitize_untrusted_field(result.vault_path)}")
    print(f"env: {sanitize_untrusted_field(result.env_path)}")
    print(f"env_written: {result.env_written}")
    print(f"created: {len(result.created)}")
    for path in result.created:
        print(f"  + {sanitize_untrusted_field(path)}")
    if result.skipped:
        print(f"skipped_existing: {len(result.skipped)}")
        for path in result.skipped[:20]:
            print(f"  = {sanitize_untrusted_field(path)}")
        if len(result.skipped) > 20:
            print(f"  ... {len(result.skipped) - 20} more")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.env)
    failed = False
    for name, ok, detail in doctor(config):
        _print_result(name, ok, detail)
        failed = failed or not ok
    return 1 if failed else 0


def cmd_ingest_source(args: argparse.Namespace) -> int:
    config = load_config(args.env)
    _print_config_context(config)
    target = copy_source(Path(args.path), config.sources_dir, category=args.category)
    print(f"copied: {sanitize_untrusted_field(target)}")
    if args.extract and is_extractable(target):
        result = extract_source(
            target,
            config.sources_dir / "extracted",
            force=args.force_extract,
            source_root=config.sources_dir,
        )
        print(
            f"extraction: {sanitize_untrusted_field(result.status)} "
            f"{sanitize_untrusted_text(result.detail)}"
        )
        if result.target:
            print(f"extracted_text: {sanitize_untrusted_field(result.target)}")
        if result.status in {"failed", "empty"}:
            return 1
    print("Text retrieval works best for extracted text, .md/.txt/.scs/.cdl/.il/.va/.tex/.log files.")
    return 0


def cmd_extract_sources(args: argparse.Namespace) -> int:
    config = load_config(args.env)
    _print_config_context(config)
    results = extract_all_sources(config.sources_dir, force=args.force)
    if not results:
        print(f"No PDF/EPUB sources found under {sanitize_untrusted_field(config.sources_dir)}.")
        return 0
    failed = False
    for result in results:
        failed = failed or result.status in {"failed", "empty"}
        target = f" -> {sanitize_untrusted_field(result.target)}" if result.target else ""
        chars = f" chars={result.chars}" if result.chars else ""
        print(
            f"[{sanitize_untrusted_field(result.status)}] {sanitize_untrusted_field(result.source)}"
            f"{target}{chars} {sanitize_untrusted_text(result.detail)}"
        )
    return 1 if failed else 0


def cmd_organize_sources(args: argparse.Namespace) -> int:
    config = load_config(args.env)
    _print_config_context(config)
    result = organize_sources(config.sources_dir, apply=args.apply)
    mode = "applied" if args.apply else "dry-run"
    moved = sum(1 for item in result.items if item.moved)
    planned = sum(1 for item in result.items if item.path != item.target)
    print(f"mode: {mode}")
    print(f"sources: {sanitize_untrusted_field(result.sources_dir)}")
    print(f"files: {len(result.items)}")
    print(f"planned_moves: {planned}")
    print(f"moved: {moved}")
    print(f"plan: {sanitize_untrusted_field(result.plan_path)}")
    print(f"index: {sanitize_untrusted_field(result.index_path)}")
    print(f"manifest: {sanitize_untrusted_field(result.manifest_path)}")
    if result.items:
        print()
        for item in result.items[: args.limit]:
            action = "move" if item.path != item.target else "keep"
            if item.moved:
                action = "moved"
            print(
                f"- [{action}] {sanitize_untrusted_field(item.category)}: "
                f"{sanitize_untrusted_field(item.path.name)}"
            )
            print(f"  reason: {sanitize_untrusted_field(item.reason)}")
            print(f"  target: {sanitize_untrusted_field(item.target)}")
        if len(result.items) > args.limit:
            print(
                f"... {len(result.items) - args.limit} more files in "
                f"{sanitize_untrusted_field(result.plan_path)}"
            )
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    config = load_config(args.env)
    source_root = config.sources_dir.resolve()
    seen: set[Path] = set()
    hits = []
    for hit in search(config.sources_dir, args.query, limit=args.limit):
        key = hit.path.resolve()
        if key not in seen:
            seen.add(key)
            hits.append(hit)
    if config.sources_dir.resolve() != config.vault_path.resolve():
        for hit in search(config.vault_path, args.query, limit=args.limit, exclude_roots=(config.sources_dir,)):
            key = hit.path.resolve()
            if key not in seen:
                seen.add(key)
                hits.append(hit)

    def sort_key(hit):
        try:
            in_sources = hit.path.resolve().is_relative_to(source_root)
        except ValueError:
            in_sources = False
        return (1 if in_sources else 0, hit.score)

    hits.sort(key=sort_key, reverse=True)
    for index, hit in enumerate(hits[: args.limit], 1):
        print(f"{index}. {sanitize_untrusted_field(hit.title)}")
        print(f"   score: {hit.score:.3f}")
        print(f"   path: {sanitize_untrusted_field(hit.path)}")
        print(f"   {sanitize_untrusted_field(hit.excerpt)}")
    if not hits:
        print("No matches.")
    return 0


def cmd_ask_pack(args: argparse.Namespace) -> int:
    config = load_config(args.env)
    source_context = build_context(config.sources_dir, args.question, limit=args.limit)
    wiki_context = build_context(config.vault_path, args.question, limit=args.limit, exclude_roots=(config.sources_dir,))
    print("# Virtuoso analog reasoning context")
    print()
    print("## Question")
    print(sanitize_untrusted_text(args.question))
    print()
    print("## Source context")
    print(source_context)
    print()
    print("## Wiki context")
    print(wiki_context)
    print()
    print(ANALOG_CHECKLIST)
    print()
    print("## Suggested assistant instruction")
    print(suggested_instruction())
    return 0


def _print_summary(summary) -> int:
    if summary.stdout:
        print(sanitize_untrusted_text(summary.stdout), end="")
    if summary.stderr:
        print(sanitize_untrusted_text(summary.stderr), end="", file=sys.stderr)
    if summary.remote_dir:
        print(f"\nremote_dir: {sanitize_untrusted_field(summary.remote_dir)}")
    print(f"elapsed_seconds: {summary.elapsed_seconds:.1f}")
    print(f"returncode: {summary.returncode}")
    return summary.returncode


def cmd_bridge_status(args: argparse.Namespace) -> int:
    return _print_summary(status(load_config(args.env)))


def cmd_eval_skill(args: argparse.Namespace) -> int:
    return _print_summary(eval_skill(load_config(args.env), args.expr, timeout=args.timeout))


def cmd_load_skill(args: argparse.Namespace) -> int:
    return _print_summary(load_skill(load_config(args.env), Path(args.path), timeout=args.timeout))


def cmd_snapshot(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    return _print_summary(snapshot(load_config(args.env), output, timeout=args.timeout))


def cmd_run_spectre(args: argparse.Namespace) -> int:
    return _print_summary(
        run_spectre_remote(load_config(args.env), Path(args.netlist), name=args.name, timeout=args.timeout)
    )


def cmd_pull_run(args: argparse.Namespace) -> int:
    config = load_config(args.env)
    rc = pull_remote_run(config, args.run_name, Path(args.local_dir), timeout=args.timeout)
    print(f"returncode: {rc}")
    return rc


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--env",
        default=argparse.SUPPRESS,
        help="Path to .env. May appear before or after the command.",
    )
    parser = argparse.ArgumentParser(
        prog="virtuoso-wiki-bridge",
        description="Combine Virtuoso/Spectre bridge operations with an Obsidian-style analog knowledge base.",
    )
    parser.add_argument("--env", help="Path to .env. Defaults to ./.env, then ~/.virtuoso-wiki-bridge/.env.")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser(
        "init-vault",
        parents=[common],
        help="Create an analog design wiki vault and matching .env.",
    )
    p.add_argument("path", help="Vault directory to create.")
    p.add_argument("--env-path", help="Backward-compatible alias for --env when creating the generated .env.")
    p.add_argument("--force-env", action="store_true", help="Overwrite env-path if it already exists.")
    p.add_argument("--remote-workdir", default="~/virtuoso-work/virtuoso-wiki-bridge")
    p.set_defaults(func=cmd_init_vault)

    p = sub.add_parser("doctor", parents=[common], help="Check vault, sources, bridge CLI, and optional SSH.")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("ingest-source", parents=[common], help="Copy a book/paper/netlist/SKILL file into sources.")
    p.add_argument("path")
    p.add_argument(
        "--category",
        choices=INGEST_CATEGORIES,
        default="books",
        help="Allowed source subfolder. Default: books.",
    )
    p.add_argument("--extract", action=argparse.BooleanOptionalAction, default=True, help="Extract PDF/EPUB text when possible.")
    p.add_argument("--force-extract", action="store_true", help="Overwrite an existing extracted text file.")
    p.set_defaults(func=cmd_ingest_source)

    p = sub.add_parser("extract-sources", parents=[common], help="Extract all PDF/EPUB files under sources into sources/extracted.")
    p.add_argument("--force", action="store_true", help="Overwrite existing extracted text files.")
    p.set_defaults(func=cmd_extract_sources)

    p = sub.add_parser("organize-sources", parents=[common], help="Classify sources, write INDEX.md, and optionally move files into category folders.")
    p.add_argument("--apply", action="store_true", help="Move files according to the generated plan. Without this, only writes a dry-run plan.")
    p.add_argument("-n", "--limit", type=int, default=20, help="Number of plan items to print.")
    p.set_defaults(func=cmd_organize_sources)

    p = sub.add_parser("search", parents=[common], help="Search sources first, then wiki pages.")
    p.add_argument("query")
    p.add_argument("-n", "--limit", type=int, default=8)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("ask-pack", parents=[common], help="Create an analog-design context pack for an LLM.")
    p.add_argument("question")
    p.add_argument("-n", "--limit", type=int, default=6)
    p.set_defaults(func=cmd_ask_pack)

    p = sub.add_parser("bridge-status", parents=[common], help="Run upstream virtuoso-bridge status.")
    p.set_defaults(func=cmd_bridge_status)

    p = sub.add_parser("eval-skill", parents=[common], help="Run inline SKILL through upstream virtuoso-bridge.")
    p.add_argument("expr")
    p.add_argument(
        "--timeout",
        type=_positive_int,
        default=DEFAULT_EVAL_TIMEOUT,
        help=f"Operation timeout in seconds. Default: {DEFAULT_EVAL_TIMEOUT}.",
    )
    p.set_defaults(func=cmd_eval_skill)

    p = sub.add_parser("load-skill", parents=[common], help="Load a .il/.skill file through upstream virtuoso-bridge.")
    p.add_argument("path")
    p.add_argument(
        "--timeout",
        type=_positive_int,
        default=DEFAULT_LOAD_TIMEOUT,
        help=f"Operation timeout in seconds. Default: {DEFAULT_LOAD_TIMEOUT}.",
    )
    p.set_defaults(func=cmd_load_skill)

    p = sub.add_parser("snapshot", parents=[common], help="Capture focused Virtuoso/Maestro state via upstream bridge.")
    p.add_argument("-o", "--output")
    p.add_argument(
        "--timeout",
        type=_positive_int,
        default=DEFAULT_SNAPSHOT_TIMEOUT,
        help=f"Operation timeout in seconds. Default: {DEFAULT_SNAPSHOT_TIMEOUT}.",
    )
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("run-spectre", parents=[common], help="Run a Spectre netlist over optional SSH fallback.")
    p.add_argument("netlist")
    p.add_argument("--name")
    p.add_argument(
        "--timeout",
        type=_positive_int,
        default=DEFAULT_SPECTRE_TIMEOUT,
        help=f"Per-process timeout in seconds. Default: {DEFAULT_SPECTRE_TIMEOUT}.",
    )
    p.set_defaults(func=cmd_run_spectre)

    p = sub.add_parser("pull-run", parents=[common], help="Pull a named SSH run from the configured runs directory.")
    p.add_argument("run_name", help="Safe run name previously used with run-spectre --name.")
    p.add_argument("local_dir")
    p.add_argument(
        "--timeout",
        type=_positive_int,
        default=DEFAULT_PULL_TIMEOUT,
        help=f"Operation timeout in seconds. Default: {DEFAULT_PULL_TIMEOUT}.",
    )
    p.set_defaults(func=cmd_pull_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(f"virtuoso-wiki-bridge {__version__}")
        return 0
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: {sanitize_untrusted_text(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
