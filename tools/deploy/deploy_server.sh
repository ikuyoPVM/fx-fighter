#!/bin/bash
set -e
WEB=/var/www/ikuyo.xyz
STAMP=$(date +%Y%m%d-%H%M%S)

echo "=== 1. backup ==="
sudo -n mkdir -p /root/site-backups
sudo -n tar czf /root/site-backups/ikuyo-$STAMP.tgz --exclude=.git -C /var/www ikuyo.xyz
sudo -n ls -lh /root/site-backups/ikuyo-$STAMP.tgz

echo "=== 2. put /fx/ ==="
sudo -n mkdir -p $WEB/fx
sudo -n cp /tmp/fx-deploy/index.html /tmp/fx-deploy/rates.js /tmp/fx-deploy/engine.js /tmp/fx-deploy/ui.js $WEB/fx/
sudo -n chmod 644 $WEB/fx/*

echo "=== 3. patch entries (idempotent) ==="
sudo -n python3 /tmp/fx-deploy/patch_site.py $WEB

echo "=== 4. ownership ==="
sudo -n chown -R www-data:www-data $WEB

echo "=== 5. local self-check ==="
ls -la $WEB/fx
grep -c 'fx-nav' $WEB/index.html || true
curl -sS -o /dev/null -w 'index %{http_code}\n' -H 'Host: ikuyo.xyz' http://127.0.0.1/
curl -sS -o /dev/null -w 'fxdir %{http_code}\n' -H 'Host: ikuyo.xyz' http://127.0.0.1/fx/
curl -sS -o /dev/null -w 'rates %{http_code} %{size_download}B\n' -H 'Host: ikuyo.xyz' http://127.0.0.1/fx/rates.js
echo DONE