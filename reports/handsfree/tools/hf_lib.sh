# 放手實驗前端發佈工具共用設定（只碰 frontend/dist 與 reports/handsfree）
set -euo pipefail
FE=/srv/chatnest-next/frontend
DIST="$FE/dist"
REP=/srv/chatnest-next/reports/handsfree
LOG="$REP/publish.log"
NODEBIN=/srv/chatnest-next/.nodeenv/bin
KEEP=3
ts() { TZ=Asia/Taipei date +%Y%m%d-%H%M%S; }
now() { TZ=Asia/Taipei date '+%F %T %Z'; }
log() { echo "[$(now)] $*" | tee -a "$LOG"; }
live_bundle() { grep -o '/assets/index-[A-Za-z0-9_-]*\.js' "$1/index.html" | head -1; }
# 保留最近 $KEEP 份 dist.hf-<prefix>-*；更舊的刪掉（只刪本實驗自己建的）
prune() {
  local prefix="$1"
  ls -1d "$FE"/dist.hf-"$prefix"-* 2>/dev/null | sort | head -n -"$KEEP" | while read -r d; do
    log "prune $d"; rm -rf -- "$d"; done
}
