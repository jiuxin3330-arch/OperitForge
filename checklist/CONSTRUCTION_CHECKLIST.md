# 施工檢查表

歷次工單覆核裁定「收進檢查表」的條目,原本散在五份工單裡。
散著就等於不存在——下一個施工的人不會去翻五份工單,而這些坑會反覆出現。
本檔是那份檢查表。每條都標了它是從哪裡撞出來的。

新增規則:只有經覆核裁定採納的才寫進來,並附出處。不寫「應該要小心」這種沒有動作的條目。

---

## 一、「施工者身在被施工的系統之內」——目前五種形狀

同一個錯誤的五張臉:施工者是被施工系統的一部分,於是量測、動作、判斷都被那個系統影響,
而綠燈照樣亮。每一種都是真的撞到過的,不是假想。

| # | 形狀 | 撞到的情形 | 對策 | 出處 |
|---|---|---|---|---|
| 1 | **自己擋住自己的量測** | 從 `exec_vps` 內部打 hands,拿到 000/000/000,看起來像服務死了,其實是自己阻塞自己 | 探測要從被探測路徑之外發起 | `VPS_AUDIT_20260901.md` |
| 2 | **自己殺掉自己的手** | 施工腳本由 `exec_vps` 派生,留在同一個 cgroup;`systemctl restart` 預設 `KillMode=control-group`,腳本被自己下的重啟指令殺掉 | 施工與探測一律 `systemd-run --unit` 出獨立 cgroup | `VPS_AUDIT_20260901.md` |
| 3 | **掛載不同** | 查到 backend 以 root 跑就推論寫得進去;線上 `ProtectSystem=strict` 讓它唯讀,而測試把路徑指到可寫的 tmp,整片綠燈沒碰到真的掛載 | 沙箱行為要在同規格沙箱實測,每個修復要有反向對照組 | TICKET-H |
| 4 | **環境 fallback 改寫斷言** | 刪除型工作鎖狀態碼:測試環境無 dist → 404 綠;生產有 SPA fallback → 200 HTML。綠在測試環境卻描述不了生產 | **刪除型工作的斷言鎖「路由表／符號表裡沒有」,不要鎖狀態碼** | TICKET-H ④ |
| 5 | **身分不同** | 落檔目錄是 `root:root`,而生產 extractor 以 `sudo -u nestmemory` 跑;熱修時用 root 測所以看起來是好的,生產一定失敗而且被 `except` 自吞成一行 stderr | **用生產的那個身分實測**;目錄權限靠 `os.makedirs(mode=0o700)` 在新建時就對,不靠人記得 chown | TICKET-K |

下次再撞到新的一種,加一列,不要只寫在工單裡。

---

## 二、驗證

- **拆掉修復必須紅**(先破後立)。綠燈不是通過,反向對照紅了才是。
- **這條對驗證者自己也適用**:規劃窗覆核 TICKET-K 時,前兩次反向對照都沒紅,
  是它自己的 harness 錯(golden_runner 硬插 `sys.path`,暫存複本沒被載入;改路徑又弄斷 import)。
  **綠得太快先懷疑自己的量測,不要先相信結論。**(TICKET-K 覆核)
- **改到無人看管的排程腳本,上線前用複本真跑一次,不只靠 golden。**
  明晚 03:30 沒有人在看,而改的正是那支腳本。(TICKET-K 覆核採納)
- **量測工具的預設行為會偽造結論。** 兩次形狀不同、道理一樣:
  curl 送出前自行 `remove_dot_segments`,讓 `/mcp-KEY/../mcp` 看起來像穿越成功
  (加 `--path-as-is` 送字面路徑後全部 404);`pgrep -af "chrome-headless-shell"`
  匹配到自己那行 pgrep 的命令列,於是「閒置時沒有殘留進程」看起來是假的
  (改用 `/proc/*/comm` 與 unit 的 `cgroup.procs` 重量:0 個)。
  **探測會進自己的結果集**——第 1 種形狀的變體。測之前先問:這個工具替我做了什麼我沒要求的事?
  (方案B、第三批 ②)
- **不信自己的綠燈**:0.19 秒跑完的端到端測試要去查它到底跑了什麼,
  並把「產物必須是 patch 過的」寫成斷言。(TICKET-I A 段覆核記功)
- 繞過迴圈直接呼叫函式,測到的是「沒有迴圈的世界」。(TICKET-H,規劃窗自述)

---

## 三、施工

- **重構會把既有的錯誤路徑弄丟,而且很安靜。** 抽 `commit_batch()` 時把 `extract()` 移出 `try`,
  LLM 失敗會讓批次停在 pending 而不是 failed;補 `_fail_batch()` 給兩邊共用。
  抽函式後要逐條回頭看原本的 except 覆蓋到哪裡。(TICKET-K)
- **施工者一旦失聯就沒人能救自己**:改動線上服務的腳本要自帶回滾保險
  (新舊路徑任一非 200 就把備份 cp 回去重啟),不要把還原押在人身上。(方案B ①)
- **等空閒再重啟**:輪詢 `pgrep -P $(MainPID)`,連續數秒沒有子進程再 restart,不要猜時機。(方案B ①)
- **修一處之前先 grep 有沒有第二處。** 工單點名 `claude.py:314`,實測 `memory_bridge.py`
  的 `ANCHOR_URL` 也寫死舊路徑;而且 runtime 與 legacy 兩棵樹都要改,
  只改 runtime 下次重建就退回。(方案B ①⑤)
- **改底色/改樣式時 grep 同名 selector 的所有歷史層**:三層舊 CSS 各畫了一次 border,
  飽和底看不見、淺底現形。(v115)
- **`disable` 擋不住 dbus/socket activation。** `disable` 只擋開機自啟。
  `multipathd` 有 `multipathd.socket` 會把它叫回來;`fwupd`/`udisks2`/`upower` 是 dbus-activated,
  停完當下是 inactive,幾十分鐘後有人查一次 dbus 就又活了(`fwupd` 甚至是 `static`,根本不能 disable)。
  真的要停就 `mask`——建立指向 /dev/null 的 symlink,不刪任何檔案、`unmask` 即還原。
  **停用之後隔一段時間再回頭看一次**,不要停完當下看到 inactive 就結案。(第三批 ①)
- **改到常駐服務的檔,必須在該服務真的重啟一次之後驗證,diff 對不算數。**
  方案 B ⑤a「第二處」在 legacy `memory_bridge.py` 加了 `os.environ.get(...)` 卻沒 `import os`;
  服務當時沒重啟,錯誤躺了九天,9/11 06:36 unattended-upgrade 升 libc/python 後 needrestart
  替所有 python 服務重啟,它每 3 秒摔一次、摔了五千多次沒人知道:09:00 喚醒被壓、
  模型清單退回 fallback、cn 四回合跑在 sonnet-4-6。規劃窗覆核只看了 diff,漏審。
  至少要 `python -c "import <模組>"` 過,能重啟的就真的重啟一次看它活著;
  另外「摔了五千次沒人知道」本身是第二個洞:常駐服務要有 crash loop 警報。(9/11 事故)
- **不要為了方便打穿刻意立的邊界。** 密鑰放 `/root/` 而 bridge 以 chatagent 跑,
  正解是把密鑰移到雙方都讀得到的單一正本目錄,不是加 ACL。(方案B ②)

---

## 四、界線

- **工單沒寫的不要順手做。** 糯糯說「更進一步的美化是美化窗的工作」。(TICKET-H)
- **工單寫錯了方法就說,不要照抄。** TICKET-I 寫「比 manifest sha」,
  但 manifest 只記四檔,`autonomy_tool.py` 在裡面沒有位置——而它正是會被刪掉的那一個。
  改比「即將寫入的 staging vs 現行 runtime」逐檔。規劃窗採納。(TICKET-I A 段)
- **拒做也是交付的一部分,附理由。** TICKET-K 第 1 點的壞 JSON regex 救援:
  檔案室的東西要被當成事實引用,寧可明晚重抽一次完整的,也不要今晚存進一筆半真的。
  規劃窗同意並把該項自工單刪除。(TICKET-K 覆核)
- **「版控」是指資產在版控,不是資產在磁碟上另一個目錄。**
  護欄與 `autonomy_tool.py` 一度只活在 VPS 上,而護欄是那顆雷的唯一保險。
  生產現行版要收進 repo 的 `prod/`,md5 逐位元對生產。(TICKET-I 補件一)
