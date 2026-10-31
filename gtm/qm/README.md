# qm deployment stub

This folder is a starter for a **separate** qm deployment. It is not a running qm, and it does not contain qm source.

Read `INTEGRATION.md` before you copy anything.

`layer/` follows the deployment directory in qm `docs/deploy-directory.md` only as far as this shell needs:

- `qm.config.jsonc` is a contract v1 stub. `qm check` was not run on it.
- `sandbox/skills/gtm/` is a shared skill. `qm up` sends that tree to the deployment layer.
- `mcp/onyx-mcp-server.json` is the body of `PUT /v1/admin/mcp-servers/onyx`. That call is not a field of `qm.config.jsonc`.

Generate the real directory with `qm init` in its own repository. Copy the skill and the MCP file into that directory. Do not commit secret values.
