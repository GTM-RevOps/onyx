import assert from "node:assert/strict";
import { test } from "node:test";

import { handle, type AccessEnv } from "./index.ts";

const env: AccessEnv = {
  ONYX_ORIGIN: "https://onyx-staging.pushpress.com",
  CF_ACCESS_CLIENT_ID: "client-id",
  CF_ACCESS_CLIENT_SECRET: "client-secret",
};

const workerHost = "https://mcp-staging.pushpress.com";

function recordingFetch(): { fetchImpl: typeof fetch; calls: Request[] } {
  const calls: Request[] = [];
  const fetchImpl: typeof fetch = async (input, init) => {
    calls.push(new Request(input, init));
    return new Response("upstream", { status: 200 });
  };
  return { fetchImpl, calls };
}

function incoming(
  path: string,
  method: string,
  headers?: HeadersInit,
  body?: string,
): Request {
  return new Request(`${workerHost}${path}`, {
    method,
    headers,
    body,
  });
}

test("POST /mcp forwards with Access headers and Authorization", async () => {
  const { fetchImpl, calls } = recordingFetch();
  const response = await handle(
    incoming("/mcp", "POST", {
      authorization: "Bearer onyx_pat_test",
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
      "cf-access-client-id": "caller-supplied",
      "x-forwarded-for": "203.0.113.5",
    }, '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'),
    env,
    fetchImpl,
  );

  assert.equal(response.status, 200);
  assert.equal(await response.text(), "upstream");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://onyx-staging.pushpress.com/mcp");
  assert.equal(calls[0].method, "POST");
  assert.equal(calls[0].redirect, "manual");
  assert.equal(calls[0].headers.get("cf-access-client-id"), "client-id");
  assert.equal(calls[0].headers.get("cf-access-client-secret"), "client-secret");
  assert.equal(calls[0].headers.get("authorization"), "Bearer onyx_pat_test");
  assert.equal(calls[0].headers.get("content-type"), "application/json");
  assert.equal(
    calls[0].headers.get("accept"),
    "application/json, text/event-stream",
  );
  assert.equal(calls[0].headers.get("x-forwarded-for"), null);
  assert.equal(
    await calls[0].text(),
    '{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
  );
});

test("POST /api/manage/credential returns 404 and does not fetch", async () => {
  const { fetchImpl, calls } = recordingFetch();
  const response = await handle(
    incoming("/api/manage/credential", "POST", {
      authorization: "Bearer onyx_pat_test",
      "content-type": "application/json",
    }, "{}"),
    env,
    fetchImpl,
  );

  assert.equal(response.status, 404);
  assert.equal(await response.text(), "not found");
  assert.equal(calls.length, 0);
});

test("POST /mcp drops Cookie", async () => {
  const { fetchImpl, calls } = recordingFetch();
  await handle(
    incoming("/mcp", "POST", {
      cookie: "session=secret",
      authorization: "Bearer onyx_pat_test",
    }),
    env,
    fetchImpl,
  );

  assert.equal(calls.length, 1);
  assert.equal(calls[0].headers.get("cookie"), null);
  assert.equal(calls[0].headers.get("authorization"), "Bearer onyx_pat_test");
});

test("GET and DELETE /mcp forward the path and query", async () => {
  for (const method of ["GET", "DELETE"]) {
    const { fetchImpl, calls } = recordingFetch();
    const response = await handle(
      incoming("/mcp?session=abc", method, {
        authorization: "Bearer onyx_pat_test",
        accept: "application/json, text/event-stream",
      }),
      env,
      fetchImpl,
    );

    assert.equal(response.status, 200, method);
    assert.equal(calls.length, 1, method);
    assert.equal(
      calls[0].url,
      "https://onyx-staging.pushpress.com/mcp?session=abc",
      method,
    );
    assert.equal(calls[0].method, method);
    assert.equal(calls[0].headers.get("cf-access-client-id"), "client-id");
    assert.equal(calls[0].headers.get("cookie"), null);
  }
});

test("GET /.well-known/ forwards OAuth discovery and drops Cookie", async () => {
  const paths = [
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-protected-resource/mcp",
    "/.well-known/oauth-authorization-server",
  ];
  for (const path of paths) {
    const { fetchImpl, calls } = recordingFetch();
    const response = await handle(
      incoming(`${path}?issuer=1`, "GET", { cookie: "session=secret" }),
      env,
      fetchImpl,
    );

    assert.equal(response.status, 200, path);
    assert.equal(calls.length, 1, path);
    assert.equal(
      calls[0].url,
      `https://onyx-staging.pushpress.com${path}?issuer=1`,
      path,
    );
    assert.equal(calls[0].headers.get("cookie"), null, path);
    assert.equal(calls[0].headers.get("cf-access-client-secret"), "client-secret");
  }
});

test("rejects web search, API, traversal, and /mcp prefix tricks with no upstream call", async () => {
  const cases: Array<{ method: string; path: string }> = [
    { method: "POST", path: "/web-search/search-lite" },
    { method: "POST", path: "/web-search/open-urls" },
    { method: "GET", path: "/web-search/search-lite" },
    { method: "GET", path: "/web-search/open-urls" },
    { method: "POST", path: "/web-search/search-lite?q=sales" },
    { method: "POST", path: "/api/chat/send-chat-message" },
    { method: "GET", path: "/api/persona" },
    { method: "POST", path: "/api/" },
    { method: "GET", path: "/" },
    { method: "GET", path: "/admin" },
    { method: "POST", path: "/mcp/../web-search" },
    { method: "POST", path: "/mcp/../web-search/search-lite" },
    { method: "POST", path: "/mcp/../web-search/open-urls" },
    { method: "POST", path: "/mcp/../../api/manage/credential" },
    { method: "POST", path: "/mcp/..%2Fweb-search" },
    { method: "POST", path: "/mcp%2f..%2fweb-search/search-lite" },
    { method: "POST", path: "/%2e%2e/web-search/search-lite" },
    { method: "POST", path: "/.well-known/%2e%2e/web-search" },
    { method: "POST", path: "/.well-known/%2e%2e%2fweb-search" },
    { method: "POST", path: "/.well-known/oauth-protected-resource/../../web-search/search-lite" },
    { method: "POST", path: "/.well-known/oauth-protected-resource/%2e%2e/%2e%2e/web-search/open-urls" },
    { method: "POST", path: "/.well-known/web-search/search-lite" },
    { method: "GET", path: "/mcp%5c../web-search" },
    { method: "POST", path: "/mcpx" },
    { method: "POST", path: "/mcp/" },
    { method: "POST", path: "/mcp/extra" },
    { method: "GET", path: "/mcp/oauth/callback" },
    { method: "POST", path: "/MCP" },
    { method: "POST", path: "/mcp%00" },
    { method: "GET", path: "//mcp" },
    { method: "GET", path: "/.well-known" },
    { method: "PUT", path: "/mcp" },
    { method: "PATCH", path: "/mcp" },
    { method: "HEAD", path: "/mcp" },
    { method: "OPTIONS", path: "/mcp" },
    { method: "PUT", path: "/web-search/search-lite" },
  ];

  for (const { method, path } of cases) {
    const { fetchImpl, calls } = recordingFetch();
    const body = method === "GET" || method === "HEAD" ? undefined : "{}";
    const response = await handle(
      incoming(path, method, { authorization: "Bearer onyx_pat_test" }, body),
      env,
      fetchImpl,
    );
    const label = `${method} ${path}`;
    assert.equal(response.status, 404, label);
    assert.equal(await response.text(), "not found", label);
    assert.equal(calls.length, 0, label);
  }
});

test("a bad ONYX_ORIGIN does not fetch", async () => {
  const badOrigins = [
    "http://onyx-staging.pushpress.com",
    "https://onyx-staging.pushpress.com/mcp",
    "https://user:pass@onyx-staging.pushpress.com",
    "https://onyx-staging.pushpress.com?x=1",
    "not a url",
  ];
  for (const origin of badOrigins) {
    const { fetchImpl, calls } = recordingFetch();
    const response = await handle(
      incoming("/mcp", "POST", { authorization: "Bearer onyx_pat_test" }),
      { ...env, ONYX_ORIGIN: origin },
      fetchImpl,
    );
    assert.equal(response.status, 404, origin);
    assert.equal(await response.text(), "not found", origin);
    assert.equal(calls.length, 0, origin);
  }
});
