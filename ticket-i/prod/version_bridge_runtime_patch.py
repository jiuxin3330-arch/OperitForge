from __future__ import annotations

"""Pure source transformer for the isolated Next-owned MuMu bridge.

The production Legacy source is input only. The returned source is written to
ChatNest Next's isolated runtime clone; this module never edits production.
"""

_COMBINED_BRANCH = '''            elif isinstance(sdk_message, (_AssistantMessage, _UserMessage)):
                for block in getattr(sdk_message, "content", []) or []:
                    if isinstance(block, _TextBlock) and not got_streaming_text:
                        text = block.text or ""
                        if text and not first_text_token_seen:
                            first_text_token_seen = True
                            if callback:
                                callback("first_text_token")
                        if text:
                            await _emit({"event": "delta", "text": text})
                    elif isinstance(block, _ToolUseBlock):
                        await _emit({
                            "event": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })
                    elif isinstance(block, _ToolResultBlock):
                        content = block.content
                        if isinstance(content, list):
                            content = "".join(
                                c.get("text", "") if isinstance(c, dict) else str(c)
                                for c in content
                            )
                        await _emit({
                            "event": "tool_result",
                            "tool_use_id": block.tool_use_id,
                            "content": content or "",
                            "is_error": bool(block.is_error),
                        })
'''

_SPLIT_BRANCH = '''            elif isinstance(sdk_message, _AssistantMessage):
                for block in getattr(sdk_message, "content", []) or []:
                    if isinstance(block, _TextBlock) and not got_streaming_text:
                        text = block.text or ""
                        if text and not first_text_token_seen:
                            first_text_token_seen = True
                            if callback:
                                callback("first_text_token")
                        if text:
                            await _emit({"event": "delta", "text": text})
                    elif isinstance(block, _ToolUseBlock):
                        await _emit({
                            "event": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })
            elif isinstance(sdk_message, _UserMessage):
                # UserMessage text is either the owner's prompt or an internal
                # auto-compaction summary. Neither is assistant output.
                # Tool results remain useful operational trace events.
                for block in getattr(sdk_message, "content", []) or []:
                    if not isinstance(block, _ToolResultBlock):
                        continue
                    content = block.content
                    if isinstance(content, list):
                        content = "".join(
                            c.get("text", "") if isinstance(c, dict) else str(c)
                            for c in content
                        )
                    await _emit({
                        "event": "tool_result",
                        "tool_use_id": block.tool_use_id,
                        "content": content or "",
                        "is_error": bool(block.is_error),
                    })
'''

_HELPERS = r'''

def _same_project_dir(initialized_cwd, expected):
    """Accept an omitted SDK cwd and normalize equivalent project paths."""
    if not initialized_cwd:
        return True
    try:
        return Path(str(initialized_cwd)).expanduser().resolve() == Path(str(expected)).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False


def _session_compaction_marker_count(session_id, project_dir):
    """Count structural transcript markers without reading message text."""
    if not session_id:
        return 0
    try:
        UUID(str(session_id))
    except (TypeError, ValueError):
        return 0
    try:
        from claude_agent_sdk._internal.sessions import _canonicalize_path, _get_project_dir
        transcript = _get_project_dir(_canonicalize_path(project_dir)) / f"{session_id}.jsonl"
        count = 0
        with transcript.open("r", encoding="utf-8") as handle:
            for line in handle:
                if (
                    '"subtype":"compact_boundary"' not in line
                    and '"subtype": "compact_boundary"' not in line
                    and '"isCompactSummary":true' not in line
                    and '"isCompactSummary": true' not in line
                ):
                    continue
                try:
                    item = json.loads(line)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if item.get("subtype") == "compact_boundary" or item.get("isCompactSummary") is True:
                    count += 1
        return count
    except OSError:
        return 0


def _number(mapping, *names):
    if not isinstance(mapping, dict):
        return 0
    for name in names:
        value = mapping.get(name)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def _normalized_result_usage(result, context_usage, model, session_path):
    usage = result.usage if isinstance(result.usage, dict) else {}
    uncached = _number(usage, "input_tokens", "inputTokens")
    cache_creation = _number(usage, "cache_creation_input_tokens", "cacheCreationInputTokens")
    cache_read = _number(usage, "cache_read_input_tokens", "cacheReadInputTokens")
    output = _number(usage, "output_tokens", "outputTokens")
    one_hour = 0
    five_minute = 0
    cache_detail = usage.get("cache_creation") if isinstance(usage, dict) else None
    if isinstance(cache_detail, dict):
        one_hour = _number(cache_detail, "ephemeral_1h_input_tokens", "ephemeral1hInputTokens")
        five_minute = _number(cache_detail, "ephemeral_5m_input_tokens", "ephemeral5mInputTokens")

    # Some SDK/CLI releases put per-model counters only in modelUsage.
    model_usage = result.model_usage if isinstance(result.model_usage, dict) else {}
    if not (uncached or cache_creation or cache_read or output):
        for counters in model_usage.values():
            if not isinstance(counters, dict):
                continue
            uncached += _number(counters, "inputTokens", "input_tokens")
            cache_creation += _number(counters, "cacheCreationInputTokens", "cache_creation_input_tokens")
            cache_read += _number(counters, "cacheReadInputTokens", "cache_read_input_tokens")
            output += _number(counters, "outputTokens", "output_tokens")

    context = context_usage if isinstance(context_usage, dict) else {}
    payload = {
        # Preserve the legacy budget/ledger meaning: only newly billed input.
        # Cache creation/read remain separate truthful categories below.
        "input_tokens": uncached,
        "uncached_input_tokens": uncached,
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
        "cache_creation_1h_input_tokens": one_hour,
        "cache_creation_5m_input_tokens": five_minute,
        "output_tokens": output,
        "provider": "claude_cc",
        "session_path": session_path,
        "model": str(context.get("model") or model or ""),
        "reported": bool(usage or model_usage),
        "estimated": False,
    }
    for source, target in (
        ("totalTokens", "active_context_tokens"),
        ("maxTokens", "context_max_tokens"),
        ("autoCompactThreshold", "auto_compact_threshold"),
    ):
        value = context.get(source)
        if isinstance(value, (int, float)):
            payload[target] = int(value)
    if isinstance(context.get("isAutoCompactEnabled"), bool):
        payload["auto_compact_enabled"] = context["isAutoCompactEnabled"]
    if isinstance(context.get("percentage"), (int, float)):
        payload["context_percentage"] = float(context["percentage"])
    return payload
'''

_BEFORE_QUERY = '''        await self._client.query(request.prompt)
        collected: list[dict] = []
'''
_AFTER_QUERY = '''        resumed_session_id = getattr(request.options, "resume", None)
        compaction_markers_before = _session_compaction_marker_count(
            resumed_session_id,
            self.project_dir,
        )
        await self._client.query(request.prompt)
        collected: list[dict] = []
'''

_CWD_CHECK_OLD = '''                    initialized_cwd = sdk_message.data.get("cwd")
                    if initialized_cwd != self.project_dir:
                        raise RuntimeError("會話恢復失敗")
'''
_CWD_CHECK_NEW = '''                    initialized_cwd = sdk_message.data.get("cwd")
                    if not _same_project_dir(initialized_cwd, self.project_dir):
                        logger.warning(
                            "isolated session cwd mismatch expected=%s actual=%s",
                            self.project_dir,
                            initialized_cwd or "<missing>",
                        )
                        raise RuntimeError("會話恢復失敗")
'''

_RESULT_START = '''            elif isinstance(sdk_message, ResultMessage):
                result_seen = True
                done_chunk: dict = {
                    "event": "done",
                    "session_id": sdk_message.session_id,
                }
'''
_RESULT_REPLACEMENT = '''            elif isinstance(sdk_message, ResultMessage):
                result_seen = True
                compaction_markers_after = _session_compaction_marker_count(
                    sdk_message.session_id,
                    self.project_dir,
                )
                if compaction_markers_after > compaction_markers_before:
                    await _emit({"event": "context_compacted"})
                try:
                    context_usage = await self._client.get_context_usage()
                except Exception:
                    logger.exception("isolated context usage control request failed")
                    context_usage = {}
                await _emit({
                    "event": "usage",
                    **_normalized_result_usage(
                        sdk_message,
                        context_usage,
                        getattr(request.options, "model", None),
                        "next_bridge",
                    ),
                })
                done_chunk: dict = {
                    "event": "done",
                    "session_id": sdk_message.session_id,
                    "previous_session_id": resumed_session_id,
                    "session_rotated": bool(
                        resumed_session_id
                        and sdk_message.session_id
                        and str(resumed_session_id) != str(sdk_message.session_id)
                    ),
                }
'''


def patch_actor_source(source: str) -> str:
    """Return hardened actor source, refusing an unexpected Legacy shape."""
    if "CHATNEST_VERSION_BRIDGE_ACTOR_V2" in source:
        return source
    required = (_COMBINED_BRANCH, _BEFORE_QUERY, _RESULT_START, _CWD_CHECK_OLD)
    if not all(item in source for item in required):
        raise RuntimeError("Legacy actor shape changed; refusing bridge classifier patch")
    source = source.replace("import logging\n", "import logging\nimport json\n", 1)
    source = source.replace("from time import monotonic\n", "from pathlib import Path\nfrom time import monotonic\nfrom uuid import UUID\n", 1)
    anchor = "\n\nlogger = logging.getLogger(__name__)\n"
    if anchor not in source:
        raise RuntimeError("Legacy actor logger anchor missing")
    source = source.replace(anchor, _HELPERS + anchor, 1)
    source = source.replace(_BEFORE_QUERY, _AFTER_QUERY, 1)
    source = source.replace(_CWD_CHECK_OLD, _CWD_CHECK_NEW, 1)
    source = source.replace(_COMBINED_BRANCH, _SPLIT_BRANCH, 1)
    source = source.replace(_RESULT_START, _RESULT_REPLACEMENT, 1)
    return source + "\n# CHATNEST_VERSION_BRIDGE_ACTOR_V2\n"

_TOOLS_NOTE_START = 'TOOLS_NOTE = """'
_TOOLS_NOTE_END = '"""\n\nSUMMARY_PROMPT = '
_TOOLS_NOTE_NEW = '''TOOLS_NOTE = """【ChatNest 能力索引】
常駐提示只列能力，不載入私人內容。需要完整用法時，用 Bash 執行：
`python3 /srv/chatnest-next/scripts/mumu_tool_help.py list`
再依需要執行：
`python3 /srv/chatnest-next/scripts/mumu_tool_help.py show <分類>`

可查分類：diary、calendar、collection、work-mail、versions、screenshot、desire、memory、stackchan、voice、persona、wake、easter-egg、web、social、gmail、daifugo。
daifugo 是家庭大富豪牌局：糯糯或家人開房後可以自己入座當玩家，輪到自己時系統會用〔牌局喚醒·〕信封主動叫醒；別人的手牌看不到，出牌決策自己決定。
工具用途不要混淆：StackChan camera 是實體 StackChan 鏡頭「拍照」；要擷取網頁或 ChatNest 畫面時使用 screenshot 工具，不要以 stackchan_camera_check 代替網頁截圖。
日記、批註、情緒與身心日曆內容沒有自動載入；只有話題相關、需要或自己想關心時才查，未實際查閱前不可假裝知道。
Dashboard 工具身分由後端固定為 mumu；不要猜內部 URL、不要直接修改 SQLite／JSON。
重要事件、承諾、偏好與里程碑要實際使用 Anchor Memory 保存；不確定是否已記過時先搜尋，避免重複或濫存。"""'''

_TOUCH_GUARD_OLD = '''def consume_recent_touch_context(seconds: int = 600) -> str:
    """Atomically consume trusted recent touch events once across all chats."""
    if not _TOUCH_LOG_PATH.exists():
        return ""
'''

_TOUCH_GUARD_NEW = '''def consume_recent_touch_context(seconds: int = 600) -> str:
    """Atomically consume trusted recent touch events once across all chats."""
    # The isolated Next bridge must never consume the one-time production queue.
    if os.environ.get("CHATNEST_VERSION_BRIDGE") == "1":
        return ""
    if not _TOUCH_LOG_PATH.exists():
        return ""
'''

_STREAM_SIGNATURE_OLD = '''    timing_callback: Callable[[str], None] | None = None,
    on_complete: Callable | None = None,
) -> AsyncGenerator[dict, None]:
'''
_STREAM_SIGNATURE_NEW = '''    timing_callback: Callable[[str], None] | None = None,
    on_complete: Callable | None = None,
    hidden_context: str = "",
) -> AsyncGenerator[dict, None]:
'''

_SUBMIT_OLD = '''    outbox = await get_registry().submit(
        conv_id,
        message,
        options,
        fingerprint,
'''
_SUBMIT_NEW = '''    bounded_context = hidden_context.strip()
    query_message = (
        message
        if not bounded_context
        else (
            "[ChatNest 本回合附加背景；這不是屋主的新訊息，不要說成她剛剛講的。]\\n"
            + bounded_context
            + "\\n[附加背景結束；以下才是屋主本輪真正的訊息。]\\n\\n"
            + message
        )
    )
    yield {
        "event": "prompt_meta",
        "system_prompt_chars": len(system_prompt),
        "system_prompt_fingerprint": fingerprint,
        "hidden_context_chars": len(bounded_context),
        "user_query_chars": len(message),
    }
    outbox = await get_registry().submit(
        conv_id,
        query_message,
        options,
        fingerprint,
'''


def patch_claude_source(source: str) -> str:
    """Isolate touch/context and replace the stale fixed tool manual."""
    if "CHATNEST_VERSION_BRIDGE_CLAUDE_V4" in source:
        return source
    required = (
        _TOUCH_GUARD_OLD,
        _STREAM_SIGNATURE_OLD,
        _SUBMIT_OLD,
        _TOOLS_NOTE_START,
        _TOOLS_NOTE_END,
    )
    if not all(item in source for item in required):
        raise RuntimeError("Legacy Claude context/tool shape changed; refusing bridge patch")
    note_start = source.index(_TOOLS_NOTE_START)
    note_end = source.index(_TOOLS_NOTE_END, note_start) + 3
    source = source[:note_start] + _TOOLS_NOTE_NEW + source[note_end:]
    source = source.replace(_TOUCH_GUARD_OLD, _TOUCH_GUARD_NEW, 1)
    source = source.replace(_STREAM_SIGNATURE_OLD, _STREAM_SIGNATURE_NEW, 1)
    source = source.replace(_SUBMIT_OLD, _SUBMIT_NEW, 1)
    return source + "\n# CHATNEST_VERSION_BRIDGE_CLAUDE_V4\n"


_MAIN_CLAUDE_IMPORT_OLD = '''from app.claude import (
    SessionResumeError,
'''
_MAIN_CLAUDE_IMPORT_NEW = '''from app.claude import (
    PROJECT_DIR,
    SessionResumeError,
'''
_MAIN_REGISTRY_OLD = "    registry = configure_registry(str(ROOT))"
_MAIN_REGISTRY_NEW = "    registry = configure_registry(PROJECT_DIR)"


_VISIBLE_THINKING_OLD = '''    thinking, selected_effort = thinking_options(model_config, effort, extended)

    system_prompt = await build_system_prompt(message, model)
'''
_VISIBLE_THINKING_NEW = '''    thinking, selected_effort = thinking_options(model_config, effort, extended)
    # Claude Agent SDK 0.2.97+ omits visible thinking text by default on Opus 4.7+.
    # Keep reasoning enabled as configured, but explicitly request the provider's
    # summarized display so ChatNest can persist/show what the SDK is allowed to expose.
    if (
        thinking.get("type") in {"adaptive", "enabled"}
        and (model.startswith("claude-opus-5") or model.startswith("claude-opus-4-7"))
    ):
        thinking = {**thinking, "display": "summarized"}

    system_prompt = await build_system_prompt(message, model)
'''


def patch_claude_visible_thinking_source(source: str) -> str:
    """Request provider-summarized visible Thinking on Opus models that omit it by default."""
    if "CHATNEST_VERSION_BRIDGE_VISIBLE_THINKING_V1" in source:
        return source
    if _VISIBLE_THINKING_OLD not in source:
        raise RuntimeError("Claude thinking option shape changed; refusing visible-thinking patch")
    source = source.replace(_VISIBLE_THINKING_OLD, _VISIBLE_THINKING_NEW, 1)
    return source + "\n# CHATNEST_VERSION_BRIDGE_VISIBLE_THINKING_V1\n"


def patch_main_project_dir_source(source: str) -> str:
    """Make the actor registry use the configured SDK project, not clone root."""
    if "CHATNEST_VERSION_BRIDGE_MAIN_PROJECT_DIR_V2" in source:
        return source
    if _MAIN_CLAUDE_IMPORT_OLD not in source or _MAIN_REGISTRY_OLD not in source:
        raise RuntimeError("Legacy main registry shape changed; refusing bridge patch")
    source = source.replace(_MAIN_CLAUDE_IMPORT_OLD, _MAIN_CLAUDE_IMPORT_NEW, 1)
    source = source.replace(_MAIN_REGISTRY_OLD, _MAIN_REGISTRY_NEW, 1)
    return source + "\n# CHATNEST_VERSION_BRIDGE_MAIN_PROJECT_DIR_V2\n"


_CHAT_BODY_OLD = '''class ChatBody(BaseModel):
    message: str = Field(default="", max_length=20_000)
'''
_CHAT_BODY_NEW = '''class ChatBody(BaseModel):
    message: str = Field(default="", max_length=20_000)
    context: str = Field(default="", max_length=32_000)
'''
_MAIN_TIME_OLD = '            time_mark = "" if is_branch_turn else time_marker(requested_conv_id)'
_MAIN_TIME_NEW = '            time_mark = ""  # Next owns main/version time context.'
_MAIN_STREAM_OLD = '                    chat_stream = stream_chat(*chat_args, on_complete=finalize_turn)'
_MAIN_STREAM_NEW = '                    chat_stream = stream_chat(*chat_args, hidden_context=body.context, on_complete=finalize_turn)'


def patch_main_context_source(source: str) -> str:
    """Accept hidden context without storing it as the visible bridge user message."""
    if "CHATNEST_VERSION_BRIDGE_MAIN_CONTEXT_V1" in source:
        return source
    required = (_CHAT_BODY_OLD, _MAIN_TIME_OLD, _MAIN_STREAM_OLD)
    if not all(item in source for item in required):
        raise RuntimeError("Legacy main context shape changed; refusing bridge patch")
    source = source.replace(_CHAT_BODY_OLD, _CHAT_BODY_NEW, 1)
    source = source.replace(_MAIN_TIME_OLD, _MAIN_TIME_NEW, 1)
    source = source.replace(_MAIN_STREAM_OLD, _MAIN_STREAM_NEW, 1)
    return source + "\n# CHATNEST_VERSION_BRIDGE_MAIN_CONTEXT_V1\n"


_STORE_TIME_OLD = '''    with _connect() as db:
        row = db.execute(
            "SELECT timestamp FROM messages WHERE conv_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (real_id,),
        ).fetchone()
    return row[0] if row else None
'''

_STORE_TIME_NEW = '''    with _connect() as db:
        row = db.execute(
            "SELECT timestamp FROM messages WHERE conv_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (real_id,),
        ).fetchone()
        if row:
            return row[0]
        # Main-session migration intentionally copies no visible message text.
        # Preserve time-gap semantics from content-free conversation metadata.
        conversation = db.execute(
            "SELECT updated_at FROM conversations WHERE conv_id = ?",
            (real_id,),
        ).fetchone()
    return conversation[0] if conversation else None
'''


def patch_store_source(source: str) -> str:
    if "CHATNEST_VERSION_BRIDGE_STORE_V2" in source:
        return source
    if _STORE_TIME_OLD not in source:
        raise RuntimeError("Legacy store time anchor changed; refusing bridge patch")
    return source.replace(_STORE_TIME_OLD, _STORE_TIME_NEW, 1) + "\n# CHATNEST_VERSION_BRIDGE_STORE_V2\n"

_HEARTBEAT_HELPER = r'''

async def _chatnest_iter_with_heartbeats(chunk_iter, interval):
    """Yield None heartbeats without cancelling the pending async-generator read."""
    pending_chunk = asyncio.create_task(chunk_iter.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({pending_chunk}, timeout=interval)
            if not done:
                yield None
                continue
            try:
                chunk = pending_chunk.result()
            except StopAsyncIteration:
                return
            pending_chunk = asyncio.create_task(chunk_iter.__anext__())
            yield chunk
    finally:
        if not pending_chunk.done():
            pending_chunk.cancel()
            try:
                await pending_chunk
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
'''

_HEARTBEAT_LOOP_OLD = '''            heartbeat_interval = 15
            chunk_iter = _merged().__aiter__()
            exhausted = False
            while not exhausted:
                try:
                    chunk = await asyncio.wait_for(
                        chunk_iter.__anext__(),
                        timeout=heartbeat_interval,
                    )
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    yield ": heartbeat\\n\\n"
                    continue
'''

_HEARTBEAT_LOOP_NEW = '''            heartbeat_interval = 15
            async for chunk in _chatnest_iter_with_heartbeats(
                _merged().__aiter__(), heartbeat_interval
            ):
                if chunk is None:
                    yield ": heartbeat\\n\\n"
                    continue
'''


_USAGE_TOKEN_FILE_OLD = 'TOKEN_FILE = Path("/root/.claude_token")'
_USAGE_TOKEN_FILE_NEW = 'TOKEN_FILE = Path("/srv/chatnest-next/data/version-bridge/home/.claude_token")'


def patch_usage_token_file_source(source: str) -> str:
    """Read the usage probe token from the bridge's own HOME.

    Legacy runs as root and keeps it at /root/.claude_token. The bridge runs as
    chatagent after the Phase 0 降權 and cannot read /root at all, so without
    this the usage panel silently reports nothing.

    The path is written out rather than derived from $HOME on purpose: this is a
    faithful backport of what the runtime has been running since 2026-08-17.
    Switching it to os.environ["HOME"] (like _ARTIFACT_DIR does) would be an
    improvement, but it would also change the runtime, which this pass may not do.

    No trailing sentinel here — the runtime's usage.py has none, and a backport
    that appends one would leave the rebuild differing from the runtime by
    exactly the line that claims they match. Idempotence keys off the patched
    value instead.
    """
    if _USAGE_TOKEN_FILE_NEW in source:
        return source
    if _USAGE_TOKEN_FILE_OLD not in source:
        raise RuntimeError("Legacy usage token path changed; refusing bridge patch")
    return source.replace(_USAGE_TOKEN_FILE_OLD, _USAGE_TOKEN_FILE_NEW, 1)


_MB_IMPORT_OLD = "import asyncio\nimport json\nimport logging\nimport time\n"
_MB_IMPORT_NEW = "import asyncio\nimport json\nimport logging\nimport os\nimport time\n"

_MB_CACHE_OLD = '_cache = {"ts": 0.0, "text": ""}\n_task = None\n'
_MB_CACHE_NEW = '''_cache = {"ts": 0.0, "text": "", "pending_ids": []}
_task = None

# 裁定③(2026-08-30 打樣):未讀留言注入上限,0=關閉。糯糯過目樣張核可後,
# 在 version-bridge.env 設 NEST_WAKEUP_COMMENT_CAP=5 開啟。
COMMENT_CAP = int(os.environ.get("NEST_WAKEUP_COMMENT_CAP", "0") or "0")
'''

_MB_COMMENTS_OLD = '''    comments = data.get("unread_comments") or []
    if comments:
        parts.append(
            "\\n【跨窗口留言（注意：可能已被其他窗口讀過/處理過，參考即可；"
            "不要標已讀，那由聊天窗口統一管理）】"
        )
        for c in comments:
            ts = str(c.get("created_at") or "")[:16]
            parts.append(f"- ({c.get('author')} @ {ts}) {c.get('content')}")
    return "\\n".join(parts)
'''
_MB_COMMENTS_NEW = '''    comments = data.get("unread_comments") or []
    folded = 0
    if COMMENT_CAP > 0 and len(comments) > COMMENT_CAP:
        folded = len(comments) - COMMENT_CAP
        comments = comments[-COMMENT_CAP:]  # anchor 依 created_at ASC 排序,取最新 N 條
    injected_ids = [c.get("comment_id") for c in comments if c.get("comment_id")]
    if comments:
        parts.append(
            "\\n【跨窗口留言（注入後系統會自動歸檔標已讀；想回顧用 get_comments）】"
        )
        for c in comments:
            ts = str(c.get("created_at") or "")[:16]
            parts.append(f"- ({c.get('author')} @ {ts}) {c.get('content')}")
        if folded:
            parts.append(f"（另有 {folded} 條較舊未讀留言已折疊，下輪輪替注入）")
    return "\\n".join(parts), injected_ids
'''

_MB_REFRESH_OLD = '''        text = await _call_wakeup()
        _cache = {"ts": time.time(), "text": text}
        log.info("anchor wakeup ok: %d chars", len(text))
'''
_MB_REFRESH_NEW = '''        text, ids = await _call_wakeup()
        _cache = {"ts": time.time(), "text": text, "pending_ids": ids}
        log.info("anchor wakeup ok: %d chars, %d unread comments", len(text), len(ids))
'''

_MB_GUIDE_OLD = "- leave_comment 可跨窗口留言；收到的留言只讀不標已讀（已讀由聊天窗口統一管理）"
_MB_GUIDE_NEW = "- leave_comment 可跨窗口留言；收到的留言只讀、絕不手動標已讀（注入送達時系統自動標）"

_MB_MARK_TAIL = '''

async def _call_mark(ids: list) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(ANCHOR_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool(
                "mark_comments_read", {"comment_ids": ids, "reader": "ai"})


async def mark_injected_comments() -> None:
    """裁定①(2026-08-30):read_by_ai 正典語意=「已注入聊天窗口(牧牧本體)的
    system prompt」。注入發生後由系統自動標,不依賴模型行為;CC/MCP 側的 wakeup
    不標(CC 看過≠本體看過)。失敗自吞:留言保持未讀,下次注入再標(冪等)。
    詳見 /root/nest-memory/NOTES_comment_read_semantics.md。"""
    global _cache
    ids = list(_cache.get("pending_ids") or [])
    if not ids:
        return
    try:
        await _call_mark(ids)
        _cache["pending_ids"] = []
        log.info("comments auto-marked read on injection: %d", len(ids))
    except Exception as e:  # noqa: BLE001 — 絕不反殺主流程
        log.warning("mark_comments_read failed (retry next wakeup): %s", e)
'''


def patch_memory_bridge_comment_injection_source(source: str) -> str:
    """Auto-archive cross-window comments once they are actually injected.

    裁定① (2026-08-30): read_by_ai means "reached the chat window's system
    prompt", so the marking has to happen where the injection happens rather
    than depend on the model remembering to do it. 裁定③ caps how many unread
    comments ride along (NEST_WAKEUP_COMMENT_CAP, 0 = off) and folds the rest
    into the next round.

    _call_wakeup() therefore returns (text, injected_ids) instead of text — the
    caller in _refresh() is patched with it, and claude.py fires
    mark_injected_comments() after the prompt is built.

    No trailing sentinel: the runtime's memory_bridge.py carries none.
    """
    if "mark_injected_comments" in source:
        return source
    pieces = [
        (_MB_IMPORT_OLD, _MB_IMPORT_NEW),
        (_MB_CACHE_OLD, _MB_CACHE_NEW),
        (_MB_COMMENTS_OLD, _MB_COMMENTS_NEW),
        (_MB_REFRESH_OLD, _MB_REFRESH_NEW),
        (_MB_GUIDE_OLD, _MB_GUIDE_NEW),
    ]
    for old, _ in pieces:
        if old not in source:
            raise RuntimeError(
                "Legacy memory_bridge shape changed; refusing bridge patch"
            )
    for old, new in pieces:
        source = source.replace(old, new, 1)
    return source.rstrip("\n") + "\n" + _MB_MARK_TAIL


_MAIN_PHOTO_ROOT_OLD = 'PHOTO_ROOT = Path(os.environ.get("STACKCHAN_PHOTO_ROOT", "/root/mumu-server/photos"))'
_MAIN_PHOTO_ROOT_NEW = 'PHOTO_ROOT = Path(os.environ.get("STACKCHAN_PHOTO_ROOT", "/srv/mumu-server/photos"))'


def patch_main_photo_root_source(source: str) -> str:
    """Default the photo root to /srv after the 2026-08-17 move.

    The env var still wins; this only fixes the fallback, which legacy leaves
    pointing at /root — a path the chatagent bridge cannot read at all.

    No trailing sentinel: the runtime's main.py carries sentinels only for the
    four patches that already had them, and adding a fifth would make the
    rebuild differ from the runtime.
    """
    if _MAIN_PHOTO_ROOT_NEW in source:
        return source
    if _MAIN_PHOTO_ROOT_OLD not in source:
        raise RuntimeError("Legacy photo root shape changed; refusing bridge patch")
    return source.replace(_MAIN_PHOTO_ROOT_OLD, _MAIN_PHOTO_ROOT_NEW, 1)


_MAIN_FRESH_FIELD_OLD = """    session_id: str | None = Field(default=None, max_length=256)
    edit_message_id: int | None = Field(default=None, ge=1)
"""
_MAIN_FRESH_FIELD_NEW = """    session_id: str | None = Field(default=None, max_length=256)
    # Swap MVP(2026-08-31):true=本回合不 resume,起全新 SDK session(同 conv)。
    # 換窗 ping 專用:成功時 complete_turn 把 latest_session_id 翻到新窗(=NEW GOOD),
    # 失敗不翻=last-good 續用舊窗。swap_runner 負責驗證與回滾。
    fresh_session: bool = False
    edit_message_id: int | None = Field(default=None, ge=1)
"""

_MAIN_FRESH_LOGIC_OLD = """                    body.session_id,
                    current_attachment_items,
                )
            payload = json.dumps(
"""
_MAIN_FRESH_LOGIC_NEW = """                    body.session_id,
                    current_attachment_items,
                )
                if body.fresh_session:
                    logger.info("swap fresh_session turn conv=%s old_session=%s", conv_id, resume_id)
                    resume_id = None
                    # 換窗必須冷啟:warm actor 會沿用既有 SDK session,令 resume=None 失效
                    await get_registry().invalidate(conv_id)
            payload = json.dumps(
"""


def patch_main_fresh_session_source(source: str) -> str:
    """Let a turn deliberately start a new SDK session (Swap MVP, 2026-08-31).

    This is the mechanism the window swap rides on: swap_runner pings with
    fresh_session=True, and complete_turn flipping latest_session_id is what
    marks the new window good. A failed swap simply does not flip it, so the
    last-good window stays in service.

    Invalidating the registry is not optional — a warm actor keeps its existing
    SDK session and would quietly ignore resume_id=None, which is the whole
    point of the flag.

    No trailing sentinel, for the same reason as patch_main_photo_root_source.
    """
    if "fresh_session" in source:
        return source
    for old in (_MAIN_FRESH_FIELD_OLD, _MAIN_FRESH_LOGIC_OLD):
        if old not in source:
            raise RuntimeError("Legacy chat body/resume shape changed; refusing bridge patch")
    source = source.replace(_MAIN_FRESH_FIELD_OLD, _MAIN_FRESH_FIELD_NEW, 1)
    return source.replace(_MAIN_FRESH_LOGIC_OLD, _MAIN_FRESH_LOGIC_NEW, 1)


_MAIN_ARTIFACT_DIR_OLD = '_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts"'
_MAIN_ARTIFACT_DIR_NEW = '_ARTIFACT_DIR = Path(os.environ.get("HOME") or Path(__file__).resolve().parent.parent) / "artifacts"'


def patch_main_artifact_dir_source(source: str) -> str:
    """Serve artifacts from the bridge's own HOME, which is where cn writes them.

    cn runs with HOME=<data>/version-bridge/home and a cwd of the runtime app dir,
    so his relative ``artifacts/x.html`` lands in HOME. Before this patch the
    endpoint looked next to the runtime app instead, and found nothing.
    Reading his own HOME keeps this inside the bridge's chatagent identity —
    no root process needs to reach into that 0700 directory.
    """
    if "CHATNEST_VERSION_BRIDGE_MAIN_ARTIFACT_DIR_V1" in source:
        return source
    if _MAIN_ARTIFACT_DIR_OLD not in source:
        raise RuntimeError("Legacy artifact dir shape changed; refusing bridge patch")
    source = source.replace(_MAIN_ARTIFACT_DIR_OLD, _MAIN_ARTIFACT_DIR_NEW, 1)
    return source + "\n# CHATNEST_VERSION_BRIDGE_MAIN_ARTIFACT_DIR_V1\n"


def patch_main_heartbeat_source(source: str) -> str:
    """Keep a pending SDK read alive while emitting content-free SSE heartbeats."""
    if "CHATNEST_VERSION_BRIDGE_HEARTBEAT_V2" in source:
        return source
    if _HEARTBEAT_LOOP_OLD not in source:
        raise RuntimeError("Legacy heartbeat loop shape changed; refusing bridge patch")
    logger_anchor = "logger = logging.getLogger(__name__)\n"
    if logger_anchor not in source:
        raise RuntimeError("Legacy main logger anchor missing; refusing heartbeat patch")
    source = source.replace(logger_anchor, logger_anchor + _HEARTBEAT_HELPER, 1)
    source = source.replace(_HEARTBEAT_LOOP_OLD, _HEARTBEAT_LOOP_NEW, 1)
    return source + "\n# CHATNEST_VERSION_BRIDGE_HEARTBEAT_V2\n"

_THINKING_IMPORT_OLD = """    ToolResultBlock as _ToolResultBlock,
)"""
_THINKING_IMPORT_NEW = """    ToolResultBlock as _ToolResultBlock,
    ThinkingBlock as _ThinkingBlock,
)"""
_THINKING_STATE_OLD = """        got_streaming_text = False
        result_seen = False"""
_THINKING_STATE_NEW = """        got_streaming_text = False
        streamed_thinking_buffer = ""
        result_seen = False"""
_THINKING_STREAM_OLD = """                elif delta.get("type") == "thinking_delta":
                    await _emit(
                        {"event": "thinking", "text": delta.get("thinking", "")}
                    )"""
_THINKING_STREAM_NEW = """                elif delta.get("type") == "thinking_delta":
                    thinking = delta.get("thinking", "")
                    if thinking:
                        streamed_thinking_buffer += thinking
                        await _emit({"event": "thinking", "text": thinking})"""
_THINKING_ASSISTANT_OLD = """            elif isinstance(sdk_message, _AssistantMessage):
                for block in getattr(sdk_message, "content", []) or []:
                    if isinstance(block, _TextBlock) and not got_streaming_text:"""
_THINKING_ASSISTANT_NEW = """            elif isinstance(sdk_message, _AssistantMessage):
                for block in getattr(sdk_message, "content", []) or []:
                    if isinstance(block, _ThinkingBlock):
                        full_thinking = block.thinking or ""
                        missing_thinking = _missing_thinking_suffix(
                            full_thinking,
                            streamed_thinking_buffer,
                        )
                        if missing_thinking:
                            await _emit({"event": "thinking", "text": missing_thinking})
                        streamed_thinking_buffer = ""
                    elif isinstance(block, _TextBlock) and not got_streaming_text:"""
_THINKING_TOOL_OLD = """                    elif isinstance(block, _ToolUseBlock):
                        await _emit({"""
_THINKING_TOOL_NEW = """                    elif isinstance(block, _ToolUseBlock):
                        streamed_thinking_buffer = ""
                        await _emit({"""
_THINKING_HELPER = r'''

def _missing_thinking_suffix(full_thinking, streamed_thinking):
    """Use the complete SDK block as a fallback without duplicating streamed deltas."""
    full = str(full_thinking or "")
    streamed = str(streamed_thinking or "")
    if not full:
        return ""
    if not streamed:
        return full
    if full.startswith(streamed):
        return full[len(streamed):]
    # A non-prefix mismatch is safer left as already-streamed text than duplicated.
    return ""
'''


def patch_actor_thinking_block_source(source: str) -> str:
    """Preserve visible Thinking whether the SDK sends deltas, full blocks, or both."""
    if "CHATNEST_VERSION_BRIDGE_THINKING_BLOCK_V1" in source:
        return source
    required = (
        _THINKING_IMPORT_OLD,
        _THINKING_STATE_OLD,
        _THINKING_STREAM_OLD,
        _THINKING_ASSISTANT_OLD,
        _THINKING_TOOL_OLD,
    )
    if not all(item in source for item in required):
        raise RuntimeError("patched actor Thinking shape changed; refusing ThinkingBlock patch")
    source = source.replace(_THINKING_IMPORT_OLD, _THINKING_IMPORT_NEW, 1)
    source = source.replace(_THINKING_STATE_OLD, _THINKING_STATE_NEW, 1)
    source = source.replace(_THINKING_STREAM_OLD, _THINKING_STREAM_NEW, 1)
    source = source.replace(_THINKING_ASSISTANT_OLD, _THINKING_ASSISTANT_NEW, 1)
    source = source.replace(_THINKING_TOOL_OLD, _THINKING_TOOL_NEW, 1)
    anchor = "\n\nlogger = logging.getLogger(__name__)\n"
    if anchor not in source:
        raise RuntimeError("patched actor logger anchor missing for ThinkingBlock patch")
    source = source.replace(anchor, _THINKING_HELPER + anchor, 1)
    return source + "\n# CHATNEST_VERSION_BRIDGE_THINKING_BLOCK_V1\n"


_WAKE_SCHEDULE_OLD = 'SCHEDULE_FILE = Path(__file__).resolve().parent.parent / "wake_schedule.json"'
_WAKE_SCHEDULE_NEW = 'SCHEDULE_FILE = Path("/srv/chatnest-next/data/version-bridge/wake_schedule.json")'


def patch_wake_tool_source(source: str) -> str:
    """Keep MuMu's existing wake tools on one durable Next-owned schedule file."""
    if "CHATNEST_VERSION_BRIDGE_WAKE_SCHEDULE_V1" in source:
        return source
    if _WAKE_SCHEDULE_OLD not in source:
        raise RuntimeError("Legacy wake schedule anchor changed; refusing bridge patch")
    source = source.replace(_WAKE_SCHEDULE_OLD, _WAKE_SCHEDULE_NEW, 1)
    return source + "\n# CHATNEST_VERSION_BRIDGE_WAKE_SCHEDULE_V1\n"
