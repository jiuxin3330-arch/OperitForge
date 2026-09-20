#!/bin/bash
# TICKET-Q 重啟腳本（在 VPS 以 root 用 systemd-run 跑，不要從 exec_vps 的 cgroup 直接 restart——檢查表第 2 條）
#   systemd-run --unit=ticketq-deploy --collect bash /root/ticketq-scratch/deploy_restart.sh
# 做的事：等 anchor 空閒 → 再備份一次 → 產 owner key → restart → 等健康 → 驗 19+9 工具 → 任一步失敗自動回滾到 baseline 7c2e317
set -u
SRC=/root/anchor-memory
DATA=$SRC/memory_data
LOG=/root/ticketq-scratch/deploy.log
KEY=$(cat /srv/chatnest-next/runtime/mcp-keys/anchor.key)
URL="http://127.0.0.1:8765/mcp-$KEY"
TS=$(TZ=Asia/Taipei date +%Y%m%d_%H%M%S)
exec > >(tee -a "$LOG") 2>&1
echo "== deploy start $TS"

# 0. 等空閒：anchor 是 stateless，看最近 10 秒 journal 有沒有 CallToolRequest
for i in $(seq 1 30); do
  n=$(journalctl -u anchor-memory --since '-10s' --no-pager 2>/dev/null | grep -c CallToolRequest)
  [ "$n" = "0" ] && break
  echo "busy ($n calls in last 10s), wait..."; sleep 5
done

# 1. 重啟前備份（最新狀態）
sqlite3 "$DATA/memories.db" ".backup $DATA/memories.db.bak-ticketq-prerestart-$TS" || { echo "backup failed"; exit 2; }
tar czf "$DATA/chroma.bak-ticketq-prerestart-$TS.tar.gz" -C "$DATA" chroma chroma.sqlite3
echo "backup: memories.db.bak-ticketq-prerestart-$TS  chroma.bak-ticketq-prerestart-$TS.tar.gz"
md5sum "$DATA/memories.db.bak-ticketq-prerestart-$TS"

# 2. owner key
$SRC/venv/bin/python3 -c "import sys; sys.path.insert(0,'$SRC'); import anchor_config as c; print('owner key:', c.ensure_owner_key())"
ls -la $SRC/owner.key

# 3. import 檢查（9/11 條：改到常駐服務載入的檔案，重啟前 compile+import，重啟後再驗）
cd $SRC && $SRC/venv/bin/python3 -m py_compile anchor_config.py anchor_ext.py anchor_db.py anchor_memory.py anchor_mcp_http.py || { echo "compile failed"; exit 3; }

# 4. restart
BEFORE=$(systemctl show anchor-memory -p NRestarts --value)
systemctl restart anchor-memory
sleep 12
STATE=$(systemctl show anchor-memory -p ActiveState --value)/$(systemctl show anchor-memory -p SubState --value)
NR=$(systemctl show anchor-memory -p NRestarts --value)
echo "after restart: $STATE NRestarts=$NR (before $BEFORE)"

# 5. 健康 + 工具清單
python3 - "$URL" <<'PY'
import sys, json, asyncio
sys.path.insert(0, "/root/anchor-memory/venv/lib/python3.12/site-packages")
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
URL = sys.argv[1]
LEGACY = ["store_memory","search_memory","delete_memory","connect_memories","get_neighbors","set_emotion","set_tier",
          "annotate_memory","get_annotations","search_annotations","wakeup","leave_comment","get_comments",
          "mark_comments_read","pin_memory","unpin_memory","cite_memory","consolidate","dream_pass","graph_stats"]
NEW = ["memory_task_create","memory_task_list","memory_task_resolve","create_entity_card","set_entity_card_status",
       "update_card_fact","get_entity_card","cards_affected_by","memory_lineage"]
async def main():
    async with streamablehttp_client(URL) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name for t in (await s.list_tools()).tools}
            miss = [t for t in LEGACY + NEW if t not in tools]
            print("tools:", len(tools), "missing:", miss)
            if miss: sys.exit(5)
            # 只讀健康：graph_stats、wakeup、search（不強化）、lineage、task_list、get_entity_card
            for name, args in [("graph_stats", {}), ("wakeup", {"n_high_emotion": 0, "n_random": 0}),
                               ("search_memory", {"query": "花椰菜", "n_results": 2}),
                               ("memory_lineage", {"memory_id": "core_001_relationship"}),
                               ("memory_task_list", {}), ("get_entity_card", {})]:
                res = await s.call_tool(name, args)
                txt = res.content[0].text if res.content else ""
                print(f"  {name}: ok {len(txt)} chars" + (" | " + txt.splitlines()[0][:80] if txt else ""))
asyncio.run(main())
PY
RC=$?
if [ "$STATE" != "active/running" ] || [ "$RC" != "0" ]; then
  echo "!! health failed (state=$STATE rc=$RC) → rollback to baseline 7c2e317"
  cd $SRC && git stash -q && git checkout -q 7c2e317 -- anchor_db.py anchor_memory.py anchor_mcp_http.py && systemctl restart anchor-memory
  sleep 8; systemctl is-active anchor-memory; exit 9
fi
echo "== schema_meta"; sqlite3 -header "$DATA/memories.db" "select * from schema_meta"
echo "== deploy OK $(TZ=Asia/Taipei date)"
