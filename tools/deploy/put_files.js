#!/usr/bin/env node
/* Update single files in a GitHub repo through the Contents API (no git needed).
   node put_files.js <owner/repo> <dir> <path> [path...]
   - file exists locally  -> create or update it
   - file missing locally -> delete it from the repo
   Every path gets its own commit (message can be passed with --message="..."). */
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const argv = process.argv.slice(2);
const message = (argv.find(a => a.startsWith('--message=')) || '--message=update').split('=')[1];
const pos = argv.filter(a => !a.startsWith('--'));
const [repo, dir, ...files] = pos;
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
  const txt = await res.text();
  if (!res.ok) throw new Error(`${method} ${p} -> ${res.status}: ${txt.slice(0, 200)}`);
  return txt ? JSON.parse(txt) : null;
}

async function currentSha(p) {
  try {
    const r = await api('GET', `/repos/${repo}/contents/${encodeURI(p)}`);
    return r && r.sha ? r.sha : null;
  } catch (e) {
    return null;
  }
}

(async () => {
  for (const f of files) {
    const rel = f.replace(/\\/g, '/');
    const sha = await currentSha(rel);
    const full = path.join(dir, rel);
    if (fs.existsSync(full)) {
      const content = fs.readFileSync(full).toString('base64');
      const body = { message, content };
      if (sha) body.sha = sha;
      const r = await api('PUT', `/repos/${repo}/contents/${rel}`, body);
      console.log('put ' + rel + ' -> ' + (r.commit && r.commit.sha.slice(0, 8)));
    } else if (sha) {
      const r = await api('DELETE', `/repos/${repo}/contents/${rel}`, { message, sha });
      console.log('del ' + rel + ' -> ' + (r.commit && r.commit.sha.slice(0, 8)));
    } else {
      console.log('skip ' + rel + ' (not in repo, not local)');
    }
  }
})().catch(e => { console.error('FAIL ' + e.message); process.exit(1); });