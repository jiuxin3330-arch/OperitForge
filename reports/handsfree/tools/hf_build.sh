#!/bin/bash
# 用法：hf_build.sh  → 在 systemd-run 記憶體上限下 tsc + vite build 到 staging（不碰線上 dist）
source "$(dirname "$0")/hf_lib.sh"
STAGE="$REP/stage-$(ts)"
log "build start -> $STAGE"
systemd-run --quiet --wait --pipe --collect \
  -p MemoryMax=900M -p MemorySwapMax=400M \
  --working-directory="$FE" \
  --setenv=PATH="$NODEBIN:/usr/bin:/bin" \
  /bin/bash -c "node_modules/.bin/tsc -b && node_modules/.bin/vite build --outDir '$STAGE' --emptyOutDir" \
  2>&1 | tail -n 15
test -f "$STAGE/index.html" || { log "build FAILED (no index.html)"; exit 1; }
log "build ok $STAGE bundle=$(live_bundle "$STAGE")"
echo "$STAGE"
