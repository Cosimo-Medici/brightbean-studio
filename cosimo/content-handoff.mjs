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

// Eliot, 20 November 2026: each approved post goes out on its own planned day at
// 12:15 p.m. America/New_York. Picks map in order to these weekday offsets from
// the Monday delivery date; --days overrides them (for example 1,2,4).
export const DEFAULT_DAY_OFFSETS = [1, 2, 3];
const ZONE = 'America/New_York';
export function newYorkInstant(date, hour = 12, minute = 15) {
  const [y, m, d] = date.split('-').map(Number);
  const wall = Date.UTC(y, m - 1, d, hour, minute);
  let guess = wall + 5 * 3600000;
  for (let i = 0; i < 3; i++) {
    const p = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: ZONE, hourCycle: 'h23',
      year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
      .formatToParts(new Date(guess)).map(x => [x.type, x.value]));
    guess += wall - Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute);
  }
  return new Date(guess).toISOString();
}
const addDays = (date, n) => new Date(Date.parse(`${date}T00:00:00Z`) + n * 86400000).toISOString().slice(0, 10);
// Content identity: text and image bytes plus the visible fields. Planning
// fields and local file paths do not make a different version of the post.
const contentDigest = post => sha(JSON.stringify({ sourceId: post.sourceId, speaker: post.speaker, title: post.title,
  textSha256: post.textSha256, imageSha256: post.imageSha256, altText: post.altText }));
const legacyDigest = ({ plannedDate, plannedAt, ...post }) => sha(JSON.stringify(post));

export function prepare(manifestPath, speaker, dayOffsets = DEFAULT_DAY_OFFSETS) {
  const manifest = read(manifestPath);
  assert(manifest.status === 'ready' && /^\d{4}-\d{2}-\d{2}$/.test(manifest.date), 'Expected a ready weekly delivery manifest.');
  assert(speaker && manifest.posts?.length, 'Speaker and posts are required.');
  assert(new Date(`${manifest.date}T12:00:00Z`).getUTCDay() === 1, 'Weekly delivery date must be the Monday of the publishing week.');
  assert(dayOffsets.length >= manifest.posts.length && new Set(dayOffsets).size === dayOffsets.length
    && dayOffsets.every(n => Number.isInteger(n) && n >= 0 && n <= 4), 'Each pick needs its own weekday offset (0 = Monday … 4 = Friday).');
  const seen = new Set();
  const order = [...manifest.posts].map(p => p.pick).sort((a, b) => a - b);
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
      plannedDate: addDays(manifest.date, dayOffsets[order.indexOf(post.pick)]),
      plannedAt: newYorkInstant(addDays(manifest.date, dayOffsets[order.indexOf(post.pick)])),
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
      const digest = contentDigest(post);
      let entry = state.posts[post.sourceId];
      const sameVersion = entry && [entry.digest, entry.contentDigest].some(d => d === digest || d === legacyDigest(post));
      if (entry && !sameVersion) {
        // Never overwrite or duplicate: native edits in the hub take precedence.
        results.push({ sourceId: post.sourceId, id: entry.postId || null, status: 'source_changed', reused: true,
          action: 'Edit the existing hub draft natively; no second draft was created.' });
        continue;
      }
      if (entry?.postId) {
        const existing = await request(`posts/${entry.postId}`);
        results.push({ sourceId: post.sourceId, id: existing.id, status: existing.status, reused: true,
          plannedAt: entry.plannedAt || post.plannedAt || null });
        continue;
      }
      entry ??= state.posts[post.sourceId] = { digest, contentDigest: digest, startedAt: Date.now() };
      if (post.plannedAt) Object.assign(entry, { plannedDate: post.plannedDate, plannedAt: post.plannedAt });
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
        internal_notes: JSON.stringify({ sourceId: post.sourceId, speaker: post.speaker, textSha256: post.textSha256, imageSha256: post.imageSha256,
          plannedAt: post.plannedAt || null }),
      };
      const created = await request('posts/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      entry.postId = created.id;
      save(journal, state);
      const actual = await request(`posts/${created.id}`);
      assert(actual.status === 'draft' && actual.caption === post.caption, 'Draft readback did not match the handoff.');
      results.push({ sourceId: post.sourceId, id: actual.id, status: actual.status, reused: false, plannedAt: post.plannedAt || null });
    }
    return results;
  } finally { fs.closeSync(fd); fs.unlinkSync(lock); }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try {
    const [command, ...args] = process.argv.slice(2);
    const opts = Object.fromEntries(Array.from({ length: args.length / 2 }, (_, i) => [args[i * 2].replace(/^--/, ''), args[i * 2 + 1]]));
    if (command === 'prepare') {
      const bundle = prepare(opts.manifest, opts.speaker, opts.days ? opts.days.split(',').map(Number) : DEFAULT_DAY_OFFSETS);
      save(opts.out, bundle);
      console.log(`Prepared ${bundle.posts.length} posts. Planned: ${bundle.posts.map(p => `${p.sourceId} ${p.plannedAt}`).join('; ')}. No upload or scheduling performed.`);
    } else if (command === 'import') {
      console.log(JSON.stringify(await importDrafts(read(opts.bundle), { url: opts.url, tokenFile: opts['token-file'], account: opts.account, journal: opts.journal }), null, 2));
    } else throw new Error('Use prepare --manifest FILE --speaker NAME --out FILE [--days 1,2,3], or import --bundle FILE --url ORIGIN --token-file FILE --account UUID --journal FILE');
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
