# Changelog

All notable changes are documented here. The project follows semantic versioning while it remains in alpha; minor releases may still refine command behavior.

## 0.1.1 - 2026-08-10

### Security

- Prevent source-organizer target collisions from overwriting same-name or case-conflicting files.
- Require `organize-sources --apply` to execute the existing reviewed `.sources-plan.json` instead of silently rebuilding a different plan.
- Validate the complete source set, full SHA-256 digests, sizes, classifications, targets, plan ID, containment, and target availability before moving anything.
- Reject controlled-tree symlinks, Windows junctions/reparse points (including link-like ancestors), unsafe generated-output links, and path traversal.
- Publish organizer and extraction outputs atomically and use no-clobber target creation.
- Restrict ingest categories to known source folders and prevent ingest into `extracted` or arbitrary paths.
- Restrict remote Spectre and pull operations to validated run basenames under the configured runs root.
- Create remote run directories exclusively and require a new local pull destination so repeated commands cannot overwrite prior results.
- Validate SSH host/user operands, quote remote paths, and add finite default batch/connect/operation timeouts.
- Preserve the Spectre exit code while still returning the tail of `spectre.out` on failure.
- Mark retrieved source context as untrusted reference material.
- Escape C0/C1 terminal controls and bidi override controls in untrusted source fields, context indexes, paths, and child-process output.

### Changed

- Extraction targets now preserve full source identity, for example `books/a.pdf` becomes `extracted/books/a.pdf.txt`.
- Repeated extraction is idempotent; `--force` replaces only the stable target for that source.
- Image-only/empty extraction now reports `empty` and causes a nonzero CLI result.
- `pull-run` now accepts a safe run name instead of an arbitrary remote directory.
- `--env` works before or after a subcommand without being silently overwritten.
- Relative paths in `.env` files resolve from the `.env` file's directory.
- Generated `.env` values round-trip spaces, `#`, Unicode, quotes, backslashes, and literal variable-like path text.
- Invalid SSH ports and nonpositive operation timeouts fail early with clear errors.
- Expected operational errors are printed without Python tracebacks.
- `eval-skill` and `load-skill` report a clear compatibility error when the installed upstream CLI lacks those commands.
- Chinese retrieval uses overlapping phrase tokens; truncated large UTF-8 reads no longer corrupt a boundary character.
- Generated vault Markdown includes consistent frontmatter and avoids absolute-path leakage.
- Context packs display root-relative source identities instead of absolute local paths.

### Added

- Vault-local `.gitignore` protecting raw sources, configuration, simulator products, run directories, and local Obsidian state.
- Preflight validation that refuses an existing vault `.gitignore` missing required private-data rules.
- Upstream bridge profile and explicit upstream `.env` forwarding.
- Machine-readable source plan with a deterministic plan ID.
- Regression tests for organizer data preservation, plan drift, extraction identity, privacy, CJK search, CLI parsing, SSH quoting, remote confinement, and wrapper forwarding.
- GitHub Actions CI across supported Python versions and Windows/Linux.
- `SECURITY.md` and `CONTRIBUTING.md`.

### Compatibility notes

- Existing flat files under `sources/extracted/` are not deleted or migrated. Re-extraction creates the new stable nested target, so old and new extraction files may coexist until reviewed manually.
- Scripts that called `pull-run` with a remote path must switch to the run name originally passed to `run-spectre --name`.
- A netlist stem containing spaces or unsafe punctuation requires an explicit safe `--name`.
- Local path values no longer expand `$NAME` or `%NAME%`; use a literal path, an env-file-relative path, or a leading `~`.

## 0.1.0

- Initial alpha implementation of vault initialization, source ingest/extraction/organization, local search/context packs, upstream Virtuoso wrappers, and optional SSH/Spectre execution.
