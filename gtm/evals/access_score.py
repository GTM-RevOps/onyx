"""Score Hub vs Informatics search results. This module does not call Onyx."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessResult:
    document_id: str
    title: str
    url: str
    content: str


@dataclass(frozen=True)
class AccessScore:
    passed: bool
    informatics_hits: int
    reason: str


def is_informatics(result: AccessResult, page_id: str) -> bool:
    """True when a hit is the Informatics page or a page that cites its id."""
    dashed = page_id.lower()
    compact = dashed.replace("-", "")
    blob = " ".join(
        [result.document_id, result.title, result.url, result.content]
    ).lower()
    return dashed in blob or compact in blob


def informatics_hit_count(results: list[AccessResult], page_id: str) -> int:
    return sum(1 for result in results if is_informatics(result, page_id))


def score_hub_user(results: list[AccessResult], page_id: str) -> AccessScore:
    hits = informatics_hit_count(results, page_id)
    if hits:
        return AccessScore(False, hits, "a Hub-only token saw Informatics")
    return AccessScore(True, 0, "no Informatics results")


def score_viewer(results: list[AccessResult], page_id: str) -> AccessScore:
    hits = informatics_hit_count(results, page_id)
    if hits < 1:
        return AccessScore(False, hits, "a viewer token did not see Informatics")
    return AccessScore(True, hits, "viewer sees Informatics")


def score_revoked(status: int) -> AccessScore:
    """A revoked token must fail closed. 401 and 403 both refuse the search."""
    if status in {401, 403}:
        return AccessScore(True, 0, f"revoked token refused ({status})")
    return AccessScore(False, 0, f"revoked token was accepted ({status})")
