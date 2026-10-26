# -*- coding: utf-8 -*-
"""Fetch real ECB daily reference rates (via frankfurter.dev) and emit rates.js.

Data: ECB euro reference rates, daily business days. Real market data.
Every pair in the simulator is derived from these EUR-base quotes:
    EURUSD = 1 / (EUR base USD) ...
Actually frankfurter returns: 1 EUR = X QUOTE, so EURUSD = USD value directly,
USDJPY = JPY/USD, GBPUSD = USD/GBP, etc.
"""
import json, urllib.request, datetime, sys, os

START = "2022-01-03"
END = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
QUOTES = ["USD", "JPY", "GBP", "CHF", "AUD", "CAD", "NZD", "CNY"]

url = f"https://api.frankfurter.app/{START}..{END}?from=EUR&to={','.join(QUOTES)}"
req = urllib.request.Request(url, headers={"User-Agent": "fx-fighter/1.0"})
raw = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
rates = raw["rates"]
dates = sorted(rates.keys())
print("days:", len(dates), dates[0], "->", dates[-1], file=sys.stderr)

# forward-fill any missing quote on a given day (ECB occasionally omits one)
series = {q: [] for q in QUOTES}
last = {q: None for q in QUOTES}
for d in dates:
    row = rates[d]
    for q in QUOTES:
        v = row.get(q, last[q])
        if v is None:
            v = 1.0
        last[q] = v
        series[q].append(v)

def enc(vals):
    # x1e5 integer grid: exact for ECB's 5-significant-digit publication
    return ",".join(str(int(round(v * 100000))) for v in vals)

out = []
out.append("/* rates.js - REAL market data, generated %s" % datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
out.append("   Source: European Central Bank euro reference rates, daily business days,")
out.append("   fetched from api.frankfurter.dev (ECB mirror). 1 EUR = X QUOTE.")
out.append("   Values are stored as integers x1e5 so the file stays small and exact. */")
out.append("window.FX_REAL_DATA = {")
out.append('  src: "ECB euro reference rates (daily, business days)",')
out.append('  base: "EUR",')
out.append('  generated: "%s",' % datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
out.append('  dates: "%s",' % ",".join(d.replace("-", "") for d in dates))
out.append("  quotes: {")
for i, q in enumerate(QUOTES):
    sep = "," if i < len(QUOTES) - 1 else ""
    out.append('    %s: "%s"%s' % (q, enc(series[q]), sep))
out.append("  }")
out.append("};")

# 输出路径：默认仓库根的 rates.js，可传参覆盖（例如站点里的 fx/rates.js）
if len(sys.argv) > 1:
    dst = sys.argv[1]
else:
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rates.js")
open(dst, "w", encoding="utf-8").write("\n".join(out) + "\n")
print("wrote", dst, os.path.getsize(dst), "bytes", file=sys.stderr)
print(json.dumps({q: series[q][-1] for q in QUOTES}))