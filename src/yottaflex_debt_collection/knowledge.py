"""Small deterministic BM25 index for policy rules and project documentation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Any

import yaml


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[_-][a-z0-9]+)*", re.IGNORECASE)
_HEADING_PATTERN = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$", re.MULTILINE)
_RULE_ID_PATTERN = re.compile(r"^R-[A-Z0-9]+-\d+$")
_SKIPPED_DOCS = {"validation_summary.md"}
_STOP_WORDS = {
    "a", "an", "and", "are", "at", "be", "can", "does", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "should", "the", "this",
    "to", "what", "when", "which", "with",
}
_QUERY_SYNONYMS = {
    "active": ("requested", "approved", "effective"),
    "create": ("open", "threshold", "dpd_threshold"),
    "created": ("open", "threshold", "dpd_threshold"),
    "cutoff": ("p1_min_score", "p2_min_score", "70", "40"),
    "cutoffs": ("p1_min_score", "p2_min_score", "70", "40"),
    "dispute": ("disputed",),
    "disputed": ("dispute",),
    "external": ("external_data_used", "synthetic"),
    "generation": ("synthetic", "external", "personal"),
    "hours": ("local", "start_local", "end_local", "window"),
    "outcomes": ("kept", "partial", "broken", "match_status"),
    "personal": ("personal", "synthetic", "external_data_used"),
    "promise": ("commitment", "reconcile", "reconciliation"),
    "promises": ("commitment", "reconcile", "reconciliation"),
    "records": ("dataset", "synthetic"),
    "workflow": ("case", "dpd_threshold", "threshold", "open"),
    "split": ("partial", "allow_partial_allocation"),
    "tolerance": ("tolerance_pct", "grace_days", "5"),
    "tiers": ("p1_min_score", "p2_min_score", "70", "40"),
}
_RULE_SECTIONS = {
    "R-PAIDOFF-01": "suppression",
    "R-SCORE-01": "scoring",
    "R-RECON-01": "reconcile",
}


@dataclass(frozen=True)
class KnowledgeChunk:
    source: str
    citation: str
    title: str
    text: str
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class SearchResult:
    citation: str
    source: str
    title: str
    text: str
    score: float


def _tokens(text: str) -> tuple[str, ...]:
    result: list[str] = []
    for token in _TOKEN_PATTERN.findall(text):
        lowered = token.lower()
        result.append(lowered)
        result.extend(part for part in re.split(r"[_-]+", lowered) if part)
    return tuple(token for token in result if token not in _STOP_WORDS)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _policy_chunks(policy_path: Path) -> list[KnowledgeChunk]:
    policy: Any = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise ValueError(f"Policy root must be a mapping: {policy_path}")
    rules = policy.get("rules")
    if not isinstance(rules, dict):
        raise ValueError(f"Policy has no rules mapping: {policy_path}")

    chunks: list[KnowledgeChunk] = []
    for rule_id, rule in rules.items():
        if not isinstance(rule_id, str) or not _RULE_ID_PATTERN.fullmatch(rule_id):
            raise ValueError(f"Invalid policy rule ID: {rule_id!r}")
        section = _RULE_SECTIONS.get(rule_id)
        section_data = policy.get(section) if section else None
        text = (
            f"{rule_id}\n"
            f"{yaml.safe_dump(rule, sort_keys=False, allow_unicode=False)}"
        )
        if section_data is not None:
            text += (
                f"\n{section}\n"
                f"{yaml.safe_dump(section_data, sort_keys=False, allow_unicode=False)}"
            )
        chunks.append(
            KnowledgeChunk(
                source="config/policy.yaml",
                citation=f"[{rule_id}]",
                title=rule_id,
                text=text.strip(),
                tokens=_tokens(text),
            )
        )
    return chunks


def _document_chunks(root: Path) -> list[KnowledgeChunk]:
    files = [root / "README.md"]
    docs_root = root / "docs"
    if docs_root.is_dir():
        files.extend(
            path
            for path in docs_root.rglob("*.md")
            if path.name.lower() not in _SKIPPED_DOCS
        )

    chunks: list[KnowledgeChunk] = []
    for path in sorted(set(files)):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        headings = list(_HEADING_PATTERN.finditer(text))
        if not headings:
            content = text.strip()
            if content:
                chunks.append(
                    KnowledgeChunk(
                        source=relative,
                        citation=f"[{relative}]",
                        title=path.stem,
                        text=content,
                        tokens=_tokens(content),
                    )
                )
            continue

        for index, heading in enumerate(headings):
            start = heading.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            title = heading.group(2).strip()
            body = text[start:end].strip()
            if not body:
                continue
            content = f"{title}\n{body}"
            chunks.append(
                KnowledgeChunk(
                    source=relative,
                    citation=f"[{relative}#{_slug(title)}]",
                    title=title,
                    text=content,
                    tokens=_tokens(content),
                )
            )
    return chunks


class PolicyKnowledgeIndex:
    """Index policy rules and documentation with BM25 ranking."""

    def __init__(self, repository_root: Path | str) -> None:
        root = Path(repository_root).resolve()
        policy_path = root / "config" / "policy.yaml"
        if not policy_path.is_file():
            raise FileNotFoundError(f"Policy file is missing: {policy_path}")
        self.chunks = _policy_chunks(policy_path) + _document_chunks(root)
        if not self.chunks:
            raise ValueError(f"No policy or documentation chunks found under {root}")
        self._frequencies = [Counter(chunk.tokens) for chunk in self.chunks]
        self._lengths = [len(chunk.tokens) for chunk in self.chunks]
        self._average_length = sum(self._lengths) / len(self._lengths)
        self._document_frequency: Counter[str] = Counter()
        for frequencies in self._frequencies:
            self._document_frequency.update(frequencies.keys())

    def search(self, query: str, limit: int = 4) -> list[SearchResult]:
        if limit < 1:
            raise ValueError("Search result limit must be at least one")
        query_tokens = list(_tokens(query))
        for token in tuple(query_tokens):
            query_tokens.extend(_QUERY_SYNONYMS.get(token, ()))
        if not query_tokens:
            return []
        unique_tokens = set(query_tokens)
        count = len(self.chunks)
        k1 = 1.5
        b = 0.75
        results: list[SearchResult] = []
        for index, chunk in enumerate(self.chunks):
            score = 0.0
            for token in unique_tokens:
                frequency = self._frequencies[index].get(token, 0)
                if not frequency:
                    continue
                document_frequency = self._document_frequency[token]
                inverse_frequency = math.log(
                    1 + (count - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                denominator = frequency + k1 * (
                    1 - b + b * self._lengths[index] / self._average_length
                )
                score += inverse_frequency * frequency * (k1 + 1) / denominator
            if score > 0:
                if chunk.source == "config/policy.yaml":
                    score *= 1.35
                results.append(
                    SearchResult(
                        citation=chunk.citation,
                        source=chunk.source,
                        title=chunk.title,
                        text=chunk.text,
                        score=score,
                    )
                )
        results.sort(key=lambda result: (-result.score, result.source, result.title))
        return results[:limit]
