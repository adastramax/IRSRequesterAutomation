"""Token-based site-name matching copied from the validated mock flow."""

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


def _progressive_site_name_variants(site_name: str) -> list[str]:
    """Return progressively stripped variants of a site name for fuzzy matching."""
    variants = [site_name]
    # Strip parenthetical address suffix: "IRS SBSE FE Atlanta, GA (2888 Woodcock Blvd)" -> "IRS SBSE FE Atlanta, GA"
    stripped_parens = re.sub(r"\s*\(.*?\)\s*$", "", site_name).strip()
    if stripped_parens and stripped_parens != site_name:
        variants.append(stripped_parens)
    # Strip trailing ", STATE" or ", CITY, STATE": "IRS SBSE FE Atlanta, GA" -> "IRS SBSE FE Atlanta"
    stripped_state = re.sub(r",\s*[A-Z]{2}\s*$", "", stripped_parens or site_name).strip()
    if stripped_state and stripped_state not in variants:
        variants.append(stripped_state)
    return variants


def best_site_match(input_site_name: str, candidate_site_names: list[str]) -> SiteMatchResult:
    best_name: str | None = None
    best_score = 0.0

    variants = _progressive_site_name_variants(input_site_name)
    for variant in variants:
        for candidate_site_name in candidate_site_names:
            score = score_site_match(variant, candidate_site_name)
            if score > best_score:
                best_score = score
                best_name = candidate_site_name

    return SiteMatchResult(
        input_site_name=input_site_name,
        matched_site_name=best_name,
        score=best_score,
    )


def top_site_matches(input_site_name: str, candidate_site_names: list[str], *, limit: int = 5) -> list[dict[str, float | str]]:
    ranked = [
        {"site_name": candidate_site_name, "score": score_site_match(input_site_name, candidate_site_name)}
        for candidate_site_name in candidate_site_names
    ]
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:limit]


def requires_explicit_site_confirmation(input_site_name: str, matched_site_name: str | None) -> bool:
    if matched_site_name is None:
        return True

    normalized_input = normalize_site_name(input_site_name)
    normalized_match = normalize_site_name(matched_site_name)
    if normalized_input == normalized_match:
        return False

    input_tokens = set(tokenize(input_site_name))
    matched_tokens = set(tokenize(matched_site_name))
    if input_tokens and input_tokens.issubset(matched_tokens):
        return False

    return True
