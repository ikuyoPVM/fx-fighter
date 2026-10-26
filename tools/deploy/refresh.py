#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refresh the ECB reference rates and publish them everywhere.

1. fetch ECB euro reference rates (via the frankfurter mirror)
2. rewrite the local rates.js on the nginx host (only if the data changed)
3. push the same rates.js to the GitHub repos through the Contents API

Run by cron on the server. Token lives in /etc/fx-refresh/token (root, 600).
Every step is best effort: a network hiccup never leaves a broken file behind.
"""
import base64
import datetime
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_RATES = '/var/www/ikuyo.xyz/fx/rates.js'
TOKEN_FILE = '/etc/fx-refresh/token'
TARGETS = [
    ('ikuyoPVM/fx-fighter', 'rates.js'),
    ('ikuyoPVM/ikuyo.xyz', 'fx/rates.js'),
]
API = 'https://api.github.com'
START = '2022-01-03'


def log(msg):
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print('[%s] %s' % (stamp, msg), flush=True)


def build():
    end = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    quotes = ['USD', 'JPY', 'GBP', 'CHF', 'AUD', 'CAD', 'NZD', 'CNY']
    url = 'https://api.frankfurter.app/%s..%s?from=EUR&to=%s' % (START, end, ','.join(quotes))
    req = urllib.request.Request(url, headers={'User-Agent': 'fx-fighter-refresh/1.0'})
    raw = json.loads(urllib.request.urlopen(req, timeout=90).read().decode())
    rates = raw['rates']
    dates = sorted(rates.keys())
    series = {q: [] for q in quotes}
    last = {q: None for q in quotes}
    for d in dates:
        row = rates[d]
        for q in quotes:
            v = row.get(q, last[q])
            if v is None:
                v = 1.0
            last[q] = v
            series[q].append(v)

    def enc(vals):
        return ','.join(str(int(round(v * 100000))) for v in vals)

    now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    out = [
        '/* rates.js - REAL market data, generated %s' % now,
        '   Source: European Central Bank euro reference rates, daily business days,',
        '   fetched from api.frankfurter.dev (ECB mirror). 1 EUR = X QUOTE.',
        '   Values are stored as integers x1e5 so the file stays small and exact. */',
        'window.FX_REAL_DATA = {',
        '  src: "ECB euro reference rates (daily, business days)",',
        '  base: "EUR",',
        '  generated: "%s",' % now,
        '  dates: "%s",' % ','.join(d.replace('-', '') for d in dates),
        '  quotes: {',
    ]
    for i, q in enumerate(quotes):
        sep = ',' if i < len(quotes) - 1 else ''
        out.append('    %s: "%s"%s' % (q, enc(series[q]), sep))
    out += ['  }', '};', '']
    return '\n'.join(out), dates[-1], len(dates)


def gh(method, path, body, token):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
        'User-Agent': 'fx-fighter-refresh',
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def publish(repo_path, remote_path, text, token, message):
    cur = gh('GET', '/repos/%s/contents/%s' % (repo_path, remote_path), None, token)
    sha = cur['sha'] if isinstance(cur, dict) else None
    body = {
        'message': message,
        'content': base64.b64encode(text.encode('utf-8')).decode('ascii'),
    }
    if sha:
        body['sha'] = sha
    res = gh('PUT', '/repos/%s/contents/%s' % (repo_path, remote_path), body, token)
    return res.get('commit', {}).get('sha', '?')[:8]


def norm(text):
    """drop the timestamp lines so 'did the data change' is a real comparison"""
    return '\n'.join(l for l in text.splitlines() if 'generated' not in l)


def main():
    try:
        text, last_date, days = build()
    except Exception as e:
        log('FETCH FAILED: %s' % e)
        return 1
    log('fetched %d business days, last=%s' % (days, last_date))

    changed = True
    if os.path.exists(LOCAL_RATES):
        with open(LOCAL_RATES, encoding='utf-8') as f:
            changed = norm(f.read()) != norm(text)
    if not changed:
        log('rates unchanged, nothing to do')
        return 0

    tmp = tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False, dir='/tmp')
    tmp.write(text)
    tmp.close()
    subprocess.run(['install', '-o', 'www-data', '-g', 'www-data', '-m', '644', tmp.name, LOCAL_RATES], check=True)
    os.unlink(tmp.name)
    log('wrote %s (%d bytes)' % (LOCAL_RATES, len(text)))

    if not (os.path.exists(TOKEN_FILE) or os.environ.get('GH_TOKEN')):
        log('no github token, skip publishing')
        return 0
    token = os.environ.get('GH_TOKEN')
    if not token:
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
    msg = 'chore: refresh ECB reference rates (%s)' % last_date
    for repo, path in TARGETS:
        try:
            sha = publish(repo, path, text, token, msg)
            log('pushed %s:%s -> %s' % (repo, path, sha))
        except urllib.error.HTTPError as e:
            log('push %s:%s failed: %s %s' % (repo, path, e.code, e.read()[:200]))
        except Exception as e:
            log('push %s:%s failed: %s' % (repo, path, e))
    return 0


if __name__ == '__main__':
    sys.exit(main())