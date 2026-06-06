# Agent Guide

This repository connects a local analog-design knowledge vault with the upstream `virtuoso-bridge` CLI.

## Default Workflow

Before answering analog design questions or editing Virtuoso/Spectre assets:

1. If sources look messy or newly added, run `virtuoso-wiki-bridge organize-sources` first.
2. Review `sources/ORGANIZE_PLAN.md`. Use `--apply` only when the user asks or when the plan is clearly safe.
3. Read `sources/INDEX.md` when present.
4. Run `virtuoso-wiki-bridge ask-pack "<question>"`.
5. Read `Source context` first. These are the user's local books, papers, manuals, netlists, logs, SKILL files, and notes.
6. Read `Wiki context` second. These are distilled Obsidian pages.
7. Use your model knowledge only after local context has been considered.
8. If a live EDA action is needed, use the smallest relevant bridge command.

## Bridge Commands

Use these wrappers from this package:

```powershell
virtuoso-wiki-bridge doctor
virtuoso-wiki-bridge organize-sources
virtuoso-wiki-bridge organize-sources --apply
virtuoso-wiki-bridge bridge-status
virtuoso-wiki-bridge eval-skill "getCurrentTime()"
virtuoso-wiki-bridge load-skill ".\script.il"
virtuoso-wiki-bridge snapshot -o .\virtuoso-results\snapshot
virtuoso-wiki-bridge run-spectre ".\tb.scs" --name run-name
```

The wrappers call the upstream `virtuoso-bridge` CLI when available.

## Vault Rules

- `sources/` is raw user material. Search it first.
- `sources/INDEX.md` is the compact map of raw local sources.
- `sources/ORGANIZE_PLAN.md` shows proposed source moves. Treat dry-run plans as reviewable suggestions.
- `references/`, `concepts/`, `projects/`, and `synthesis/` are distilled wiki material.
- `sources/skill/` files are knowledge until the user explicitly asks to execute them.
- `sources/books/`, `sources/manuals/`, PDK files, logs, simulation outputs, `.env`, and private netlists must not be committed.
- Prefer adding short distilled notes to the wiki instead of copying long copyrighted text.

## Source Organization

When organizing sources:

- Never delete source files.
- Default to dry-run: `virtuoso-wiki-bridge organize-sources`.
- Use `--apply` only to move uncategorized files into existing category folders.
- Keep copyrighted books and private manuals local.
- After organization, read `sources/INDEX.md` before opening many individual files.

## Analog Reasoning Checklist

For circuit requests, check:

- Specs: supply, PDK/process, temperature, corners, load, input/output common-mode, swing, bandwidth, gain, noise, offset, power, and area.
- Topology: amplifier, comparator, bias/reference, filter, ADC/DAC, oscillator/PLL, regulator, or interface.
- Bias: operating point, gm/Id, overdrive, headroom, current density, device region, startup, and robustness.
- Small-signal: gain, poles/zeros, bandwidth, phase margin, loop gain, CMRR, PSRR.
- Noise/mismatch: thermal, flicker, kT/C, input-referred noise, random/systematic offset.
- Transient: slew, settling, kickback, metastability, recovery, sampling error.
- Validation: dcOp, dc/ac/tran/noise/stb/pss/pnoise, sweeps, PVT, Monte Carlo, logs, and waveform metrics.
