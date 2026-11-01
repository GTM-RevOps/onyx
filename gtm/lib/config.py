"""Load gtm/config/gtm.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from gtm.lib.envfile import GTM_ROOT
from gtm.lib.parse import (
    ConfigError,
    as_bool,
    as_dict,
    as_int,
    as_list,
    as_str,
    require_key,
    str_list,
)

# Answer-and-draft. Search reads the brain. It does not write to another system.
ALLOWED_TOOL_CODES = frozenset({"SearchTool"})


@dataclass(frozen=True)
class TaskTemplate:
    name: str
    prompt: str


@dataclass(frozen=True)
class DocumentSetSpec:
    key: str
    name: str
    description: str
    cc_pair_names: tuple[str, ...]
    is_public: bool
    notion_sections: tuple[str, ...]


@dataclass(frozen=True)
class AgentSpec:
    key: str
    name: str
    description: str
    prompt_file: str
    document_set_keys: tuple[str, ...]
    tool_codes: tuple[str, ...]
    tasks: tuple[TaskTemplate, ...]
    featured: bool
    display_priority: int
    datetime_aware: bool
    replace_base_system_prompt: bool
    starter_message_limit: int
    task_prompt: str
    is_public: bool = True
    viewer_emails: tuple[str, ...] = ()


@dataclass(frozen=True)
class LlmSpec:
    provider_name: str
    provider: str
    api_key_env: str
    chat_model_env: str
    chat_model_default: str
    fast_model_env: str
    fast_model_default: str
    chat_max_input_tokens: int
    fast_max_input_tokens: int
    set_chat_default_if_unset: bool
    set_vision_default_if_unset: bool
    set_naming_default_if_unset: bool
    set_search_selection_default_if_unset: bool


@dataclass(frozen=True)
class NotionSpec:
    name: str
    source: str
    input_type: str
    access_type: str
    refresh_freq_seconds: int
    prune_freq_seconds: int
    recursive_index_enabled: bool
    token_env: str
    root_page_id_env: str
    credential_key: str
    root_page_id: str = ""
    excluded_page_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PrivateNotionSpec:
    name: str
    source: str
    input_type: str
    access_type: str
    refresh_freq_seconds: int
    prune_freq_seconds: int
    recursive_index_enabled: bool
    root_page_id: str
    viewers: tuple[str, ...]


@dataclass(frozen=True)
class GtmConfig:
    version: int
    llm: LlmSpec
    notion: NotionSpec
    informatics: PrivateNotionSpec
    document_sets: tuple[DocumentSetSpec, ...]
    agents: tuple[AgentSpec, ...]
    harness_prompt_file: str
    not_in_brain_phrase: str
    label: str
    task_prompt: str
    gtm_root: Path

    def read_text(self, relative: str) -> str:
        path = self.gtm_root / relative
        if not path.is_file():
            raise ConfigError(f"Missing {path}")
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise ConfigError(f"{path} is empty")
        return text

    def document_set(self, key: str) -> DocumentSetSpec:
        for spec in self.document_sets:
            if spec.key == key:
                return spec
        raise ConfigError(f"Unknown document set {key}")


def load_gtm_config(path: Path | None = None) -> GtmConfig:
    config_path = path or (GTM_ROOT / "config" / "gtm.yaml")
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    root = as_dict(loaded, str(config_path))
    version = as_int(require_key(root, "version", "config"), "version")
    if version != 1:
        raise ConfigError(f"Unsupported config version {version}")

    harness = as_dict(require_key(root, "harness", "config"), "harness")
    phrase = as_str(
        require_key(harness, "not_in_brain_phrase", "harness"),
        "not_in_brain_phrase",
    ).strip()
    task_prompt = as_str(
        require_key(harness, "task_prompt", "harness"), "task_prompt"
    ).strip()
    prompt_file = as_str(
        require_key(harness, "prompt_file", "harness"), "prompt_file"
    ).strip()

    notion, informatics = _notion_blocks(
        as_dict(require_key(root, "notion", "config"), "notion")
    )
    config = GtmConfig(
        version=version,
        llm=_llm(as_dict(require_key(root, "llm", "config"), "llm")),
        notion=notion,
        informatics=informatics,
        document_sets=_document_sets(
            as_list(require_key(root, "document_sets", "config"), "document_sets"),
            informatics_connector=informatics.name,
        ),
        agents=(),
        harness_prompt_file=prompt_file,
        not_in_brain_phrase=phrase,
        label=as_str(require_key(harness, "label", "harness"), "label").strip(),
        task_prompt=task_prompt,
        gtm_root=GTM_ROOT,
    )
    agents = _agents(
        as_list(require_key(root, "agents", "config"), "agents"),
        config,
    )
    config = GtmConfig(
        version=config.version,
        llm=config.llm,
        notion=config.notion,
        informatics=config.informatics,
        document_sets=config.document_sets,
        agents=agents,
        harness_prompt_file=config.harness_prompt_file,
        not_in_brain_phrase=config.not_in_brain_phrase,
        label=config.label,
        task_prompt=config.task_prompt,
        gtm_root=config.gtm_root,
    )
    _check_files(config)
    return config


def _llm(raw: dict[str, object]) -> LlmSpec:
    spec = LlmSpec(
        provider_name=as_str(require_key(raw, "provider_name", "llm"), "provider_name").strip(),
        provider=as_str(require_key(raw, "provider", "llm"), "provider").strip(),
        api_key_env=as_str(require_key(raw, "api_key_env", "llm"), "api_key_env").strip(),
        chat_model_env=as_str(
            require_key(raw, "chat_model_env", "llm"), "chat_model_env"
        ).strip(),
        chat_model_default=as_str(
            require_key(raw, "chat_model_default", "llm"), "chat_model_default"
        ).strip(),
        fast_model_env=as_str(
            require_key(raw, "fast_model_env", "llm"), "fast_model_env"
        ).strip(),
        fast_model_default=as_str(
            require_key(raw, "fast_model_default", "llm"), "fast_model_default"
        ).strip(),
        chat_max_input_tokens=as_int(
            require_key(raw, "chat_max_input_tokens", "llm"), "chat_max_input_tokens"
        ),
        fast_max_input_tokens=as_int(
            require_key(raw, "fast_max_input_tokens", "llm"), "fast_max_input_tokens"
        ),
        set_chat_default_if_unset=as_bool(
            require_key(raw, "set_chat_default_if_unset", "llm"),
            "set_chat_default_if_unset",
        ),
        set_vision_default_if_unset=as_bool(
            require_key(raw, "set_vision_default_if_unset", "llm"),
            "set_vision_default_if_unset",
        ),
        set_naming_default_if_unset=as_bool(
            require_key(raw, "set_naming_default_if_unset", "llm"),
            "set_naming_default_if_unset",
        ),
        set_search_selection_default_if_unset=as_bool(
            require_key(raw, "set_search_selection_default_if_unset", "llm"),
            "set_search_selection_default_if_unset",
        ),
    )
    if spec.provider != "openai":
        raise ConfigError("llm.provider must be openai for this shell")
    return spec


def _notion_blocks(raw: dict[str, object]) -> tuple[NotionSpec, PrivateNotionSpec]:
    hub = as_dict(require_key(raw, "hub", "notion"), "notion.hub")
    private = as_dict(require_key(raw, "informatics", "notion"), "notion.informatics")
    return _public_notion(hub), _private_notion(private)


def _public_notion(raw: dict[str, object]) -> NotionSpec:
    spec = NotionSpec(
        name=as_str(require_key(raw, "name", "notion"), "notion name").strip(),
        source=as_str(require_key(raw, "source", "notion"), "notion source").strip(),
        input_type=as_str(
            require_key(raw, "input_type", "notion"), "input_type"
        ).strip(),
        access_type=as_str(
            require_key(raw, "access_type", "notion"), "access_type"
        ).strip(),
        refresh_freq_seconds=as_int(
            require_key(raw, "refresh_freq_seconds", "notion"),
            "refresh_freq_seconds",
        ),
        prune_freq_seconds=as_int(
            require_key(raw, "prune_freq_seconds", "notion"),
            "prune_freq_seconds",
        ),
        recursive_index_enabled=as_bool(
            require_key(raw, "recursive_index_enabled", "notion"),
            "recursive_index_enabled",
        ),
        token_env=as_str(require_key(raw, "token_env", "notion"), "token_env").strip(),
        root_page_id_env=as_str(
            require_key(raw, "root_page_id_env", "notion"), "root_page_id_env"
        ).strip(),
        credential_key=as_str(
            require_key(raw, "credential_key", "notion"), "credential_key"
        ).strip(),
        root_page_id=as_str(
            require_key(raw, "root_page_id", "notion"), "root_page_id"
        ).strip(),
        excluded_page_ids=str_list(
            require_key(raw, "excluded_page_ids", "notion"), "excluded_page_ids"
        ),
    )
    if spec.source != "notion":
        raise ConfigError("notion.source must be notion")
    if spec.input_type not in {"poll", "load_state"}:
        raise ConfigError("notion.input_type must be poll or load_state")
    if spec.access_type != "public":
        raise ConfigError("notion.access_type must be public for the org-wide brain")
    if spec.credential_key != "notion_integration_token":
        raise ConfigError(
            "notion.credential_key must be notion_integration_token. "
            "That is the key NotionConnector.load_credentials reads."
        )
    return spec


def _private_notion(raw: dict[str, object]) -> PrivateNotionSpec:
    viewers = str_list(require_key(raw, "viewers", "informatics"), "viewers")
    if len(viewers) != len({email.lower() for email in viewers}):
        raise ConfigError("informatics.viewers has a duplicate email")
    spec = PrivateNotionSpec(
        name=as_str(require_key(raw, "name", "informatics"), "informatics name").strip(),
        source=as_str(require_key(raw, "source", "informatics"), "source").strip(),
        input_type=as_str(
            require_key(raw, "input_type", "informatics"), "input_type"
        ).strip(),
        access_type=as_str(
            require_key(raw, "access_type", "informatics"), "access_type"
        ).strip(),
        refresh_freq_seconds=as_int(
            require_key(raw, "refresh_freq_seconds", "informatics"),
            "refresh_freq_seconds",
        ),
        prune_freq_seconds=as_int(
            require_key(raw, "prune_freq_seconds", "informatics"),
            "prune_freq_seconds",
        ),
        recursive_index_enabled=as_bool(
            require_key(raw, "recursive_index_enabled", "informatics"),
            "recursive_index_enabled",
        ),
        root_page_id=as_str(
            require_key(raw, "root_page_id", "informatics"), "root_page_id"
        ).strip(),
        viewers=viewers,
    )
    if spec.source != "notion":
        raise ConfigError("informatics.source must be notion")
    if spec.access_type != "private":
        raise ConfigError("informatics.access_type must be private")
    if not spec.recursive_index_enabled:
        raise ConfigError("informatics.recursive_index_enabled must be true")
    return spec


def _document_sets(
    items: list[object], *, informatics_connector: str
) -> tuple[DocumentSetSpec, ...]:
    specs: list[DocumentSetSpec] = []
    keys: set[str] = set()
    names: set[str] = set()
    for item in items:
        raw = as_dict(item, "document set")
        key = as_str(require_key(raw, "key", "document set"), "document set key").strip()
        name = as_str(require_key(raw, "name", "document set"), "document set name").strip()
        if key in keys:
            raise ConfigError(f"Duplicate document set key {key}")
        if name in names:
            raise ConfigError(f"Duplicate document set name {name}")
        keys.add(key)
        names.add(name)
        cc_pair_names = str_list(
            require_key(raw, "cc_pair_names", name), "cc_pair_names"
        )
        is_public = as_bool(require_key(raw, "is_public", name), "is_public")
        if is_public and informatics_connector in cc_pair_names:
            raise ConfigError(
                f"{name} is public and lists {informatics_connector}. "
                "Informatics stays off every public document set."
            )
        specs.append(
            DocumentSetSpec(
                key=key,
                name=name,
                description=as_str(
                    require_key(raw, "description", name), "description"
                ).strip(),
                cc_pair_names=cc_pair_names,
                is_public=is_public,
                notion_sections=str_list(
                    require_key(raw, "notion_sections", name), "notion_sections"
                ),
            )
        )
    return tuple(specs)


def _agents(items: list[object], config: GtmConfig) -> tuple[AgentSpec, ...]:
    specs: list[AgentSpec] = []
    keys: set[str] = set()
    names: set[str] = set()
    task_names: set[str] = set()
    known_sets = {spec.key for spec in config.document_sets}
    for item in items:
        raw = as_dict(item, "agent")
        key = as_str(require_key(raw, "key", "agent"), "agent key").strip()
        name = as_str(require_key(raw, "name", "agent"), "agent name").strip()
        if key in keys:
            raise ConfigError(f"Duplicate agent key {key}")
        if name in names:
            raise ConfigError(f"Duplicate agent name {name}")
        keys.add(key)
        names.add(name)
        set_keys = str_list(
            require_key(raw, "document_set_keys", name), "document_set_keys"
        )
        missing = [set_key for set_key in set_keys if set_key not in known_sets]
        if missing:
            raise ConfigError(f"{name} references unknown document sets: {missing}")
        tool_codes = str_list(require_key(raw, "tool_codes", name), "tool_codes")
        refused = [code for code in tool_codes if code not in ALLOWED_TOOL_CODES]
        if refused:
            raise ConfigError(
                f"{name} requests {refused}. This shell allows SearchTool only."
            )
        tasks = _tasks(require_key(raw, "tasks", name), name, task_names)
        override = raw.get("task_prompt")
        task_prompt = (
            as_str(override, f"{name} task_prompt").strip()
            if override is not None
            else config.task_prompt
        )
        specs.append(
            AgentSpec(
                key=key,
                name=name,
                description=as_str(
                    require_key(raw, "description", name), "description"
                ).strip(),
                prompt_file=as_str(
                    require_key(raw, "prompt_file", name), "prompt_file"
                ).strip(),
                document_set_keys=set_keys,
                tool_codes=tool_codes,
                tasks=tasks,
                featured=as_bool(require_key(raw, "featured", name), "featured"),
                display_priority=as_int(
                    require_key(raw, "display_priority", name), "display_priority"
                ),
                datetime_aware=as_bool(
                    require_key(raw, "datetime_aware", name), "datetime_aware"
                ),
                replace_base_system_prompt=as_bool(
                    require_key(raw, "replace_base_system_prompt", name),
                    "replace_base_system_prompt",
                ),
                starter_message_limit=as_int(
                    require_key(raw, "starter_message_limit", name),
                    "starter_message_limit",
                ),
                task_prompt=task_prompt,
                is_public=as_bool(raw["public"], "public") if "public" in raw else True,
                viewer_emails=str_list(raw["viewer_emails"], "viewer_emails")
                if "viewer_emails" in raw
                else (),
            )
        )
    for spec in specs:
        if not spec.is_public and not spec.viewer_emails:
            raise ConfigError(f"{spec.name} is private and has no viewer_emails")
    return tuple(specs)


def _tasks(
    value: object, agent_name: str, seen: set[str]
) -> tuple[TaskTemplate, ...]:
    tasks: list[TaskTemplate] = []
    for item in as_list(value, f"{agent_name} tasks"):
        raw = as_dict(item, f"{agent_name} task")
        name = as_str(require_key(raw, "name", "task"), "task name").strip()
        if name in seen:
            raise ConfigError(f"Duplicate task name {name}")
        seen.add(name)
        tasks.append(
            TaskTemplate(
                name=name,
                prompt=as_str(require_key(raw, "prompt", name), "task prompt").strip(),
            )
        )
    if not tasks:
        raise ConfigError(f"{agent_name} has no tasks")
    return tuple(tasks)


def _check_files(config: GtmConfig) -> None:
    harness = config.read_text(config.harness_prompt_file)
    if config.not_in_brain_phrase not in harness:
        raise ConfigError("The harness prompt does not contain not_in_brain_phrase")
    menu = config.read_text("specs/task-menu.md")
    space = config.read_text("specs/notion-space.md")
    for spec in config.document_sets:
        for section in spec.notion_sections:
            if section not in space:
                raise ConfigError(f"specs/notion-space.md does not name {section}")
    for agent in config.agents:
        config.read_text(agent.prompt_file)
        for task in agent.tasks:
            if task.name not in menu:
                raise ConfigError(f"specs/task-menu.md does not name {task.name}")
