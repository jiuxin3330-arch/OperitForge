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

# 2026-08-18 修復(P4 複審工單):memory.db 變熱後,檔案級 tar 會撕裂
# (WAL checkpoint 與 tar 競態,「file changed as we read it」)。
# 改用 sqlite3 .backup 線上備份取一致快照,tar 只碰快照,不碰活體 db。
STAGE=$(mktemp -d "$DEST/.stage.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/srv/nest-memory/db"
chown -R nestmemory:nestmemory "$STAGE"
sudo -u nestmemory sqlite3 "$BASE/db/memory.db" ".backup '$STAGE/srv/nest-memory/db/memory.db'"

tar -czf "$OUT" -C / srv/nest-memory/raw srv/nest-memory/state root/nest-memory -C "$STAGE" srv/nest-memory/db
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
