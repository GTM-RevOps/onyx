#!/usr/bin/env python3
"""Run the GTM question file against Onyx chat and score citations.

    python3 gtm/evals/run_evals.py --self-check
    python3 gtm/evals/run_evals.py --dry-run
    python3 gtm/evals/run_evals.py
    python3 gtm/evals/run_evals.py --id sdr-icp
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from gtm.evals.score import (
    EvalCase,
    RetrievedDoc,
    Score,
    load_cases,
    score_answer,
)
from gtm.lib.client import OnyxClient
from gtm.lib.config import GtmConfig, load_gtm_config
from gtm.lib.envfile import GTM_ROOT, load_default_env
from gtm.lib.parse import ConfigError, as_dict, as_list


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--id", default=None, help="Run one case id.")
    parser.add_argument("--agent", default=None, help="Run one agent name.")
    args = parser.parse_args(argv)
    try:
        if args.self_check:
            self_check()
            print("self-check passed")
            return 0
        load_default_env(args.env_file)
        config = load_gtm_config()
        cases = _load(config)
        cases = _filter(cases, args.id, args.agent)
        _check_agents(config, cases)
        if args.dry_run:
            print(f"DRY RUN. {len(cases)} cases. No request was sent.")
            for case in cases:
                print(
                    f"{case.id} agent={case.agent_name} "
                    f"citations_required={case.require_citation} "
                    f"fallback={case.expect_not_in_brain}"
                )
            return 0
        return _run_live(config, cases)
    except ConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def self_check() -> None:
    config = load_gtm_config()
    cases = {case.id: case for case in _load(config)}
    _check_agents(config, tuple(cases.values()))
    phrase = config.not_in_brain_phrase
    cited = score_answer(
        cases["sdr-icp"],
        "Our ICP is multi-site gyms.",
        ["notion-icp"],
        [_doc("notion-icp", "ICP", "https://notion.so/ICP", "Firmographics")],
        phrase,
    )
    _expect(cited.passed, "cited ICP should pass")
    missing = score_answer(
        cases["sdr-icp"],
        "Our ICP is multi-site gyms.",
        [],
        [],
        phrase,
    )
    _expect(not missing.passed and missing.reason == "no citation_info", missing.reason)
    fallback = score_answer(
        cases["sdr-missing-discount"],
        "This is not in the brain.",
        [],
        [],
        phrase,
    )
    _expect(fallback.passed, "fallback should pass")
    invented = score_answer(
        cases["sdr-missing-discount"],
        "This is not in the brain.",
        ["fake-doc"],
        [],
        phrase,
    )
    _expect(not invented.passed, "a fallback with a citation should fail")
    blocked = score_answer(
        cases["sdr-do-not-send"],
        "A human sends the email. I will not apply a discount.",
        [],
        [],
        phrase,
    )
    _expect(blocked.passed, "a draft-only refusal should pass")
    sent = score_answer(
        cases["sdr-do-not-send"],
        "I sent the email and a human can review it.",
        [],
        [],
        phrase,
    )
    _expect(not sent.passed, "a claim that the email was sent should fail")


def _run_live(config: GtmConfig, cases: tuple[EvalCase, ...]) -> int:
    api_key = os.environ.get("ONYX_API_KEY", "").strip()
    if not api_key:
        raise ConfigError("Set ONYX_API_KEY.")
    if not (api_key.startswith("on_") or api_key.startswith("dn_")):
        raise ConfigError("ONYX_API_KEY must be an Onyx API key. It starts with on_.")
    base = os.environ.get("ONYX_API_BASE", "http://localhost:3000/api").strip()
    timeout = _timeout("ONYX_CHAT_TIMEOUT", 180)
    client = OnyxClient(
        base,
        api_key,
        timeout,
        [api_key, os.environ.get("OPENAI_API_KEY", "")],
    )
    persona_ids = _persona_ids(client)
    failed = 0
    for case in cases:
        persona_id = persona_ids.get(case.agent_name)
        if persona_id is None:
            print(f"FAIL {case.id} agent {case.agent_name} is not in Onyx")
            failed += 1
            continue
        payload = as_dict(
            client.request(
                "POST",
                "/chat/send-chat-message",
                _chat_body(case.question, persona_id),
            ),
            f"{case.id} response",
        )
        error = payload.get("error_msg")
        if isinstance(error, str) and error:
            print(f"FAIL {case.id} {error}")
            failed += 1
            continue
        citation_ids, documents, answer = _read_response(payload)
        result = score_answer(
            case,
            answer,
            citation_ids,
            documents,
            config.not_in_brain_phrase,
        )
        _print_result(case.id, result, answer)
        if not result.passed:
            failed += 1
    print(f"{len(cases) - failed} passed, {failed} failed")
    return 1 if failed else 0


def _chat_body(question: str, persona_id: int) -> dict[str, object]:
    info: dict[str, object] = {"persona_id": persona_id}
    if os.environ.get("GTM_EVAL_INCOGNITO", "").strip().lower() == "true":
        info["incognito"] = True
    return {
        "message": question,
        "stream": False,
        "include_citations": True,
        "chat_session_info": info,
    }


def _persona_ids(client: OnyxClient) -> dict[str, int]:
    listing = as_list(client.request("GET", "/admin/persona"), "agents")
    ids: dict[str, int] = {}
    for item in listing:
        persona = as_dict(item, "agent")
        name = persona.get("name")
        persona_id = persona.get("id")
        if isinstance(name, str) and isinstance(persona_id, int):
            ids[name] = persona_id
    return ids


def _read_response(
    payload: dict[str, object],
) -> tuple[list[str], list[RetrievedDoc], str]:
    answer = payload.get("answer")
    answer_text = answer if isinstance(answer, str) else ""
    citation_ids: list[str] = []
    raw_citations = payload.get("citation_info")
    if isinstance(raw_citations, list):
        for item in raw_citations:
            if isinstance(item, dict) and isinstance(item.get("document_id"), str):
                citation_ids.append(item["document_id"])
    documents: list[RetrievedDoc] = []
    raw_docs = payload.get("top_documents")
    if isinstance(raw_docs, list):
        for item in raw_docs:
            if not isinstance(item, dict):
                continue
            documents.append(
                RetrievedDoc(
                    document_id=_str_field(item, "document_id"),
                    semantic_identifier=_str_field(item, "semantic_identifier"),
                    link=_str_field(item, "link"),
                    blurb=_str_field(item, "blurb"),
                )
            )
    return citation_ids, documents, answer_text


def _load(config: GtmConfig) -> tuple[EvalCase, ...]:
    path = GTM_ROOT / "evals" / "questions.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return load_cases(loaded, config.not_in_brain_phrase)


def _filter(
    cases: tuple[EvalCase, ...], case_id: str | None, agent: str | None
) -> tuple[EvalCase, ...]:
    selected = cases
    if case_id is not None:
        selected = tuple(case for case in selected if case.id == case_id)
    if agent is not None:
        selected = tuple(case for case in selected if case.agent_name == agent)
    if not selected:
        raise ConfigError("No eval cases matched")
    return selected


def _check_agents(config: GtmConfig, cases: tuple[EvalCase, ...]) -> None:
    names = {agent.name for agent in config.agents}
    for case in cases:
        if case.agent_name not in names:
            raise ConfigError(f"{case.id} uses unknown agent {case.agent_name}")


def _print_result(case_id: str, result: Score, answer: str) -> None:
    status = "PASS" if result.passed else "FAIL"
    source = result.source_hit or "-"
    print(
        f"{status} {case_id} citations={result.citation_count} "
        f"source={source} {result.reason}"
    )
    if not result.passed:
        excerpt = " ".join(answer.split())
        if len(excerpt) > 240:
            excerpt = excerpt[:240] + "..."
        if excerpt:
            print(f"  answer: {excerpt}")


def _doc(document_id: str, title: str, link: str, blurb: str) -> RetrievedDoc:
    return RetrievedDoc(document_id, title, link, blurb)


def _str_field(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    return value if isinstance(value, str) else ""


def _timeout(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as error:
        raise ConfigError(f"{name} must be a number") from error


def _expect(condition: bool, detail: str) -> None:
    if not condition:
        raise ConfigError(detail)


if __name__ == "__main__":
    raise SystemExit(main())
