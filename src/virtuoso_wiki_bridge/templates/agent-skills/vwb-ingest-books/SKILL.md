---
name: vwb-ingest-books
description: Read newly added books, papers or manuals in a Virtuoso Wiki Bridge vault and integrate their knowledge into cited Markdown pages. Use when the user asks to ingest new documents or update the personal knowledge base from local sources.
---

# Incremental document ingestion

Resolve the user's vault and program `.env`, then read `.manifest.json`, `index.md` and recent `log.md`. Default locations are `sources/books`, `sources/papers` and `sources/manuals`. Preserve existing data and unknown manifest fields. This workflow does not execute scripts inside the source documents.

## Read and verify

- Inventory the requested sources and calculate SHA-256. Skip matching `content_hash` values, including moved duplicates. For changed contents, refresh the associated extracted text and update existing notes instead of duplicating them.
- Use `vwb extract-sources` for new PDF/EPUB text. Existing extraction targets are skipped; `--force` refreshes all extractable sources, so use it only when that scope is appropriate. A scanned/empty extraction needs OCR or visual reading; report incomplete coverage.
- Read the text and relevant diagrams/formulas in the original PDF. Track PDF viewer page numbers. Preserve the original documents and copyright notices; write distilled notes rather than copying long sections.

## Integrate

- Search existing pages before creating new ones. Put general concepts in `concepts/`, source notes in `references/`, procedures in `skills/`, project-specific results in `projects/`, and cross-source reasoning in `synthesis/`.
- Link related pages and add backlinks where helpful. Include `title`, `category`, `tags`, `sources`, `summary`, `created`, `updated` and `lifecycle: draft` frontmatter. Use relative source paths and page citations. Keep any more detailed metadata convention already used by the vault.
- Mark inference with `^[inferred]` and unresolved source ambiguity with `^[ambiguous]`. Do not report textbook simulations as results from the user's VM. Document contradictory formulas or units with the original page and the basis of any correction.
- Respect `WIKI_STAGED_WRITES=true`: proposed category pages go in `_staging/`, with clear targets for edits. Do not silently promote them; record pending status.

## Record the update

For each processed source, add a manifest entry with `content_hash: "sha256:<digest>"`, `ingested_at`, `size_bytes`, `modified_at`, `source_type: document`, `project`, `pages_created` and `pages_updated`. Preserve existing entries; update available stats consistently without resetting historical counts. For staged work, record it as pending rather than completed ingestion so an identical hash will not skip unfinished promotion.

Update `index.md`, append to `log.md`, and refresh `hot.md` with at most three recent operations. Validate newly added links, source paths and page numbers; confirm the original hash is unchanged. Test one representative `vwb search` query. Report sources read, coverage, pages created/updated and unresolved limitations. Semantic/vector indexing is optional and must not be claimed unless configured and verified.
