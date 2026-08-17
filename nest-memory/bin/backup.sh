#!/bin/bash
# Nest Memory — Phase 0 基礎備份
# 目的地(具體指定):/srv/nest-memory/backup(本機)。
# 異地備份目的地尚未有可用憑證,待糯糯決定(見 /root/nest-memory/PHASE0_NOTES.md)。
# 內容:raw/ + state/ + /root/nest-memory 文件。保留 14 份,成功後寫 backup_last_success。
set -euo pipefail
umask 077

BASE=/srv/nest-memory
DEST=$BASE/backup
STAMP=$(date +%Y%m%d-%H%M%S)
OUT=$DEST/nest-memory-$STAMP.tar.gz

tar -czf "$OUT" -C / srv/nest-memory/raw srv/nest-memory/state srv/nest-memory/db root/nest-memory
chown nestmemory:nestmemory "$OUT"
chmod 600 "$OUT"

# 驗證壓縮檔可讀
tar -tzf "$OUT" > /dev/null

# 輪替:保留最新 14 份
ls -1t "$DEST"/nest-memory-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f

SIZE=$(stat -c %s "$OUT")
printf '{"ts": "%s", "ok": true, "file": "%s", "bytes": %s}\n' \
  "$(date -Iseconds)" "$OUT" "$SIZE" > "$BASE/health/backup_last_success.json"
chown nestmemory:nestmemory "$BASE/health/backup_last_success.json"
