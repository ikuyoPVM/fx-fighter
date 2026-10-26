#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sync /var/www/ikuyo.xyz to the latest ikuyoPVM/ikuyo.xyz main.

The server cannot reach github.com:443, but api.github.com works, so the tree is
walked through the Git Data API:
  - every tracked blob is compared by git blob sha (sha1("blob <len>\\0" + data))
  - only files that differ (or are missing) are downloaded and replaced
  - files that exist on the server but not in the repo are only *reported* (the
    live site has production edits that never went back to GitHub)
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

REPO = 'ikuyoPVM/ikuyo.xyz'
BRANCH = 'main'
ROOT = '/var/www/ikuyo.xyz'
TOKEN_FILE = '/etc/fx-refresh/token'


def token():
    return open(TOKEN_FILE).read().strip()


def api(path, raw=False):
    req = urllib.request.Request('https://api.github.com' + path, headers={
        'Authorization': 'Bearer ' + token(),
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'ikuyo-sync',
    })
    data = urllib.request.urlopen(req, timeout=90).read()
    return data if raw else json.loads(data.decode())


def blob_sha(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def main():
    head = api('/repos/%s/git/ref/heads/%s' % (REPO, BRANCH))
    commit_sha = head['object']['sha']
    commit = api('/repos/%s/git/commits/%s' % (REPO, commit_sha))
    tree = api('/repos/%s/git/trees/%s?recursive=1' % (REPO, commit['tree']['sha']))
    if tree.get('truncated'):
        print('!! tree truncated, aborting')
        return 2
    blobs = [t for t in tree['tree'] if t['type'] == 'blob']
    print('remote main = %s  "%s"' % (commit_sha[:8], commit['message'].splitlines()[0]))
    print('tracked files = %d' % len(blobs))

    updated, added, same, failed = [], [], 0, []
    for b in blobs:
        rel = b['path']
        dst = os.path.join(ROOT, rel)
        remote_sha = b['sha']
        if os.path.exists(dst):
            with open(dst, 'rb') as f:
                local = f.read()
            if blob_sha(local) == remote_sha:
                same += 1
                continue
            kind = updated
        else:
            kind = added
        try:
            raw = api('/repos/%s/git/blobs/%s' % (REPO, remote_sha))
            data = base64.b64decode(raw['content'])
            if blob_sha(data) != remote_sha:
                raise RuntimeError('sha mismatch after download')
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dst))
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
            os.chmod(tmp, 0o755 if b.get('mode') == '100755' else 0o644)
            os.replace(tmp, dst)
            subprocess.run(['chown', 'www-data:www-data', dst], check=False)
            kind.append((rel, len(data)))
        except Exception as e:
            failed.append((rel, str(e)))

    print('\nunchanged: %d' % same)
    if updated:
        print('updated: %d' % len(updated))
        for rel, size in updated:
            print('  M %-28s %6d B' % (rel, size))
    if added:
        print('added: %d' % len(added))
        for rel, size in added:
            print('  A %-28s %6d B' % (rel, size))
    if failed:
        print('FAILED: %d' % len(failed))
        for rel, err in failed:
            print('  ! %s  %s' % (rel, err))

    tracked = set(b['path'] for b in blobs)
    local_only = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d != '.git']
        for f in files:
            rel = os.path.relpath(os.path.join(base, f), ROOT).replace(os.sep, '/')
            if rel not in tracked:
                local_only.append(rel)
    if local_only:
        print('\n只在服务器上、仓库里没有的文件（保留未动）: %d' % len(local_only))
        for rel in sorted(local_only)[:40]:
            print('  ? ' + rel)
        if len(local_only) > 40:
            print('  ... 还有 %d 个' % (len(local_only) - 40))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())