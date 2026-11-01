// Proxies GET, POST, and DELETE for /mcp and the two OAuth well-known paths.
// Every other path and method is 404 and does not call the origin.

export type AccessEnv = {
  ONYX_ORIGIN: string;
  CF_ACCESS_CLIENT_ID: string;
  CF_ACCESS_CLIENT_SECRET: string;
};

const ALLOWED_METHODS: ReadonlySet<string> = new Set(["GET", "POST", "DELETE"]);

// A traversal that stays under /.well-known/ must still not name these APIs.
const BLOCKED_SEGMENTS: ReadonlySet<string> = new Set([
  "api",
  "open-urls",
  "search-lite",
  "web-search",
]);

const FORWARDED_HEADERS: readonly string[] = [
  "authorization",
  "content-type",
  "accept",
  "mcp-session-id",
  "mcp-protocol-version",
  "last-event-id",
];

const WELL_KNOWN_ROOTS: readonly string[] = [
  "/.well-known/oauth-protected-resource",
  "/.well-known/oauth-authorization-server",
];

function notFound(): Response {
  return new Response("not found", {
    status: 404,
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}

function httpsOrigin(value: string): string | null {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (url.protocol !== "https:") {
    return null;
  }
  if (url.username !== "" || url.password !== "") {
    return null;
  }
  if (url.search !== "" || url.hash !== "") {
    return null;
  }
  if (url.pathname !== "/" && url.pathname !== "") {
    return null;
  }
  return url.origin;
}

function hasBlockedSegment(pathname: string): boolean {
  for (const segment of pathname.split("/")) {
    if (BLOCKED_SEGMENTS.has(segment.toLowerCase())) {
      return true;
    }
  }
  return false;
}

function isSafeSegment(segment: string): boolean {
  if (
    segment.length === 0 ||
    segment === "." ||
    segment === ".." ||
    segment.endsWith(".")
  ) {
    return false;
  }
  return /^[A-Za-z0-9._-]+$/.test(segment);
}

function isWellKnownPath(pathname: string): boolean {
  for (const root of WELL_KNOWN_ROOTS) {
    if (pathname === root) {
      return true;
    }
    const prefix = `${root}/`;
    if (!pathname.startsWith(prefix)) {
      continue;
    }
    return pathname.slice(prefix.length).split("/").every(isSafeSegment);
  }
  return false;
}

function isAllowedPath(pathname: string): boolean {
  if (
    pathname.includes("%") ||
    pathname.includes("\\") ||
    pathname.includes("//")
  ) {
    return false;
  }
  if (hasBlockedSegment(pathname)) {
    return false;
  }
  if (pathname === "/mcp") {
    return true;
  }
  return isWellKnownPath(pathname);
}

export async function handle(
  request: Request,
  env: AccessEnv,
  fetchImpl: typeof fetch,
): Promise<Response> {
  const origin = httpsOrigin(env.ONYX_ORIGIN);
  if (origin === null) {
    return notFound();
  }
  if (!ALLOWED_METHODS.has(request.method)) {
    return notFound();
  }

  const incoming = new URL(request.url);
  if (!isAllowedPath(incoming.pathname)) {
    return notFound();
  }

  const target = new URL(incoming.pathname + incoming.search, origin);
  if (target.origin !== origin || !isAllowedPath(target.pathname)) {
    return notFound();
  }

  const headers = new Headers();
  for (const name of FORWARDED_HEADERS) {
    const value = request.headers.get(name);
    if (value !== null) {
      headers.set(name, value);
    }
  }
  headers.set("CF-Access-Client-Id", env.CF_ACCESS_CLIENT_ID);
  headers.set("CF-Access-Client-Secret", env.CF_ACCESS_CLIENT_SECRET);

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
  };
  if (request.method === "POST" || request.method === "DELETE") {
    const bytes = new Uint8Array(await request.arrayBuffer());
    if (bytes.byteLength > 0) {
      init.body = bytes;
    }
  }

  return fetchImpl(target.toString(), init);
}

const worker = {
  fetch(request: Request, env: AccessEnv): Promise<Response> {
    return handle(request, env, fetch);
  },
};

export default worker;
