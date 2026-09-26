#!/bin/bash
# 用法：hf_rollback.sh [snapshot-dir]  → 預設用最新一份 dist.hf-snap-*；可重複按（冪等：同一份快照不會被吃掉）
# 現行 dist 整份搬去 dist.hf-undone-<ts>（保留最近 3 份），快照複製一份換上。
source "$(dirname "$0")/hf_lib.sh"
SNAP="${1:-$(ls -1d "$FE"/dist.hf-snap-* 2>/dev/null | sort | tail -1)}"
test -n "$SNAP" && test -f "$SNAP/index.html" || { log "rollback FAILED: no snapshot"; exit 1; }
FROM="$(live_bundle "$DIST")"
cp -a "$SNAP" "$FE/dist.hf-incoming"
mv "$DIST" "$FE/dist.hf-undone-$(ts)"
mv "$FE/dist.hf-incoming" "$DIST"
log "rollback $FROM -> $(live_bundle "$DIST") using $SNAP"
prune undone
