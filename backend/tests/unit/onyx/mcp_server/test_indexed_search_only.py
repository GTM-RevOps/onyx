"""MCP web tools register only when indexed-search-only mode is off."""

import asyncio

import pytest
from fastmcp import FastMCP

from onyx.mcp_server.tools.search import (
    indexed_search_only_from_env,
    register_web_tools,
)


async def _tool_names(server: FastMCP) -> set[str]:
    return {tool.name for tool in await server.list_tools()}


def test_indexed_search_only_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_INDEXED_SEARCH_ONLY", raising=False)
    assert indexed_search_only_from_env() is False


def test_indexed_search_only_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_INDEXED_SEARCH_ONLY", "true")
    assert indexed_search_only_from_env() is True


def test_register_web_tools_skips_web_tools_when_indexed_only() -> None:
    server = FastMCP(name="gtm-indexed-only")
    register_web_tools(server, indexed_search_only=True)
    names = asyncio.run(_tool_names(server))
    assert "search_web" not in names
    assert "open_urls" not in names


def test_register_web_tools_registers_web_tools_by_default() -> None:
    server = FastMCP(name="gtm-default")
    register_web_tools(server, indexed_search_only=False)
    names = asyncio.run(_tool_names(server))
    assert "search_web" in names
    assert "open_urls" in names
