# Connectors

This folder holds PushPress connectors that Onyx does not load.

## Sybill transcripts

`sybill/connector.py` implements `CheckpointedConnector` and `SlimConnector`. Those are the interfaces in `backend/onyx/connectors/interfaces.py`. The indexing runner calls `load_from_checkpoint` for `input_type: poll`. `retrieve_all_slim_docs` is the list a prune uses.

The class raises `NotImplementedError`. A mistaken registration fails the index run instead of indexing an empty source.

Onyx builds a connector from `CONNECTOR_CLASS_MAP` in `backend/onyx/connectors/registry.py`. This class is not in that map. No upstream file is edited. The steps to register it later are in `gtm/UPSTREAM_CHANGES.md`.

Do not add permission sync. That path lives under `backend/ee`.

## Push a transcript without a connector

`POST /api/onyx-api/ingestion` indexes one document. The admin API key needs Manage Connectors. The body is `IngestionDocument` (`backend/onyx/server/onyx_api/models.py`):

```json
{
  "document": {
    "semantic_identifier": "Call with Acme 2026-10-01",
    "sections": [
      {
        "type": "text",
        "text": "Transcript text"
      }
    ],
    "metadata": {
      "account": "Acme",
      "source_kind": "sybill"
    }
  }
}
```

Onyx stores the document as source `ingestion_api`. Put the cc pair id in `cc_pair_id` when the transcript should join a document set. Omit it to use the default ingestion pair.

Attach that pair to a document set, then to the agent that should read the calls.
