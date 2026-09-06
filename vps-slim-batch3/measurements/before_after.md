# 施工前後量測(2026-09-06)

## free -m

```
施工前 23:00
               total        used        free      shared  buff/cache   available
Mem:            1962         973         266           0         914         988
Swap:           2399        1390        1009

完工 23:50(mask 掉被 dbus 拉回的 udisks2/upower/fwupd 之後)
Mem:            1962         635         524           0         988        1326
Swap:           2399        1337        1062
```

## 服務 MemoryCurrent(施工前 23:00,前 20 名)

```
   297865216  anchor-memory.service
   244932608  chatnest-version-bridge.service
   173367296  chatnest-next.service
    84922368  chatnest-screenshot-worker.service   ← 常駐,尖峰 508MB
    80719872  systemd-journald.service
    79974400  cron.service
    37187584  stackchan-mcp.service
    28585984  mumu-server.service
    27750400  hands-mcp.service
    23498752  mumu-panel.service                   ← 停用
    23384064  cf-tunnel.service
    23379968  fwupd.service                        ← 停用(後改 mask)
    22302720  daifugo-mcp.service
    22233088  mumu-ota.service
    21008384  toy-mcp.service
    20000768  chatnest.service
    19218432  multipathd.service                   ← 停用
    17350656  rsyslog.service
    17092608  nest-serving.service
    15908864  voice-mcp.service
    10969088  mumu-chat.service                    ← 停用
     2605056  udisks2.service                      ← 停用(後改 mask)
      770048  upower.service                       ← 停用(後改 mask)
      524288  ModemManager.service                 ← 停用
```

停用小計約 80 MB;screenshot-worker 常駐 82MB + 尖峰 508MB 從此不再常駐。

**單一服務的前後相減不可靠**:施工過程跑了兩輪完整 pytest,核心在壓力下大量回收分頁,
anchor 一度從 297MB 掉到 57MB 再回到 172MB。判斷依據是逐時記錄的 `swap_watch.csv`。

## ufw

```
施工前:22/tcp, 3000, 8000/tcp, 8003/tcp, 8080/tcp, 8888/tcp (v4+v6)
完工  :22/tcp, 8000/tcp, 8003/tcp (v4+v6)
```

## pytest

```
施工前:395 collected, 2 errors during collection, 6 failed
完工  :400 passed, 1 skipped, 0 failed, 0 error   (167 秒)
```

## screenshot worker 端到端

```
派 job → 6 秒 completed
空閒 62 秒後 exit 0
退出後:0 個 chromium、0 個 node、worker cgroup 不存在
worker 執行中再派一個 job:兩個都 completed
安全網(純淨版):靜置 40 秒 job 維持 queued → 跑安全網 → 立回觸發檔 → 6 秒 completed
```

## 一週觀察

`/srv/nest-memory/health/swap_watch.csv`,每小時一列,以 nestmemory 身分寫入。

```
ts,mem_used_mb,mem_avail_mb,buffcache_mb,swap_used_mb,swap_free_mb,anchor_mb,bridge_mb,next_mb,worker_mb,hands_mb
2026-09-06T23:20:21+08:00,925,1036,1128,1357,1042,174,117,66,187,225
2026-09-06T23:26:07+08:00,741,1220,1284,1340,1059,172,116,60,0,214
2026-09-06T23:50:17+08:00,686,1275,977,1337,1062,57,225,100,0,241
```

(第一列的 worker_mb=187 是因為當時測試誤觸發了生產 worker——那個回歸已修,見 NOTES ②。)
