"""Excluded Notion pages are skipped, and so are the pages under them."""

from pydantic import ValidationError

from onyx.connectors.notion.config import (
    EXCLUDED_PAGE_ID_FORMAT_ERROR,
    NotionConnectorConfig,
)
from onyx.connectors.notion.connector import (
    BlockReadOutput,
    NotionConnector,
    NotionPage,
)

_HUB = "1cd17a7f-1e33-4794-a832-05ef95ab2a60"
_INFORMATICS = "408233ce-1c17-81e4-a92f-e23cc8bb95fd"
_CHILD = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _page(page_id: str) -> NotionPage:
    return NotionPage(
        id=page_id,
        created_time="2026-01-01T00:00:00.000Z",
        last_edited_time="2026-01-01T00:00:00.000Z",
        in_trash=False,
        properties={"Name": {"type": "title", "title": [{"plain_text": page_id}]}},
        url=f"https://www.notion.so/{page_id.replace('-', '')}",
    )


def test_default_connector_excludes_nothing() -> None:
    assert NotionConnector().indexed_pages == set()


def test_config_stores_dashed_ids_and_rejects_other_text() -> None:
    config = NotionConnectorConfig(
        excluded_page_ids=[_INFORMATICS.upper(), "408233ce1c1781e4a92fe23cc8bb95fd"]
    )
    assert config.excluded_page_ids == [_INFORMATICS, _INFORMATICS]

    try:
        NotionConnectorConfig(excluded_page_ids=["not-a-page"])
    except ValidationError as error:
        assert EXCLUDED_PAGE_ID_FORMAT_ERROR in str(error)
    else:
        raise AssertionError("a non-id was accepted")


def test_excluded_page_and_its_subtree_are_not_crawled() -> None:
    connector = NotionConnector(
        root_page_id=_HUB,
        recursive_index_enabled=True,
        excluded_page_ids=[_INFORMATICS],
    )
    assert _INFORMATICS in connector.indexed_pages

    fetched: list[str] = []

    def fetch(page_id: str) -> NotionPage:
        fetched.append(page_id)
        return _page(page_id)

    def read_blocks(page_id: str, is_slim: bool = False) -> BlockReadOutput:
        del is_slim
        if page_id == _HUB:
            return BlockReadOutput(
                blocks=[],
                child_page_ids=[_INFORMATICS],
                hierarchy_nodes=[],
                has_content=True,
            )
        raise AssertionError(f"read blocks for {page_id}")

    connector._fetch_page = fetch  # type: ignore[method-assign]
    connector._read_blocks = read_blocks  # type: ignore[method-assign]

    list(connector._read_pages([_page(_HUB)]))

    assert _INFORMATICS not in fetched
    assert _CHILD not in fetched
