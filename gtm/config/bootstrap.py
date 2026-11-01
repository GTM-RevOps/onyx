#!/usr/bin/env python3
"""Create or update the PushPress GTM agents in a running Onyx instance.

The script is idempotent. A second run updates the OpenAI provider, leaves an
existing Notion connector in place, and patches agents only when the text changed.

    python3 gtm/config/bootstrap.py --self-check
    python3 gtm/config/bootstrap.py --dry-run
    python3 gtm/config/bootstrap.py
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from gtm.lib.client import Api, OnyxClient
from gtm.lib.config import AgentSpec, GtmConfig, PrivateNotionSpec, load_gtm_config
from gtm.lib.dry_run import Call, RecordingApi
from gtm.lib.envfile import load_default_env
from gtm.lib.parse import ConfigError, as_dict, as_int, as_list


@dataclass(frozen=True)
class LlmResult:
    chat_model_configuration_id: int | None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the same steps against an in-memory API. No network.",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Create, then update, against the in-memory API and check the calls.",
    )
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument(
        "--skip-notion",
        action="store_true",
        help="Do not create the Notion connector. Document sets keep any connector they already have.",
    )
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        if args.self_check:
            self_check()
            print("self-check passed")
            return 0
        load_default_env(args.env_file)
        config = load_gtm_config(args.config)
        if args.dry_run:
            api = RecordingApi()
            logs = apply(api, config, require_secrets=False, skip_notion=args.skip_notion)
            print("DRY RUN. No request was sent.")
            for line in logs:
                print(line)
            print(render_plan(api.calls))
            return 0
        api = live_client(require_secrets=True)
        for line in apply(api, config, require_secrets=True, skip_notion=args.skip_notion):
            print(line)
        return 0
    except ConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def self_check() -> None:
    os.environ["OPENAI_API_KEY"] = "sk-gtm-self-check"
    os.environ["NOTION_INTEGRATION_TOKEN"] = "ntn_gtm_self_check"
    os.environ["NOTION_ROOT_PAGE_ID"] = ""
    os.environ.pop("GTM_OPENAI_PROVIDER_NAME", None)
    os.environ.pop("OPENAI_CHAT_MODEL", None)
    os.environ.pop("OPENAI_FAST_MODEL", None)
    config = load_gtm_config()
    api = RecordingApi()
    for index, email in enumerate(config.informatics.viewers):
        api.users.append(
            {"id": str(uuid.UUID(int=index + 1)), "email": email}
        )
        api.credentials.append(
            {
                "id": 800 + index,
                "source": "notion",
                "user_email": email,
                "admin_public": True,
            }
        )
    apply(api, config, require_secrets=True, skip_notion=False)
    first = list(api.calls)
    api.calls.clear()
    apply(api, config, require_secrets=True, skip_notion=False)
    second = list(api.calls)

    _expect_path(first, "POST", "/manage/admin/connector-with-credential")
    if _has_path(second, "POST", "/manage/admin/connector-with-credential"):
        raise ConfigError("The second run created the Notion connector again")
    _expect_path(first, "PUT", "/admin/llm/provider")
    _expect_path(second, "PUT", "/admin/llm/provider")
    if _count(second, "POST", "/persona") != 0:
        raise ConfigError("The second run created an agent again")
    if _count(second, "POST", "/manage/admin/document-set") != 0:
        raise ConfigError("The second run created a document set again")
    if _count(second, "PATCH", "/persona/") != 0:
        raise ConfigError("The second run patched an unchanged agent")
    if _count(first, "POST", "/persona") != len(config.agents):
        raise ConfigError("The first run did not create every agent")
    _expect_search_tool_only(first)
    _expect_secret_sent(first, "sk-gtm-self-check", "ntn_gtm_self_check")
    plan = render_plan(first)
    if "sk-gtm-self-check" in plan or "ntn_gtm_self_check" in plan:
        raise ConfigError("The dry-run plan included a secret")
    if _count(first, "PUT", "/manage/connector/") != len(config.informatics.viewers):
        raise ConfigError("The first run did not pair every Informatics viewer")
    if _count(second, "PUT", "/manage/connector/") != 0:
        raise ConfigError("The second run paired an Informatics viewer again")
    if _count(second, "DELETE", "/manage/connector/") != 0:
        raise ConfigError("The second run removed an Informatics pair")
    _expect_excluded(first, config.informatics.root_page_id)
    api.calls.clear()
    narrower = replace(
        config.informatics, viewers=config.informatics.viewers[:3]
    )
    ensure_private_connector(
        api,
        narrower,
        require_secrets=True,
        logs=[],
    )
    if _count(api.calls, "DELETE", "/manage/connector/") != 1:
        raise ConfigError("Removing a viewer did not delete their pair")
    bare = RecordingApi()
    try:
        ensure_private_connector(bare, config.informatics, require_secrets=True, logs=[])
    except ConfigError as error:
        if config.informatics.viewers[0] not in str(error):
            raise
    else:
        raise ConfigError("A missing Notion credential did not fail")


def live_client(require_secrets: bool) -> OnyxClient:
    api_key = os.environ.get("ONYX_API_KEY", "").strip()
    if require_secrets and not api_key:
        raise ConfigError("Set ONYX_API_KEY. Create it in the Onyx admin UI.")
    if api_key and not (api_key.startswith("on_") or api_key.startswith("dn_")):
        raise ConfigError("ONYX_API_KEY must be an Onyx API key. It starts with on_.")
    base = os.environ.get("ONYX_API_BASE", "http://localhost:3000/api").strip()
    timeout = _timeout("ONYX_HTTP_TIMEOUT", 60)
    secrets = [
        api_key,
        os.environ.get("OPENAI_API_KEY", ""),
        os.environ.get("NOTION_INTEGRATION_TOKEN", ""),
    ]
    return OnyxClient(base, api_key, timeout, secrets)


def apply(
    api: Api,
    config: GtmConfig,
    *,
    require_secrets: bool,
    skip_notion: bool,
) -> list[str]:
    logs: list[str] = []
    llm = ensure_llm(api, config, require_secrets=require_secrets, logs=logs)
    cc_pair_id = ensure_notion(
        api, config, require_secrets=require_secrets, skip_notion=skip_notion, logs=logs
    )
    informatics_ids = ensure_private_connector(
        api,
        config.informatics,
        require_secrets=require_secrets and not skip_notion,
        logs=logs,
    )
    pairs_by_name: dict[str, list[int]] = {}
    if cc_pair_id is not None:
        pairs_by_name[config.notion.name] = [cc_pair_id]
    if informatics_ids:
        pairs_by_name[config.informatics.name] = informatics_ids
    set_ids = ensure_document_sets(
        api,
        config,
        pairs_by_name=pairs_by_name,
        logs=logs,
    )
    label_id = ensure_label(api, config, logs)
    tool_ids = resolve_tools(api, config)
    for agent in config.agents:
        if any(key not in set_ids for key in agent.document_set_keys):
            logs.append(f"Skip agent {agent.name}. A document set is not ready.")
            continue
        ensure_agent(
            api,
            config,
            agent,
            set_ids,
            tool_ids,
            label_id,
            llm,
            logs,
            require_secrets=require_secrets,
        )
        ensure_prompts(api, agent, logs)
    return logs


def ensure_llm(
    api: Api,
    config: GtmConfig,
    *,
    require_secrets: bool,
    logs: list[str],
) -> LlmResult:
    env_name = os.environ.get("GTM_OPENAI_PROVIDER_NAME", "").strip()
    provider_name = env_name or config.llm.provider_name
    key = os.environ.get(config.llm.api_key_env, "").strip()
    if not key:
        if require_secrets:
            raise ConfigError(
                f"Set {config.llm.api_key_env}. The bootstrap stores it in Onyx."
            )
        key = "dry-run-placeholder"
        logs.append(f"{config.llm.api_key_env} is unset. A live run stops here.")
    chat_model = _env_or(config.llm.chat_model_env, config.llm.chat_model_default)
    fast_model = _env_or(config.llm.fast_model_env, config.llm.fast_model_default)
    listing = as_dict(api.request("GET", "/admin/llm/provider"), "LLM providers")
    providers = as_list(listing.get("providers"), "providers")
    existing = _find_named(providers, provider_name, "LLM provider")
    models = _model_rows(
        chat_model,
        config.llm.chat_max_input_tokens,
        fast_model,
        config.llm.fast_max_input_tokens,
    )
    body: dict[str, object] = {
        "name": provider_name,
        "provider": config.llm.provider,
        "api_key": key,
        "api_key_changed": True,
        "is_public": True,
        "is_auto_mode": False,
        "groups": [],
        "personas": [],
        "keep_existing_models": existing is not None,
        "model_configurations": models,
    }
    query = {"is_creation": "true"}
    action = "create"
    if existing is not None:
        body["id"] = as_int(existing.get("id"), "provider id")
        query = {"is_creation": "false"}
        action = "update"
    saved = as_dict(
        api.request("PUT", "/admin/llm/provider", body, query),
        "LLM provider",
    )
    provider_id = as_int(saved.get("id"), "provider id")
    logs.append(f"{action} OpenAI provider {provider_name} (id {provider_id})")
    _set_default_if_unset(
        api,
        listing,
        "default_text",
        "/admin/llm/default",
        provider_id,
        chat_model,
        config.llm.set_chat_default_if_unset,
        logs,
    )
    _set_default_if_unset(
        api,
        listing,
        "default_vision",
        "/admin/llm/default-vision",
        provider_id,
        chat_model,
        config.llm.set_vision_default_if_unset,
        logs,
    )
    _set_default_if_unset(
        api,
        listing,
        "default_chat_naming",
        "/admin/llm/default-chat-naming",
        provider_id,
        fast_model,
        config.llm.set_naming_default_if_unset,
        logs,
    )
    _set_default_if_unset(
        api,
        listing,
        "default_search_selection",
        "/admin/llm/default-search-selection",
        provider_id,
        fast_model,
        config.llm.set_search_selection_default_if_unset,
        logs,
    )
    return LlmResult(chat_model_configuration_id=_model_id(saved, chat_model))


def ensure_notion(
    api: Api,
    config: GtmConfig,
    *,
    require_secrets: bool,
    skip_notion: bool,
    logs: list[str],
) -> int | None:
    if skip_notion:
        logs.append("Skip Notion (--skip-notion).")
        return None
    token = os.environ.get(config.notion.token_env, "").strip()
    if not token:
        if require_secrets:
            raise ConfigError(
                f"Set {config.notion.token_env}, or pass --skip-notion."
            )
        logs.append(
            f"{config.notion.token_env} is unset. A live run stops here. "
            "With a token, the script POSTs /manage/admin/connector-with-credential."
        )
        return None
    statuses = as_list(
        api.request("GET", "/manage/admin/connector/status"),
        "connector status",
    )
    existing = _find_named(statuses, config.notion.name, "connector")
    if existing is not None:
        source = as_dict(existing.get("connector"), "connector").get("source")
        if source != "notion":
            raise ConfigError(
                f"{config.notion.name} exists and its source is {source}."
            )
        cc_pair_id = as_int(existing.get("cc_pair_id"), "cc_pair_id")
        logs.append(
            f"Keep Notion connector {config.notion.name} (cc pair {cc_pair_id}). "
            "The token was not rotated."
        )
        return cc_pair_id
    specific: dict[str, object] = {
        "recursive_index_enabled": config.notion.recursive_index_enabled,
    }
    root = os.environ.get(config.notion.root_page_id_env, "").strip()
    root = root or config.notion.root_page_id
    if root:
        specific["root_page_id"] = root
    if config.notion.excluded_page_ids:
        specific["excluded_page_ids"] = list(config.notion.excluded_page_ids)
    created = api.request(
        "POST",
        "/manage/admin/connector-with-credential",
        {
            "connector": {
                "name": config.notion.name,
                "source": config.notion.source,
                "input_type": config.notion.input_type,
                "connector_specific_config": specific,
                "refresh_freq": config.notion.refresh_freq_seconds,
                "prune_freq": config.notion.prune_freq_seconds,
                "access_type": config.notion.access_type,
                "groups": [],
            },
            "pairing": {
                "name": config.notion.name,
                "access_type": config.notion.access_type,
            },
            "credential_json": {config.notion.credential_key: token},
            "credential_sharing": {"admin_public": True},
        },
    )
    created_obj = as_dict(created, "connector create")
    if created_obj.get("success") is False:
        raise ConfigError(str(created_obj.get("message") or "Notion create failed"))
    cc_pair_id = as_int(created_obj.get("data"), "cc_pair_id")
    logs.append(f"Create Notion connector {config.notion.name} (cc pair {cc_pair_id})")
    return cc_pair_id


def ensure_private_connector(
    api: Api,
    spec: PrivateNotionSpec,
    *,
    require_secrets: bool,
    logs: list[str],
) -> list[int]:
    """Create the Informatics connector and pair one private credential per viewer."""
    credentials = as_list(
        api.request("GET", "/manage/admin/credential"), "credentials"
    )
    chosen: dict[str, dict[str, object]] = {}
    missing: list[str] = []
    for email in spec.viewers:
        owned = _credentials_for_viewer(credentials, email)
        if len(owned) == 1:
            chosen[email.lower()] = owned[0]
            continue
        if len(owned) > 1:
            raise ConfigError(
                f"{email} owns {len(owned)} Notion credentials. "
                "Leave one admin-public Informatics credential and re-run."
            )
        missing.append(email)
    if missing:
        message = _missing_credential_message(missing)
        if require_secrets:
            raise ConfigError(message)
        logs.append(message)
        return []

    rows = as_list(api.request("GET", "/manage/admin/connector"), "connectors")
    existing = _find_named(rows, spec.name, "connector")
    if existing is None:
        created = as_dict(
            api.request(
                "POST",
                "/manage/admin/connector",
                {
                    "name": spec.name,
                    "source": spec.source,
                    "input_type": spec.input_type,
                    "connector_specific_config": {
                        "recursive_index_enabled": spec.recursive_index_enabled,
                        "root_page_id": spec.root_page_id,
                    },
                    "refresh_freq": spec.refresh_freq_seconds,
                    "prune_freq": spec.prune_freq_seconds,
                    "access_type": spec.access_type,
                    "groups": [],
                },
            ),
            "informatics connector",
        )
        connector_id = as_int(created.get("id"), "connector id")
        logs.append(f"Create Informatics connector {spec.name} (id {connector_id})")
    else:
        connector_id = as_int(existing.get("id"), "connector id")
        logs.append(f"Keep Informatics connector {spec.name} (id {connector_id})")

    statuses = as_list(
        api.request("GET", "/manage/admin/connector/status"),
        "connector status",
    )
    paired = _pairs_for_connector(statuses, connector_id)
    paired_emails = {
        _pair_email(row): row for row in paired if _pair_email(row)
    }
    wanted = {email.lower() for email in spec.viewers}
    cc_pair_ids: list[int] = []
    for email in spec.viewers:
        current = paired_emails.get(email.lower())
        if current is not None:
            cc_pair_ids.append(as_int(current.get("cc_pair_id"), "cc pair id"))
            logs.append(f"Keep Informatics pair for {email}")
            continue
        credential = chosen[email.lower()]
        credential_id = as_int(credential.get("id"), "credential id")
        # ConnectorCredentialPairMetadata requires name. access_type and groups
        # are the private CE pairing: no groups, so access is the credential owner.
        created_pair = as_dict(
            api.request(
                "PUT",
                f"/manage/connector/{connector_id}/credential/{credential_id}",
                {
                    "name": f"{spec.name} ({email})",
                    "access_type": "private",
                    "groups": [],
                },
            ),
            "informatics pair",
        )
        if created_pair.get("success") is False:
            raise ConfigError(str(created_pair.get("message") or "pair failed"))
        cc_pair_ids.append(as_int(created_pair.get("data"), "cc pair id"))
        logs.append(f"Pair Informatics credential for {email}")

    for row in paired:
        email = _pair_email(row)
        if email in wanted:
            continue
        credential = as_dict(row.get("credential"), "credential")
        credential_id = as_int(credential.get("id"), "credential id")
        api.request(
            "DELETE",
            f"/manage/connector/{connector_id}/credential/{credential_id}",
        )
        logs.append(f"Remove Informatics pair for {email or credential_id}")
    return cc_pair_ids


def ensure_document_sets(
    api: Api,
    config: GtmConfig,
    *,
    pairs_by_name: dict[str, list[int]],
    logs: list[str],
) -> dict[str, int]:
    listing = as_list(
        api.request("GET", "/manage/document-set", query={"get_editable": "true"}),
        "document sets",
    )
    ids: dict[str, int] = {}
    for spec in config.document_sets:
        desired, complete = _ids_for_names(spec.cc_pair_names, pairs_by_name)
        existing = _find_named(listing, spec.name, "document set")
        if existing is None:
            if not desired:
                logs.append(
                    f"Skip document set {spec.name}. Its connector is not paired yet."
                )
                continue
            created = api.request(
                "POST",
                "/manage/admin/document-set",
                _document_set_body(None, spec.name, spec.description, desired, spec.is_public),
            )
            set_id = _id_from_create(created, "document set id")
            logs.append(f"Create document set {spec.name} (id {set_id})")
            ids[spec.key] = set_id
            continue
        set_id = as_int(existing.get("id"), "document set id")
        ids[spec.key] = set_id
        current = _summary_ids(existing)
        if not complete:
            desired = sorted(current)
        if (
            existing.get("description") == spec.description
            and existing.get("is_public") is spec.is_public
            and current == set(desired)
        ):
            logs.append(f"Keep document set {spec.name} (id {set_id})")
            continue
        if existing.get("is_up_to_date") is False:
            logs.append(
                f"Skip {spec.name}. Onyx is still syncing it. Re-run when it is idle."
            )
            continue
        api.request(
            "PATCH",
            "/manage/admin/document-set",
            _document_set_body(set_id, spec.name, spec.description, desired, spec.is_public),
        )
        logs.append(f"Update document set {spec.name} (id {set_id})")
    return ids


def ensure_label(api: Api, config: GtmConfig, logs: list[str]) -> int:
    labels = as_list(api.request("GET", "/persona/labels"), "labels")
    existing = _find_named(labels, config.label, "label")
    if existing is not None:
        label_id = as_int(existing.get("id"), "label id")
        logs.append(f"Keep label {config.label} (id {label_id})")
        return label_id
    created = as_dict(
        api.request("POST", "/persona/labels", {"name": config.label}),
        "label",
    )
    label_id = as_int(created.get("id"), "label id")
    logs.append(f"Create label {config.label} (id {label_id})")
    return label_id


def resolve_tools(api: Api, config: GtmConfig) -> dict[str, int]:
    tools = as_list(api.request("GET", "/tool"), "tools")
    found: dict[str, int] = {}
    for item in tools:
        tool = as_dict(item, "tool")
        code = tool.get("in_code_tool_id")
        if isinstance(code, str) and code:
            found[code] = as_int(tool.get("id"), f"{code} id")
    needed: set[str] = set()
    for agent in config.agents:
        needed.update(agent.tool_codes)
    missing = sorted(code for code in needed if code not in found)
    if missing:
        raise ConfigError(
            f"Onyx has no built-in tool {missing}. SearchTool is the internal search tool."
        )
    return {code: found[code] for code in needed}


def ensure_agent(
    api: Api,
    config: GtmConfig,
    agent: AgentSpec,
    set_ids: dict[str, int],
    tool_ids: dict[str, int],
    label_id: int,
    llm: LlmResult,
    logs: list[str],
    require_secrets: bool,
) -> None:
    user_ids: list[str] | None = None
    if agent.viewer_emails:
        user_ids = _user_ids(api, agent.viewer_emails, require_secrets, logs)
        if user_ids is None:
            logs.append(f"Skip agent {agent.name}. A viewer has no Onyx user yet.")
            return
    body = _agent_body(config, agent, set_ids, tool_ids, label_id, llm, user_ids)
    listing = as_list(api.request("GET", "/admin/persona"), "agents")
    existing = _find_named(listing, agent.name, "agent")
    if existing is not None and existing.get("builtin_persona") is True:
        raise ConfigError(f"{agent.name} is a built-in agent. Rename the GTM agent.")
    if existing is None:
        created = as_dict(api.request("POST", "/persona", body), "agent")
        logs.append(f"Create agent {agent.name} (id {as_int(created.get('id'), 'agent id')})")
        return
    persona_id = as_int(existing.get("id"), "agent id")
    current = as_dict(api.request("GET", f"/persona/{persona_id}"), "agent")
    if _agent_matches(current, body):
        logs.append(f"Keep agent {agent.name} (id {persona_id})")
        return
    api.request("PATCH", f"/persona/{persona_id}", body)
    logs.append(f"Update agent {agent.name} (id {persona_id})")


def ensure_prompts(api: Api, agent: AgentSpec, logs: list[str]) -> None:
    listing = as_list(api.request("GET", "/input_prompt"), "input prompts")
    existing_by_name: dict[str, dict[str, object]] = {}
    for item in listing:
        prompt = as_dict(item, "input prompt")
        title = prompt.get("prompt")
        if isinstance(title, str):
            existing_by_name[title] = prompt
    for task in agent.tasks:
        current = existing_by_name.get(task.name)
        if current is None:
            api.request(
                "POST",
                "/input_prompt",
                {"prompt": task.name, "content": task.prompt, "is_public": True},
            )
            logs.append(f"Create input prompt {task.name}")
            continue
        if current.get("content") == task.prompt:
            logs.append(f"Keep input prompt {task.name}")
            continue
        prompt_id = as_int(current.get("id"), "input prompt id")
        api.request(
            "PATCH",
            f"/input_prompt/{prompt_id}",
            {"prompt": task.name, "content": task.prompt, "active": True},
        )
        logs.append(f"Update input prompt {task.name}")


def _agent_body(
    config: GtmConfig,
    agent: AgentSpec,
    set_ids: dict[str, int],
    tool_ids: dict[str, int],
    label_id: int,
    llm: LlmResult,
    user_ids: list[str] | None,
) -> dict[str, object]:
    sections: list[str] = []
    for key in agent.document_set_keys:
        for section in config.document_set(key).notion_sections:
            if section not in sections:
                sections.append(section)
    harness = config.read_text(config.harness_prompt_file)
    role = config.read_text(agent.prompt_file)
    pages = "\n".join(f"- {section}" for section in sections)
    system_prompt = (
        f"{harness}\n\n{role}\n\nPrefer these Notion pages:\n{pages}\n"
    )
    starters = [
        {"name": task.name, "message": task.prompt}
        for task in agent.tasks[: agent.starter_message_limit]
    ]
    body: dict[str, object] = {
        "name": agent.name,
        "description": agent.description,
        "document_set_ids": [set_ids[key] for key in agent.document_set_keys],
        "is_public": agent.is_public,
        "tool_ids": [tool_ids[code] for code in agent.tool_codes],
        "system_prompt": system_prompt,
        "task_prompt": agent.task_prompt,
        "datetime_aware": agent.datetime_aware,
        "replace_base_system_prompt": agent.replace_base_system_prompt,
        "is_featured": agent.featured,
        "display_priority": agent.display_priority,
        "label_ids": [label_id],
        "starter_messages": starters,
    }
    if llm.chat_model_configuration_id is not None:
        body["default_model_configuration_id"] = llm.chat_model_configuration_id
    if user_ids is not None:
        body["users"] = user_ids
    return body


def _agent_matches(current: dict[str, object], desired: dict[str, object]) -> bool:
    if _text(current.get("system_prompt")) != _text(desired.get("system_prompt")):
        return False
    if _text(current.get("task_prompt")) != _text(desired.get("task_prompt")):
        return False
    if current.get("description") != desired.get("description"):
        return False
    if current.get("is_public") is not desired.get("is_public"):
        return False
    if "users" in desired and _user_id_set(current.get("users")) != _user_id_set(
        desired.get("users")
    ):
        return False
    if current.get("is_featured") is not desired.get("is_featured"):
        return False
    if current.get("display_priority") != desired.get("display_priority"):
        return False
    if current.get("datetime_aware") is not desired.get("datetime_aware"):
        return False
    if current.get("replace_base_system_prompt") is not desired.get(
        "replace_base_system_prompt"
    ):
        return False
    if _row_ids(current.get("document_sets")) != set(
        as_int(item, "document set id")
        for item in as_list(desired.get("document_set_ids"), "document_set_ids")
    ):
        return False
    if _row_ids(current.get("tools")) != set(
        as_int(item, "tool id") for item in as_list(desired.get("tool_ids"), "tool_ids")
    ):
        return False
    if _row_ids(current.get("labels")) != set(
        as_int(item, "label id")
        for item in as_list(desired.get("label_ids"), "label_ids")
    ):
        return False
    if _starters(current.get("starter_messages")) != _starters(
        desired.get("starter_messages")
    ):
        return False
    wanted_model = desired.get("default_model_configuration_id")
    if isinstance(wanted_model, int) and current.get("default_model_configuration_id") != wanted_model:
        return False
    return True


def _document_set_body(
    set_id: int | None,
    name: str,
    description: str,
    cc_pair_ids: list[int],
    is_public: bool,
) -> dict[str, object]:
    body: dict[str, object] = {
        "name": name,
        "description": description,
        "cc_pair_ids": cc_pair_ids,
        "is_public": is_public,
        "users": [],
        "groups": [],
        "federated_connectors": [],
    }
    if set_id is not None:
        body["id"] = set_id
    return body


def _ids_for_names(
    names: tuple[str, ...], pairs_by_name: dict[str, list[int]]
) -> tuple[list[int], bool]:
    ids: list[int] = []
    complete = True
    for name in names:
        found = pairs_by_name.get(name, [])
        if not found:
            complete = False
            continue
        ids.extend(found)
    return ids, complete


def _credentials_for_viewer(
    credentials: list[object], email: str
) -> list[dict[str, object]]:
    owned: list[dict[str, object]] = []
    for item in credentials:
        credential = as_dict(item, "credential")
        source = str(credential.get("source") or "")
        owner = credential.get("user_email")
        if source == "notion" and isinstance(owner, str) and owner.lower() == email.lower():
            owned.append(credential)
    return owned


def _missing_credential_message(emails: list[str]) -> str:
    lines = [
        "Informatics needs one Notion credential owned by each viewer.",
        "Use a new read-only Notion internal integration. Do not use RevOps | Dev.",
    ]
    for email in emails:
        lines.append(
            f"{email}: promote them to admin, have them POST /api/manage/credential "
            'as themselves with {"credential_json": {"notion_integration_token": "<token>"}, '
            '"admin_public": true, "source": "notion", "name": "Informatics"}, then demote them.'
        )
    lines.append("Re-run the bootstrap after those credentials exist.")
    return " ".join(lines)


def _pairs_for_connector(statuses: list[object], connector_id: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in statuses:
        status = as_dict(item, "connector status")
        connector = status.get("connector")
        if not isinstance(connector, dict):
            continue
        if connector.get("id") != connector_id:
            continue
        rows.append(status)
    return rows


def _pair_email(row: dict[str, object]) -> str:
    credential = row.get("credential")
    if not isinstance(credential, dict):
        return ""
    email = credential.get("user_email")
    return email.lower() if isinstance(email, str) else ""


def _user_ids(
    api: Api,
    emails: tuple[str, ...],
    require_secrets: bool,
    logs: list[str],
) -> list[str] | None:
    listing = as_list(
        api.request("GET", "/manage/users/accepted/all"), "users"
    )
    by_email: dict[str, str] = {}
    for item in listing:
        user = as_dict(item, "user")
        email = user.get("email")
        user_id = user.get("id")
        if isinstance(email, str) and user_id is not None:
            by_email[email.lower()] = str(user_id)
    missing = [email for email in emails if email.lower() not in by_email]
    if missing:
        message = (
            "These viewers have no Onyx user yet. They must sign in with Google first: "
            + ", ".join(missing)
        )
        if require_secrets:
            raise ConfigError(message)
        logs.append(message)
        return None
    return [by_email[email.lower()] for email in emails]


def _user_id_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    ids: set[str] = set()
    for item in value:
        if isinstance(item, str):
            ids.add(item)
        elif isinstance(item, dict) and item.get("id") is not None:
            ids.add(str(item["id"]))
    return ids


def _expect_excluded(calls: list[Call], page_id: str) -> None:
    for call in calls:
        if call.path != "/manage/admin/connector-with-credential" or call.body is None:
            continue
        connector = call.body.get("connector")
        if not isinstance(connector, dict):
            continue
        config = connector.get("connector_specific_config")
        if not isinstance(config, dict):
            continue
        excluded = config.get("excluded_page_ids")
        if isinstance(excluded, list) and page_id in excluded:
            return
    raise ConfigError("The Hub connector does not exclude the Informatics page")


def _model_rows(
    chat_model: str, chat_tokens: int, fast_model: str, fast_tokens: int
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for name, tokens, display in (
        (chat_model, chat_tokens, chat_model),
        (fast_model, fast_tokens, fast_model),
    ):
        if name in seen:
            continue
        seen.add(name)
        rows.append(
            {
                "name": name,
                "is_visible": True,
                "supports_chat": True,
                "supports_image_input": True,
                "max_input_tokens": tokens,
                "display_name": display,
            }
        )
    return rows


def _set_default_if_unset(
    api: Api,
    listing: dict[str, object],
    field: str,
    path: str,
    provider_id: int,
    model_name: str,
    enabled: bool,
    logs: list[str],
) -> None:
    if not enabled or listing.get(field) is not None:
        return
    api.request(
        "POST",
        path,
        {"provider_id": provider_id, "model_name": model_name},
    )
    logs.append(f"Set {field} to {model_name}")


def _find_named(
    items: list[object], name: str, what: str
) -> dict[str, object] | None:
    found: dict[str, object] | None = None
    for item in items:
        obj = as_dict(item, what)
        if obj.get("name") == name:
            if found is not None:
                raise ConfigError(f"More than one {what} is named {name}")
            found = obj
    return found


def _model_id(provider: dict[str, object], model_name: str) -> int | None:
    configs = provider.get("model_configurations")
    if not isinstance(configs, list):
        return None
    for item in configs:
        if not isinstance(item, dict):
            continue
        if item.get("name") == model_name and isinstance(item.get("id"), int):
            return item["id"]
    return None


def _summary_ids(document_set: dict[str, object]) -> set[int]:
    raw = document_set.get("cc_pair_summaries")
    if not isinstance(raw, list):
        return set()
    ids: set[int] = set()
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("id"), int):
            ids.add(item["id"])
    return ids


def _row_ids(value: object) -> set[int]:
    if not isinstance(value, list):
        return set()
    ids: set[int] = set()
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("id"), int):
            ids.add(item["id"])
    return ids


def _starters(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        return ()
    rows: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        message = item.get("message")
        if isinstance(name, str) and isinstance(message, str):
            rows.append((name, message.strip()))
    return tuple(rows)


def _text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _id_from_create(value: object, what: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return as_int(as_dict(value, what).get("id"), what)


def _env_or(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _timeout(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as error:
        raise ConfigError(f"{name} must be a number") from error


def _plan_bits(body: dict[str, object]) -> list[str]:
    bits: list[str] = []
    for key in ("name", "provider", "source", "prompt"):
        value = body.get(key)
        if isinstance(value, str):
            bits.append(f"{key}={value}")
    return bits


def render_plan(calls: list[Call]) -> str:
    lines: list[str] = []
    for call in calls:
        bits = [call.method, call.path]
        if call.query:
            bits.append(" ".join(f"{key}={value}" for key, value in call.query.items()))
        if call.body:
            bits.extend(_plan_bits(call.body))
            connector = call.body.get("connector")
            if isinstance(connector, dict):
                bits.extend(_plan_bits(connector))
        lines.append(" ".join(bits))
    return "\n".join(lines)


def _expect_path(calls: list[Call], method: str, path: str) -> None:
    if not _has_path(calls, method, path):
        raise ConfigError(f"Missing {method} {path}")


def _has_path(calls: list[Call], method: str, path: str) -> bool:
    return _count(calls, method, path) > 0


def _count(calls: list[Call], method: str, path: str) -> int:
    total = 0
    for call in calls:
        if call.method == method and (
            call.path == path or (path.endswith("/") and call.path.startswith(path))
        ):
            total += 1
    return total


def _expect_search_tool_only(calls: list[Call]) -> None:
    for call in calls:
        if call.method == "POST" and call.path == "/persona" and call.body:
            tool_ids = call.body.get("tool_ids")
            if tool_ids != [7]:
                raise ConfigError(f"Agent tools were {tool_ids}, expected [7]")


def _expect_secret_sent(calls: list[Call], openai_key: str, notion_token: str) -> None:
    saw_openai = False
    saw_notion = False
    for call in calls:
        if call.body is None:
            continue
        if call.body.get("api_key") == openai_key:
            saw_openai = True
        credential = call.body.get("credential_json")
        if isinstance(credential, dict) and credential.get("notion_integration_token") == notion_token:
            saw_notion = True
    if not saw_openai:
        raise ConfigError("The provider request did not include the OpenAI key")
    if not saw_notion:
        raise ConfigError("The connector request did not include the Notion token")


if __name__ == "__main__":
    raise SystemExit(main())
