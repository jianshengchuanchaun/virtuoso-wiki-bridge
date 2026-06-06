"""Command line interface for Virtuoso Wiki Bridge."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .analog import ANALOG_CHECKLIST, suggested_instruction
from .config import load_config
from .extract import extract_all_sources, extract_source, is_extractable
from .vault import init_vault
from .virtuoso import doctor, eval_skill, load_skill, pull_remote_run, run_spectre_remote, snapshot, status
from .wiki import build_context, copy_source, search


def _print_result(name: str, ok: bool, detail: str) -> None:
    print(f"[{'ok' if ok else 'fail'}] {name}: {detail}")


def cmd_init_vault(args: argparse.Namespace) -> int:
    result = init_vault(
        args.path,
        env_path=args.env_path,
        force_env=args.force_env,
        remote_workdir=args.remote_workdir,
    )
    print(f"vault: {result.vault_path}")
    print(f"env: {result.env_path}")
    print(f"env_written: {result.env_written}")
    print(f"created: {len(result.created)}")
    for path in result.created:
        print(f"  + {path}")
    if result.skipped:
        print(f"skipped_existing: {len(result.skipped)}")
        for path in result.skipped[:20]:
            print(f"  = {path}")
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
    target = copy_source(Path(args.path), config.sources_dir, category=args.category)
    print(f"copied: {target}")
    if args.extract and is_extractable(target):
        result = extract_source(target, config.sources_dir / "extracted", force=args.force_extract)
        print(f"extraction: {result.status} {result.detail}")
        if result.target:
            print(f"extracted_text: {result.target}")
    print("Text retrieval works best for extracted text, .md/.txt/.scs/.cdl/.il/.va/.tex/.log files.")
    return 0


def cmd_extract_sources(args: argparse.Namespace) -> int:
    config = load_config(args.env)
    results = extract_all_sources(config.sources_dir, force=args.force)
    if not results:
        print(f"No PDF/EPUB sources found under {config.sources_dir}.")
        return 0
    failed = False
    for result in results:
        failed = failed or result.status == "failed"
        target = f" -> {result.target}" if result.target else ""
        chars = f" chars={result.chars}" if result.chars else ""
        print(f"[{result.status}] {result.source}{target}{chars} {result.detail}")
    return 1 if failed else 0


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
        print(f"{index}. {hit.title}")
        print(f"   score: {hit.score:.3f}")
        print(f"   path: {hit.path}")
        print(f"   {hit.excerpt}")
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
    print(args.question)
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
        print(summary.stdout, end="")
    if summary.stderr:
        print(summary.stderr, end="", file=sys.stderr)
    if summary.remote_dir:
        print(f"\nremote_dir: {summary.remote_dir}")
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
    rc = pull_remote_run(config, args.remote_dir, Path(args.local_dir))
    print(f"returncode: {rc}")
    return rc


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--env", help="Path to .env. Defaults to ./.env, then ~/.virtuoso-wiki-bridge/.env.")
    parser = argparse.ArgumentParser(
        prog="virtuoso-wiki-bridge",
        description="Combine Virtuoso/Spectre bridge operations with an Obsidian-style analog knowledge base.",
    )
    parser.add_argument("--env", help="Path to .env. Defaults to ./.env, then ~/.virtuoso-wiki-bridge/.env.")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("init-vault", help="Create an analog design wiki vault and matching .env.")
    p.add_argument("path", help="Vault directory to create.")
    p.add_argument("--env-path", default=".env", help="Where to write generated .env. Default: .env.")
    p.add_argument("--force-env", action="store_true", help="Overwrite env-path if it already exists.")
    p.add_argument("--remote-workdir", default="~/virtuoso-work/virtuoso-wiki-bridge")
    p.set_defaults(func=cmd_init_vault)

    p = sub.add_parser("doctor", parents=[common], help="Check vault, sources, bridge CLI, and optional SSH.")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("ingest-source", parents=[common], help="Copy a book/paper/netlist/SKILL file into sources.")
    p.add_argument("path")
    p.add_argument("--category", default="books", help="Subfolder under sources. Default: books.")
    p.add_argument("--extract", action=argparse.BooleanOptionalAction, default=True, help="Extract PDF/EPUB text when possible.")
    p.add_argument("--force-extract", action="store_true", help="Overwrite an existing extracted text file.")
    p.set_defaults(func=cmd_ingest_source)

    p = sub.add_parser("extract-sources", parents=[common], help="Extract all PDF/EPUB files under sources into sources/extracted.")
    p.add_argument("--force", action="store_true", help="Overwrite existing extracted text files.")
    p.set_defaults(func=cmd_extract_sources)

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
    p.add_argument("--timeout", type=int)
    p.set_defaults(func=cmd_eval_skill)

    p = sub.add_parser("load-skill", parents=[common], help="Load a .il/.skill file through upstream virtuoso-bridge.")
    p.add_argument("path")
    p.add_argument("--timeout", type=int)
    p.set_defaults(func=cmd_load_skill)

    p = sub.add_parser("snapshot", parents=[common], help="Capture focused Virtuoso/Maestro state via upstream bridge.")
    p.add_argument("-o", "--output")
    p.add_argument("--timeout", type=int)
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("run-spectre", parents=[common], help="Run a Spectre netlist over optional SSH fallback.")
    p.add_argument("netlist")
    p.add_argument("--name")
    p.add_argument("--timeout", type=int)
    p.set_defaults(func=cmd_run_spectre)

    p = sub.add_parser("pull-run", parents=[common], help="Pull an optional SSH run directory back locally.")
    p.add_argument("remote_dir")
    p.add_argument("local_dir")
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
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
