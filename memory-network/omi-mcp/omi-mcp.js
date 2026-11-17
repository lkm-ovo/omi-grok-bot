// Minimal Omi MCP client (Streamable HTTP) using curl for transport.
// The API key is read from ~/.config/omi/mcp-key and never printed or placed
// in process arguments; it only travels inside a 0600 curl config file that
// is deleted after each run.
// Usage:
//   node omi-mcp.js list
//   node omi-mcp.js call <tool-name> '<json-args>'
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const ENDPOINT = 'https://api.omi.me/v1/mcp';
const KEY_FILE = path.join(os.homedir(), '.config', 'omi', 'mcp-key');
const WORKDIR = path.join(os.homedir(), 'workspace', '.omi-private');

function readKey() {
  const k = fs.readFileSync(KEY_FILE, 'utf8').trim();
  if (!k.startsWith('omi_mcp_')) throw new Error('stored key does not start with omi_mcp_');
  return k;
}

// One curl POST of a JSON-RPC payload. Returns { status, headers, bodyText }.
// sessionId is sent when provided; a new Mcp-Session-Id in the response is returned.
function postRpc(payload, sessionId) {
  const key = readKey();
  const stamp = Date.now() + '-' + Math.random().toString(36).slice(2, 8);
  const cfg = path.join(WORKDIR, `.curl-cfg-${stamp}`);
  const reqBody = path.join(WORKDIR, `.curl-req-${stamp}.json`);
  const resBody = path.join(WORKDIR, `.curl-res-${stamp}`);
  const resHead = path.join(WORKDIR, `.curl-head-${stamp}`);
  try {
    const headers = [
      'header = "Authorization: Bearer ' + key + '"',
      'header = "Content-Type: application/json"',
      'header = "Accept: application/json, text/event-stream"',
    ];
    if (sessionId) headers.push('header = "Mcp-Session-Id: ' + sessionId + '"');
    fs.writeFileSync(cfg, headers.join('\n') + '\n', { mode: 0o600 });
    fs.writeFileSync(reqBody, JSON.stringify(payload), { mode: 0o600 });
    let stdout = '';
    try {
      stdout = execFileSync(
        'curl',
        ['-s', '-K', cfg, '-X', 'POST', '--data-binary', '@' + reqBody, '-D', resHead, '-o', resBody, ENDPOINT],
        { encoding: 'utf8', timeout: 60000 }
      );
    } catch (e) {
      // curl writes the HTTP code to stdout via -w only when asked; here a non-zero
      // exit usually means network failure. Surface stderr if present.
      throw new Error('curl transport failed: ' + (e.stderr || e.message));
    }
    const headText = fs.existsSync(resHead) ? fs.readFileSync(resHead, 'utf8') : '';
    const bodyText = fs.existsSync(resBody) ? fs.readFileSync(resBody, 'utf8') : '';
    const statusMatch = headText.match(/^HTTP\/\S+ (\d+)/m);
    const status = statusMatch ? parseInt(statusMatch[1], 10) : 0;
    const sidMatch = headText.match(/^mcp-session-id:\s*(.+)$/im);
    return { status, headers: headText, bodyText, sessionId: sidMatch ? sidMatch[1].trim() : null };
  } finally {
    for (const f of [cfg, reqBody, resBody, resHead]) { try { fs.unlinkSync(f); } catch {} }
  }
}

// Parse a Streamable HTTP response body: plain JSON, or SSE (data: {...} lines).
function parseRpcBody(bodyText) {
  const trimmed = bodyText.trim();
  if (!trimmed) throw new Error('empty MCP response body');
  if (trimmed.startsWith('{')) return JSON.parse(trimmed);
  // SSE: collect data: lines, use the last complete JSON-RPC message.
  const datas = [];
  for (const line of trimmed.split('\n')) {
    const t = line.trim();
    if (t.startsWith('data:')) datas.push(t.slice(5).trim());
  }
  if (!datas.length) throw new Error('unrecognized MCP response: ' + trimmed.slice(0, 200));
  return JSON.parse(datas[datas.length - 1]);
}

async function main() {
  const cmd = process.argv[2];
  if (!cmd || (cmd !== 'list' && cmd !== 'call')) {
    console.error('usage: node omi-mcp.js list | call <tool> [json-args]');
    process.exit(2);
  }
  // 1. initialize
  let r = postRpc({
    jsonrpc: '2.0', id: 1, method: 'initialize',
    params: {
      protocolVersion: '2025-03-26', capabilities: {},
      clientInfo: { name: 'muse-omi', version: '1.0.0' },
    },
  });
  if (r.status === 401) { console.error('MCP auth failed (401). Key is wrong or revoked.'); process.exit(1); }
  if (r.status !== 200) { console.error('initialize HTTP ' + r.status + ': ' + r.bodyText.slice(0, 300)); process.exit(1); }
  const init = parseRpcBody(r.bodyText);
  if (init.error) { console.error('initialize error: ' + JSON.stringify(init.error)); process.exit(1); }
  const sessionId = r.sessionId || init.result?._meta?.sessionId;
  console.error('connected: server=' + (init.result?.serverInfo?.name || '?') + ' ' + (init.result?.serverInfo?.version || '') + ' protocol=' + (init.result?.protocolVersion || '?'));
  // 2. initialized notification (no response expected)
  try {
    postRpc({ jsonrpc: '2.0', method: 'notifications/initialized' }, sessionId);
  } catch {}
  if (cmd === 'list') {
    const lr = postRpc({ jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} }, sessionId);
    const msg = parseRpcBody(lr.bodyText);
    if (msg.error) { console.error('tools/list error: ' + JSON.stringify(msg.error)); process.exit(1); }
    const tools = msg.result?.tools || [];
    console.log(JSON.stringify(tools.map((t) => ({ name: t.name, description: (t.description || '').slice(0, 160) })), null, 2));
    return;
  }
  // call
  const tool = process.argv[3];
  let args = {};
  if (process.argv[4]) { try { args = JSON.parse(process.argv[4]); } catch { console.error('bad json args'); process.exit(2); } }
  const cr = postRpc({ jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: tool, arguments: args } }, sessionId);
  const msg = parseRpcBody(cr.bodyText);
  if (msg.error) { console.error('tools/call error: ' + JSON.stringify(msg.error)); process.exit(1); }
  console.log(JSON.stringify(msg.result, null, 2));
}

main().catch((e) => { console.error('error: ' + e.message); process.exit(1); });
