"""`mcp_path_alias` 的路由規則測試。

這層是安全邊界:過渡完成後(`MCP_LEGACY_PATH=0`)它是「知不知道密鑰」的唯一判準。
所以規則要用測試鎖住,不能只靠對線上服務打幾發 curl——線上打的那幾發,
在舊路徑還開著的期間本來就都會過,測不出關掉之後的行為。

特別鎖住兩件容易錯的事:
1. 尾斜線必須自己吃掉。不吃的話會落到 Starlette 的 trailing-slash 307,
   而那個 redirect 的 Location 會把**沒有密鑰的舊路徑**吐給對方。
2. 前綴不得黏字比對。`/mcp-<KEY>x` 不是 `/mcp-<KEY>`,
   否則密鑰等於只要猜對前綴就好。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "mcp_path_alias.py"

spec = importlib.util.spec_from_file_location("_mcp_path_alias", MODULE_PATH)
mcp_path_alias = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mcp_path_alias
spec.loader.exec_module(mcp_path_alias)

KEY = "TESTKEY"
ALIAS = f"/mcp-{KEY}"


class Downstream:
    """假的下游 app:只記下它收到的 path。"""

    def __init__(self):
        self.seen: list[str] = []

    async def __call__(self, scope, receive, send):
        self.seen.append(scope.get("path"))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def call(app, path: str, scope_type: str = "http") -> tuple[int | None, list[str]]:
    """送一發請求進去,回 (狀態碼, 下游看到的 path 們)。"""
    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    await app({"type": scope_type, "path": path, "headers": [], "method": "POST"}, receive, send)
    status = next((m["status"] for m in sent if m["type"] == "http.response.start"), None)
    return status, sent


@pytest.fixture()
def legacy_on():
    down = Downstream()
    return down, mcp_path_alias.MCPPathAlias(down, ALIAS, "/mcp", legacy_enabled=True)


@pytest.fixture()
def legacy_off():
    down = Downstream()
    return down, mcp_path_alias.MCPPathAlias(down, ALIAS, "/mcp", legacy_enabled=False)


@pytest.mark.anyio
async def test_alias_is_rewritten_to_target(legacy_on):
    down, app = legacy_on
    status, _ = await call(app, ALIAS)
    assert status == 200
    assert down.seen == ["/mcp"]


@pytest.mark.anyio
async def test_trailing_slash_is_absorbed_not_redirected(legacy_on):
    """/mcp-<KEY>/ 要直接變成 /mcp。

    若原樣傳成 /mcp/,Starlette 會回 307 並把 Location 指到 /mcp
    ——等於把沒有密鑰的舊路徑主動告訴對方。
    """
    down, app = legacy_on
    status, _ = await call(app, ALIAS + "/")
    assert status == 200
    assert down.seen == ["/mcp"], "尾斜線沒被吃掉,會漏出舊路徑"


@pytest.mark.anyio
async def test_subpath_is_preserved(legacy_on):
    down, app = legacy_on
    await call(app, ALIAS + "/messages")
    assert down.seen == ["/mcp/messages"]


@pytest.mark.anyio
@pytest.mark.parametrize("path", [
    "/mcp-TESTKEYx",      # 前綴黏字
    "/mcp-TESTKE",        # 少一字
    "/mcp-wrongkey",
    "/mcp-",
    "/mcpTESTKEY",
])
async def test_near_miss_keys_are_not_rewritten(legacy_on, path):
    """差一點的密鑰一律不改寫,原樣交下游(下游自己 404)。"""
    down, app = legacy_on
    await call(app, path)
    assert down.seen == [path], f"{path} 不該被當成別名"


@pytest.mark.anyio
async def test_literal_dot_dot_does_not_escape_to_target(legacy_off):
    """字面 ../ 不構成繞道。

    /mcp-<KEY>/../mcp 會被改寫成 /mcp/../mcp 原樣交下游——那是一個字面路徑,
    Starlette 不會替它做 remove_dot_segments,所以配不到任何路由。
    重點是它**沒有**變成乾淨的 /mcp。
    """
    down, app = legacy_off
    await call(app, ALIAS + "/../mcp")
    assert down.seen == ["/mcp/../mcp"]
    assert down.seen != ["/mcp"], "../ 被正規化成舊路徑就等於繞過密鑰"


@pytest.mark.anyio
async def test_legacy_path_open_during_transition(legacy_on):
    """過渡期間舊路徑必須還通,否則就是一次性切換。"""
    down, app = legacy_on
    status, _ = await call(app, "/mcp")
    assert status == 200
    assert down.seen == ["/mcp"]


@pytest.mark.anyio
async def test_legacy_path_closed_after_transition(legacy_off):
    """步驟⑤之後舊路徑要 404,而且根本不進下游。"""
    down, app = legacy_off
    status, _ = await call(app, "/mcp")
    assert status == 404
    assert down.seen == [], "舊路徑關掉後不該還把請求交給下游"


@pytest.mark.anyio
async def test_legacy_subpath_also_closed(legacy_off):
    down, app = legacy_off
    status, _ = await call(app, "/mcp/messages")
    assert status == 404
    assert down.seen == []


@pytest.mark.anyio
async def test_non_http_scopes_pass_through_untouched(legacy_off):
    """lifespan 必須原樣放行——session manager 是靠它啟動的。

    這裡刻意用 legacy_off:即使舊路徑關著,lifespan 也不能被攔。
    """
    down, app = legacy_off
    await call(app, "/mcp", scope_type="lifespan")
    assert down.seen == ["/mcp"], "lifespan 被攔掉的話 session manager 不會啟動"


@pytest.mark.anyio
async def test_key_file_is_created_locked_down(tmp_path):
    key_file = tmp_path / "mcp_path_key.txt"
    key = mcp_path_alias.load_or_create_key(key_file)

    assert len(key) >= 32
    assert oct(key_file.stat().st_mode)[-3:] == "600"
    assert mcp_path_alias.load_or_create_key(key_file) == key, "重讀要拿到同一把,不能每次重啟都換"


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"
