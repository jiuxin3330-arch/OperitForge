#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import fnmatch
import hashlib
import json
import re
import shutil
from pathlib import Path

from version_bridge_runtime_patch import (
    patch_actor_source,
    patch_actor_thinking_block_source,
    patch_claude_source,
    patch_claude_visible_thinking_source,
    patch_main_artifact_dir_source,
    patch_main_context_source,
    patch_main_fresh_session_source,
    patch_main_photo_root_source,
    patch_memory_bridge_comment_injection_source,
    patch_main_heartbeat_source,
    patch_main_project_dir_source,
    patch_store_source,
    patch_usage_token_file_source,
    patch_wake_tool_source,
)

SOURCE = Path("/srv/chatnest/full-stack")
DEFAULT_TARGET = Path("/srv/chatnest-next/runtime/version-bridge-app")
# TICKET-I B1(裁定乙):只屬於 bridge、legacy 沒有的檔案。
# 放程式碼而不是把 266 行塞進 patch 源碼的字串常數 —— 見 bridge-extras/README.md。
BRIDGE_EXTRAS = Path("/srv/chatnest-next/bridge-extras")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument(
        "--overwrite-drifted-runtime",
        action="store_true",
        help=(
            "即使現行 runtime 領先 patch 源碼也照樣覆蓋。"
            "只有在你確認那些差異都已回填進 patch 源碼之後才該用(見 TICKET-I)。"
        ),
    )
    args = parser.parse_args()
    source = args.source.resolve()
    target = args.target.resolve()
    if source != SOURCE.resolve():
        raise SystemExit("refusing unexpected Legacy source")
    staging = target.with_name(target.name + ".staging")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, mode=0o700)
    shutil.copytree(
        source / "app",
        staging / "app",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.bak*"),
    )
    shutil.copytree(source / "static", staging / "static")
    for name in (
        "PERSONA.md",
        "models.json",
        "STACKCHAN_MCP.md",
        "splash_lines.json",
        "themes.json",
        "vapid_public.txt",
    ):
        path = source / name
        if path.is_file():
            shutil.copy2(path, staging / name)
    for name in ("uploads", "photos", "artifacts", "fonts"):
        (staging / name).mkdir(exist_ok=True)
    # tts_cache 與 legacy(8787) 共用同一實體目錄:語音由 bridge 生成、經 legacy /api/voice 服務
    # (2026-08-17 修復聊天語音播放;詳見 /root/nest-memory/PHASE0_NOTES.md)
    tts_link = staging / "tts_cache"
    if not tts_link.exists():
        tts_link.symlink_to("/srv/chatnest/full-stack/tts_cache")

    actor_path = staging / "app" / "actor.py"
    actor_path.write_text(
        patch_actor_thinking_block_source(
            patch_actor_source(actor_path.read_text(encoding="utf-8"))
        ),
        encoding="utf-8",
    )
    claude_path = staging / "app" / "claude.py"
    claude_path.write_text(
        patch_claude_visible_thinking_source(
            patch_claude_source(claude_path.read_text(encoding="utf-8"))
        ),
        encoding="utf-8",
    )
    store_path = staging / "app" / "store.py"
    store_path.write_text(
        patch_store_source(store_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    extras = sorted(BRIDGE_EXTRAS.glob("*.py")) if BRIDGE_EXTRAS.is_dir() else []
    for extra in extras:
        shutil.copy2(extra, staging / "app" / extra.name)

    wake_tool_path = staging / "app" / "wake_tool.py"
    wake_tool_path.write_text(
        patch_wake_tool_source(wake_tool_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    usage_path = staging / "app" / "usage.py"
    usage_path.write_text(
        patch_usage_token_file_source(usage_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    memory_bridge_path = staging / "app" / "memory_bridge.py"
    memory_bridge_path.write_text(
        patch_memory_bridge_comment_injection_source(
            memory_bridge_path.read_text(encoding="utf-8")
        ),
        encoding="utf-8",
    )

    main_path = staging / "app" / "main.py"
    text = patch_main_project_dir_source(main_path.read_text(encoding="utf-8"))
    text = patch_main_context_source(text)
    text = patch_main_artifact_dir_source(text)
    text = patch_main_photo_root_source(text)
    text = patch_main_fresh_session_source(text)
    text = patch_main_heartbeat_source(text)
    fallback = '''                except (SessionResumeError, StopAsyncIteration):
                    logger.info("session resume failed for conv=%s, retrying without session", conv_id)
                    chat_args = (prompt, conv_id, None, body.model,
                                 body.effort, body.extended, log_timing)
                    chat_stream = stream_chat(*chat_args, on_complete=finalize_turn)
                    first_chunk = await chat_stream.__anext__()
'''
    replacement = '''                except SessionResumeError:
                    logger.warning("version bridge resume failed for conv=%s", conv_id)
                    raise
                except StopAsyncIteration as exc:
                    logger.warning("version bridge session ended before first event for conv=%s", conv_id)
                    raise SessionResumeError("version bridge session ended before first event") from exc
'''
    if fallback not in text:
        raise SystemExit("Legacy resume fallback pattern changed; refusing runtime build")
    text = text.replace(fallback, replacement, 1)
    text = re.sub(
        r'''            try:\n                preview = \(text or ""\)\.strip\(\)\.replace\("\\n", " "\)\[:60\]\n                asyncio\.create_task\(asyncio\.to_thread\(\n                    send_push_all, "牧牧回覆了💙", preview or "回覆完成了～", "/",\n                \)\)\n            except Exception:\n                logger\.exception\("push dispatch failed"\)\n''',
        '            # Version bridge never sends push notifications.\n',
        text,
        count=1,
    )
    text = re.sub(
        r'''                        try:\n                            preview = \(response_text or ""\)\.strip\(\)\.replace\("\\n", " "\)\[:60\]\n                            asyncio\.create_task\(asyncio\.to_thread\(\n                                send_push_all, "牧牧回覆了💙", preview or "回覆完成了～", "/",\n                            \)\)\n                        except Exception:\n                            logger\.exception\("push dispatch failed"\)\n''',
        '                        # Version bridge never sends push notifications.\n',
        text,
        count=1,
    )
    if "retrying without session" in text:
        raise SystemExit("unsafe resume fallback remains in runtime clone")
    if "send_push_all, \"牧牧回覆了💙\"" in text:
        raise SystemExit("push dispatch remains in runtime clone")
    text += '\n# CHATNEST_VERSION_BRIDGE_RUNTIME_V1\n'
    main_path.write_text(text, encoding="utf-8")

    manifest = {
        "source": str(source),
        "source_main_sha256": sha256(source / "app" / "main.py"),
        "source_actor_sha256": sha256(source / "app" / "actor.py"),
        "runtime_main_sha256": sha256(main_path),
        "runtime_actor_sha256": sha256(actor_path),
        "runtime_claude_sha256": sha256(claude_path),
        "runtime_store_sha256": sha256(store_path),
        "actor_classifier_hardened": True,
        "thinking_block_fallback": True,
        "visible_thinking_display": "summarized",
        "cwd_compatibility_hardened": True,
        "production_touch_queue_isolated": True,
        "registry_project_dir_hardened": True,
        "hidden_context_transport": True,
        "passive_memory_latest_query_only": True,
        "next_owned_time_context": True,
        "prompt_metrics_emitted": True,
        "concise_tool_index": True,
        "on_demand_tool_help": True,
        "tool_help_contract_checked": True,
        "content_free_time_fallback": True,
        "compaction_rotation_observed": True,
        "detailed_usage_emitted": True,
        "resume_fallback_removed": True,
        "push_dispatch_removed": True,
        "noncancelling_heartbeat": True,
        "next_owned_wake_schedule": True,
        "artifact_dir_from_home": True,
        "bridge_extras": {
            extra.name: sha256(staging / "app" / extra.name) for extra in extras
        },
        "usage_token_from_bridge_home": True,
        "comment_injection_auto_marked": True,
        "photo_root_srv_default": True,
        "swap_fresh_session": True,
    }
    (staging / "runtime-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
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
        raise SystemExit("\n".join(message))
    if target.exists():
        shutil.rmtree(target)
    staging.rename(target)
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
