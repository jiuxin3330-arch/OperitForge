"""MCP 路徑別名 —— 方案 B 的雙路並存過渡層(2026-09-02)。

背景:cloudflared 繞過 ufw,把 MCP 端點直接掛在公開網域上,實測可從外部
無驗證 initialize。方案 A(Cloudflare Access)廢案——claude.ai 的 connector
沒有 Request headers 欄位(beta,帳號未開放),Service Token 送不出去,
加了 Access 等於把所有窗口鎖在門外。

改走方案 B:比照 toy 既有做法,MCP 端點藏在帶密鑰的路徑下 /mcp-<KEY>。

## 為什麼需要這一層

FastMCP 的 streamable_http_path 只能設一個值,直接改掉就是「一次性切換」——
舊 connector 當場失效,而 claude.ai 那邊的設定不是我能動的。施工鐵律要求
雙路並存:先讓兩條路都通,糯糯新增 connector、實測、移除舊的,最後才關舊路。

所以這層做的事只有一件:把 /mcp-<KEY> 的請求改寫成 /mcp 再交給原本的 app。
舊路徑 /mcp 原封不動繼續服務,直到過渡完成後用環境變數關掉。

## 用法

    import mcp_path_alias
    if __name__ == "__main__":
        mcp_path_alias.serve(mcp, "/root/<svc>/mcp_path_key.txt")

等價於原本的 mcp.run(transport="streamable-http")——SDK 的
run_streamable_http_async 就是 streamable_http_app() + uvicorn,
而 streamable_http_app() 自帶 lifespan(session manager),包一層不影響。

## 過渡完成後關閉舊路徑

    systemctl set-environment 或 unit 檔加 Environment=MCP_LEGACY_PATH=0
    → 舊的 /mcp 回 404,只剩 /mcp-<KEY> 能用。
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

LEGACY_ENV = "MCP_LEGACY_PATH"


def load_or_create_key(key_path: str | Path) -> str:
    """讀密鑰,沒有就生一把並鎖成 0600。密鑰只存在檔案裡,不進 git、不進日誌。"""
    path = Path(key_path)
    if path.exists():
        key = path.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_urlsafe(24)
    path.write_text(key + "\n", encoding="utf-8")
    path.chmod(0o600)
    return key


class MCPPathAlias:
    """把 alias 路徑改寫成 target 交給下游;可選擇性把 target 本身關掉。"""

    def __init__(self, app, alias: str, target: str = "/mcp", legacy_enabled: bool = True):
        self.app = app
        self.alias = alias.rstrip("/")
        self.target = target.rstrip("/") or "/mcp"
        self.legacy_enabled = legacy_enabled

    def _matches(self, path: str, prefix: str) -> bool:
        return path == prefix or path.startswith(prefix + "/")

    async def __call__(self, scope, receive, send):
        # lifespan / websocket 一律原樣放行
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if self._matches(path, self.alias):
            rest = path[len(self.alias):]
            # /mcp-<KEY>/ 也視為 /mcp,免得踩到 Starlette 的 trailing-slash 307
            # ——那個 redirect 會把 Location 指回沒有密鑰的舊路徑。
            new_path = self.target if rest in ("", "/") else self.target + rest
            scope = dict(scope)
            scope["path"] = new_path
            scope["raw_path"] = new_path.encode("utf-8")
        elif not self.legacy_enabled and self._matches(path, self.target):
            await self._gone(send)
            return

        await self.app(scope, receive, send)

    async def _gone(self, send) -> None:
        body = b'{"error":"not found"}'
        await send({"type": "http.response.start", "status": 404,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def serve(mcp, key_path: str | Path, *, host: str | None = None, port: int | None = None) -> None:
    """取代 mcp.run(transport='streamable-http'),加上 /mcp-<KEY> 別名。"""
    import uvicorn

    key = load_or_create_key(key_path)
    settings = mcp.settings
    target = getattr(settings, "streamable_http_path", "/mcp")
    legacy_enabled = os.environ.get(LEGACY_ENV, "1") != "0"

    app = MCPPathAlias(mcp.streamable_http_app(), f"/mcp-{key}", target, legacy_enabled)

    # 只印路徑長度,不印密鑰本身——journald 是 root 可讀但沒必要把密鑰灑進去。
    print(f"[mcp_path_alias] alias=/mcp-<{len(key)} chars> "
          f"legacy({target})={'on' if legacy_enabled else 'off'}", flush=True)

    uvicorn.run(app,
                host=host or settings.host,
                port=port or settings.port,
                log_level=settings.log_level.lower())
