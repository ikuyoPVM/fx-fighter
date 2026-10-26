# -*- coding: utf-8 -*-
"""在站点的 HTML 里插入 FX 模拟入口（导航 + 首页卡片），并补上样式。
幂等：重复执行不会重复插入。直接对线上文件跑，因此不会覆盖服务器上独有的内容。
用法: python3 patch_site.py /var/www/ikuyo.xyz
"""
import os, re, sys, glob

root = sys.argv[1] if len(sys.argv) > 1 else '.'
LABEL = {'zh': 'FX 模拟', 'en': 'FX Simulator', 'ja': 'FXシミュレーター'}

CARD = {
'zh': '''        <div class="fx-tuiguang">
            <div class="fx-tuiguang-wen">
                <span class="xinwen-biaoqian">新栏目</span>
                <h3><a href="fx/">FX FIGHTER · 真实外汇模拟终端</a></h3>
                <p>把「行情当天气看」的那套终端，换成了真外汇：13 个货币对、欧洲央行真实日线打底，点差 / 佣金 / 隔夜利息 / 强平一套券商规则齐全。10 万虚拟资金，点开就能下单，不涉及任何真实资金。</p>
            </div>
            <a class="fx-tuiguang-btn" href="fx/">进入交易终端 →</a>
        </div>
''',
'en': '''        <div class="fx-tuiguang">
            <div class="fx-tuiguang-wen">
                <span class="xinwen-biaoqian">New</span>
                <h3><a href="fx/">FX FIGHTER · Real Forex Simulator</a></h3>
                <p>The terminal that treated prices like weather, rebuilt for real currencies: 13 pairs on genuine ECB daily data, with spreads, commission, swaps and stop-outs. 100,000 virtual capital, no real money involved.</p>
            </div>
            <a class="fx-tuiguang-btn" href="fx/">Open the terminal →</a>
        </div>
''',
'ja': '''        <div class="fx-tuiguang">
            <div class="fx-tuiguang-wen">
                <span class="xinwen-biaoqian">新コーナー</span>
                <h3><a href="fx/">FX FIGHTER · リアル為替シミュレーター</a></h3>
                <p>「相場を天気のように見る」端末を、本物の為替に作り替えました。13 通貨ペア、ECB の実データ、スプレッド・手数料・スワップ・強制決済まで。仮想資金 10 万、実際のお金は使いません。</p>
            </div>
            <a class="fx-tuiguang-btn" href="fx/">端末を開く →</a>
        </div>
'''}

CSS = '''
/* ===== FX 模拟入口（新栏目） ===== */
nav a.fx-nav {
    color: #FFD54A !important;
    font-weight: 700;
}

nav a.fx-nav:hover {
    color: #fff !important;
}

.fx-tuiguang {
    clear: both;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 22px;
    width: 100%;
    margin: 0 0 22px;
    padding: 18px 20px;
    background: linear-gradient(115deg, #14161c 0%, #1d222c 55%, #14161c 100%);
    border-left: 5px solid #B80000;
    border-radius: 6px;
}

.fx-tuiguang-wen { flex: 1 1 auto; min-width: 0; }

.fx-tuiguang-wen h3 { margin: 8px 0 6px; font-size: 18px; line-height: 1.4; }

.fx-tuiguang-wen h3 a { color: #f2f6ff; text-decoration: none; }

.fx-tuiguang-wen h3 a:hover { color: #FFD54A; }

.fx-tuiguang-wen p { margin: 0; color: #a9b4c4; font-size: 13.5px; line-height: 1.75; }

.fx-tuiguang .xinwen-biaoqian { background-color: #B80000; color: #fff; }

.fx-tuiguang-btn {
    flex: 0 0 auto;
    display: inline-block;
    padding: 11px 20px;
    border-radius: 4px;
    background: #B80000;
    color: #fff !important;
    font-weight: 700;
    font-size: 14px;
    text-decoration: none;
    white-space: nowrap;
    transition: background .15s ease;
}

.fx-tuiguang-btn:hover { background: #e00000; }

@media (max-width: 720px) {
    .fx-tuiguang { flex-direction: column; align-items: stretch; gap: 14px; padding: 16px; }
    .fx-tuiguang-wen h3 { font-size: 16px; }
    .fx-tuiguang-btn { text-align: center; }
}
'''


def lang_of(name):
    if name.endswith('-en.html'):
        return 'en'
    if name.endswith('-ja.html'):
        return 'ja'
    return 'zh'


def main():
    changed, added_nav, added_card = [], 0, 0
    for path in sorted(glob.glob(os.path.join(root, '*.html'))):
        name = os.path.basename(path)
        with open(path, encoding='utf-8') as f:
            text = f.read()
        orig = text
        lg = lang_of(name)

        if 'class="fx-nav"' not in text and '</nav>' in text:
            ins = '                <a href="fx/" class="fx-nav">%s</a>\n            </nav>' % LABEL[lg]
            text = text.replace('</nav>', ins, 1)
            added_nav += 1

        if re.fullmatch(r'index(-en|-ja)?\.html', name) and 'fx-tuiguang' not in text:
            m = re.search(r'(?s)<h2 class="lanmu-biaoti">.*?</h2>', text)
            if m:
                text = text[:m.end()] + '\n' + CARD[lg] + text[m.end():]
                added_card += 1

        if text != orig:
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(text)
            changed.append(name)

    css_path = os.path.join(root, 'style.css')
    css_changed = False
    if os.path.exists(css_path):
        with open(css_path, encoding='utf-8') as f:
            css = f.read()
        if '.fx-tuiguang' not in css:
            with open(css_path, 'a', encoding='utf-8', newline='') as f:
                f.write(CSS)
            css_changed = True

    print('nav+%d card+%d files=%d css=%s' % (added_nav, added_card, len(changed), css_changed))
    bad = [n for n in (os.path.basename(p) for p in glob.glob(os.path.join(root, '*.html')))
           if open(os.path.join(root, n), encoding='utf-8').read().count('fx-nav') != 1]
    print('每页恰好一个入口' if not bad else '异常: ' + ', '.join(bad))


if __name__ == '__main__':
    main()