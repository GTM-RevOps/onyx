# Upstream files this fork changes

Two Community Edition files, so the public Notion crawl can skip a page and the pages under it.

| File | Change |
| --- | --- |
| `backend/onyx/connectors/notion/config.py` | Optional `excluded_page_ids`. Empty or omitted means no exclusions. Values are dashed page ids. A 32-character hex id is stored dashed. |
| `backend/onyx/connectors/notion/connector.py` | `__init__` seeds `indexed_pages` with those ids. The crawler already skips an id in that set before it reads child pages. |

The unit test is `backend/tests/unit/onyx/connectors/notion/test_notion_excluded_pages.py`.

No file under `backend/ee/` is imported or edited.

## Not registered

The Sybill connector is not registered. Onyx loads connectors from `CONNECTOR_CLASS_MAP` in `backend/onyx/connectors/registry.py`. A class outside that map does not run. Registration needs these upstream edits. Do not make them until a transcript sync is in scope.

| File | Change |
| --- | --- |
| `backend/onyx/configs/constants.py` | Add `DocumentSource.SYBILL` and a line in `DocumentSourceDescription`. |
| `backend/onyx/connectors/registry.py` | Map that source to `gtm.connectors.sybill`. |
| `backend/onyx/connectors/capability_checks/registry.py` | Add a credential check when you want Create to probe Sybill. |
| `web/src/lib/connectors/connectors.tsx` | Add the admin form fields. |
| `web/src/lib/credentials/constants.ts` | Add the `sybill_api_token` field. |

The API process imports connector modules from `backend/`. `gtm/` is not on that path. A later registration also needs a one-file shim under `backend/onyx/connectors/sybill/` that imports the class in `gtm/`, or the process path must include the repo root. That shim is a core edit. Leave it out.

Until then, push a transcript with `POST /api/onyx-api/ingestion`. See `gtm/connectors/README.md`.
