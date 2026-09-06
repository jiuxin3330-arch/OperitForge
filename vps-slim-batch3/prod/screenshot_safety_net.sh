#!/bin/bash
# 第三批 ② 安全網:正常路徑是 backend 派 job 時立觸發檔、systemd .path 拉起 worker。
# 萬一那條路徑壞掉(觸發檔寫不進去、path unit 沒 enable),job 會安靜卡在 queued。
# 這支每 30 分鐘用唯讀連線數一次 queued,有才立觸發檔——成本是一次 sqlite SELECT,
# 不是把 chromium 叫起來。不直接 systemctl start,是為了讓所有啟動都走同一條路徑。
set -u
DB='file:/root/chatnest-next/data/app.sqlite3?mode=ro'
TRIGGER=/srv/chatnest-next/data/screenshot-trigger/pending
n=$(sqlite3 -readonly "$DB" "select count(*) from screenshot_jobs where state='queued';" 2>/dev/null)
if [ -z "$n" ]; then
  echo "safety-net: 讀不到 DB,不動作"
  exit 0
fi
if [ "$n" -gt 0 ]; then
  echo "safety-net: 有 $n 個 queued job 沒被撿走,立觸發檔"
  install -d -m 700 "$(dirname "$TRIGGER")"
  touch "$TRIGGER"
else
  echo "safety-net: queued=0"
fi
