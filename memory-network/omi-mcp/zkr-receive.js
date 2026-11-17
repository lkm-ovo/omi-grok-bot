// Minimal ZK Relay receiver (Node). Reads the agent link from stdin, reveals,
// decrypts, and writes the secret to omi-mcp-key.txt (0600) in this directory.
// Never prints the secret, key, or token — only status and byte counts.
const https = require('https');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const AAD = 'zk-relay/v1;envelope';
const OUT = path.join(__dirname, 'omi-mcp-key.txt');

function b64urlDecode(s) { return Buffer.from(s, 'base64url'); }

async function main() {
  const raw = await new Promise((resolve, reject) => {
    let d = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => { d += c; });
    process.stdin.on('end', () => resolve(d.trim()));
    process.stdin.on('error', reject);
  });
  let u;
  try { u = new URL(raw); } catch { console.error('invalid URL'); process.exit(2); }
  const m = /^\/a\/([A-Za-z0-9_-]+)$/.exec(u.pathname);
  if (!m) { console.error('invalid agent path'); process.exit(2); }
  const id = m[1];
  const frag = (u.hash.startsWith('#') ? u.hash.slice(1) : u.hash).split('.');
  if (frag.length !== 3 || frag[0] !== 'v1') { console.error('invalid fragment'); process.exit(2); }
  const key = b64urlDecode(frag[1]);
  const token = frag[2];
  if (key.length !== 32 || b64urlDecode(token).length !== 32) {
    console.error('invalid key/token length'); process.exit(2);
  }

  const result = await new Promise((resolve, reject) => {
    const req = https.request(
      `https://zkr.scalingforever.com/api/v1/secrets/${id}/reveal`,
      {
        method: 'POST',
        headers: {
          Authorization: 'zk-relay ' + token,
          Accept: 'application/vnd.zk-relay.encrypted+json',
          'zk-relay-receiver': '2',
        },
      },
      (res) => {
        let b = '';
        res.on('data', (c) => { b += c; });
        res.on('end', () => resolve({ status: res.statusCode, body: b }));
      }
    );
    req.on('error', reject);
    req.setTimeout(25000, () => req.destroy(new Error('request timed out')));
    req.end();
  });

  console.error('reveal HTTP status: ' + result.status);
  if (result.status !== 200) {
    console.error('reveal failed (404 = wrong token, 410 = gone/expired, 429 = rate limited)');
    process.exit(1);
  }
  let container;
  try { container = JSON.parse(result.body); } catch { console.error('bad container JSON'); process.exit(1); }
  if (container.v !== 1 || container.aad !== AAD) { console.error('bad container'); process.exit(1); }
  const nonce = b64urlDecode(container.nonce);
  const ct = b64urlDecode(container.ciphertext);
  if (nonce.length !== 12 || ct.length < 17) { console.error('bad nonce/ciphertext'); process.exit(1); }
  let plain;
  try {
    const decipher = crypto.createDecipheriv('aes-256-gcm', key, nonce);
    decipher.setAAD(Buffer.from(AAD, 'utf8'));
    decipher.setAuthTag(ct.slice(-16));
    plain = Buffer.concat([decipher.update(ct.slice(0, -16)), decipher.final()]);
  } catch (e) { console.error('decrypt failed: ' + e.message); process.exit(1); }
  let env;
  try { env = JSON.parse(plain.toString('utf8')); } catch { console.error('bad envelope JSON'); process.exit(1); }
  if (env.v !== 1 || !env.name || !env.mediaType || (env.kind !== 'text' && env.kind !== 'file')) {
    console.error('bad envelope'); process.exit(1);
  }
  const secret = b64urlDecode(env.data);
  fs.writeFileSync(OUT, secret, { mode: 0o600 });
  console.error(
    'saved: kind=' + env.kind + ', ' + secret.length + ' bytes, trailing newline: ' +
    (secret.length > 0 && secret[secret.length - 1] === 10)
  );
}

main().catch((e) => { console.error('error: ' + e.message); process.exit(1); });
