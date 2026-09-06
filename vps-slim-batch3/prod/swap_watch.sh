#!/bin/bash
# 第三批(2026-09-06)一週觀察:每小時記一列記憶體/swap。
# 用途:瘦身之後 swap 到底有沒有降、有沒有再爬回去。一週後看這張表決定要不要升 4GB。
# 以 nestmemory 身分跑,寫進 health/——這個目錄的檔案身分要一致(TICKET-K 第五種形狀的教訓)。
set -u
OUT=/srv/nest-memory/health/swap_watch.csv
read -r _ total used free shared buffcache avail < <(free -m | sed -n '2p')
read -r _ stotal sused sfree < <(free -m | sed -n '3p')
svc() { local m; m=$(systemctl show -p MemoryCurrent --value "$1" 2>/dev/null); case "$m" in ''|'[not set]'|18446744073709551615) echo 0;; *) echo $((m/1048576));; esac; }
if [ ! -f "$OUT" ]; then
  echo "ts,mem_used_mb,mem_avail_mb,buffcache_mb,swap_used_mb,swap_free_mb,anchor_mb,bridge_mb,next_mb,worker_mb,hands_mb" > "$OUT"
fi
printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n" \
  "$(date -Iseconds)" "$used" "$avail" "$buffcache" "$sused" "$sfree" \
  "$(svc anchor-memory.service)" "$(svc chatnest-version-bridge.service)" \
  "$(svc chatnest-next.service)" "$(svc chatnest-screenshot-worker.service)" \
  "$(svc hands-mcp.service)" >> "$OUT"
