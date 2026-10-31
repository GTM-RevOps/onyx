# Upstream files this fork changes

No upstream Onyx file is modified.

New files are `gtm/` and `.env.gtm.example`. `gtm/.gitignore` ignores `gtm/.env` only.

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
