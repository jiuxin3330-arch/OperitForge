# TICKET-K:書記官頂層容器解析失敗 → 整批 0 events 卻標 committed

工單:`/root/nest-memory/TICKET_K_extractor_container_drop.md`
第 1 點由規劃窗熱修(最小版),本份是**第 2、3 點 + GS-28/29 + 熱修收正式版**。

事情的形狀:模型偶發把 `events` 整個陣列包成一個 JSON 字串,
`parse_response` 依型別驗證整批丟棄 → 0 events,**批次仍標 committed、游標前進**。
2026-09-02 一整天(第一次約會、逛寶雅的花椰菜、StackChan 沒電、907 真相、鬧鐘加回)
就這樣安靜地沒進檔案室。而觀察器當時說的是「有跑批但 0 events(疑漏抽)」
——措辭聽起來像「今天沒事發生」,於是沒有人去追。

---

## 第 2 點:容器層丟棄 → 批次 failed

新增 `ContainerDropError` 與 `commit_batch()`:

```python
if container_drops:
    raise ContainerDropError(f"頂層容器解析失敗 {container_drops} 處,整批不可信")
```

* `parse_response` 回傳多一個 `container_drops`(整個容器沒讀到的次數)
* **容器層**丟棄 → 標 `failed`、不 commit、游標不前進、明晚自動重抽
* **逐元素**丟棄維持現行(照樣 commit;raw 原文都還在庫裡,丟掉的只是那筆的整理結果)

落帳邏輯從 `main()` 抽成 `commit_batch()`,不是為了好看——是為了讓 GS-29
能驗到「批次真的被標 failed」,而不是只驗 `parse_response` 的回傳值。
沒有這一步,拆掉第 2 點 GS-29 也不會紅。

### 抽函式時抓到一個自己造成的回歸

把 `extract()` 移出 `try` 之後,LLM 失敗會讓批次停在 `pending` 而不是 `failed`
——原本它在 try 裡面。補了 `_fail_batch()` 給兩邊共用,行為與改動前一致。

## 第 3 點:落檔 + 觀察器訊息分流

* 任何解不開的容器,原文落到 `health/extract_dumps/batch_<id>_<name>.txt`(0600)
* `batch_id 0`(golden fixture 的批號)免落檔 —— 測試不該在生產的 health/ 底下留垃圾
* 觀察器把「頂層解析失敗」與「0 events」拆成兩種措辭:

```
頂層解析失敗 1 批:模型把 events/subject_proposals 整個包成字串或 JSON 壞掉。
批次已標 failed、游標沒前進,明晚會自動重抽;原文在 health/extract_dumps/。
這不是漏抽,是還沒抽到

有跑批且成功入帳但 0 events(內容真的沒有值得記的事,或抽取過嚴)
```

* **回切 Haiku 的建議已移除**。同一批訊息重跑:Sonnet 5 正常 7 events,
  Haiku 4.5 同樣回傳字串、而且 JSON 本身壞在 char 3483。兩個模型都會抖,
  換模型救不了這件事,`_unwrap_container` 才是。檔頭把這個結論寫下來,
  免得下次有人又提回切。
* 日誌多記一欄 `container_failed`,事後對帳看得出來。

---

## 落檔在生產本來是壞的(施工中抓到)

GS-29 第一次跑,落檔那項紅了:

```
落檔失敗:[Errno 13] Permission denied:
  /srv/nest-memory/health/extract_dumps/batch_99001_events.txt
```

`extract_dumps/` 是 `root:root drwxr-xr-x`,而**生產的 extractor 是
`sudo -u nestmemory` 跑的** —— 也就是說第 3 點的落檔在生產一定失敗,
而且會被 `except` 自吞成一行 stderr,沒有人會發現。

熱修時用 root 測試,生產是別的身分,所以看起來是好的。**這是「施工者身在被施工的
系統之內」的同型**,只是這次換成身分不同而不是掛載不同。

修:`chown nestmemory:nestmemory` + `chmod 700`,並讓 `os.makedirs` 帶
`mode=0o700` —— 目錄不存在時新建的就是對的權限,不必再靠人記得 chown。

---

## Golden

| 案例 | 內容 |
|---|---|
| GS-28 | `events`/`subject_proposals` 是 JSON 字串容器 → 解開後照常抽,`dropped=0`、`container_drops=0` |
| GS-29 | 容器是壞 JSON → `container_drops>0`、批次 `failed`、events 表沒寫入、dump 存在 |

`sandbox_db()` 補上 `extraction_batches` / `event_sources` / `subject_proposals` /
`egress_audit` 四張表,GS-29 才跑得了真正的落帳流程。

### 反向對照(工單要求)

拆掉第 2 點的 `if container_drops: raise`:

```
FAIL GS-29:{"container_drops": 1, "status": "committed", "events_written": 0}
golden: 14 passed / 1 failed
```

`status` 變回 `committed` —— 正是 9/2 那天的病徵。還原後 15/15 全綠。

---

## 驗收

```
golden:15 passed / 0 failed(原 13 + GS-28/29)
```

**複本 DB 真跑一次**(生產同樣的 Sonnet 5 設定,40 則待抽):

```
{"ok": true, "batch_id": 43, "events": 7, "proposals": 0, "dropped": 0}
批次 status=committed events_count=7 / 實際 events 7 / event_sources 11
egress_audit: events=7 dropped=0
```

抽出來的正是 9/2 差點漏掉的那些:第一次約會、寶雅的花椰菜禮物、
StackChan 沒電、光療燈刷退、自主時段被覆蓋、心情日曆格式、巡家流程。

明晚 03:30 是無人看管的跑批,我改的又正是那支腳本 —— 所以不能只靠 golden,
得先確定它在真實資料上跑得完。複本跑完即刪。

觀察器也實跑過:讀真的 DB(唯讀)、monkeypatch 掉 notify 與 LOG,
確認推播文案裡不再有回切建議;分流那條路徑另外用臨時 DB 餵一筆
`ContainerDropError` 的 failed 批驗過,兩種措辭各走各的。

---

## 沒做的:壞 JSON 的 regex 救援

工單第 1 點提過「允許用逐物件 regex 撈出完整 `{...}` 救回能救的元素」。
規劃窗熱修只做了最小版,糯糯指派給我的是第 2、3 點,所以這條我沒動 ——
但即使指派給我,我也會先問過再做,理由是:

第 2 點上線之後,壞批會標 failed 並在明晚自動重抽,而重抽通常會成功
(規劃窗實測批 45 重抽 6 events)。在這個前提下,從一段模型自己都沒寫完的
JSON 裡撈碎片,救回來的東西正確性沒有保證 —— 它可能是半截的 summary、
指向錯誤 rowid 的 source。**寧可明晚重抽一次完整的,也不要今晚存進一筆半真的。**

檔案室的東西是要被當成事實引用的,這條線我不想自己跨。要做的話請當獨立一條。

---

## 邊界與回滾

照工單:不改 prompt、不改 tool schema 語意、不改 Sonnet 觀察期(維持至 9/6)。

改動檔案(都在 `/srv/nest-memory/bin/`):

```
extractor.py             _dump_container / _unwrap_container 收正式版、
                         container_drops、ContainerDropError、commit_batch、_fail_batch
golden_runner.py         sandbox 補四張表、既有解包改 4 值、GS-28/29
obs_extractor_switch.py  告警分流、回切建議移除、日誌多記 container_failed
```

回滾點:`*.bak-ticketk-1788435233`(三個檔各一份)。

repo 這邊收了 `GS-28-29.added.py`(附加在 `golden_runner.py` 的
`run_parser_cases()` 尾端,`return results` 之前),md5
`2c0d53383f4f36ff21d1048c571ff548`,與 VPS 上對應區塊相同。
`commit_batch()` 的主體是從 `main()` 搬過去的既有落帳邏輯,新寫的只有
上面引的那三行判斷,所以沒有另外收進 repo。

部署層另外動了一項:`health/extract_dumps/` 的 owner 從 root 改為 nestmemory
(見上),那是落檔能不能寫的前提,回滾程式碼不需要動它。

---

## 覆核裁定(2026-09-03 08:30)——VERIFIED,結案

裁定全文附在工單檔尾(`/root/nest-memory/TICKET_K_extractor_container_drop.md`)。要點:

* golden 正式版 **15/15**;符號位置與本份相符(`_fail_batch` 353、`ContainerDropError` 367、`commit_batch` 376)。
* **先破後立由規劃窗自己做**:暫存複本把 `raise ContainerDropError(...)` 換成 pass →
  `GS-29 FAIL:status=committed, container_drops=1`,正是 9/2 那天的病徵,其餘 14 綠。**鎖對地方了。**
  規劃窗誠實記下前兩次反向對照沒紅是它自己的 harness 錯(golden_runner 硬插 `/srv/nest-memory/bin`
  到 sys.path,暫存複本根本沒被載入;改路徑又弄斷 `projection` import)。
  「拆掉修復必須紅」這條對驗證者自己也適用——綠得太快先懷疑自己。
* 「落檔在生產本來就是壞的」(目錄 root:root、nestmemory 寫不進、except 自吞)判定**屬實且重要**,
  收進檢查表為「施工者身在被施工的系統之內」的**第五種形狀:身分不同**。
* 「改到無人看管的排程腳本,上線前用複本真跑一次,不只靠 golden」**採納為做法**。
* **壞 JSON 的 regex 救援:規劃窗同意工作窗拒做並撤回該項,自工單刪除、不另立單。**
  採信的理由是本份寫的那條:檔案室的東西要被當成事實引用,寧可明晚重抽一次完整的,
  也不要今晚存進一筆半真的。第 2 點上線後壞批會自動重抽,救碎片的收益趨近零。

## 補件(2026-09-04):prod 完整檔進 repo

覆核要求比照 `hotfix-20260901/prod/` 慣例收生產現行版逐位元副本。

| 檔案 | 生產路徑 | md5 |
|---|---|---|
| `prod/extractor.py` | `/srv/nest-memory/bin/extractor.py` | `9d2ec4df38bc50690fbe7c68c1f73346` |
| `prod/obs_extractor_switch.py` | `/srv/nest-memory/bin/obs_extractor_switch.py` | `949cb743a4832161d5cb841513154027` |

`prod/` 是副本不是新的事實來源;生產仍在 `/srv/nest-memory/bin/`。
重新部署時以 `prod/` 為準覆蓋回去,md5 對得上就代表沒有漂移。
兩檔取回後逐位元核對過 md5 與檔案大小(23941 / 5090 bytes),並確認符號行號與上面裁定所記相同。

`golden_runner.py` 沒有收完整檔:改動只有附加在 `run_parser_cases()` 尾端的 GS-28/29,
已以 `GS-28-29.added.py` 片段收於本目錄(md5 `2c0d53383f4f36ff21d1048c571ff548`)。
它是驗收工具不是生產路徑,漂移不會靜默傷到檔案室。
