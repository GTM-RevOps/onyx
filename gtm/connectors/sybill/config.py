"""Typed config for a future Sybill transcript connector.

TODO: not registered. Onyx never loads this module. See gtm/connectors/README.md.
"""

from typing import Annotated

from onyx.connectors.connector_config import ConnectorConfig
from onyx.connectors.field_policy import FieldClass, FieldPolicy, ScopeInclude

# TODO: confirm the Sybill workspace field before registration. An empty value
# means every workspace the token can read.


class SybillConnectorConfig(ConnectorConfig):
    """Mirrors SybillConnector.__init__. Keep the field names identical."""

    batch_size: Annotated[int, FieldPolicy(FieldClass.COSMETIC)] = 10
    workspace_id: Annotated[
        str | None,
        FieldPolicy(FieldClass.SCOPE, scope=ScopeInclude(empty_means_all=True)),
    ] = None
