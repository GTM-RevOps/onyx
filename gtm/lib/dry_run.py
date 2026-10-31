"""In-memory Onyx API for --dry-run and --self-check. It does not use the network."""

from __future__ import annotations

from dataclasses import dataclass

from gtm.lib.parse import ConfigError, as_dict, as_int, as_list, as_str


@dataclass
class Call:
    method: str
    path: str
    body: dict[str, object] | None
    query: dict[str, str] | None


class RecordingApi:
    """Accept the bootstrap's real calls and remember what it created."""

    def __init__(self) -> None:
        self.calls: list[Call] = []
        self.provider: dict[str, object] | None = None
        self.defaults: dict[str, dict[str, object]] = {}
        self.connectors: list[dict[str, object]] = []
        self.document_sets: list[dict[str, object]] = []
        self.labels: list[dict[str, object]] = []
        self.personas: list[dict[str, object]] = []
        self.prompts: list[dict[str, object]] = []
        self._next_id = 1

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        query: dict[str, str] | None = None,
    ) -> object:
        self.calls.append(Call(method, path, body, query))
        if method == "GET" and path == "/admin/llm/provider":
            return self._provider_listing()
        if method == "PUT" and path == "/admin/llm/provider":
            return self._put_provider(body or {})
        if method == "POST" and path in {
            "/admin/llm/default",
            "/admin/llm/default-vision",
            "/admin/llm/default-chat-naming",
            "/admin/llm/default-search-selection",
        }:
            if body is None:
                raise ConfigError(f"{path} needs a body")
            self.defaults[path] = body
            return None
        if method == "GET" and path == "/manage/admin/connector/status":
            return self.connectors
        if method == "POST" and path == "/manage/admin/connector-with-credential":
            return self._create_connector(body or {})
        if method == "GET" and path == "/manage/document-set":
            return self.document_sets
        if method == "POST" and path == "/manage/admin/document-set":
            return self._create_document_set(body or {})
        if method == "PATCH" and path == "/manage/admin/document-set":
            self._patch_document_set(body or {})
            return None
        if method == "GET" and path == "/persona/labels":
            return self.labels
        if method == "POST" and path == "/persona/labels":
            label_id = self._alloc()
            label = {"id": label_id, "name": as_str((body or {}).get("name"), "label")}
            self.labels.append(label)
            return label
        if method == "GET" and path == "/tool":
            return [
                {
                    "id": 7,
                    "name": "SearchTool",
                    "in_code_tool_id": "SearchTool",
                }
            ]
        if method == "GET" and path == "/admin/persona":
            return [
                {
                    "id": persona["id"],
                    "name": persona["name"],
                    "builtin_persona": False,
                }
                for persona in self.personas
            ]
        if method == "GET" and path.startswith("/persona/"):
            return self._persona(as_int(int(path.rsplit("/", 1)[-1]), "persona id"))
        if method == "POST" and path == "/persona":
            return self._save_persona(None, body or {})
        if method == "PATCH" and path.startswith("/persona/"):
            persona_id = as_int(int(path.rsplit("/", 1)[-1]), "persona id")
            return self._save_persona(persona_id, body or {})
        if method == "GET" and path == "/input_prompt":
            return self.prompts
        if method == "POST" and path == "/input_prompt":
            prompt_id = self._alloc()
            prompt = {
                "id": prompt_id,
                "prompt": (body or {}).get("prompt"),
                "content": (body or {}).get("content"),
                "active": True,
                "is_public": False,
            }
            self.prompts.append(prompt)
            return prompt
        if method == "PATCH" and path.startswith("/input_prompt/"):
            prompt_id = as_int(int(path.rsplit("/", 1)[-1]), "prompt id")
            for prompt in self.prompts:
                if prompt["id"] == prompt_id:
                    prompt["prompt"] = (body or {}).get("prompt")
                    prompt["content"] = (body or {}).get("content")
                    return prompt
            raise ConfigError(f"Unknown input prompt {prompt_id}")
        raise ConfigError(f"Dry run has no handler for {method} {path}")

    def _alloc(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    def _provider_listing(self) -> dict[str, object]:
        providers: list[object] = []
        if self.provider is not None:
            providers.append(self.provider)
        return {
            "providers": providers,
            "default_text": self.defaults.get("/admin/llm/default"),
            "default_vision": self.defaults.get("/admin/llm/default-vision"),
            "default_chat_naming": self.defaults.get("/admin/llm/default-chat-naming"),
            "default_search_selection": self.defaults.get(
                "/admin/llm/default-search-selection"
            ),
        }

    def _put_provider(self, body: dict[str, object]) -> dict[str, object]:
        previous: dict[str, int] = {}
        if self.provider is not None:
            stored = self.provider.get("model_configurations")
            if isinstance(stored, list):
                for item in stored:
                    model = as_dict(item, "stored model")
                    model_id = model.get("id")
                    model_name = model.get("name")
                    if isinstance(model_id, int) and isinstance(model_name, str):
                        previous[model_name] = model_id
        models = as_list(body.get("model_configurations"), "model_configurations")
        configs: list[dict[str, object]] = []
        for item in models:
            model = as_dict(item, "model")
            name = as_str(model.get("name"), "model name")
            configs.append({"id": previous.get(name, self._alloc()), "name": name})
        provider_id = body.get("id")
        if not isinstance(provider_id, int):
            provider_id = self._alloc()
        self.provider = {
            "id": provider_id,
            "name": body.get("name"),
            "provider": body.get("provider"),
            "model_configurations": configs,
        }
        return self.provider

    def _create_connector(self, body: dict[str, object]) -> dict[str, object]:
        connector = as_dict(body.get("connector"), "connector")
        cc_pair_id = self._alloc()
        self.connectors.append(
            {
                "cc_pair_id": cc_pair_id,
                "name": connector.get("name"),
                "connector": {
                    "source": connector.get("source"),
                    "name": connector.get("name"),
                },
            }
        )
        return {"success": True, "data": cc_pair_id}

    def _create_document_set(self, body: dict[str, object]) -> int:
        set_id = self._alloc()
        self.document_sets.append(self._document_set_row(set_id, body))
        return set_id

    def _patch_document_set(self, body: dict[str, object]) -> None:
        set_id = as_int(body.get("id"), "document set id")
        for index, existing in enumerate(self.document_sets):
            if existing["id"] == set_id:
                self.document_sets[index] = self._document_set_row(set_id, body)
                return
        raise ConfigError(f"Unknown document set {set_id}")

    def _document_set_row(
        self, set_id: int, body: dict[str, object]
    ) -> dict[str, object]:
        cc_ids = as_list(body.get("cc_pair_ids"), "cc_pair_ids")
        return {
            "id": set_id,
            "name": body.get("name"),
            "description": body.get("description"),
            "is_public": body.get("is_public"),
            "is_up_to_date": True,
            "cc_pair_summaries": [
                {"id": as_int(cc_id, "cc pair id")} for cc_id in cc_ids
            ],
        }

    def _save_persona(
        self, persona_id: int | None, body: dict[str, object]
    ) -> dict[str, object]:
        if persona_id is None:
            persona_id = self._alloc()
            self.personas.append({"id": persona_id})
        for persona in self.personas:
            if persona["id"] == persona_id:
                persona.update(body)
                persona["id"] = persona_id
                persona["builtin_persona"] = False
                return {"id": persona_id, "name": persona.get("name")}
        raise ConfigError(f"Unknown persona {persona_id}")

    def _persona(self, persona_id: int) -> dict[str, object]:
        for persona in self.personas:
            if persona["id"] == persona_id:
                return {
                    **persona,
                    "document_sets": _id_rows(persona.get("document_set_ids")),
                    "tools": _id_rows(persona.get("tool_ids")),
                    "labels": _id_rows(persona.get("label_ids")),
                }
        raise ConfigError(f"Unknown persona {persona_id}")


def _id_rows(value: object) -> list[dict[str, int]]:
    if not isinstance(value, list):
        return []
    return [{"id": as_int(item, "id")} for item in value]
