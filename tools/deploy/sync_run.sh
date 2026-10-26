#!/bin/bash
# 备份线上站点后，从 GitHub 同步最新代码（服务器上执行）
set -e
STAMP=$(date +%Y%m%d-%H%M%S)
BK=/root/site-backups/ikuyo-$STAMP-pre-sync.tgz
sudo -n tar czf "$BK" --exclude=.git -C /var/www ikuyo.xyz
sudo -n ls -lh "$BK"
echo "=== sync from github ==="
sudo -n python3 /tmp/fx-deploy/sync_from_github.py
echo "=== self check ==="
sudo -n nginx -t 2>&1 | tail -2
curl -sS -o /dev/null -w 'home %{http_code}\n' -H 'Host: ikuyo.xyz' http://127.0.0.1/
curl -sS -o /dev/null -w 'fx/  %{http_code}\n' -H 'Host: ikuyo.xyz' http://127.0.0.1/fx/