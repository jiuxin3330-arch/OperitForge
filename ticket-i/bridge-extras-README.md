# bridge-extras

只屬於 version bridge、legacy 沒有的檔案。

`build_version_bridge_runtime.py` 會把這裡的每個 `.py` 複製進 `staging/app/`,
並把它們的 sha 記進 `runtime-manifest.json`。

之所以不放進 patch 源碼當字串:這裡是真正的程式碼,該以程式碼的形式存在、
能被 import、被 lint、被 diff。266 行的東西塞進字串常數,下次要改它的人會恨我們。

之所以不回填進 legacy(`/srv/chatnest/full-stack/app/`):legacy 用不到它,
放過去只會讓那邊多一個沒有呼叫者的檔。

現有內容:

| 檔案 | 為什麼只屬於 bridge |
|---|---|
| `autonomy_tool.py` | 自主時段的 MCP server 與待辦紙條,由 bridge 的 `claude.py` 載入 |
