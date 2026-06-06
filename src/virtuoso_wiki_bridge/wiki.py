"""Local knowledge search for analog design vaults."""

from __future__ import annotations

import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".rst",
    ".tex",
    ".log",
    ".out",
    ".lis",
    ".scs",
    ".sp",
    ".spi",
    ".cdl",
    ".cir",
    ".il",
    ".skill",
    ".va",
    ".vams",
    ".csv",
}
TEXT_FILENAMES = {
    "logFile",
    "spectre.out",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9_.+#/-]+|[\u4e00-\u9fff]{1,4}")


@dataclass(frozen=True)
class SearchHit:
    path: Path
    score: float
    title: str
    excerpt: str


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in TOKEN_RE.findall(text):
        token = raw.lower()
        tokens.append(token)
        compact = token.replace("-", "").replace("/", "")
        if compact != token:
            tokens.append(compact)
    return tokens


def read_text_file(path: Path, limit_chars: int = 800_000) -> str:
    data = path.read_bytes()
    if len(data) > limit_chars:
        data = data[:limit_chars]
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(encoding).replace("\ufeff", "")
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace").replace("\ufeff", "")


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def iter_text_files(root: Path, *, exclude_roots: Iterable[Path] = ()) -> Iterable[Path]:
    if not root.exists():
        return
    root = root.expanduser().resolve()
    excludes = tuple(path.expanduser().resolve() for path in exclude_roots)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if any(_under(resolved, excluded) for excluded in excludes):
            continue
        try:
            relative_parts = resolved.relative_to(root).parts
        except ValueError:
            relative_parts = path.parts
        if any(part.startswith(".") and part != ".obsidian" for part in relative_parts):
            continue
        if path.suffix.lower() in TEXT_EXTENSIONS or path.name in TEXT_FILENAMES:
            yield path


def title_for(path: Path, text: str) -> str:
    for line in text.splitlines()[:30]:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
        if stripped.startswith("title:"):
            return stripped.split(":", 1)[1].strip().strip('"')
        if stripped.lower().startswith("simulator lang"):
            return path.name
    return path.stem


def excerpt_for(text: str, query_tokens: set[str], max_chars: int = 440) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    best = lines[0]
    best_score = -1
    for line in lines[:400]:
        score = len(set(tokenize(line)) & query_tokens)
        if score > best_score:
            best = line
            best_score = score
    if len(best) <= max_chars:
        return best
    return best[: max_chars - 3] + "..."


def search(root: Path, query: str, *, limit: int = 8, exclude_roots: Iterable[Path] = ()) -> list[SearchHit]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    query_set = set(query_tokens)
    docs: list[tuple[Path, str, list[str]]] = []
    doc_freq = {token: 0 for token in query_set}
    for path in iter_text_files(root, exclude_roots=exclude_roots):
        try:
            text = read_text_file(path)
        except OSError:
            continue
        tokens = tokenize(text)
        token_set = set(tokens)
        for token in query_set:
            if token in token_set:
                doc_freq[token] += 1
        docs.append((path, text, tokens))

    total_docs = max(len(docs), 1)
    hits: list[SearchHit] = []
    for path, text, tokens in docs:
        counts: dict[str, int] = {}
        for token in tokens:
            if token in query_set:
                counts[token] = counts.get(token, 0) + 1
        if not counts:
            continue
        length_norm = math.sqrt(len(tokens))
        score = 0.0
        for token, count in counts.items():
            idf = math.log((1 + total_docs) / (1 + doc_freq.get(token, 0))) + 1
            score += (count / length_norm) * idf
        hits.append(SearchHit(path, score, title_for(path, text), excerpt_for(text, query_set)))
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]


def copy_source(source: Path, sources_dir: Path, *, category: str = "books") -> Path:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"source file not found: {source}")
    target_dir = sources_dir / category
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if target.exists():
        stem = source.stem
        suffix = source.suffix
        index = 2
        while target.exists():
            target = target_dir / f"{stem}-{index}{suffix}"
            index += 1
    shutil.copy2(source, target)
    return target


def build_context(root: Path, query: str, *, limit: int = 6, exclude_roots: Iterable[Path] = ()) -> str:
    hits = search(root, query, limit=limit, exclude_roots=exclude_roots)
    if not hits:
        return "No local context found."
    return "\n\n".join(
        f"[{index}] {hit.title}\npath: {hit.path}\nscore: {hit.score:.3f}\nexcerpt: {hit.excerpt}"
        for index, hit in enumerate(hits, 1)
    )
