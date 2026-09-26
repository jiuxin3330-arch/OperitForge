#!/bin/bash
# 用法：hf_publish.sh <stage-dir> "一句人話說明"
# 先把現行 dist 整份快照成 dist.hf-snap-<ts>（保留最近 3 份），再合併發佈（不 --delete，保住 apk／舊 assets），index.html 最後才換。
source "$(dirname "$0")/hf_lib.sh"
STAGE="${1:?stage dir}"; WHY="${2:-}"
test -f "$STAGE/index.html"
SNAP="$FE/dist.hf-snap-$(ts)"
cp -a "$DIST" "$SNAP"
log "snapshot $SNAP (was $(live_bundle "$DIST"))"
rsync -a --exclude=index.html "$STAGE"/ "$DIST"/
cp -p "$STAGE/index.html" "$DIST/index.html.hf-new" && mv -f "$DIST/index.html.hf-new" "$DIST/index.html"
log "publish $(live_bundle "$DIST") from $STAGE :: $WHY"
prune snap
