#!/usr/bin/env node
// A draft-only bridge. Native BrightBean owns editing, scheduling and publishing.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';

const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
const assert = (ok, message) => { if (!ok) throw new Error(message); };
function save(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const tmp = `${file}.${process.pid}.tmp`;
  const fd = fs.openSync(tmp, 'w', 0o600);
  try { fs.writeFileSync(fd, JSON.stringify(value, null, 2) + '\n'); fs.fsyncSync(fd); }
  finally { fs.closeSync(fd); }
  fs.renameSync(tmp, file);
}

export function prepare(manifestPath, speaker) {
  const manifest = read(manifestPath);
  assert(manifest.status === 'ready' && /^\d{4}-\d{2}-\d{2}$/.test(manifest.date), 'Expected a ready weekly delivery manifest.');
  assert(speaker && manifest.posts?.length, 'Speaker and posts are required.');
  const seen = new Set();
  const posts = manifest.posts.map(post => {
    assert(Number.isInteger(post.pick) && !seen.has(post.pick), 'Post picks must be distinct integers.');
    seen.add(post.pick);
    const text = fs.readFileSync(post.text);
    const image = fs.readFileSync(post.image);
    assert(sha(text) === post.textSha256 && sha(image) === post.imageSha256, `Source files changed for pick ${post.pick}; regenerate the delivery manifest.`);
    assert(image.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex')), 'Expected a PNG cartoon.');
    const caption = text.toString('utf8');
    assert(caption.trim() && [...caption].length <= 3000, `Pick ${post.pick} exceeds LinkedIn's caption limit or is empty.`);
    return {
      sourceId: `weekly:${manifest.date}:${post.pick}`,
      speaker, title: post.title, caption, image: path.resolve(post.image),
      textSha256: post.textSha256, imageSha256: post.imageSha256,
      altText: post.altText || post.title,
    };
  });
  return { version: 1, date: manifest.date, posts };
}

export async function importDrafts(bundle, { url, tokenFile, account, journal }) {
  const origin = new URL(url);
  assert(origin.protocol === 'https:' || (origin.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(origin.hostname)), 'Use HTTPS or loopback.');
  assert(!origin.username && !origin.password && origin.pathname === '/' && !origin.search && !origin.hash, 'Hub URL must be an origin.');
  assert(bundle.version === 1 && bundle.posts?.length && account, 'Invalid bundle or missing account.');
  const token = fs.readFileSync(tokenFile, 'utf8').trim();
  assert(token.startsWith('bb_studio_'), 'Expected a BrightBean API token file.');
  const request = async (route, options = {}) => {
    const response = await fetch(new URL(`/api/v1/${route}`, origin), {
      ...options, redirect: 'error', signal: AbortSignal.timeout(60000),
      headers: { Authorization: `Bearer ${token}`, ...options.headers },
    });
    assert(response.ok, `BrightBean ${route}: HTTP ${response.status}. Journal retained; inspect before retrying.`);
    return response.json();
  };
  fs.mkdirSync(path.dirname(journal), { recursive: true, mode: 0o700 });
  const lock = `${journal}.lock`;
  const fd = fs.openSync(lock, 'wx', 0o600);
  fs.writeFileSync(fd, String(process.pid));
  try {
    const state = fs.existsSync(journal) ? read(journal) : { origin: origin.origin, account, posts: {} };
    assert(state.origin === origin.origin && state.account === account, 'Journal belongs to another hub/account.');
    const { accounts } = await request('accounts/');
    const target = accounts.find(a => a.id === account);
    assert(target && ['linkedin_personal', 'linkedin_company'].includes(target.platform), 'Account must be an allowlisted LinkedIn account.');
    const results = [];
    for (const post of bundle.posts) {
      const bytes = fs.readFileSync(post.image);
      assert(sha(bytes) === post.imageSha256 && sha(post.caption) === post.textSha256, `Bundle content changed: ${post.sourceId}`);
      const digest = sha(JSON.stringify(post));
      let entry = state.posts[post.sourceId];
      if (entry) assert(entry.digest === digest, `Already imported a different version of ${post.sourceId}; edit its existing hub draft instead of creating another.`);
      if (entry?.postId) {
        const existing = await request(`posts/${entry.postId}`);
        results.push({ sourceId: post.sourceId, id: existing.id, status: existing.status, reused: true });
        continue;
      }
      entry ??= state.posts[post.sourceId] = { digest, startedAt: Date.now() };
      const tokenHash = sha(token);
      assert(!entry.tokenHash || entry.tokenHash === tokenHash, 'Unresolved import used another API key; reconcile it before changing credentials.');
      entry.tokenHash = tokenHash;
      // Upstream expires replay records after 24h. Unknown outcomes older than
      // 23h require reconciliation, never a blind create with an expired key.
      assert(Date.now() - entry.startedAt < 23 * 3600000, 'Unresolved import is older than the replay window; reconcile it in the hub before continuing.');
      save(journal, state);
      const key = `cosimo-${sha(`${account}:${post.sourceId}`)}`;
      if (!entry.mediaId) {
        const form = new FormData();
        form.set('file', new Blob([bytes], { type: 'image/png' }), `${post.imageSha256}.png`);
        form.set('alt_text', post.altText);
        form.set('title', post.title);
        form.set('idempotency_key', `${key}-media`);
        const media = await request('media/', { method: 'POST', body: form });
        entry.mediaId = media.id;
        save(journal, state);
      }
      const body = {
        social_account_id: account, caption: post.caption, title: post.title,
        media_asset_ids: [entry.mediaId], action: 'draft', idempotency_key: key,
        internal_notes: JSON.stringify({ sourceId: post.sourceId, speaker: post.speaker, textSha256: post.textSha256, imageSha256: post.imageSha256 }),
      };
      const created = await request('posts/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      entry.postId = created.id;
      save(journal, state);
      const actual = await request(`posts/${created.id}`);
      assert(actual.status === 'draft' && actual.caption === post.caption, 'Draft readback did not match the handoff.');
      results.push({ sourceId: post.sourceId, id: actual.id, status: actual.status, reused: false });
    }
    return results;
  } finally { fs.closeSync(fd); fs.unlinkSync(lock); }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try {
    const [command, ...args] = process.argv.slice(2);
    const opts = Object.fromEntries(Array.from({ length: args.length / 2 }, (_, i) => [args[i * 2].replace(/^--/, ''), args[i * 2 + 1]]));
    if (command === 'prepare') {
      const bundle = prepare(opts.manifest, opts.speaker);
      save(opts.out, bundle);
      console.log(`Prepared ${bundle.posts.length} posts. No upload or scheduling performed.`);
    } else if (command === 'import') {
      console.log(JSON.stringify(await importDrafts(read(opts.bundle), { url: opts.url, tokenFile: opts['token-file'], account: opts.account, journal: opts.journal }), null, 2));
    } else throw new Error('Use prepare --manifest FILE --speaker NAME --out FILE, or import --bundle FILE --url ORIGIN --token-file FILE --account UUID --journal FILE');
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
