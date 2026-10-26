#!/bin/bash
# 安装 / 更新 FX 数据的每日刷新任务（服务器上执行）
set -e
DEST=/opt/fx-fighter
sudo -n mkdir -p $DEST /etc/fx-refresh
sudo -n cp /tmp/fx-deploy/refresh.py $DEST/refresh.py
sudo -n chmod 755 $DEST/refresh.py
sudo -n chown root:root $DEST/refresh.py

# GitHub token（只 root 可读，refresh.py 用它把数据推回两个仓库）
if [ -f /tmp/fx-deploy/gh-token ]; then
  sudo -n install -m 600 -o root -g root /tmp/fx-deploy/gh-token /etc/fx-refresh/token
  rm -f /tmp/fx-deploy/gh-token
fi

# cron：工作日 23:40（ECB 约 23:00 CST 公布），错开整点
sudo -n tee /etc/cron.d/fx-refresh >/dev/null <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
# 每个工作日 ECB 公布参考汇率后刷新 fx 数据（服务器副本 + 两个 GitHub 仓库）
40 23 * * 1-5 root /opt/fx-fighter/refresh.py >> /var/log/fx-refresh.log 2>&1
CRON
sudo -n chmod 644 /etc/cron.d/fx-refresh

echo "--- cron installed ---"
cat /etc/cron.d/fx-refresh
ls -la /etc/fx-refresh/
echo "--- dry run (no change expected) ---"
sudo -n /opt/fx-fighter/refresh.py
echo "--- log ---"
sudo -n tail -5 /var/log/fx-refresh.log 2>/dev/null || true