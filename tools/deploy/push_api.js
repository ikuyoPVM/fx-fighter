#!/usr/bin/env node
/* Push one commit through the GitHub Git Data API.
   (this machine cannot reach github.com:443, but api.github.com works)
   node tools/deploy/push_api.js <owner/repo> <dir> "<message>" [--fresh] [--base-ref heads/main] */
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const args = process.argv.slice(2);
const flags = new Set(args.filter(a => a.startsWith('--')));
const pos = args.filter(a => !a.startsWith('--'));
const repo = pos[0], dir = pos[1], message = pos[2];
const baseRef = (args.find(a => a.startsWith('--base-ref=')) || '--base-ref=heads/main').split('=')[1];
const FRESH = flags.has('--fresh');

const token = execFileSync('gh', ['auth', 'token'], { encoding: 'utf8' }).trim();
const API = 'https://api.github.com';

async function api(method, p, body) {
  const res = await fetch(API + p, {
    method,
    headers: {
      Authorization: 'Bearer ' + token,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'fx-fighter-deploy',
      'Content-Type': 'application/json'
    },
    body: body ? JSON.stringify(body) : undefined
  });
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch (e) { }
  if (!res.ok) throw new Error(`${method} ${p} -> ${res.status}: ${text.slice(0, 300)}`);
  return json;
}

const git = (...a) => execFileSync('git', a, { cwd: dir, encoding: 'utf8' });

async function blobEntry(rel) {
  const full = path.join(dir, rel);
  if (!fs.existsSync(full)) return { path: rel.replace(/\\/g, '/'), mode: '100644', type: 'blob', sha: null };
  const b64 = fs.readFileSync(full).toString('base64');
  const blob = await api('POST', `/repos/${repo}/git/blobs`, { content: b64, encoding: 'base64' });
  return { path: rel.replace(/\\/g, '/'), mode: '100644', type: 'blob', sha: blob.sha };
}

(async () => {
  let entries = [];
  if (FRESH) {
    const files = git('ls-files').split('\n').filter(Boolean);
    if (!files.length) throw new Error('nothing staged (git add first)');
    // an empty repo has no tree/blob endpoints: seed it with the Contents API first
    let base = null;
    try {
      base = await api('GET', `/repos/${repo}/git/ref/${baseRef}`);
    } catch (e) {
      const seed = files.find(f => f.endsWith('.md')) || files[0];
      const b64 = fs.readFileSync(path.join(dir, seed)).toString('base64');
      await api('PUT', `/repos/${repo}/contents/${seed}`, { message, content: b64 });
      console.log('seeded ' + seed);
      base = await api('GET', `/repos/${repo}/git/ref/${baseRef}`);
    }
    const baseSha = base.object.sha;
    const baseCommit = await api('GET', `/repos/${repo}/git/commits/${baseSha}`);
    for (const f of files) {
      entries.push(await blobEntry(f));
      console.log('blob ' + f);
    }
    const tree = await api('POST', `/repos/${repo}/git/trees`, { base_tree: baseCommit.tree.sha, tree: entries });
    const commit = await api('POST', `/repos/${repo}/git/commits`, { message, tree: tree.sha, parents: [baseSha] });
    await api('PATCH', `/repos/${repo}/git/refs/${baseRef}`, { sha: commit.sha, force: false });
    console.log('created ' + commit.sha + '  files=' + files.length);
    return;
  }

  const base = await api('GET', `/repos/${repo}/git/ref/${baseRef}`);
  const baseSha = base.object.sha;
  const baseCommit = await api('GET', `/repos/${repo}/git/commits/${baseSha}`);
  const changed = git('diff', '--name-only', baseSha, 'HEAD').split('\n').filter(Boolean);
  if (!changed.length) { console.log('no diff, skip'); return; }
  for (const f of changed) {
    entries.push(await blobEntry(f));
    console.log('blob ' + f);
  }
  const tree = await api('POST', `/repos/${repo}/git/trees`, { base_tree: baseCommit.tree.sha, tree: entries });
  const commit = await api('POST', `/repos/${repo}/git/commits`, { message, tree: tree.sha, parents: [baseSha] });
  await api('PATCH', `/repos/${repo}/git/refs/${baseRef}`, { sha: commit.sha, force: false });
  console.log('pushed ' + commit.sha + '  files=' + changed.length);
})().catch(e => { console.error('FAIL ' + e.message); process.exit(1); });