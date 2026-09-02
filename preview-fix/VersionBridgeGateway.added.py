"""② 新增到 backend/app/gateways.py 的 gateway。

實際位置:插在 `class DashboardGateway:` 之前。
同一次改動還從 LEGACY_PREFIXES 移除了 "artifact"(見 NOTES ②)。

backend/app/main.py 的三處接線:

    from .gateways import DashboardGateway, LegacyGateway, VersionBridgeGateway

    version_bridge_gateway = VersionBridgeGateway()        # 接在既有兩個 gateway 之後

    # artifact_preview() 裡:
    response = await version_bridge_gateway.request("GET", f"artifact/{name}", params={})

依賴的既有名字(gateways.py 檔頭已有):httpx、HTTPException、Any、
settings、secret_value、allowed。
"""

VERSION_BRIDGE_PREFIXES = ("artifact",)


class VersionBridgeGateway:
    """Read cn's artifacts through the bridge, which owns that HOME.

    cn writes into the bridge's HOME (0700, chatagent). Fetching through the
    bridge keeps the read inside chatagent instead of opening a new corridor
    where this root-owned backend reaches into his private directory.

    The allow-list is deliberately one entry: this gateway exists for artifact
    previews and nothing else.
    """

    def __init__(self) -> None:
        self.token: str | None = None

    async def _authenticate(self, client: httpx.AsyncClient) -> str:
        password = secret_value(
            "VERSION_BRIDGE_PASSWORD", "VERSION_BRIDGE_PASSWORD_FILE"
        )
        if not password:
            raise HTTPException(
                status_code=503, detail="version bridge gateway is not configured"
            )
        response = await client.post("/api/auth", json={"password": password})
        if response.is_error:
            raise HTTPException(
                status_code=502, detail="version bridge authentication failed"
            )
        self.token = response.json()["token"]
        return self.token

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any],
    ) -> httpx.Response:
        if not allowed(path, VERSION_BRIDGE_PREFIXES):
            raise HTTPException(
                status_code=404, detail="version bridge route not allowed"
            )
        async with httpx.AsyncClient(
            base_url=settings.version_bridge_url, timeout=30
        ) as client:
            token = self.token or await self._authenticate(client)
            response = await client.request(
                method,
                f"/api/{path.strip('/')}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code == 401:
                # The bridge token is HMAC(CHAT_SECRET, "chat-v1"): no expiry,
                # and a restart re-derives the same value. What does invalidate
                # it is rotating CHAT_SECRET — and without this retry the cached
                # token would then stay wrong until this process restarts too.
                self.token = None
                token = await self._authenticate(client)
                response = await client.request(
                    method,
                    f"/api/{path.strip('/')}",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
        return response
