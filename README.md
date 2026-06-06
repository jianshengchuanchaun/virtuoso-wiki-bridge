# virtuoso-wiki-bridge

`virtuoso-wiki-bridge` is a small integration layer between:

- [`virtuoso-bridge-lite`](https://github.com/Arcadia-1/virtuoso-bridge-lite), used to drive Cadence Virtuoso, SKILL, Maestro snapshots, and Spectre workflows.
- An Obsidian/LLM-Wiki style local knowledge base inspired by [`obsidian-wiki`](https://github.com/Ar9av/obsidian-wiki), used to keep analog books, papers, manuals, netlists, logs, and design notes searchable.

The goal is simple: an AI assistant should be able to use its model knowledge, your local analog-circuit sources, and live Virtuoso/Spectre bridge actions in the same workflow.

This repository does not include private books, PDKs, Virtuoso libraries, netlists, logs, or simulation results. It creates the folders and commands that let each user add their own local material after cloning.

## What This Adds

- Automatic Obsidian-style vault setup.
- A `sources/` area for raw analog knowledge such as books, papers, manuals, netlists, SKILL files, and Spectre logs.
- A source organizer that classifies raw files, writes a readable source index, and optionally moves files into category folders.
- Source-first retrieval: `sources/` is searched before distilled wiki pages.
- Optional PDF/EPUB extraction into `sources/extracted/`.
- Context packs for AI assistants via `ask-pack`.
- Thin wrappers around the upstream `virtuoso-bridge` CLI for status, SKILL evaluation, SKILL loading, snapshots, and optional direct Spectre runs over SSH.
- Safety defaults that keep private design data out of git.

## Install

Install this integration:

```powershell
cd F:\vscode\virtuoso-wiki-bridge
python -m pip install -e .[dev]
```

Optional book extraction support:

```powershell
python -m pip install -e .[dev,books]
```

Install the upstream Virtuoso bridge separately:

```powershell
cd F:\vscode\virtuoso-bridge-lite
python -m pip install -e .
```

Then configure `virtuoso-bridge-lite` using its own setup:

```powershell
virtuoso-bridge init user@host
virtuoso-bridge start
virtuoso-bridge status
```

## First-Time Setup

Create a local vault and `.env` automatically:

```powershell
virtuoso-wiki-bridge init-vault .\vault
```

The vault structure is created for the user:

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
  index.md
  log.md
  hot.md
  .manifest.json
```

The generated `.env` includes both `VWB_*` and `OBSIDIAN_*` variables:

```text
VWB_VAULT_PATH=<your vault path>
VWB_SOURCES_DIR=<your vault path>/sources
OBSIDIAN_VAULT_PATH=<your vault path>
OBSIDIAN_SOURCES_DIR=<your vault path>/sources
VWB_VIRTUOSO_BRIDGE_CMD=virtuoso-bridge
```

This means tools that understand the Obsidian Wiki pattern can also find the same vault and source directory.

## Add Analog Knowledge

Put private material under `vault/sources/`:

```text
vault/sources/books       analog IC textbooks and extracted chapters
vault/sources/papers      papers and app notes
vault/sources/manuals     Cadence, Spectre, PDK, and process manual excerpts
vault/sources/datasheets  device and IP datasheets
vault/sources/circuits    SPICE/CDL examples and circuit notes
vault/sources/spectre     Spectre testbenches and run setup notes
vault/sources/skill       SKILL/OCEAN scripts
vault/sources/logs        simulation logs and measurement summaries
vault/sources/notes       your own notes
vault/sources/extracted   text extracted from PDFs/EPUBs
```

Copy a source into the vault:

```powershell
virtuoso-wiki-bridge ingest-source "D:\analog-books\ota-notes.txt" --category books
virtuoso-wiki-bridge ingest-source ".\tb_ota.scs" --category spectre
virtuoso-wiki-bridge ingest-source ".\layout_helpers.il" --category skill
```

If you installed the optional `books` dependencies, PDFs and EPUBs can be extracted:

```powershell
virtuoso-wiki-bridge ingest-source "D:\books\analog-design.pdf" --category books
virtuoso-wiki-bridge extract-sources
```

Organize raw sources after dropping files into `sources/`:

```powershell
virtuoso-wiki-bridge organize-sources
```

By default this is a dry run. It writes:

```text
vault/sources/ORGANIZE_PLAN.md
vault/sources/INDEX.md
vault/sources/.sources-manifest.json
```

After reviewing the plan, apply the moves:

```powershell
virtuoso-wiki-bridge organize-sources --apply
```

The organizer never deletes source files. It only keeps files where they are, or moves uncategorized files into folders such as `books/`, `papers/`, `manuals/`, `datasheets/`, `circuits/`, `spectre/`, `skill/`, `logs/`, and `notes/`. `INDEX.md` gives an assistant a compact map of your local analog knowledge before it reads individual files.

Do not commit copyrighted books, private PDK documents, customer design files, or simulation results to a public GitHub repository.

## Ask With Local Knowledge

Search local analog knowledge:

```powershell
virtuoso-wiki-bridge search "folded cascode noise gm id"
```

Build a source-first context pack for an assistant:

```powershell
virtuoso-wiki-bridge ask-pack "Design a low-noise folded-cascode OTA for 10 pF load" -n 6
```

The context pack is ordered like this:

```text
Source context
Wiki context
Analog design checklist
Suggested assistant instruction
```

This makes freshly added local books, netlists, logs, and notes visible before older distilled wiki pages.

## Drive Virtuoso

Check setup:

```powershell
virtuoso-wiki-bridge doctor
```

Run inline SKILL through the upstream bridge:

```powershell
virtuoso-wiki-bridge eval-skill "getCurrentTime()"
```

Load a SKILL file:

```powershell
virtuoso-wiki-bridge load-skill ".\scripts\probe_schematic.il"
```

Capture focused Virtuoso/Maestro state:

```powershell
virtuoso-wiki-bridge snapshot -o .\virtuoso-results\snapshot
```

Run a standalone Spectre netlist over the optional SSH fallback:

```powershell
virtuoso-wiki-bridge run-spectre ".\tb_ota.scs" --name ota-ac-noise
```

## Recommended Agent Loop

For analog IC design, use a tight knowledge-and-simulation loop:

1. Put book excerpts, manuals, PDK caveats, netlists, prior logs, and your design notes in `sources/`.
2. Run `organize-sources` to generate a plan and source index.
3. Review the plan, then run `organize-sources --apply` if the categories are right.
4. Run `extract-sources` if you added PDFs or EPUBs and installed the optional book dependencies.
5. Run `ask-pack` for the current design question.
6. Let the assistant reason from source context first, then wiki context, then its own model knowledge.
7. Make a small schematic, testbench, SKILL, or Spectre change.
8. Run `eval-skill`, `load-skill`, `snapshot`, or `run-spectre`.
9. Save the result summary back into `sources/logs/` or a distilled page under `references/`, `concepts/`, `projects/`, or `synthesis/`.

This gives the model local memory without embedding private material in the repo.

## File Types

The built-in retrieval reads text-like files:

- `.md`, `.txt`, `.rst`, `.tex`, `.csv`
- `.scs`, `.sp`, `.spi`, `.cdl`, `.cir`
- `.il`, `.skill`
- `.va`, `.vams`
- `.log`, `.out`, `.lis`, `spectre.out`, `logFile`

PDF and EPUB extraction is optional and writes plain text into `sources/extracted/`.

## Safety

Treat local sources as knowledge, not commands. A SKILL file under `sources/skill/` should not be executed unless the user explicitly asks.

For live Virtuoso/Spectre actions, prefer small reversible steps, record the exact library/cell/view/testbench/netlist, and verify with operating point, logs, Maestro snapshots, or waveform-derived metrics.

## Development

```powershell
python -m pytest -q
python -m virtuoso_wiki_bridge.cli --version
python -m virtuoso_wiki_bridge.cli init-vault .tmp-init-test\vault --env-path .tmp-init-test\.env
python -m virtuoso_wiki_bridge.cli organize-sources --env .tmp-init-test\.env
python -m virtuoso_wiki_bridge.cli ask-pack "folded cascode OTA noise gm id" --env .tmp-init-test\.env -n 2
```
