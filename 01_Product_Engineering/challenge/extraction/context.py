"""Deterministic, lossless work-unit planning for bounded model prompts."""

from __future__ import annotations

import os
from dataclasses import dataclass

from schemas.extraction.extraction import ExtractionArtifact


@dataclass(frozen=True)
class WorkUnit:
    """Pages owned by one inference call; adjacent pages are context only."""

    owned_page_numbers: tuple[int, ...]
    context_page_numbers: tuple[int, ...]
    estimated_tokens: int


def estimate_tokens(text: str) -> int:
    """Conservative portable estimate; no model-specific tokenizer is required."""
    return max(1, (len(text) + 3) // 4)


def _page_tokens(artifact: ExtractionArtifact, page_number: int) -> int:
    page = next(page for page in artifact.pages if page.page_number == page_number)
    # Evidence lines add IDs, coordinates, and parser labels around each source
    # span. Reserve 64 characters per element rather than treating raw text alone
    # as the complete prompt.
    return max(
        1,
        sum(len(element.text or "") + 64 for element in page.elements) // 4,
    )


def plan_work_units(
    artifact: ExtractionArtifact,
    *,
    max_tokens: int | None = None,
    context_pages: int | None = None,
) -> list[WorkUnit]:
    """Assign every page exactly once without silently truncating source text."""
    budget = max_tokens or int(os.getenv("EXTRACTION_CONTEXT_TOKENS", "12000"))
    neighbors = (
        context_pages
        if context_pages is not None
        else int(os.getenv("EXTRACTION_CONTEXT_PAGES", "1"))
    )
    if budget < 1 or neighbors < 0:
        raise ValueError(
            "Context token budget must be positive and context pages nonnegative"
        )
    owner_budget = max(1, budget // (1 + 2 * neighbors))

    page_numbers = [page.page_number for page in artifact.pages]
    units: list[WorkUnit] = []
    owned: list[int] = []
    token_count = 0
    for page_number in page_numbers:
        page_tokens = _page_tokens(artifact, page_number)
        if owned and token_count + page_tokens > owner_budget:
            units.append(_unit(page_numbers, owned, token_count, neighbors))
            owned, token_count = [], 0
        # A single oversized page remains intact. Splitting it would break table and
        # field relationships; its explicit over-budget size is observable in the plan.
        owned.append(page_number)
        token_count += page_tokens
    if owned:
        units.append(_unit(page_numbers, owned, token_count, neighbors))

    assigned = [page for unit in units for page in unit.owned_page_numbers]
    if assigned != page_numbers or len(assigned) != len(set(assigned)):
        raise AssertionError(
            "Every artifact page must have exactly one work-unit owner"
        )
    return units


def _unit(
    page_numbers: list[int], owned: list[int], token_count: int, neighbors: int
) -> WorkUnit:
    first = page_numbers.index(owned[0])
    last = page_numbers.index(owned[-1]) + 1
    context = (
        page_numbers[max(0, first - neighbors) : first]
        + page_numbers[last : last + neighbors]
    )
    return WorkUnit(tuple(owned), tuple(context), token_count)
