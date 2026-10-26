/* node selftest for engine.js — run: node tools/selftest.js */
globalThis.window = globalThis;
require('../rates.js');
const FX = require('../engine.js');
const W = FX.buildWorld(window.FX_REAL_DATA);

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('  ok   ' + name + (extra !== undefined ? '  ' + extra : '')); }
  else { fail++; console.log('  FAIL ' + name + (extra !== undefined ? '  ' + extra : '')); }
}
function near(a, b, tol) { return Math.abs(a - b) <= tol; }

console.log('== world ==');
ok('days', W.n > 900, W.n + ' ' + W.dates[0] + '..' + W.dates[W.n - 1]);
ok('symbols', W.symbols.length === 13);
const eurusd = W.symbols.find(s => s.name === 'EURUSD');
const usdjpy = W.symbols.find(s => s.name === 'USDJPY');
ok('EURUSD last close realistic', eurusd.closes[W.n - 1] > 0.9 && eurusd.closes[W.n - 1] < 1.5, eurusd.closes[W.n - 1].toFixed(5));
ok('USDJPY last close realistic', usdjpy.closes[W.n - 1] > 90 && usdjpy.closes[W.n - 1] < 250, usdjpy.closes[W.n - 1].toFixed(3));
// cross consistency: GBPJPY = USDJPY / GBPUSD
const gbpjpy = W.symbols.find(s => s.name === 'GBPJPY');
const gbpusd = W.symbols.find(s => s.name === 'GBPUSD');
ok('GBPJPY = USDJPY * GBPUSD', near(gbpjpy.closes[W.n - 1], usdjpy.closes[W.n - 1] * gbpusd.closes[W.n - 1], 0.02),
  gbpjpy.closes[W.n - 1].toFixed(3) + ' vs ' + (usdjpy.closes[W.n - 1] * gbpusd.closes[W.n - 1]).toFixed(3));

console.log('== engine init ==');
const eng = new FX.Engine(W, { seed: 7, balance: 100000, leverage: 100 });
const st = eng.sym['EURUSD'];
ok('mid > 0', st.mid > 0, st.mid.toFixed(5));
ok('ask > bid', st.ask > st.bid, st.bid.toFixed(5) + ' / ' + st.ask.toFixed(5));
ok('spread in pips sane', st.spreadPips > 0.05 && st.spreadPips < 5, st.spreadPips.toFixed(2));
ok('account equity = balance', near(eng.equity(), 100000, 1e-6), eng.equity().toFixed(2));
ok('bars seeded', (st.bars['EURUSDM5'] || []).length > 100, (st.bars['EURUSDM5'] || []).length + ' M5 bars');
ok('D1 uses real closes', (st.bars['EURUSDD1'] || []).length > 100, (st.bars['EURUSDD1'] || []).length + ' D1 bars');
const lastD1 = (st.bars['EURUSDD1'] || []).slice(-1)[0];
ok('today D1 open == prev real close', lastD1 && near(lastD1.o, eurusd.closes[W.n - 2], 1e-9), lastD1 && lastD1.o.toFixed(5) + ' vs ' + eurusd.closes[W.n - 2].toFixed(5));

console.log('== pip / margin math ==');
ok('EURUSD pip value 1 lot = $10', near(eng.pipValueUSD('EURUSD', 1), 10, 0.001), eng.pipValueUSD('EURUSD', 1).toFixed(4));
ok('USDJPY pip value 1 lot = 1000/USDJPY', near(eng.pipValueUSD('USDJPY', 1), 1000 / eng.sym['USDJPY'].mid, 0.02),
  eng.pipValueUSD('USDJPY', 1).toFixed(4) + ' (expect ' + (1000 / eng.sym['USDJPY'].mid).toFixed(4) + ')');
const r = eng.order({ sym: 'EURUSD', side: 1, lots: 1, type: 'market' });
ok('market buy filled', r.ok, r.err);
ok('commission charged', near(eng.balance, 100000 - 3.5, 1e-6), eng.balance.toFixed(2));
const acc1 = eng.account();
ok('margin = notional/100', near(acc1.margin, 1 * 100000 * eng.usdPerBase('EURUSD') / 100, 0.5), acc1.margin.toFixed(2));
ok('slippage recorded', eng.diag.slipPips >= 0 && eng.diag.slipPips < 3, eng.diag.slipPips.toFixed(3) + ' pips');

console.log('== p/l symmetry ==');
const pos = eng.positions[0];
const pl0 = eng._posPL(pos, st.bid);
eng.step(60);
const moved = eng._priceAt('EURUSD', eng.clock) - eng._priceAt('EURUSD', W.startMs);
const pl1 = eng._posPL(eng.positions[0], eng.sym['EURUSD'].bid);
ok('p/l moves with price', Math.abs(pl1 - pl0) > 0 || Math.abs(moved) < 1e-9, 'pl ' + pl0.toFixed(2) + ' -> ' + pl1.toFixed(2));

console.log('== day-end anchoring to real close ==');
const eng2 = new FX.Engine(W, { seed: 11 });
const idx = eng2._dayIdx(eng2.clock);
const endMs = eng2._dayStartForIdx(idx) + 86400000 - 1000;
const pxEnd = eng2._priceAt('EURUSD', endMs);
ok('price at 23:59 pins to real close', near(pxEnd, eurusd.closes[idx], eurusd.closes[idx] * 2e-5),
  pxEnd.toFixed(5) + ' vs real ' + eurusd.closes[idx].toFixed(5));

console.log('== stop loss / take profit ==');
const eng3 = new FX.Engine(W, { seed: 3, balance: 100000, leverage: 100 });
const s3 = eng3.sym['EURUSD'];
const closeToBid = s3.bid - 0.0030;
const tpPx = s3.ask + 0.0030;
const r3 = eng3.order({ sym: 'EURUSD', side: 1, lots: 0.5, type: 'market', sl: +closeToBid.toFixed(5), tp: +tpPx.toFixed(5) });
ok('order with SL/TP accepted', r3.ok, r3.err);
for (let i = 0; i < 600; i++) eng3.step(60);
ok('SL or TP eventually fired or still open', eng3.history.length >= 1 || eng3.positions.length === 1,
  'history=' + eng3.history.length + ' open=' + eng3.positions.length);
if (eng3.history.length) {
  const h = eng3.history[0];
  ok('closed trade booked', h.lots > 0 && isFinite(h.net), h.sym + ' ' + h.pips.toFixed(1) + 'p net ' + h.net.toFixed(2));
}

console.log('== pending limit order ==');
const eng4 = new FX.Engine(W, { seed: 5, balance: 100000, leverage: 100 });
const s4 = eng4.sym['EURUSD'];
const limPx = +(s4.bid - 0.0020).toFixed(5);
const r4 = eng4.order({ sym: 'EURUSD', side: 1, lots: 0.2, type: 'limit', price: limPx });
ok('limit buy accepted', r4.ok, r4.err);
let filled = false;
for (let i = 0; i < 4000 && !filled; i++) { eng4.step(30); if (eng4.positions.length) filled = true; }
ok('limit buy either filled or still pending', filled || eng4.orders.length === 1, filled ? 'filled @' + eng4.positions[0].openPx : 'still pending');
if (filled) ok('limit fill price not worse than limit', eng4.positions[0].openPx <= limPx + 1e-9, eng4.positions[0].openPx + ' vs ' + limPx);

console.log('== leverage / stop out ==');
const eng5 = new FX.Engine(W, { seed: 9, balance: 1000, leverage: 500 });
const rr = eng5.order({ sym: 'EURUSD', side: 1, lots: 4, type: 'market' });
ok('big position accepted at 500x', rr.ok, rr.err);
let so = 0;
for (let i = 0; i < 6000; i++) { eng5.step(30); if (eng5.diag.stopOuts) { so = eng5.diag.stopOuts; break; } }
ok('stop out happened', so > 0, 'stopOuts=' + so + ' balance=' + eng5.balance.toFixed(2));

console.log('== swap / rollover ==');
const eng6 = new FX.Engine(W, { seed: 13, balance: 100000, leverage: 100 });
eng6.order({ sym: 'USDJPY', side: -1, lots: 1, type: 'market' }); // short USDJPY → earns USD rate, pays JPY
const balBefore = eng6.balance;
let rolled = 0;
for (let i = 0; i < 20000 && !rolled; i++) { eng6.step(60); if (eng6.diag.rollovers) rolled = eng6.diag.rollovers; }
ok('a rollover occurred', rolled > 0, 'rollovers=' + rolled + ' swaps=' + eng6.diag.swaps.toFixed(2) + ' balDelta=' + (eng6.balance - balBefore).toFixed(2));
ok('long/short swap signs differ', (function () {
  const e = new FX.Engine(W, { seed: 21 });
  const e2 = new FX.Engine(W, { seed: 21 });
  e.order({ sym: 'USDJPY', side: 1, lots: 1 });
  e2.order({ sym: 'USDJPY', side: -1, lots: 1 });
  for (let i = 0; i < 20000; i++) { e.step(60); e2.step(60); if (e.diag.rollovers) break; }
  return Math.sign(e.diag.swaps) !== Math.sign(e2.diag.swaps);
})());

console.log('== weekend close ==');
const eng7 = new FX.Engine(W, { seed: 17 });
let guard = 0;
while (eng7.marketOpen(eng7.clock) && guard++ < 20000) eng7.step(60);
ok('market closes on weekend', !eng7.marketOpen(eng7.clock), FX.isoUTC(eng7.clock) + ' dow=' + new Date(eng7.clock).getUTCDay());
const rj = eng7.order({ sym: 'EURUSD', side: 1, lots: 0.1 });
ok('orders rejected while closed', !rj.ok, rj.err);

console.log('== stats / csv ==');
const stats = eng3.stats();
ok('stats numeric', isFinite(stats.winRate) && (isFinite(stats.profitFactor) || stats.profitFactor === Infinity), 'trades=' + stats.trades + ' wr=' + stats.winRate.toFixed(1));
const csv = eng3.statementCSV();
ok('csv has header + rows', csv.split('\n').length === eng3.history.length + 1);
ok('save/restore roundtrip', (function () {
  const snap = eng3.serialize();
  const e = new FX.Engine(W, { seed: 1 });
  e.restore(snap);
  return near(e.balance, eng3.balance, 1e-6) && e.positions.length === eng3.positions.length && e.history.length === eng3.history.length;
})());

console.log('\n== determinism ==');
const a = new FX.Engine(W, { seed: 42 }), b = new FX.Engine(W, { seed: 42 });
for (let i = 0; i < 500; i++) { a.step(60); b.step(60); }
ok('same seed -> same price', near(a.sym['EURUSD'].mid, b.sym['EURUSD'].mid, 1e-12), a.sym['EURUSD'].mid.toFixed(6));

console.log('\n' + (fail === 0 ? 'ALL PASS' : fail + ' FAILURES') + '  (' + pass + ' passed)');
process.exit(fail === 0 ? 0 : 1);

