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
    parser.add_argument(
        "--access",
        action="store_true",
        help="Check Hub vs Informatics visibility through the Onyx MCP search tool.",
    )
    parser.add_argument("--id", default=None, help="Run one case id.")
    parser.add_argument("--agent", default=None, help="Run one agent name.")
    args = parser.parse_args(argv)
    try:
        if args.self_check and not args.access:
            self_check()
            print("self-check passed")
            return 0
        if args.access:
            return _access_main(args.dry_run, args.self_check, args.env_file)
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


def _access_main(dry_run: bool, self_check_only: bool, env_file: Path | None) -> int:
    if self_check_only:
        _access_self_check()
        print("access self-check passed")
        return 0
    if not dry_run:
        load_default_env(env_file)
    config = load_gtm_config()
    page_id = config.informatics.root_page_id
    if dry_run:
        print("DRY RUN. No MCP request was sent.")
        print(f"Hub-only token must not see {page_id}")
        print(f"Viewer token must see {page_id}")
        print("Revoked token must be refused (401 or 403)")
        return 0
    return _run_access(page_id)


def _access_self_check() -> None:
    from gtm.evals.access_score import (
        AccessResult,
        score_hub_user,
        score_revoked,
        score_viewer,
    )

    page = "408233ce-1c17-81e4-a92f-e23cc8bb95fd"
    if not score_hub_user([AccessResult("hub-page", "ICP", "", "firmographics")], page).passed:
        raise ConfigError("Hub-only fixture should pass")
    leaked = AccessResult(page, "Comp", f"https://www.notion.so/{page}", "salary")
    if score_hub_user([leaked], page).passed:
        raise ConfigError("A Hub-only hit on Informatics should fail")
    if not score_viewer([leaked], page).passed:
        raise ConfigError("A viewer hit should pass")
    if score_viewer([], page).passed:
        raise ConfigError("A viewer with no hit should fail")
    if not score_revoked(401).passed or not score_revoked(403).passed:
        raise ConfigError("Revoked tokens should fail closed")
    if score_revoked(200).passed:
        raise ConfigError("A 200 from a revoked token should fail")


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
    _access_self_check()


def _run_access(page_id: str) -> int:
    import json
    import urllib.error
    import urllib.request

    from gtm.evals.access_score import AccessResult, score_hub_user, score_revoked, score_viewer

    hub_token = os.environ.get("ONYX_HUB_USER_TOKEN", "").strip()
    viewer_token = os.environ.get("ONYX_INFORMATICS_VIEWER_TOKEN", "").strip()
    revoked_token = os.environ.get("ONYX_REVOKED_TOKEN", "").strip()
    missing = [
        name
        for name, value in (
            ("ONYX_HUB_USER_TOKEN", hub_token),
            ("ONYX_INFORMATICS_VIEWER_TOKEN", viewer_token),
            ("ONYX_REVOKED_TOKEN", revoked_token),
        )
        if not value
    ]
    if missing:
        raise ConfigError("Set " + ", ".join(missing) + " to a bearer token.")
    url = os.environ.get("ONYX_MCP_URL", "").strip() or _mcp_url()
    query = f"sales compensation {page_id}"
    failed = 0
    for label, token, kind in (
        ("hub-only", hub_token, "hub"),
        ("viewer", viewer_token, "viewer"),
        ("revoked", revoked_token, "revoked"),
    ):
        status, payload = _post_mcp(url, token, query, urllib.request, urllib.error, json)
        if kind == "revoked":
            result = score_revoked(status)
        else:
            if status != 200:
                print(f"FAIL {label} MCP status {status}")
                failed += 1
                continue
            results = _mcp_results(payload)
            result = score_hub_user(results, page_id) if kind == "hub" else score_viewer(results, page_id)
        status_word = "PASS" if result.passed else "FAIL"
        print(f"{status_word} {label} hits={result.informatics_hits} {result.reason}")
        if not result.passed:
            failed += 1
    print(f"{3 - failed} passed, {failed} failed")
    return 1 if failed else 0


def _mcp_url() -> str:
    base = os.environ.get("ONYX_API_BASE", "http://localhost:3000/api").strip().rstrip("/")
    if base.endswith("/api"):
        return base[: -len("/api")] + "/mcp"
    return base + "/mcp"


def _post_mcp(
    url: str,
    token: str,
    query: str,
    request_mod: object,
    error_mod: object,
    json_mod: object,
) -> tuple[int, object]:
    body = json_mod.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_indexed_documents",
                "arguments": {"query": query},
            },
        }
    ).encode("utf-8")
    req = request_mod.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request_mod.urlopen(req, timeout=_timeout("ONYX_HTTP_TIMEOUT", 60)) as response:
            raw = response.read()
            status = int(response.status)
    except error_mod.HTTPError as error:
        raw = error.read()
        status = int(error.code)
    if not raw:
        return status, None
    try:
        return status, json_mod.loads(raw.decode("utf-8"))
    except json_mod.JSONDecodeError as error:
        raise ConfigError(f"MCP returned non-JSON ({status})") from error


def _mcp_results(payload: object) -> list:
    from gtm.evals.access_score import AccessResult

    found: list[AccessResult] = []
    for item in _result_dicts(payload):
        found.append(
            AccessResult(
                document_id=_field(item, "document_id") or _field(item, "id"),
                title=_field(item, "title"),
                url=_field(item, "url") or _field(item, "link"),
                content=_field(item, "content"),
            )
        )
    return found


def _result_dicts(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, dict):
        results = payload.get("results")
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
        result = payload.get("result")
        if isinstance(result, dict):
            return _result_dicts(result)
        content = payload.get("content")
        if isinstance(content, list):
            rows: list[dict[str, object]] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if not isinstance(text, str):
                    continue
                try:
                    import json

                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    continue
                rows.extend(_result_dicts(parsed))
            return rows
    return []


def _field(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    return value if isinstance(value, str) else ""


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
