"""MCP web tools register only when indexed-search-only mode is off."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastmcp import FastMCP

from onyx.mcp_server.tools.search import (
    indexed_search_only_from_env,
    register_web_tools,
)

_BACKEND_DIR = Path(__file__).resolve().parents[4]


async def _tool_names(server: FastMCP) -> set[str]:
    return {tool.name for tool in await server.list_tools()}


def test_indexed_search_only_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_INDEXED_SEARCH_ONLY", raising=False)
    assert indexed_search_only_from_env() is False


def test_indexed_search_only_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_INDEXED_SEARCH_ONLY", "true")
    assert indexed_search_only_from_env() is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("TRUE", True),
        (" true ", True),
        ("1", False),
        ("yes", False),
    ],
)
def test_indexed_search_only_accepts_only_the_word_true(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    monkeypatch.setenv("MCP_INDEXED_SEARCH_ONLY", raw)
    assert indexed_search_only_from_env() is expected


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


def _tool_names_from_fresh_import(*, indexed_search_only: str | None) -> list[str]:
    """Import the real MCP server in a child so registration sees this env."""
    env = os.environ.copy()
    if indexed_search_only is None:
        env.pop("MCP_INDEXED_SEARCH_ONLY", None)
    else:
        env["MCP_INDEXED_SEARCH_ONLY"] = indexed_search_only
    # api.py creates mcp_server, then imports the tools module, which registers.
    code = (
        "import asyncio\n"
        "import json\n"
        "from onyx.mcp_server.api import mcp_server\n"
        "names = [tool.name for tool in asyncio.run(mcp_server.list_tools())]\n"
        "print(json.dumps(names))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    assert isinstance(loaded, list)
    return [str(name) for name in loaded]


def test_fresh_import_registers_only_indexed_search_when_env_is_true() -> None:
    assert _tool_names_from_fresh_import(indexed_search_only="true") == [
        "search_indexed_documents"
    ]


def test_fresh_import_registers_all_three_tools_when_env_is_unset() -> None:
    assert _tool_names_from_fresh_import(indexed_search_only=None) == [
        "search_indexed_documents",
        "search_web",
        "open_urls",
    ]
