/* Screenshot a page after running some JS.  usage:
   node tools/shoot.js <file-url> <out.png> [waitMs] [jsExpression ...] */
const { spawn } = require('child_process');
const os = require('os'), path = require('path'), fs = require('fs');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const url = process.argv[2];
const out = process.argv[3];
const wait = +(process.argv[4] || 1500);
const scripts = process.argv.slice(5);
const port = 9600 + Math.floor(Math.random() * 200);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'fxshot-'));

const proc = spawn(EDGE, [
  '--headless=new', '--disable-gpu', '--allow-file-access-from-files', '--no-first-run',
  '--no-default-browser-check', '--hide-scrollbars', '--mute-audio',
  '--remote-debugging-port=' + port, '--user-data-dir=' + profile,
  '--window-size=1600,980', url
], { stdio: 'ignore' });

const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  let wsUrl;
  for (let i = 0; i < 60 && !wsUrl; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const p = list.find(t => t.type === 'page' && (t.url === url || t.url.startsWith('file:') || t.url.startsWith('http')));
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
    if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); }
  });
  await new Promise(r => ws.addEventListener('open', r));
  await send('Page.enable'); await send('Runtime.enable');
  // 显式导航：headless 有时会先握手一个 about:blank / edge:// 页面，别对着它求值
  await send('Page.navigate', { url });
  await sleep(1200);
  for (const s of scripts) {
    const code = s.startsWith('@') ? fs.readFileSync(s.slice(1), 'utf8') : s;
    const r = await send('Runtime.evaluate', { expression: code, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) console.log('JS EXC: ' + ((r.exceptionDetails.exception && r.exceptionDetails.exception.description) || r.exceptionDetails.text));
    else if (r.result && r.result.value !== undefined) console.log('JS => ' + JSON.stringify(r.result.value));
  }
  await sleep(wait);
  const shot = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(out, Buffer.from(shot.data, 'base64'));
  const errs = await send('Runtime.evaluate', { expression: 'JSON.stringify(window.__errs||[])', returnByValue: true });
  console.log('page errors: ' + ((errs.result && errs.result.value) || '[]'));
  console.log('wrote ' + out + ' ' + fs.statSync(out).size + 'B');
  ws.close(); proc.kill();
  await sleep(200);
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) { }
  process.exit(0);
})().catch(e => { console.error('ERR ' + e.message); try { proc.kill(); } catch (_) { } process.exit(1); });