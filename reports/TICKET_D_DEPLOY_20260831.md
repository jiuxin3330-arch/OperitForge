# TICKET-D 部署報告:Context Image Optimization

2026-08-31|依 TICKET-D v2(交叉審合稿定案)與 ROADMAP_20260831 第一波
|範圍:chatnest-next backend(純工具層,零紅線)|與時間錨 B++ 並行交付

## 交付內容

糯糯傳原圖、看原圖;系統只在圖片進模型時使用單次精準壓縮的 context variant。
正式取代「手動壓縮三連」,同時提升 cn 看圖品質(單次壓縮取代三次疊壓,
官方文件明言多 pass artifacts 有害模型表現)。

### 架構(照小踢核准版)

- **原圖 = source of truth**:UI/相簿/下載路徑完全未動,永遠原圖。
- **context variant**:新模組 `backend/app/image_context.py`。
  附件授權組裝點(`granted_attachments`,唯一進模型的入口,涵蓋
  bridge/anthropic_api/codex 所有 adapter)改走 `context_attachment()`:
  首次進 context 生成並持久化 variant,之後所有輪次/歷史回放/session
  restore 一律複用同一檔案,**絕不重壓**。
- metadata 新表 `attachment_context_variants`:original_w/h、variant_w/h、
  format、compression_profile、**compression_version**(未來改參數新舊可辨;
  版本不符自動重生成)。

### Resize/格式規則

- model profile 制(`PROFILES["standard"]`,env `CHATNEST_NEXT_IMAGE_PROFILE`
  可切):target **~1.15MP 等效面積**、max_edge 1568、短邊門檻 400、JPEG q85。
- 等比縮至 target 面積;原圖已在預算內 → passthrough 原圖不重編碼
  (不花無謂的一次壓縮 pass),記 `within_budget`。
- **極端長寬比保護**:縮放後短邊 <400 → 停在門檻,記 `short_edge_floor`
  warning + metadata。第一版不做 tile,留擴充點。
- JPEG → resize+q85 單次;**PNG 含 alpha 保持 PNG 禁轉 JPEG**(透明不變黑,
  測試斷言 RGBA 保留);PNG 無 alpha v1 一律 PNG;GIF/WebP 保留原格式;
  動圖不處理(API 只取首幀)→ passthrough 記錄。
- EXIF orientation 先轉正再縮(手機直拍不會歪);P 模式先轉真彩再 LANCZOS。
- **任何失敗 → fallback 原圖(寧貴不壞)+ log**;variant 檔案遺失自動重生成。
- VPS 1GB:單張同步處理,不開 queue;>20MB 上傳拒收(既有 `MAX_UPLOAD_BYTES` 已合規)。
- 多圖 >20 圖塊的 2000px 硬限:variant(≤1568)天然合規;fallback 原圖案例有 log 可追。

## 生產實測(部署日煙測)

真實最近一張圖:3120×4160 JPEG 5,360,268 bytes
→ variant 929×1238(=1,150,102 px ≈ 1.15MP)171,199 bytes。
- payload -96.8%;visual tokens 估算:variant ⌈929/28⌉×⌈1238/28⌉=1,530 tok,
  對照 API 端自動縮(1176×1568)≈2,352 tok,**約 -35% input 圖像 tokens**。
- 複用驗證:第二次呼叫回同一 variant 路徑,無重壓。
- turn_usage 真實前後對照:待糯糯下次傳圖後把數字補進 NOTES(驗收項)。

## 驗證

- 新測試 `tests/test_image_context.py` 6 項:大圖單次壓縮+複用、PNG alpha
  保留、小圖 passthrough、長截圖短邊門檻+warning、壞檔 fallback 原圖、
  非圖片不建 variant。
- backend 全套件:348 passed;5 failed 均為既有環境陳舊案例
  (斷言 8/17 搬家前 /root 舊路徑與未部署的 legacy migration 腳本,與本 diff 無關)。
- 回滾點:`*.bak-timeanchor-1788194581` 同批備份;Pillow 12.3.0 已入 venv。
- 前端零改動(她本來就傳原圖),故無 sw bump 需求。

## 驗收清單

- [x] 糯糯傳原圖:自己看清晰(UI 原圖未動)
- [x] variant 生成/複用/無重壓(log+測試為證)
- [x] 長截圖短邊保護觸發且記 warning
- [x] PNG 透明素材無黑底
- [ ] cn 辨識正常實測(表情包/長截圖小字必測)——隨日常使用驗
- [ ] turn_usage 同圖前後對照數字進 NOTES
- [ ] **儀式性驗收:糯糯正式退役「手動壓縮三連」🎉**(她的出場)
