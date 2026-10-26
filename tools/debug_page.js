#!/usr/bin/env node
/* Open a page, capture console / log / failed-request events, print them.
   node tools/debug_page.js <url> [waitMs] */
const { spawn } = require('child_process');
const os = require('os'), path = require('path'), fs = require('fs');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const url = process.argv[2];
const wait = +(process.argv[3] || 5000);
const port = 9800 + Math.floor(Math.random() * 150);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'fxdbg-'));
const proc = spawn(EDGE, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=' + port, '--user-data-dir=' + profile, '--window-size=1400,900', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  let wsUrl;
  for (let i = 0; i < 60 && !wsUrl; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const p = list.find(t => t.type === 'page');
      if (p) wsUrl = p.webSocketDebuggerUrl;
    } catch (e) { }
    if (!wsUrl) await sleep(250);
  }
  if (!wsUrl) throw new Error('no target');
  const ws = new WebSocket(wsUrl);
  let id = 0; const pend = new Map();
  const send = (m, p) => new Promise((res, rej) => { const i = ++id; pend.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method: m, params: p || {} })); });
  ws.addEventListener('message', ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); return; }
    if (m.method === 'Log.entryAdded') console.log('[log] ' + m.params.entry.level + ' ' + m.params.entry.text + (m.params.entry.url ? ' @' + m.params.entry.url : ''));
    if (m.method === 'Runtime.consoleAPICalled') console.log('[console] ' + m.params.type + ' ' + m.params.args.map(a => a.value !== undefined ? a.value : a.description).join(' '));
    if (m.method === 'Runtime.exceptionThrown') console.log('[exception] ' + (m.params.exceptionDetails.exception && m.params.exceptionDetails.exception.description || m.params.exceptionDetails.text));
    if (m.method === 'Network.loadingFailed') console.log('[netfail] ' + m.params.errorText + ' ' + (m.params.type || ''));
    if (m.method === 'Network.responseReceived') {
      const r = m.params.response;
      if (/rates\.js|engine\.js|ui\.js|index\.html/.test(r.url)) console.log('[net] ' + r.status + ' ' + r.url + ' ' + (r.headers['content-type'] || ''));
    }
  });
  await new Promise(r => ws.addEventListener('open', r));
  await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable'); await send('Network.enable');
  await send('Page.navigate', { url });
  await sleep(wait);
  const st = await send('Runtime.evaluate', {
    expression: `[location.href, document.title, typeof window.FX_REAL_DATA, (window.__errs||[]).length, document.querySelectorAll('#symList .symrow').length, document.getElementById('statusLeft').textContent].join(' | ')`,
    returnByValue: true
  });
  console.log('[state] ' + (st.result && st.result.value));
  const shotArg = process.argv.find(a => a.startsWith('--shot='));
  if (shotArg) {
    const out = shotArg.split('=')[1];
    const img = await send('Page.captureScreenshot', { format: 'png' });
    require('fs').writeFileSync(out, Buffer.from(img.data, 'base64'));
    console.log('[shot] ' + out);
  }
  ws.close(); proc.kill();
  await sleep(200);
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) { }
  process.exit(0);
})().catch(e => { console.error('ERR ' + e.message); try { proc.kill(); } catch (_) { } process.exit(1); });