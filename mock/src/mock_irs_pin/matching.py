"""Token-based site-name matching for API 3 style address strings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

TOKEN_STOPWORDS = {
    "irs",
    "us",
    "gsa",
    "ts",
    "the",
    "and",
    "of",
}


@dataclass
class SiteMatchResult:
    input_site_name: str
    matched_site_name: str | None
    score: float


def normalize_site_name(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"\bgrp\s*(\d+)\b", r"group \1", normalized)
    normalized = re.sub(r"\bcci\b", " cci ", normalized)
    normalized = re.sub(r"\bft\b", "fort", normalized)
    normalized = re.sub(r"\bst\.\b", "street", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def tokenize(value: str) -> list[str]:
    return [token for token in normalize_site_name(value).split() if token not in TOKEN_STOPWORDS]


def score_site_match(input_site_name: str, candidate_site_name: str) -> float:
    normalized_input = normalize_site_name(input_site_name)
    normalized_candidate = normalize_site_name(candidate_site_name)
    input_tokens = set(tokenize(input_site_name))
    candidate_tokens = set(tokenize(candidate_site_name))

    sequence_score = SequenceMatcher(None, normalized_input, normalized_candidate).ratio()
    common = len(input_tokens & candidate_tokens)
    query_coverage = common / max(len(input_tokens), 1)
    candidate_precision = common / max(len(candidate_tokens), 1)

    containment_bonus = 0.0
    if input_tokens and input_tokens.issubset(candidate_tokens):
        containment_bonus = 0.12

    return round(
        min(
            (0.55 * query_coverage)
            + (0.20 * candidate_precision)
            + (0.25 * sequence_score)
            + containment_bonus,
            1.0,
        )
        * 100,
        2,
    )


def best_site_match(input_site_name: str, candidate_site_names: list[str]) -> SiteMatchResult:
    best_name: str | None = None
    best_score = 0.0

    for candidate_site_name in candidate_site_names:
        score = score_site_match(input_site_name, candidate_site_name)
        if score > best_score:
            best_score = score
            best_name = candidate_site_name

    return SiteMatchResult(
        input_site_name=input_site_name,
        matched_site_name=best_name,
        score=best_score,
    )
