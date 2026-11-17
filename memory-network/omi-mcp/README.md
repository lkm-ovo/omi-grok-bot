# Omi MCP — setup notes (2026-11-16)

## Key (secret store)
- Canonical: `~/.config/omi/mcp-key` (mode 0600, 40 bytes, starts with `omi_mcp_`).
- Also available as env var `OMI_MCP_API_KEY` (exported in `~/.bashrc`, reads the file — no value embedded anywhere).
- The one-time ZK Relay link lkm sent is CONSUMED. If the key is revoked, ask lkm for a fresh link.

## Client
- `omi-mcp.js` in this directory (Node, no deps; curl transport via the egress proxy).
- `node omi-mcp.js list` — list tools (13 tools on omi-mcp-server 1.0.0).
- `node omi-mcp.js call <tool> '<json-args>'` — read-only calls, e.g. `call get_memories '{"limit": 3}'`.
- Read-only by lkm's rule. Never create/change anything in Omi unless he explicitly asks.

## Why not the stock zkr CLI
- `zkr` v1.3.1 is installed at `~/.local/bin/zkr` (signature-verified).
- Its POSTs (reveal/create) get blocked in this VM: Cloudflare treats Go's and
  Python's default clients as bots (403 / non-200), while curl and Node pass.
  `zkr status` (GET) works fine.
- `zkr-receive.js` in this directory is a Node receiver implementing the same
  ZK Relay v1 protocol (reveal + AES-256-GCM decrypt, AAD `zk-relay/v1;envelope`).
  Decryption was validated against the official protocol test vector
  (`zk-relay-interoperability`). Reads the agent link from stdin; never prints
  the secret, key, or token.

## State (2026-11-16)
- Omi account is EMPTY (memories / conversations / daily summaries all 0).
  Pendant paired today; no conversations captured yet.
