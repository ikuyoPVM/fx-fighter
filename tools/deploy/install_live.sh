#!/bin/bash
# 安装/更新常驻的实时汇率中继（服务器上执行）
set -e
sudo -n install -m 755 -o root -g root /tmp/fx-deploy/fx-live.py /opt/fx-fighter/fx-live.py
sudo -n install -m 644 -o root -g root /tmp/fx-deploy/fx-live.service /etc/systemd/system/fx-live.service
sudo -n mkdir -p /var/lib/fx-live
sudo -n touch /var/log/fx-live.log
sudo -n chmod 644 /var/log/fx-live.log

sudo -n systemctl daemon-reload
sudo -n systemctl enable --now fx-live.service
sleep 3
echo '=== service ==='
sudo -n systemctl --no-pager --lines=0 status fx-live.service | head -6
echo '=== 一次 tick 的结果（等 8 秒）==='
sleep 8
sudo -n tail -6 /var/log/fx-live.log
echo '=== live.js ==='
ls -l /var/www/ikuyo.xyz/fx/live.js
curl -sS -o /dev/null -w 'live.js %{http_code} %{size_download}B\n' -H 'Host: ikuyo.xyz' http://127.0.0.1/fx/live.js
head -c 300 /var/www/ikuyo.xyz/fx/live.js; echo