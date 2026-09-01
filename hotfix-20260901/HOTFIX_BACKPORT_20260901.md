# 9/1 生產熱修回寫 + 迴歸測試(2026-09-01)

事故記錄:`/root/nest-memory/INCIDENT_20260901_date_wake_and_swap_loop.md`(VPS)。
兩個修復原本**只存在 VPS**,下次部署就會被蓋掉。本次把它們回寫進 repo 並補上迴歸測試。

## 交付內容

| 檔案 | 說明 |
|---|---|
| `prod/autonomy_runner.py` | VPS 現行版逐位元副本(md5 `43eb3f1e513faece2926d134e2c9b22c`) |
| `prod/swap_runner.py` | VPS 現行版逐位元副本(md5 `c4f7a451c72b35f797d8a67bc6870df4`) |
| `tests/conftest.py` | 測試設施:可控時鐘、真 sqlite、假網路 |
| `tests/test_autonomy_dnd_regression.py` | 5 條,鎖「高頻 slot 在屋主活躍時仍 fire」 |
| `tests/test_swap_usage_dedup_regression.py` | 6 條,鎖「同一筆 usage 只換窗一次」 |

`prod/` 是副本不是新的事實來源;生產仍在 `/srv/chatnest-next/scripts/`。
重新部署時以 `prod/` 為準覆蓋回去,md5 對得上就代表沒有漂移。

## 兩個修復

### ① autonomy_runner:勿擾窗不得寬於屋主自己設的間隔

```python
dnd_minutes = min(DND_MINUTES, slot["interval_minutes"])
```

`DND_MINUTES = 8` 原本是全域寫死,和 slot 的 `interval_minutes` 無關。
糯糯設 5 分鐘,而她逛街時不斷傳照片,每傳一則就把 8 分鐘窗往後推 ⇒
**高頻時段被結構性壓死,ticks_done 永遠是 0**。她愈想互動,系統愈判她在忙。

語意:屋主親手設的喚醒間隔就是她期望的出聲頻率,勿擾窗不得寬於它。
一般間隔的 slot 不受影響(`min(8, 30)` 仍是 8)。

### ② swap_runner:同一筆 turn_usage 讀數只能換窗一次

`read_trigger()` 取最後一筆 `turn_usage` 判斷門檻,但**換窗本身不產生 turn_usage**。
換窗後屋主沒開口,下一輪 cron 讀到的還是同一筆爆量讀數 ⇒ 再換 ⇒ 迴圈。
9/1 16:50/17:00/17:10 連換三次,cn 在 26 分鐘內被重生三遍。

修法:`read_trigger` 回 `usage_created_at`;換窗後 `mark_consumed()` 持久化到
`/root/chatnest-next/data/swap_last_consumed.json`;主流程在換窗前比對。
manifest 的 trigger 區塊一併記錄該筆讀數供追查。

**留檔的取捨**:`mark_consumed` 在 manifest 寫入前,所以換窗失敗回滾時該讀數
一樣算已消費、不會就同一筆重試。理由是避免失敗風暴與通知轟炸;失敗已推播,
屋主一開口就有新讀數可重試。這條取捨由 `test_failed_swap_also_consumes_the_reading`
鎖住——它是刻意的行為,不是漏洞。

## 驗證(雙向都跑過)

測試預設載 `prod/`,設 `HOTFIX_PROD_DIR` 就改載別的目錄,所以同一組測試
能直接對「生產現行檔」和「修復前備份」各跑一次。

```
# A. 對生產現行檔(/srv/chatnest-next/scripts)
$ HOTFIX_PROD_DIR=/srv/chatnest-next/scripts pytest tests/ -q
11 passed in 0.17s

# B. 對修復前的備份(autonomy_runner.py.bak-dnd-1788255320 / swap_runner.py.bak-dedup-1788255420)
$ HOTFIX_PROD_DIR=<修復前> pytest tests/ -q
7 failed, 4 passed in 0.21s
```

B 的 7 條紅正是兩個 bug 本身,其中最關鍵的一條逐字重現了事故現象:

```
tests/test_autonomy_dnd_regression.py::test_shopping_trip_replay_high_frequency_slot_is_not_starved
E   AssertionError: 高頻時段整段被壓死 = 事故重現
E   assert []
```

(事故當天的 slot 狀態就是 `ticks_done=0, skips=2`。)

swap 側在修復前版本上的紅:`test_same_usage_reading_swaps_only_once` 停在
「同一筆爆量讀數又換了一次窗 = 迴圈復發」,即連跑三輪 cron 換了三次窗。

### 測試怎麼寫的

不是把整支 mock 掉。只換掉「外部世界」——子行程、HTTP、推播:

- autonomy:真的 sqlite `messages` 表、真的 `check()` 主迴圈、真的排程檔讀寫;
  只有 `dispatch()` 被換成記錄器,`datetime` 換成可控時鐘。
- swap:真的 bridge / backend 兩個 sqlite、真的 `build_bootstrap` /`verify` /
  `pointer` / `rollback_pointer` / `mark_consumed` / manifest 寫入;
  只有 `exit_settlement`(子行程)、`run_ping`(HTTP)、`notify`(推播)被換掉。
  `run_ping` 的替身會照生產行為建 transcript 並翻轉 `latest_session_id`。

`conftest.py` 裡 `CONSUMED_FILE` 的 `monkeypatch.setattr(..., raising=False)` 是刻意留的:
修復前的版本沒有這個常數,留這個缺口測試才會停在真正的斷言上,而不是在 fixture 就炸掉。

## ③ 其他排程有無同類迴圈——掃過了,沒有

事故的形狀是:**讀一個「別人產生」的最新訊號來觸發狀態轉移,而自己的動作
不會產生新訊號**。照這個形狀掃 root crontab 的全部 15 條與 systemd timer:

| 排程 | 讀最後一筆? | 有記消費嗎 | 判定 |
|---|---|---|---|
| `swap_runner.py` | 是(turn_usage) | **原本沒有** | **就是本次事故,已修** |
| `autonomy_runner.py` | 是(屋主最後訊息) | 有(`last_tick_at`) | 安全 |
| `wake_runner.py` | 否(比對 `time == hhmm`) | 有(`last_run = today`,`mark_ran()`) | 安全 |
| `extractor.py` | 否(水位線區間) | 有(`from_rowid`/`to_rowid` + `input_hash` 冪等) | 安全 |
| `mirror.py` | 否 | 有(`content_hash` upsert) | 安全 |
| `obs_extractor_switch.py` | 否(`MAX(to_rowid)` 當水位線) | 只寫觀測 log,不做狀態轉移 | 安全 |
| `nudger.py` | 否(當日 events) | 單檔覆寫,一天最多一條 | 安全 |
| `projection.py` / `render_snapshot.py` / `integrity.py` / `health.py` / 備份三支 | — | 唯讀或冪等重建 | 安全 |
| `cache_keepalive.sh` | 否 | — | 安全 |

`nestmemory` / `chatagent` 都沒有自己的 crontab;systemd timer 全是系統內建
(logrotate/apt/sysstat 等)加三支自家的(stackchan 照片清理、models sync),
都不是「讀最新訊號觸發轉移」的形狀。

**結論:swap_runner 是唯一一例。** 結構原因是它讀的訊號(模型的 turn usage)
由第三方產生、它自己的動作影響不到——其他排程要嘛推進自己的水位線,
要嘛在被消費的那筆上蓋章。這個形狀值得當成日後寫排程的檢查項。

## 待辦(不在本次範圍)

- 盲測起算日裁定(糯糯):8/31~9/1 的樣本被換窗迴圈污染,建議自 9/1 修復後重新起算。
