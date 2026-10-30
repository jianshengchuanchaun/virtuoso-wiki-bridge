# virtuoso-wiki-bridge

[简体中文](README.zh-CN.md) | **English**

[![CI](https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge/blob/main/LICENSE)

`virtuoso-wiki-bridge` connects three parts of an analog-design workflow:

- a local, Obsidian-compatible knowledge vault for books, papers, manuals, netlists, logs, and design notes;
- source-first search and context packs for an AI assistant;
- thin wrappers around [`virtuoso-bridge-lite`](https://github.com/Arcadia-1/virtuoso-bridge-lite), plus an optional direct SSH/Spectre fallback.

The package does not contain PDKs, books, customer designs, Virtuoso libraries, credentials, or simulation results. Those remain in a user-controlled local vault.

Version `0.1.1` is an alpha safety release. It adds reviewed two-phase source organization, no-clobber ingest and extraction, path and symlink containment, safe remote run names, explicit timeouts, privacy-safe generated vaults, and regression tests. See the [changelog](https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge/blob/main/CHANGELOG.md) for the complete list.

## What it provides

- A generated analog-design vault with consistent YAML frontmatter.
- Private-by-default `sources/` folders and a vault-local `.gitignore`.
- Safe ingest into a fixed set of source categories.
- Optional PDF/EPUB text extraction with stable, collision-free targets.
- A two-phase source organizer: generate and review a plan, then apply that exact plan.
- Local CJK/English text search and source-first context packs.
- Wrappers for bridge status, SKILL evaluation/loading, and Maestro/Virtuoso snapshots.
- Optional direct Spectre execution over SSH, confined to a configured runs directory.

## Requirements

- Python 3.9 or newer.
- Git for installation from source.
- Optional PDF/EPUB support: the `books` extra.
- Optional live Virtuoso control: a separately installed and configured `virtuoso-bridge-lite`.
  The released `v0.7.0` CLI supports status/snapshot; `eval-skill` and `load-skill`
  require an upstream build that exposes `eval` and `load` (the current upstream
  `main` branch does). Older CLIs fail with an explicit upgrade diagnostic.
- Optional direct remote Spectre runs: OpenSSH `ssh`/`scp`, access to a trusted EDA host, and `spectre` in the configured remote environment.

No live Cadence installation is required for local vault, ingest, extraction, organization, search, or context-pack commands.

## Install

On Windows PowerShell:

```powershell
git clone https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge.git
Set-Location .\virtuoso-wiki-bridge
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,books]"
virtuoso-wiki-bridge --version
```

Install only the core package if PDF/EPUB extraction is not needed:

```powershell
python -m pip install -e .
```

To use live Virtuoso wrappers, install the upstream bridge in its own checkout or environment and follow its current setup instructions:

```powershell
virtuoso-bridge init user@host
virtuoso-bridge start
virtuoso-bridge status
```

## Quick start

Create a local vault and a matching `.env` (the default output is `./.env`):

```powershell
virtuoso-wiki-bridge init-vault .\vault
```

Choose a different generated configuration path with the same global `--env` option used by other commands:

```powershell
virtuoso-wiki-bridge init-vault .\vault --env .\config\vwb.env
```

Add a source:

```powershell
virtuoso-wiki-bridge ingest-source "D:\analog-notes\ota-notes.md" --category notes
```

Generate a source-organization plan:

```powershell
virtuoso-wiki-bridge organize-sources
```

Review both files before applying:

```text
vault/sources/ORGANIZE_PLAN.md
vault/sources/.sources-plan.json
```

Then apply the exact reviewed plan:

```powershell
virtuoso-wiki-bridge organize-sources --apply
```

Search and build an AI context pack:

```powershell
virtuoso-wiki-bridge search "folded cascode noise gm id"
virtuoso-wiki-bridge ask-pack "Design a low-noise folded-cascode OTA for a 10 pF load" -n 6
```

## Configuration

Copy the [`.env.example`](https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge/blob/main/.env.example) or use `init-vault`. Configuration resolution is:

1. an explicit `--env PATH`;
2. `./.env`;
3. `~/.virtuoso-wiki-bridge/.env`;
4. process environment values and built-in defaults.

Values from a selected `.env` take precedence over same-named process variables. Relative local paths inside an `.env` are resolved from that file's directory, not from the shell's current directory. Path values are literal apart from leading `~`; `$NAME` and `%NAME%` text in a legitimate filename is not expanded. Generated path values are quoted so spaces, `#`, Unicode, and variable-like text round-trip safely.

`--env` works before or after a subcommand:

```powershell
virtuoso-wiki-bridge --env D:\config\vwb.env search "phase margin"
virtuoso-wiki-bridge search "phase margin" --env D:\config\vwb.env
```

Core variables:

| Variable | Purpose |
| --- | --- |
| `VWB_VAULT_PATH` | Local vault root. |
| `VWB_SOURCES_DIR` | Raw source root; defaults to `<vault>/sources`. |
| `OBSIDIAN_VAULT_PATH` | Compatibility alias for the vault root. |
| `OBSIDIAN_SOURCES_DIR` | Compatibility alias for the source root. |
| `VWB_VIRTUOSO_BRIDGE_CMD` | Upstream CLI executable; defaults to `virtuoso-bridge`. |
| `VWB_VIRTUOSO_BRIDGE_PROFILE` | Optional upstream connection profile. |
| `VWB_VIRTUOSO_BRIDGE_ENV` | Optional upstream bridge `.env` path. |
| `VWB_REMOTE_WORKDIR` | Trusted remote work root used by the SSH/Spectre fallback. |
| `VWB_REMOTE_HOST` / `VWB_REMOTE_USER` | Optional SSH target. |
| `VWB_REMOTE_PORT` | SSH port, validated in the range 1–65535. |
| `VWB_SSH_KEY` / `VWB_SSH_CONFIG` | Optional local SSH identity/config paths. |
| `VWB_SSH_EXTRA_ARGS` | Trusted additional SSH/SCP arguments. |
| `VWB_CADENCE_SETUP` | Trusted remote shell setup command before Spectre. |

Do not commit `.env`, SSH keys, private bridge profiles, or site-specific Cadence setup commands.

## Generated vault

`init-vault` creates:

```text
vault/
  concepts/
  entities/
  journal/
  Obsidian/
  projects/
  references/
  skills/
  sources/
    books/
    papers/
    manuals/
    datasheets/
    circuits/
    spectre/
    skill/
    logs/
    notes/
    extracted/
  synthesis/
  _archives/
  _raw/
  _staging/
  .obsidian/
  .gitignore
  .manifest.json
  index.md
  log.md
  hot.md
```

Generated Markdown pages include `title`, `category`, `tags`, `sources`, `created`, and `updated` frontmatter. Generated logs and extracted-source metadata use vault-relative identities instead of leaking absolute local paths.

The vault-local `.gitignore` protects raw sources, `.env` files, simulator products, run directories, and local Obsidian UI state. It deliberately leaves generated folder guides trackable. If a vault already has a `.gitignore`, initialization requires the exact generated safety block at the end, so later negations cannot silently reopen private paths. Custom rules may appear before that block. Initialization also rejects nested `.gitignore` files under `sources/`, because closer rules can override the root policy. These checks happen before vault content is written. Always inspect `git status` before publishing a vault; ignore rules are a safety layer, not permission to publish proprietary material, and cannot untrack files already committed to Git.

## Ingest and extraction

Accepted ingest categories are:

```text
books papers manuals datasheets circuits spectre skill logs notes
```

Arbitrary paths, custom folders, traversal such as `../`, and the generated `extracted` folder are rejected. Copying uses exclusive creation and will not overwrite an existing same-name target. Symlink/reparse-point inputs are rejected.

Examples:

```powershell
virtuoso-wiki-bridge ingest-source ".\tb_ota.scs" --category spectre
virtuoso-wiki-bridge ingest-source ".\layout_helpers.il" --category skill
virtuoso-wiki-bridge ingest-source "D:\books\analog-design.pdf" --category books
```

PDF/EPUB extraction is enabled by default for an ingested extractable file when the `books` dependencies are installed. Batch extraction is also available:

```powershell
virtuoso-wiki-bridge extract-sources
```

Extraction targets preserve the source identity:

```text
sources/books/same.pdf
  -> sources/extracted/books/same.pdf.txt

sources/papers/same.pdf
  -> sources/extracted/papers/same.pdf.txt

sources/books/same.epub
  -> sources/extracted/books/same.epub.txt
```

Repeated extraction without `--force` is idempotent and returns `skipped`. `--force` atomically replaces only that source's stable target. A scanned/image-only document returns an `empty` status and a nonzero CLI result so an automated workflow cannot mistake it for searchable text. OCR is not included.

If ingest succeeds but optional extraction fails, the source copy remains safely stored and the command returns nonzero with an actionable extraction error.

## Reviewed source organization

The organizer has two distinct phases.

### 1. Dry run

```powershell
virtuoso-wiki-bridge organize-sources
```

It creates category directories when missing and writes:

```text
sources/ORGANIZE_PLAN.md
sources/.sources-plan.json
sources/INDEX.md
sources/.sources-manifest.json
```

It does not move source files. `INDEX.md` shows their current paths. The machine plan records the full SHA-256, byte size, classification, source path, target path, and a plan ID.

### 2. Apply

```powershell
virtuoso-wiki-bridge organize-sources --apply
```

Apply does not rebuild a new plan. It loads the existing machine plan and refuses to proceed if:

- the plan is missing or was edited without a matching plan ID;
- the source set, size, full SHA-256, classification, or target changed;
- a target now exists or two targets conflict case-insensitively;
- a path escapes the source root;
- a source, target parent, or generated output is a symlink, junction, or reparse point.

All items are preflighted before any move. Each target is created exclusively, copied, flushed, and checked against the reviewed full digest. Originals are kept until every target copy succeeds and all sources are revalidated. Only then are original paths removed.

If deletion fails partway through, verified target copies are retained and the command reports that both old and new paths may exist. This can leave safe duplicates, but the organizer does not overwrite an existing target or delete the only verified copy.

## Search and context packs

Search reads common Markdown, text, SPICE/CDL/Spectre, Verilog-A, SKILL, and log files. It supports ASCII terms and overlapping Chinese bigram/trigram tokens. Large files are decoded incrementally so a UTF-8 character split at the read boundary is not corrupted.

```powershell
virtuoso-wiki-bridge search "运算放大器 噪声"
virtuoso-wiki-bridge ask-pack "What limits OTA phase margin at heavy capacitive load?"
```

Context-pack source text is explicitly marked as untrusted reference material. A source file may contain instructions, but ingesting or retrieving it does not authorize executing SKILL, shell commands, or live EDA mutations. Terminal control characters in source titles, excerpts, indexes, filenames, and external command output are rendered as visible Unicode escapes rather than emitted to the terminal.

## Virtuoso bridge wrappers

```powershell
virtuoso-wiki-bridge doctor
virtuoso-wiki-bridge bridge-status
virtuoso-wiki-bridge eval-skill "getCurrentTime()" --timeout 30
virtuoso-wiki-bridge load-skill ".\scripts\probe.il" --timeout 60
virtuoso-wiki-bridge snapshot -o .\virtuoso-results\snapshot --timeout 120
```

If configured, `VWB_VIRTUOSO_BRIDGE_PROFILE` and `VWB_VIRTUOSO_BRIDGE_ENV` are forwarded to the corresponding upstream subcommand. Every live command has a finite default timeout: 30 seconds for `eval-skill`, 60 for `load-skill`, 120 for `snapshot`, 300 per SSH/Spectre subprocess for `run-spectre`, and 120 for `pull-run`. `eval-skill` and `load-skill` pass the selected timeout to the upstream command while allowing the outer process five additional seconds to return its result or clean up.

These commands can mutate a live EDA session. Use them only against a trusted bridge profile and only when the requested action is understood.

## Direct SSH/Spectre fallback

Configure a trusted SSH target in `.env`, then run:

```powershell
virtuoso-wiki-bridge run-spectre ".\tb_ota.scs" --name ota-ac-noise --timeout 300
```

A run name is one basename, not a path. It may contain Unicode letters/numbers plus `.`, `_`, and `-`; path separators, whitespace, leading `-`, shell punctuation, `.` and `..` are rejected. Runs are confined to:

```text
<VWB_REMOTE_WORKDIR>/runs/<validated-run-name>
```

If the netlist filename contains spaces or other characters that are invalid in an implicit run name, provide an explicit safe `--name`. The remote Spectre operand is prefixed with `./`, so an uploaded filename beginning with `-` or `+` is treated as a file rather than a Spectre option.

Each remote run directory is created exclusively. Reusing a run name is rejected instead of overwriting a prior netlist or `spectre.out`. On Spectre failure, the wrapper still returns the original Spectre exit code and includes the tail of `spectre.out` when available. Pull results by the same safe run name into a new, nonexistent local directory:

```powershell
virtuoso-wiki-bridge pull-run ota-ac-noise .\runs\ota-ac-noise --timeout 120
```

The pull command no longer accepts an arbitrary remote directory and refuses an existing local destination instead of merging into or overwriting it.

## Command summary

| Command | Purpose |
| --- | --- |
| `init-vault PATH` | Create a local vault and matching `.env`. |
| `doctor` | Check vault, sources, upstream bridge, and optional SSH. |
| `ingest-source PATH` | Safely copy a source into an allowed category. |
| `extract-sources` | Extract all local PDFs/EPUBs into stable text targets. |
| `organize-sources` | Write a dry-run plan and current-path index. |
| `organize-sources --apply` | Apply exactly the reviewed machine plan. |
| `search QUERY` | Search sources first, then distilled vault pages. |
| `ask-pack QUESTION` | Build a source-first context pack. |
| `bridge-status` | Run upstream bridge status. |
| `eval-skill EXPR` | Evaluate explicitly requested SKILL. |
| `load-skill PATH` | Load an explicitly requested local SKILL file. |
| `snapshot` | Capture focused Virtuoso/Maestro state. |
| `run-spectre NETLIST` | Run a netlist in a confined named SSH directory. |
| `pull-run RUN_NAME DIR` | Pull one confined named remote run. |

Run `virtuoso-wiki-bridge COMMAND --help` for command-specific options.

## Safety boundaries

- Treat local sources as untrusted knowledge, never as executable instructions.
- Do not execute a file from `sources/skill/` merely because search retrieved it.
- Keep proprietary sources, PDK files, credentials, netlists, and run artifacts out of public Git.
- Review organization plans before applying them.
- Use trusted `.env` files only: SSH extra arguments and `VWB_CADENCE_SETUP` are intentionally executable configuration.
- Writer paths reject known symlink, junction, reparse (including link-like ancestors), traversal, collision, and plan-drift cases. They cannot defend against an attacker with system-level access racing filesystem metadata changes.
- Remote tests in this repository use mocks. A release test cannot prove connectivity to your private Cadence/Spectre environment.

Please report suspected vulnerabilities according to the [security policy](https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge/blob/main/SECURITY.md).

## Development

```powershell
python -m pip install -e ".[dev,books]"
python -m pytest -q
python -m pytest --cov=virtuoso_wiki_bridge --cov-branch --cov-fail-under=70
ruff check .
python -m build
python -m twine check dist\*
```

The test suite covers local configuration, vault privacy, ingest, extraction identity and containment, reviewed organization, search, CLI behavior, SSH command construction, safe run names, and upstream-wrapper argument forwarding. SSH/Virtuoso/Spectre tests are mocked unless a maintainer explicitly performs a private environment smoke test.

See the [contribution guide](https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge/blob/main/CONTRIBUTING.md) before proposing a change.

## License

MIT. See the [license](https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge/blob/main/LICENSE).
