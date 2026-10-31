# Onyx MCP registration

`onyx-mcp-server.json` is the body for:

```text
PUT /v1/admin/mcp-servers/onyx
```

The id `onyx` is the path, not a field in the body. qm stores MCP servers in its admin registry. They are not entries in `qm.config.jsonc`. Source: `docs/mcp-connectors.md` and `src/api/routes/admin/mcp-servers.ts` at qm commit `f357718`.

An admin session must send the request. An agent token is refused. This shell does not include a script for that call. The admin credential shape was not exercised here.

## Secret that is not in the file

`auth: "bearer"` requires `bearerToken` on the request. That token is only for tool discovery (`tools/list`). Calls use each person's own token. Read the discovery token from an env var at apply time. Do not write it into this file.

Use an Onyx personal access token with scope `read:search`, minted by a dedicated discovery user. Do not use an admin API key (`on_...`). An admin key would make catalog reads run as that admin.

## Per-user tokens

`credentialScope: "per-user"` needs `CONNECTOR_SECRET_KEY` in the qm secret set. That name is a required core secret in `cli/src/secrets.ts`. The rest of the computed secret catalog comes from `qm init`, not from this file.

Save each rep's Onyx token with qm's source-authenticated `POST /v1/connectors/token`. Fields named in `docs/mcp-connectors.md`: `host`, `principalId`, `accessToken`, optional `expiresAt`. Set `host` to the same value as `credentialHost`. This shell did not call that endpoint.

Replace `url` and `credentialHost` with the real Onyx origin. Per-user mode requires HTTPS. qm's connector doc says core refuses MCP URLs that resolve to loopback, link-local, private, or unspecified addresses. A private Onyx address may be rejected. That check was not re-run here.
