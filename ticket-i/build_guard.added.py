"""TICKET-I A 段:加進 scripts/build_version_bridge_runtime.py 的漂移護欄。

三處接線:

1. 檔頭 import 加 difflib、fnmatch
2. 下面這段插在 sha256() 之後
3. main() 裡加旗標,並在 staging.rename(target) 之前擋下來:

       parser.add_argument(
           "--overwrite-drifted-runtime",
           action="store_true",
           help=(
               "即使現行 runtime 領先 patch 源碼也照樣覆蓋。"
               "只有在你確認那些差異都已回填進 patch 源碼之後才該用(見 TICKET-I)。"
           ),
       )

       drifted, backup_count = _drift_report(staging, target)
       if drifted and not args.overwrite_drifted_runtime:
           stale = _manifest_sha_drift(target)
           message = [
               "",
               "拒絕覆蓋:現行 runtime 領先 patch 源碼,這次寫入會弄丟下面這些改動。",
               "",
               f"漂移檔案({len(drifted)} 個):",
               *drifted,
           ]
           if stale:
               message += ["", "manifest 自己記的 sha 也已經對不上:", *stale]
           if backup_count:
               message += [
                   "",
                   f"(另有 {backup_count} 個 .bak 備份檔也會一起消失。build 本來就不收它們,"
                   "不算漂移,但那是別人的回滾點。)",
               ]
           message += [
               "",
               "這些差異要先回填進 patch 源碼(每條一支 patch 函式 + manifest 旗標,",
               "runtime 由同一支函式產生,不要手打),回填完這裡自然就不再擋。",
               "詳見 TICKET-I:/root/nest-memory/TICKET_I_runtime_drift_backport.md",
               "",
               f"要對照差異,build 產物留在:{staging}",
               "確定要覆蓋(差異都已回填)才加 --overwrite-drifted-runtime。",
               "",
           ]
           raise SystemExit("\\n".join(message))
       if target.exists():
           shutil.rmtree(target)
       staging.rename(target)
"""

# TICKET-I(2026-09-02):runtime 曾經領先 patch 源碼而沒人發現,直到有人打算重 build。
# 那次沒炸是因為施工者先 build 到臨時目錄比對 —— 運氣加紀律,不是設計。
# 這裡把那個動作變成腳本自己會做的事。
DRIFT_IGNORED = {"runtime-manifest.json"}


def _is_build_ignored(name: str) -> bool:
    """build 本來就不收的東西:備份檔與 pyc。

    copytree 用的是 ignore_patterns("__pycache__", "*.pyc", "*.bak*"),
    所以 staging 裡沒有它們是預期行為,不是漂移。把它們算進漂移清單,
    只會讓十幾個施工回滾點淹掉真正重要的那幾個檔。
    """
    return fnmatch.fnmatch(name, "*.bak*") or fnmatch.fnmatch(name, "*.pyc")


def _relative_files(root: Path) -> set[str]:
    return {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def _line_delta(current: Path, incoming: Path) -> str:
    """兩份文字檔差幾行。二進位檔就不報行數,只說內容不同。"""
    try:
        before = current.read_text(encoding="utf-8").splitlines()
        after = incoming.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, ValueError):
        return "內容不同(二進位)"
    changed = sum(
        1
        for line in difflib.unified_diff(before, after, n=0)
        if line[:1] in "+-" and not line.startswith(("---", "+++"))
    )
    return f"內容不同({changed} 行)"


def _drift_report(staging: Path, target: Path) -> tuple[list[str], int]:
    """列出「這次寫入會覆蓋或刪掉」的東西。

    比對的是即將寫入的內容與現行 runtime 本身,不是只比 manifest 記的那幾個 sha
    —— manifest 只記 main/actor/claude/store 四個檔,而 autonomy_tool.py 這種
    只存在於 runtime 的檔案,正是靠 manifest 永遠看不見的那一類。
    """
    if not target.exists():
        return [], 0
    incoming = _relative_files(staging) - DRIFT_IGNORED
    current = _relative_files(target) - DRIFT_IGNORED
    backups = {name for name in current if _is_build_ignored(Path(name).name)}
    current -= backups
    drifted: list[str] = []
    for name in sorted(current - incoming):
        drifted.append(f"  {name} —— 只在 runtime 有,這次寫入會刪掉它")
    for name in sorted(current & incoming):
        here, there = target / name, staging / name
        if here.read_bytes() != there.read_bytes():
            drifted.append(f"  {name} —— {_line_delta(here, there)}")
    return drifted, len(backups)


def _manifest_sha_drift(target: Path) -> list[str]:
    """補充信號:manifest 自己記的 sha 與現行檔案對不上。

    這一項抓不到全部(見 _drift_report 的說明),但 manifest 說謊本身就值得講。
    """
    manifest_path = target / "runtime-manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["  runtime-manifest.json —— 讀不出來"]
    pairs = {
        "runtime_main_sha256": "app/main.py",
        "runtime_actor_sha256": "app/actor.py",
        "runtime_claude_sha256": "app/claude.py",
        "runtime_store_sha256": "app/store.py",
    }
    stale = []
    for key, name in pairs.items():
        recorded = manifest.get(key)
        path = target / name
        if not recorded or not path.is_file():
            continue
        actual = sha256(path)
        if recorded != actual:
            stale.append(f"  {name} —— manifest 記 {recorded[:12]}…,實際 {actual[:12]}…")
    return stale
