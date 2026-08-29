"""大富豪 — FastAPI + WebSocket 伺服器(單房間家庭用)。

紅線:低權 unix user 跑;共用密碼 rate limit;伺服器權威(手牌只回本人)。
"""
from __future__ import annotations

import asyncio
import hmac
import os
import time

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import game

app = FastAPI(title="daifugo", docs_url=None, redoc_url=None, openapi_url=None)

PASSWORD = os.environ.get("DAIFUGO_PASSWORD", "")
STATIC = "/srv/daifugo/static"

room = game.Room()
room_lock = asyncio.Lock()
sockets: dict[str, WebSocket] = {}  # token → ws

# ---- 密碼 rate limit(每 IP:連錯 5 次鎖 60 秒)----
_fails: dict[str, list[float]] = {}
FAIL_LIMIT = 5
FAIL_WINDOW = 60.0


def _rate_limited(ip: str) -> bool:
    now = time.time()
    _fails[ip] = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW]
    return len(_fails[ip]) >= FAIL_LIMIT


def _record_fail(ip: str):
    _fails.setdefault(ip, []).append(time.time())


class LoginBody(BaseModel):
    password: str = Field(max_length=64)
    name: str = Field(max_length=24)
    emoji: str = Field(max_length=8)
    color: str = Field(max_length=16, pattern=r"^#[0-9a-fA-F]{3,8}$")


@app.post("/api/login")
async def login(body: LoginBody, request: Request):
    ip = request.client.host if request.client else "?"
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail="錯太多次了,等一分鐘再試")
    if not PASSWORD or not hmac.compare_digest(body.password, PASSWORD):
        _record_fail(ip)
        raise HTTPException(status_code=401, detail="密碼不對")
    async with room_lock:
        try:
            token = room.join(body.name, body.emoji, body.color)
        except game.GameError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    await broadcast()
    return {"token": token}


@app.get("/api/resume")
async def resume(request: Request):
    token = request.headers.get("x-daifugo-token", "")
    async with room_lock:
        seat = room.seat_of(token)
    if seat is None:
        raise HTTPException(status_code=401, detail="座位不存在(可能已重開房)")
    return {"ok": True, "seat": seat}


async def broadcast():
    dead = []
    for token, ws in list(sockets.items()):
        try:
            await ws.send_json({"type": "state", **room.state_for(token)})
        except Exception:
            dead.append(token)
    for token in dead:
        sockets.pop(token, None)
        room.touch(token, False)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    token = ws.query_params.get("token", "")
    async with room_lock:
        seat = room.seat_of(token)
    if seat is None:
        await ws.send_json({"type": "error", "msg": "無效的座位,請重新進場"})
        await ws.close()
        return
    old = sockets.get(token)
    sockets[token] = ws
    if old is not None:
        try:
            await old.close()
        except Exception:
            pass
    room.touch(token, True)
    await broadcast()
    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")
            try:
                async with room_lock:
                    if mtype == "start":
                        room.start(token, msg.get("settings"))
                    elif mtype == "play":
                        cards = msg.get("cards")
                        if not isinstance(cards, list) or not all(
                                isinstance(c, str) and len(c) <= 4 for c in cards):
                            raise game.GameError("出牌格式不對")
                        room.play(token, cards)
                    elif mtype == "pass":
                        room.pass_turn(token)
                    elif mtype == "tribute_return":
                        card = msg.get("card")
                        if not isinstance(card, str) or len(card) > 4:
                            raise game.GameError("回贈格式不對")
                        room.tribute_return(token, card)
                    elif mtype == "ping":
                        room.touch(token, True)
                        continue
                    else:
                        raise game.GameError("未知指令")
            except game.GameError as exc:
                await ws.send_json({"type": "error", "msg": str(exc)})
                continue
            await broadcast()
    except WebSocketDisconnect:
        pass
    finally:
        if sockets.get(token) is ws:
            sockets.pop(token, None)
            room.touch(token, False)
            await broadcast()


@app.get("/")
async def index():
    return FileResponse(f"{STATIC}/index.html")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "players": len(room.players), "phase": room.phase}
