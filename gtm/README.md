# PushPress GTM shell

This fork is the org-wide AI for PushPress Sales Development, Account Executives, Customer Success, managers, and RevOps. It is a self-hosted Onyx Community Edition. People ask it questions and it drafts text. A human sends every message. It does not write to HubSpot or Outreach.

The Onyx application stays upstream. PushPress files live in `gtm/`. Monthly merges of `onyx-dot-app/onyx` stay small because this shell does not edit Onyx core.

`backend/ee` and the other Enterprise Edition code use a commercial license. Do not import them. Do not set a license key. Do not turn on Craft.

## Folder layout

```
.env.gtm.example          Example variables. No real keys.
gtm/README.md             This file.
gtm/UPSTREAM_CHANGES.md   Upstream files this fork changes (none).
gtm/.gitignore            Ignores gtm/.env.
gtm/specs/                Harness, role specs, task menu, Notion layout.
gtm/specs/prompts/        Text the bootstrap writes onto each agent.
gtm/config/gtm.yaml       Agents, document sets, Notion connector, OpenAI models.
gtm/config/bootstrap.py   Creates or updates those objects in Onyx.
gtm/connectors/           Sybill skeleton. Onyx does not load it.
gtm/evals/                Questions and the citation checker.
```

## What the shell creates

| Object | Name | Scope |
| --- | --- | --- |
| LLM provider | PushPress OpenAI | `gpt-4.1` chat, `gpt-4.1-mini` for naming and search selection |
| Connector | PushPress GTM Notion | Public Notion connector, poll every hour |
| Document sets | GTM All, GTM SDR, GTM AE, GTM CS, GTM Manager, GTM RevOps, GTM Competitive | Each set attaches that Notion connector |
| Agents | SDR Helper, AE Deal Prep, CS Helper, Manager, RevOps, Competitive Analyst | Public, featured, SearchTool only |
| Label | GTM | On every agent |
| Input prompts | One per task | Private to the admin who owns the API key |

Each agent also gets its first four tasks as starter messages. The whole company sees those.

Document sets filter by connector, not by Notion page. Every set currently includes the same connector. The page list in the agent prompt is the scope. After Notion indexes, you can attach hierarchy nodes on the agent. The bootstrap does not clear nodes you add later, because it omits `hierarchy_node_ids` on update.

`replace_base_system_prompt` is false. Onyx keeps its default system prompt, including citation format. The GTM harness is added as the agent instructions.

## Run locally with Docker Compose

Use the upstream Community Edition compose file. Do not put the OpenAI key in the compose `.env`. The bootstrap stores it through the admin API.

1. Copy the compose environment file.

```bash
cd deployment/docker_compose
cp env.template .env
docker compose up -d
```

2. Open `http://localhost:3000`. Register the first user. That user is the admin.
3. If the setup wizard asks for a provider, you can enter OpenAI there. Set `GTM_OPENAI_PROVIDER_NAME` in `gtm/.env` to the provider name the wizard saved. Leave it unset to create **PushPress OpenAI**.
4. In the admin UI, create an API key. The key starts with `on_`. Create it as the admin user.
5. Copy the example env file and fill it in.

```bash
cp .env.gtm.example gtm/.env
```

6. Create a Notion internal integration. Share the GTM space with it. Put the token in `NOTION_INTEGRATION_TOKEN`. Put the space URL or page id in `NOTION_ROOT_PAGE_ID` when you want the connector to stay inside that page.
7. Run the bootstrap.

```bash
python3 gtm/config/bootstrap.py
```

8. Wait until the Notion connector finishes its first index. Build the pages in `gtm/specs/notion-space.md`.
9. Open an agent and ask a question from `gtm/specs/task-menu.md`.

The web app proxies `/api` to the API. `ONYX_API_BASE` is `http://localhost:3000/api` for that path. Nginx in the compose stack strips the same prefix. Point `ONYX_API_BASE` at `http://localhost:8080` only when you call the API process directly.

The compose model server supplies embeddings. This shell sets the chat provider. It does not switch embeddings to OpenAI.

A second run updates the OpenAI key and the agent text. It does not rotate the Notion token. Delete the connector in the admin UI and run the bootstrap again when you need a new token. If a document set is still syncing, the script skips that set and tells you to re-run.

`--skip-notion` creates the provider, the sets, and the agents without a connector. A later run with the token attaches the connector. It does not wipe connectors already on a set when the token is missing.

## Check the scripts without Onyx

```bash
python3 gtm/config/bootstrap.py --self-check
python3 gtm/config/bootstrap.py --dry-run
python3 gtm/evals/run_evals.py --self-check
python3 gtm/evals/run_evals.py --dry-run
```

`--dry-run` and `--self-check` do not use the network. A live eval does:

```bash
python3 gtm/evals/run_evals.py
```

The eval calls `POST /api/chat/send-chat-message` with `stream: false`. It passes when `citation_info` is present and an expected source substring matches a citation id or a retrieved title, link, or blurb. A "not in the brain" case passes when the answer contains `This is not in the brain.` and `citation_info` is empty. Live evals create chat sessions. They fail until Notion has indexed the pages.

PyYAML must be installed. `python3` is enough when it is on the path. `uv run python` uses the Onyx environment.

## APIs this shell calls

The dev server and nginx expose these paths under `/api`. The API process serves them without that prefix.

| Step | Method and path | Source in this repo |
| --- | --- | --- |
| List and save the OpenAI provider | `GET` and `PUT /admin/llm/provider` | `backend/onyx/server/manage/llm/api.py` |
| Set chat, vision, naming, and search-selection defaults when unset | `POST /admin/llm/default`, `/default-vision`, `/default-chat-naming`, `/default-search-selection` | same file |
| List connectors | `GET /manage/admin/connector/status` | `backend/onyx/server/documents/connector.py` |
| Create the Notion connector and its token | `POST /manage/admin/connector-with-credential` | same file. Config keys are `root_page_id` and `recursive_index_enabled` (`backend/onyx/connectors/notion/config.py`). The credential key is `notion_integration_token`. |
| List, create, and update document sets | `GET /manage/document-set`, `POST` and `PATCH /manage/admin/document-set` | `backend/onyx/server/features/document_set/api.py` |
| List built-in tools and keep SearchTool | `GET /tool` | `backend/onyx/server/features/tool/api.py`. The code id is `SearchTool`. |
| List, create, and update agents | `GET /admin/persona`, `GET` and `PATCH /persona/{id}`, `POST /persona` | `backend/onyx/server/features/persona/api.py` |
| Label | `GET` and `POST /persona/labels` | same file |
| Task prompts for the API-key user | `GET`, `POST`, and `PATCH /input_prompt` | `backend/onyx/server/features/input_prompt/api.py`. Create stores them as private. |
| Eval answers | `POST /chat/send-chat-message` | `backend/onyx/server/query_and_chat/chat_backend.py` |

Auth is `Authorization: Bearer` plus the API key. The key belongs to the admin user.

Later writes to another system belong on an Onyx custom action or an MCP server. Do not add those tools to these agents until a human-approval design exists.

Transcripts can enter the index before Sybill is a connector. Use `POST /api/onyx-api/ingestion`. See `gtm/connectors/README.md`.

## Sync upstream

`origin` is this fork. Add upstream once:

```bash
git remote add upstream https://github.com/onyx-dot-app/onyx.git
```

Merge `upstream/main` into this fork's `main` once a month. Merge sooner when you start a change and upstream has moved.

```bash
git fetch upstream
git checkout main
git merge upstream/main
```

Conflict policy:

- Keep the upstream side for every file outside `gtm/` and `.env.gtm.example`.
- Keep the PushPress side for files inside `gtm/`.
- When an API this shell calls changes, update `gtm/config/bootstrap.py` or `gtm/evals/run_evals.py`. Do not change the Onyx route to protect the script.
- Do not resolve a conflict by editing `backend/ee` or by turning on an Enterprise feature.
- Do not commit `gtm/.env`, `OPENAI_API_KEY`, or `NOTION_INTEGRATION_TOKEN`.

`gtm/UPSTREAM_CHANGES.md` lists core files. It is empty of edits. Add a row there before you change an upstream file.

## What you do next

1. Start compose and create the admin API key.
2. Fill `gtm/.env`.
3. Run `python3 gtm/config/bootstrap.py`.
4. Share the Notion space with the integration and add the pages in `gtm/specs/notion-space.md`.
5. After the first index, run `python3 gtm/evals/run_evals.py` and read the citation report.
