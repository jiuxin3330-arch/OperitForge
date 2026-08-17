#!/bin/bash
# Nest Memory — 異地加密備份(複審必辦):age 公鑰加密 → GitHub private repo
# 私鑰糯糯保管,VPS 只有公鑰(state/age-recipient.txt)。
# 推到 OperitForge 的 nest-backup 孤兒分支,單一 commit 滾動覆蓋(amend+force),
# 保留最新 7 份,遠端體積有界。
set -euo pipefail
umask 077

BASE=/srv/nest-memory
REPO=$BASE/offsite-repo
RECIPIENT=$(cat "$BASE/state/age-recipient.txt")
LATEST=$(ls -1t "$BASE"/backup/nest-memory-*.tar.gz | head -1)
NAME=$(basename "$LATEST" .tar.gz)

mkdir -p "$REPO/backups"
age -r "$RECIPIENT" -o "$REPO/backups/$NAME.tar.gz.age" "$LATEST"

# 滾動保留 7 份
ls -1t "$REPO"/backups/*.age | tail -n +8 | xargs -r rm -f

cd "$REPO"
git add -A
if git rev-parse HEAD >/dev/null 2>&1; then
  git -c user.name=nest-backup -c user.email=nest-backup@vps commit -q --amend -m "nest-memory encrypted backups (rolling)"
else
  git -c user.name=nest-backup -c user.email=nest-backup@vps commit -q -m "nest-memory encrypted backups (rolling)"
fi
GIT_SSH_COMMAND="ssh -i /root/.ssh/nest_backup_deploy -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
  git push -q -f origin nest-backup

printf '{"ts": "%s", "ok": true, "file": "%s"}\n' "$(date -Iseconds)" "$NAME.tar.gz.age" \
  > "$BASE/health/offsite_last_success.json"
chown nestmemory:nestmemory "$BASE/health/offsite_last_success.json"
