"""Sybill call-transcript connector skeleton.

TODO: this connector is not registered and does not fetch transcripts.
Onyx will not call it. Registration steps are in gtm/connectors/README.md.

The class follows CheckpointedConnector and SlimConnector, the same pair the
indexing runner uses for a poll connector (input_type "poll"). Do not add
permission sync. This fork stays on Community Edition and does not import
backend/ee.
"""

from __future__ import annotations

from typing import Any, override

from onyx.connectors.exceptions import ConnectorValidationError
from onyx.connectors.interfaces import (
    CheckpointOutput,
    CheckpointedConnector,
    GenerateSlimDocumentOutput,
    SecondsSinceUnixEpoch,
    SlimConnector,
)
from onyx.connectors.models import ConnectorCheckpoint, ConnectorMissingCredentialError
from onyx.indexing.indexing_heartbeat import IndexingHeartbeatInterface

NOT_IMPLEMENTED = (
    "Sybill connector is not implemented. "
    "Push transcripts with POST /api/onyx-api/ingestion until it is registered."
)

# TODO: add DocumentSource.SYBILL = "sybill" before registration.
# Until then, do not yield Document objects from this class.
CREDENTIAL_KEY = "sybill_api_token"


class SybillCheckpoint(ConnectorCheckpoint):
    """Cursor for one indexing run. Onyx resets this after a successful run."""

    cursor: str | None = None


class SybillConnector(CheckpointedConnector[SybillCheckpoint], SlimConnector):
    """TODO: page Sybill calls and yield one document per transcript."""

    def __init__(
        self,
        batch_size: int = 10,
        workspace_id: str | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.workspace_id = (workspace_id or "").strip() or None
        self._api_token: str | None = None

    @override
    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        token = credentials.get(CREDENTIAL_KEY)
        if not isinstance(token, str) or not token.strip():
            raise ConnectorMissingCredentialError("Sybill")
        # TODO: confirm the credential key with Sybill before registration.
        self._api_token = token.strip()
        return None

    @override
    def validate_connector_settings(self) -> None:
        if not self._api_token:
            raise ConnectorValidationError("Sybill credentials are not loaded.")

    @override
    def load_from_checkpoint(
        self,
        start: SecondsSinceUnixEpoch,
        end: SecondsSinceUnixEpoch,
        checkpoint: SybillCheckpoint,
    ) -> CheckpointOutput[SybillCheckpoint]:
        # TODO: list calls updated between start and end, page with
        # checkpoint.cursor, and yield Document objects. Use TextSection for
        # the transcript. Set semantic_identifier to the call title.
        del start, end, checkpoint
        raise NotImplementedError(NOT_IMPLEMENTED)

    @override
    def build_dummy_checkpoint(self) -> SybillCheckpoint:
        return SybillCheckpoint(has_more=True, cursor=None)

    @override
    def validate_checkpoint_json(self, checkpoint_json: str) -> SybillCheckpoint:
        return SybillCheckpoint.model_validate_json(checkpoint_json)

    @override
    def retrieve_all_slim_docs(
        self,
        start: SecondsSinceUnixEpoch | None = None,
        end: SecondsSinceUnixEpoch | None = None,
        callback: IndexingHeartbeatInterface | None = None,
    ) -> GenerateSlimDocumentOutput:
        # TODO: list the same call ids that load_from_checkpoint would index,
        # so a later prune does not delete transcripts this connector still owns.
        del start, end, callback
        raise NotImplementedError(NOT_IMPLEMENTED)
