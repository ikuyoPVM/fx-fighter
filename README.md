# FX FIGHTER · 真实外汇模拟终端

**13 个货币对**的外汇模拟终端：真数据锚定的价格路径，加一套照着零售券商规则写的撮合引擎
（点差、佣金、滑点、保证金、隔夜利息、强平）。

打开就能用，不需要服务器、不需要账号、不联网、不涉及任何真实资金。

线上版本还有一层**实时盘中数据**：服务器上有个常驻中继每分钟抓一次真实汇率，
页面顶栏的 `● 实时` 就是它 —— 今天已经走过的每一分钟都是真实报价，只有更早的历史和还没走到的未来才是模型生成的。

**在线地址**：[ikuyo.xyz/fx/](https://ikuyo.xyz/fx/) · [ikuyopvm.github.io/fx-fighter](https://ikuyopvm.github.io/fx-fighter/)

---

## 一、怎么打开

| 方式 | 做法 |
|---|---|
| **单文件版（推荐）** | 双击 `fx-fighter.html`（已内联全部脚本和真实数据，约 190 KB） |
| 源码版 | 双击 `index.html`（同目录的 `rates.js` / `engine.js` / `ui.js` 要一起在） |

浏览器建议 Chrome / Edge / Firefox 最新版。窗口宽度 ≥ 1200px 体验最好，手机上会自动堆成一列。

## 二、文件结构

```
fx-fighter/
├── fx-fighter.html      单文件版（由 tools/bundle.py 生成）
├── index.html           界面骨架 + 全部样式
├── rates.js             真实数据：ECB 欧元基准中间价，逐交易日（2022-01 → 今）
├── engine.js            撮合引擎（纯逻辑，可在 node 里跑测试）
├── ui.js                终端界面、自绘 K 线、下单交互
└── tools/
    ├── build_rates.py   重新抓真实数据 → 生成 rates.js
    ├── bundle.py        打包单文件版
    ├── selftest.js      引擎单元测试（36 项，node 直接跑）
    ├── cdp.js           用无头 Edge 跑端到端测试并取回结果
    ├── shoot.js         无头 Edge 截图（带场景脚本）
    ├── debug_page.js    无头 Edge 打开页面并取回引擎状态（联网验收用）
    ├── e2e.html         端到端测试页（在 iframe 里驱动真页面点按钮下单）
    └── deploy/
        ├── fx-live.py        实时汇率中继（常驻，每 60 秒写 fx/live.js）
        ├── fx-live.service   systemd 单元
        ├── install_live.sh   一键安装 / 更新中继
        ├── refresh.py        每天抓 ECB 日线 → 覆盖 rates.js 并推 GitHub
        ├── install_cron.sh   装每日 cron
        ├── sync_from_github.py / sync_run.sh   GitHub → 服务器 单向同步
        └── put_files.js / push_api.js          GitHub Contents / Git Data API 发布
```

## 三、哪些是真的，哪些是模拟的

**真的：**

* **每一个交易日的收盘价**：欧洲央行（ECB）欧元基准中间价，逐交易日，共 1231 个交易日。
  来源 `api.frankfurter.dev`（ECB 镜像），抓取脚本 `tools/build_rates.py` 随时可重跑。
* **13 个品种全部由这张 EUR 基准表换算**：`EURUSD = USD`、`USDJPY = JPY/USD`、`GBPUSD = USD/GBP`……
  交叉盘（EURJPY / EURGBP / EURCHF / GBPJPY / AUDJPY）不独立乱走，一律按两条美元腿相乘除，
  三角一致性误差为 0（真市场里也只有零点几个点）。
* **每天都在真实收盘价上收线**：日内路径用布朗桥挂在「昨日真实收盘 → 今日真实收盘」之间，
  23:59 的价格精确等于真实收盘价。
* **最近几小时的盘中价是真的**（仅线上版）：服务器上的 `fx-live` 中继每 60 秒抓一次
  `api.fxratesapi.com`（EUR 基准 8 条腿），写成 `fx/live.js`；最近 3 天已经走过的分钟全部换成真实报价，
  8 条腿按上面的同一套公式折成 13 个品种。中继在 systemd 里常驻，**没人访问也在跑**。

**模拟的：**

* **中继上线之前的分钟**：那部分仍是布朗桥。中继跑得越久，真实区间越长（客户端最多回放 3 天）。
* **日内 1 分钟路径的形状**：中继没覆盖的时间段，用布朗桥 + 按品种、按 UTC 小时加权的波动率
  （东京 / 伦敦 / 纽约重叠最猛）。
* **日线的上下影线**：没有免费的历史逐日高低价，D1 蜡烛的开／收是真的，影线按波动率估的
  （鼠标悬停会标出来）。
* **最后一个 ECB 交易日之后**：日线收盘价转为模拟（按品种日波动率生成），状态栏会标「模拟日」。
* **点差、滑点、隔夜利息、强平顺序**：都是模型，参数固定写在引擎里，可在「？机制」里逐条核对。

## 四、撮合规则（摘要）

| 项目 | 规则 |
|---|---|
| 合约 | 1 手 = 100,000 基础货币，最小 0.01 手 |
| 报价 | 买价 = 中间价 + 点差/2，卖价 = 中间价 − 点差/2 |
| 点差 | 随 UTC 时段、波动、每日结算（服务器 00:00 = UTC 21:00）前后 20 分钟变化，结算时放大 3 倍以上 |
| 点值 | `pip × 手数 × 100,000 × 报价货币兑美元汇率`（EURUSD 1 手 1 点 = $10；USDJPY ≈ $6.4） |
| 佣金 | $3.5 / 手 / 单边（往返 $7） |
| 滑点 | 市价单：`点差 × 0.12 × (1 + (手数/深度)^0.75 × 1.8) × |N(0,1)|`，另有 2% 概率尾部大滑点 |
| 保证金 | 名义价值 ÷ 杠杆（1:10 ~ 1:500，受品种上限约束） |
| 隔夜利息 | `名义价值 × ((r基础 − r报价) × 方向 − 0.25%) ÷ 365`，每天服务器 00:00 结算，周三三倍 |
| 追保 / 强平 | 保证金比例 < 100% 追保；< 50% 强平浮亏最大的一笔（市价 + 2.2 倍滑点） |
| 休市 | 周六全天、周日 UTC 21:00 前、周五 UTC 21:00 后不撮合（挂单不成交、不能平仓） |
| 止损 / 止盈 | 距离须 > 点差 + 2 点；止损按市价成交（会滑点），止盈按限价成交（不会更差） |

## 五、操作

* 左边点品种；中间选周期（M1 / M5 / M15 / H1 / H4 / D1），**滚轮缩放、拖动平移、双击复位**
* 右边填手数、杠杆，可市价做多／做空，可挂**限价单／止损单**，可设**止损止盈（按点填）**
* 持仓行：`平` 全平这一笔、`半` 平一半、`改` 改止损止盈
* 键盘：`↑` 做多、`↓` 做空、`空格` 一键平仓、`Esc` 撤销全部挂单、`T` 同步时钟
* **进站默认 1×（实时）**：接上实时数据后自动对齐到服务器最新报价，之后贴着真实时间走
* 顶栏调行情速度：暂停 / 1× / 10× / 60× / 300× / 1800×（1× = 实时，1800× = 1 秒走半小时）
* **`⏱ 实时` 按钮**（或按 `T`）：点一下 = 切到 1× + 把时钟按回最新真实报价。
  - 亮绿 = 正贴着实时；琥珀 = 时钟已经偏离真实时间（倍速跑飞或暂停过），点一下归位
  - **1× 下自动同步**：偏离超过 1.5 分钟自动拉回，报价两分钟内算新鲜，后台标签页有 15 秒兜底检查
  - 归位时路径 / K 线 / 净值曲线一起重算，持仓和挂单不动
* 账户每 4 秒自动存到浏览器 localStorage，刷新页面接着玩；`⟳ 重开` 清空重来
* `⤓ CSV` 导出成交记录（Excel 直接打开）

## 六、实时中继（线上版）

服务器上 `/opt/fx-fighter/fx-live.py` 是一个常驻进程（`fx-live.service`，`Restart=always`）：

| 项 | 值 |
|---|---|
| 频率 | 每 60 秒一次（对齐到每分钟 :05 秒）；失败重试 3 次，跳变 > 5% 视为脏数据丢弃 |
| 源 | `api.fxratesapi.com/latest?base=EUR&currencies=USD,JPY,GBP,CHF,AUD,CAD,NZD,CNY` |
| 存档 | `/var/lib/fx-live/YYYYMMDD.ndjson`（每天一个文件，重启不丢当天数据） |
| 输出 | `/var/www/ikuyo.xyz/fx/live.js`（`window.FX_LIVE={src,ts,quoteTs,legs,days:[{d,tape}]}`） |
| 日志 | `/var/log/fx-live.log` |
| 前端 | `<script src="live.js?t=…">` 每 60 秒拉一次（`<script>` 天然跨域，Pages 版直接读 `https://ikuyo.xyz/fx/live.js`） |

安装 / 更新：

```bash
scp tools/deploy/fx-live.py tools/deploy/fx-live.service tools/deploy/install_live.sh ikuyo:/tmp/fx-deploy/
ssh ikuyo "bash /tmp/fx-deploy/install_live.sh"
```

平时只关心这三条：

```bash
ssh ikuyo "systemctl status fx-live --lines=0; tail -3 /var/log/fx-live.log; ls -l /var/www/ikuyo.xyz/fx/live.js"
```

它跟 ECB 日线那条 cron（`/etc/cron.d/fx-refresh`，每天 23:40 抓 ECB 并推 GitHub）互不依赖：
日线负责「今天收盘多少」，中继负责「现在多少」。

## 七、重新抓真实数据

```bash
python tools/build_rates.py     # 重新抓 ECB 日线 → 覆盖 rates.js
python tools/bundle.py          # 重新打包单文件版
```

## 八、自测

```bash
node tools/selftest.js          # 引擎 36 项单元测试：点值/保证金/强平/隔夜息/周末休市/存档/确定性
node tools/cdp.js "file:///<绝对路径>/tools/e2e.html" "#out" 30000
                                # 端到端：无头 Edge 里点真按钮下单、平仓、切品种、切周期、暂停
```

## 九、没模拟的东西

* **新闻跳空**：非农／CPI／央行决议那种瞬间跳空没有单独建模。
* **流动性深度**：深度只是滑点公式里的一个常数，没有真正的盘口排队。
* **隔夜利息**用的是政策利率近似，真实券商还会加浮动加点。
* **周末缺口**：周一开盘按模型生成，不是真实跳空幅度。
* **点值换算**用当前中间价，真实券商按结算价，会有几分钱差别。

一句话：**这是把真数据当骨架、把日内走势和券商规则当肉的一个沙盒，不是行情源，更不是投资建议。**