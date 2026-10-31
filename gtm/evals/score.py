"""Score one GTM answer. This module does not call Onyx."""

from __future__ import annotations

from dataclasses import dataclass

from gtm.lib.parse import (
    ConfigError,
    as_bool,
    as_dict,
    as_list,
    as_str,
    require_key,
    str_list,
)


@dataclass(frozen=True)
class RetrievedDoc:
    document_id: str
    semantic_identifier: str
    link: str
    blurb: str


@dataclass(frozen=True)
class EvalCase:
    id: str
    agent_name: str
    question: str
    expected_source_substrings: tuple[str, ...]
    expect_not_in_brain: bool
    require_citation: bool
    expect_any_substrings: tuple[str, ...]
    forbid_substrings: tuple[str, ...]


@dataclass(frozen=True)
class Score:
    passed: bool
    citation_count: int
    source_hit: str | None
    reason: str


def load_cases(raw: object, phrase: str) -> tuple[EvalCase, ...]:
    root = as_dict(raw, "evals")
    file_phrase = as_str(
        require_key(root, "not_in_brain_phrase", "evals"), "not_in_brain_phrase"
    ).strip()
    if file_phrase != phrase:
        raise ConfigError(
            "evals not_in_brain_phrase does not match gtm/config/gtm.yaml"
        )
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for item in as_list(require_key(root, "cases", "evals"), "cases"):
        case_raw = as_dict(item, "case")
        case_id = as_str(require_key(case_raw, "id", "case"), "case id").strip()
        if case_id in seen:
            raise ConfigError(f"Duplicate eval id {case_id}")
        seen.add(case_id)
        expect_not = as_bool(
            require_key(case_raw, "expect_not_in_brain", case_id),
            "expect_not_in_brain",
        )
        require_citation = as_bool(
            require_key(case_raw, "require_citation", case_id),
            "require_citation",
        )
        sources = _optional_str_list(case_raw, "expected_source_substrings")
        if expect_not and require_citation:
            raise ConfigError(f"{case_id} cannot require a citation and the fallback")
        if expect_not and sources:
            raise ConfigError(f"{case_id} cannot expect a source and the fallback")
        cases.append(
            EvalCase(
                id=case_id,
                agent_name=as_str(
                    require_key(case_raw, "agent_name", case_id), "agent_name"
                ).strip(),
                question=as_str(
                    require_key(case_raw, "question", case_id), "question"
                ).strip(),
                expected_source_substrings=sources,
                expect_not_in_brain=expect_not,
                require_citation=require_citation,
                expect_any_substrings=_optional_str_list(
                    case_raw, "expect_any_substrings"
                ),
                forbid_substrings=_optional_str_list(case_raw, "forbid_substrings"),
            )
        )
    return tuple(cases)


def score_answer(
    case: EvalCase,
    answer: str,
    citation_document_ids: list[str],
    documents: list[RetrievedDoc],
    phrase: str,
) -> Score:
    citation_count = len(citation_document_ids)
    lowered = answer.lower()
    for banned in case.forbid_substrings:
        if banned.lower() in lowered:
            return Score(False, citation_count, None, f"answer contains {banned!r}")
    if case.expect_not_in_brain:
        if phrase.lower() not in lowered:
            return Score(False, citation_count, None, "missing the fallback phrase")
        if citation_count:
            return Score(
                False,
                citation_count,
                None,
                "cited a source for a question that is not in the brain",
            )
        return Score(True, citation_count, None, "fallback")
    if case.require_citation and citation_count == 0:
        return Score(False, citation_count, None, "no citation_info")
    source_hit: str | None = None
    if case.expected_source_substrings:
        source_hit = _match_source(case, citation_document_ids, documents)
        if source_hit is None:
            return Score(False, citation_count, None, "no expected source")
    if case.expect_any_substrings and not any(
        part.lower() in lowered for part in case.expect_any_substrings
    ):
        return Score(False, citation_count, source_hit, "answer missed the expected text")
    return Score(True, citation_count, source_hit, "ok")


def _match_source(
    case: EvalCase,
    citation_document_ids: list[str],
    documents: list[RetrievedDoc],
) -> str | None:
    haystacks = [doc_id.lower() for doc_id in citation_document_ids]
    for doc in documents:
        haystacks.extend(
            [
                doc.document_id.lower(),
                doc.semantic_identifier.lower(),
                doc.link.lower(),
                doc.blurb.lower(),
            ]
        )
    for expected in case.expected_source_substrings:
        needle = expected.lower()
        if any(needle in haystack for haystack in haystacks):
            return expected
    return None


def _optional_str_list(raw: dict[str, object], key: str) -> tuple[str, ...]:
    if key not in raw or raw[key] is None:
        return ()
    return str_list(raw[key], key)
