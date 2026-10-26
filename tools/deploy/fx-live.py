#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fx-live — 常驻的实时汇率中继。

每 INTERVAL 秒抓一次真实汇率（EUR 基准的 8 条腿：USD JPY GBP CHF AUD CAD NZD CNY），
写进 /var/www/ikuyo.xyz/fx/live.js，里面的 tape 是「当天已走过的真实分钟价」。

  * 不管有没有人打开页面，它都在跑（systemd 常驻 + Restart=always）
  * 每天一个 tape 文件 /var/lib/fx-live/YYYYMMDD.ndjson，重启不丢当天数据
  * 抓取失败不会写坏文件：保留上一份，客户端会显示「报价 N 分钟前」或「离线」
  * 13 个货币对由这 8 条腿按与 rates.js 完全相同的公式推导，三角一致性 0 偏差

额度约束（2026-10 实测，很重要）：
  上游 api.fxratesapi.com 不带 key 时是 x-ratelimit-limit: 61 —— 61 次/小时的滚动窗口，
  而且**被限流后的失败请求同样占额度**。所以
    1) 轮询间隔取 120 秒（30 次/小时，留一半余量）；
    2) 撞到 429 就按 retry-after + 指数退避**安静一段时间**，让窗口排空；
       绝不原地重试 —— 越重试越排不空，之前就是这样把自己锁死 4 小时的。
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

OUT = '/var/www/ikuyo.xyz/fx/live.js'
STORE = '/var/lib/fx-live'
LOG = '/var/log/fx-live.log'
INTERVAL = 120          # 30 次/小时，上游额度 61 次/小时
BACKOFF = [300, 600, 1200, 1800]   # 连续失败后的静默时长：5/10/20/30 分钟
LEGS = ['USD', 'JPY', 'GBP', 'CHF', 'AUD', 'CAD', 'NZD', 'CNY']
UA = 'fx-fighter-live/1.0 (+https://ikuyo.xyz/fx/)'

# 合理性区间：防止上游返回垃圾把图表打歪
RANGE = {
    'USD': (0.5, 2.5), 'JPY': (60, 400), 'GBP': (0.4, 2.0), 'CHF': (0.4, 2.0),
    'AUD': (0.8, 3.5), 'CAD': (0.8, 3.5), 'NZD': (1.0, 4.0), 'CNY': (4.0, 15.0),
}


def log(msg):
    line = '[%s] %s' % (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), msg)
    print(line, flush=True)


class RateLimited(Exception):
    def __init__(self, wait_s):
        Exception.__init__(self, 'rate limited, retry in %ds' % wait_s)
        self.wait_s = wait_s


def http_json(url, timeout=25):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited(parse_retry_after(e.headers))
        raise


def parse_retry_after(headers):
    """上游给的是毫秒时间戳（如 1793037370856），也兼容秒数和秒偏移。"""
    raw = (headers.get('retry-after') or '').strip()
    try:
        v = float(raw)
    except ValueError:
        return 60.0
    if v > 1e12:                      # 毫秒
        return max(5.0, v / 1000.0 - time.time())
    if v > 1e9:                       # 秒级时间戳
        return max(5.0, v - time.time())
    return max(5.0, v)                # 秒偏移


def fetch_fxratesapi():
    url = 'https://api.fxratesapi.com/latest?base=EUR&currencies=' + ','.join(LEGS) + '&places=6'
    d = http_json(url)
    if not d.get('success'):
        raise RuntimeError('bad payload: %s' % str(d)[:120])
    rates = d['rates']
    legs = {}
    for k in LEGS:
        if k not in rates:
            raise RuntimeError('missing leg ' + k)
        legs[k] = float(rates[k])
    ts = int(d.get('timestamp') or time.time())
    return legs, ts, 'fxratesapi.com (%ds)' % INTERVAL


def sane(legs):
    for k, (lo, hi) in RANGE.items():
        v = legs.get(k)
        if not (v and lo < v < hi):
            raise RuntimeError('leg %s out of range: %s' % (k, v))
    return True


def day_file(ts):
    d = datetime.datetime.fromtimestamp(ts, datetime.UTC).strftime('%Y%m%d')
    return os.path.join(STORE, d + '.ndjson')


def append_tick(ts, legs, quote_ts):
    os.makedirs(STORE, exist_ok=True)
    with open(day_file(ts), 'a') as f:
        f.write(json.dumps({'ts': ts, 'q': quote_ts, 'legs': legs}, separators=(',', ':')) + '\n')


def read_tape(ts, limit=1600):
    path = day_file(ts)
    rows = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    rows = rows[-limit:]
    tape = {k: [] for k in LEGS}
    for r in rows:
        for k in LEGS:
            v = r.get('legs', {}).get(k)
            if v:
                tape[k].append('%d:%s' % (r['ts'], format(v, '.6f').rstrip('0').rstrip('.')))
    return {k: ','.join(v) for k, v in tape.items() if len(v) >= 2}


def write_live(ts, quote_ts, legs, src):
    # 最近 3 个 UTC 日（含今天）的真实分钟价，客户端按天叠到各自的日内路径上
    days = []
    for back in (2, 1, 0):
        d = datetime.datetime.fromtimestamp(ts - back * 86400, datetime.UTC)
        day0 = int(d.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        tape = read_tape(day0)
        if tape:
            days.append({'d': day0, 'tape': tape})
    payload = {
        'src': src,
        'ts': ts,
        'quoteTs': quote_ts,
        'legs': {k: round(v, 6) for k, v in legs.items()},
        'days': days,
    }
    text = 'window.FX_LIVE=' + json.dumps(payload, separators=(',', ':')) + ';\n'
    fd, tmp = tempfile.mkstemp(dir='/tmp', prefix='live-', suffix='.js')
    with os.fdopen(fd, 'w') as f:
        f.write(text)
    subprocess.run(['install', '-o', 'www-data', '-g', 'www-data', '-m', '644', tmp, OUT], check=True)
    os.unlink(tmp)
    today = days[-1]['tape'] if days else {}
    return len(text), {k: len(v.split(',')) for k, v in today.items()}


def tick(last_good):
    """一次抓取。返回 (last_good, ok, err)；err 里带着要静默多久。"""
    ts = int(time.time())
    try:
        legs, quote_ts, src = fetch_fxratesapi()
        sane(legs)
    except RateLimited as e:
        return last_good, 0, e
    except Exception as e:
        return last_good, 0, e
    # 和上一条比，跳变超过 5% 就当成脏数据
    if last_good:
        for k in LEGS:
            prev = last_good.get(k)
            if prev and abs(legs[k] / prev - 1) > 0.05:
                log('reject jump on %s: %s -> %s' % (k, prev, legs[k]))
                return last_good, 0, RuntimeError('jump on %s' % k)
    append_tick(ts, legs, quote_ts)
    size, tape_info = write_live(ts, quote_ts, legs, src)
    log('ok EURUSD=%.5f USDJPY=%.3f  live.js=%dB  ticks=%s' % (
        legs['USD'], legs['JPY'] / legs['USD'], size,
        ','.join('%s:%d' % (k, v) for k, v in sorted(tape_info.items()))))
    return legs, 1, None


def main():
    os.makedirs(STORE, exist_ok=True)
    log('fx-live started, interval=%ds, out=%s' % (INTERVAL, OUT))
    last_good = None
    streak = 0
    while True:
        last_good, ok, err = tick(last_good)
        wait = INTERVAL
        if ok:
            if streak:
                log('recovered after %d failures' % streak)
            streak = 0
        else:
            streak += 1
            wait = BACKOFF[min(streak, len(BACKOFF)) - 1]
            extra = getattr(err, 'wait_s', 0) or 0
            if extra > wait:
                wait = min(int(extra) + 5, 1800)
            log('fetch failed (streak %d): %s  → 静默 %ds' % (streak, err, wait))
        # 对齐到 :05 秒，减少和上游整分钟窗口的撞车；但两次请求间隔绝不短于 wait
        now = time.time()
        nxt = (int(now / wait) + 1) * wait + 5
        time.sleep(max(wait, nxt - now))


if __name__ == '__main__':
    sys.exit(main())