#!/usr/bin/env python3
"""為 cn-dev.uk 的 tunnel 網域套上 Cloudflare Access(VPS_AUDIT_20260901 方案 A)。

背景:cloudflared 從內部主動連出,**繞過 ufw**。7 個服務掛在公開網域上,
其中 mcp / voice / stackchan 實測可從外部無驗證直接 MCP initialize。
方案 A = 不動服務程式,在 Cloudflare 這一層加登入保護。

    純瀏覽器網域  → Allow 政策(email 白名單,一次性 PIN 登入)
    工具通道網域  → Allow 政策 + Service Auth 政策(給 MCP 客戶端帶 header 用)

## 為什麼要有這支腳本而不是直接在後台點

因為 hands.cn-dev.uk 是規劃窗(CC 窗口)唯一的 VPS 通道。設定錯了會把自己鎖在門外,
而且從沙箱裡連不到 Cloudflare API,救不回來。所以:

  * hands 預設**不在**施工範圍,要加得明確傳 --include-hands;
  * 每個動作都可以 --rollback 一鍵拆掉;
  * 先 plan 再 apply。

## 用法

    export CF_API_TOKEN=<有 Zero Trust 寫權限的 token>
    python3 access_apply.py plan
    python3 access_apply.py apply
    python3 access_apply.py status
    python3 access_apply.py rollback            # 拆掉本腳本建立的全部 app

註:VPS 上 /root/.cloudflared/cert.pem 內嵌的那把 token **不夠用**——
實測 access/apps 可以 list,create 回 1010 auth.forbidden。需要另開一把
API token,權限:Account → Access: Apps and Policies → Edit
(要建 service token 再加 Account → Access: Service Tokens → Edit)。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "098827fdfc7102df0d23a994460dd1a1")

# 只有本腳本建立的東西才會被 rollback 動到,靠這個前綴認人。
TAG = "[nest]"

# 允許登入的人。Access 沒有設 IdP 時走一次性 PIN:輸 email → 收驗證碼 → 進站。
OWNER_EMAILS = [
    "jiuxin3330@gmail.com",      # 糯糯
    "huangmumu795@gmail.com",    # 牧牧
]

SESSION_DURATION = "720h"        # 30 天,免得糯糯每次開都要重登

# kind:
#   browser — 只有人用瀏覽器開,加登入即可
#   tool    — MCP 工具通道,除了登入還要一條 Service Auth 政策讓機器帶 header 進來
APPS = [
    {"host": "chat.cn-dev.uk",      "kind": "browser", "name": "ChatNest 舊前端"},
    {"host": "voice.cn-dev.uk",     "kind": "tool",    "name": "Voice MCP + 播放器"},
    {"host": "mcp.cn-dev.uk",       "kind": "tool",    "name": "Anchor Memory MCP"},
    {"host": "stackchan.cn-dev.uk", "kind": "tool",    "name": "StackChan MCP"},
    {"host": "toy.cn-dev.uk",       "kind": "tool",    "name": "Toy MCP"},
    # hands 是規劃窗唯一的 VPS 通道,預設不動。要加請傳 --include-hands,
    # 並且先確認 MCP 客戶端真的送得出 CF-Access-Client-Id/Secret。
    {"host": "hands.cn-dev.uk",     "kind": "tool",    "name": "Hands MCP (exec_vps)",
     "lifeline": True},
]

SERVICE_TOKEN_NAME = f"{TAG} mcp-clients"


def request(method: str, path: str, body: dict | None = None) -> dict:
    token = os.environ.get("CF_API_TOKEN")
    if not token:
        sys.exit("請先 export CF_API_TOKEN=<有 Zero Trust 寫權限的 token>")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read() or b"{}")
    if not payload.get("success"):
        errors = payload.get("errors")
        raise RuntimeError(f"{method} {path} 失敗:{errors}")
    return payload


def list_apps() -> list[dict]:
    return request("GET", f"/accounts/{ACCOUNT_ID}/access/apps?per_page=200")["result"] or []


def find_app(domain: str) -> dict | None:
    return next((a for a in list_apps() if a.get("domain") == domain), None)


def ensure_service_token() -> dict | None:
    """回傳既有的 service token(不含 secret),沒有就建一個並印出憑證。

    secret 只會在建立當下出現一次,之後 Cloudflare 不再吐出來。
    """
    tokens = request("GET", f"/accounts/{ACCOUNT_ID}/access/service_tokens")["result"] or []
    existing = next((t for t in tokens if t.get("name") == SERVICE_TOKEN_NAME), None)
    if existing:
        print(f"  service token 已存在:{existing['name']} (client_id={existing['client_id']})")
        return existing

    created = request("POST", f"/accounts/{ACCOUNT_ID}/access/service_tokens",
                      {"name": SERVICE_TOKEN_NAME, "duration": "8760h"})["result"]
    print()
    print("  ┌─ Service token 建好了。下面這組 secret 只會出現這一次,現在抄走 ─┐")
    print(f"  │ CF-Access-Client-Id     : {created['client_id']}")
    print(f"  │ CF-Access-Client-Secret : {created['client_secret']}")
    print("  └───────────────────────────────────────────────────────────────┘")
    print("  MCP 客戶端要把這兩個當 HTTP header 送出,才能穿過 Access。")
    print()
    return created


def policy_allow_owner() -> dict:
    return {
        "name": f"{TAG} 屋主登入",
        "decision": "allow",
        "include": [{"email": {"email": address}} for address in OWNER_EMAILS],
    }


def policy_service_auth(client_id: str) -> dict:
    return {
        "name": f"{TAG} MCP 客戶端",
        "decision": "non_identity",
        "include": [{"service_token": {"token_id": client_id}}],
    }


def apply_app(spec: dict, service_token: dict | None) -> None:
    host = spec["host"]
    existing = find_app(host)
    if existing:
        print(f"- {host}:已經有 Access app({existing['id']}),跳過")
        return

    app = request("POST", f"/accounts/{ACCOUNT_ID}/access/apps", {
        "name": f"{TAG} {spec['name']}",
        "domain": host,
        "type": "self_hosted",
        "session_duration": SESSION_DURATION,
        "auto_redirect_to_identity": False,
        "app_launcher_visible": False,
    })["result"]
    print(f"- {host}:建好 app {app['id']}")

    base = f"/accounts/{ACCOUNT_ID}/access/apps/{app['id']}/policies"
    request("POST", base, policy_allow_owner())
    print("    + 屋主登入政策")

    if spec["kind"] == "tool":
        if not service_token:
            print("    ! 沒有 service token,這個工具通道現在只剩人能登入 —— "
                  "MCP 客戶端會被擋在外面")
        else:
            request("POST", base, policy_service_auth(service_token["id"]))
            print("    + MCP 客戶端 Service Auth 政策")


def selected(args) -> list[dict]:
    return [a for a in APPS if not a.get("lifeline") or args.include_hands]


def cmd_plan(args) -> None:
    print("將建立的 Access 應用:")
    for spec in selected(args):
        mark = "  ⚠ 生命線" if spec.get("lifeline") else ""
        print(f"  {spec['host']:<24} {spec['kind']:<8} {spec['name']}{mark}")
    skipped = [a for a in APPS if a not in selected(args)]
    for spec in skipped:
        print(f"  {spec['host']:<24} —— 略過(要動請加 --include-hands)")
    print(f"\n登入白名單:{', '.join(OWNER_EMAILS)}")
    print("工具通道會額外加一條 Service Auth 政策(CF-Access-Client-Id/Secret)。")


def cmd_apply(args) -> None:
    specs = selected(args)
    needs_token = any(s["kind"] == "tool" for s in specs)
    service_token = ensure_service_token() if needs_token else None
    for spec in specs:
        apply_app(spec, service_token)
    print("\n完成。務必馬上實測:未登入應該被導到登入頁,帶 header 的請求應該直通。")


def cmd_status(args) -> None:
    apps = {a.get("domain"): a for a in list_apps()}
    for spec in APPS:
        app = apps.get(spec["host"])
        if not app:
            print(f"  {spec['host']:<24} 未保護")
            continue
        policies = request(
            "GET", f"/accounts/{ACCOUNT_ID}/access/apps/{app['id']}/policies")["result"] or []
        names = ", ".join(p.get("name", "?") for p in policies) or "(無政策 = 全擋)"
        print(f"  {spec['host']:<24} 已保護 — {names}")


def cmd_rollback(args) -> None:
    removed = 0
    for app in list_apps():
        if not str(app.get("name", "")).startswith(TAG):
            continue
        request("DELETE", f"/accounts/{ACCOUNT_ID}/access/apps/{app['id']}")
        print(f"- 已拆除 {app.get('domain')}")
        removed += 1
    print(f"共拆除 {removed} 個(service token 保留,要刪請去後台)。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "apply", "status", "rollback"])
    parser.add_argument("--include-hands", action="store_true",
                        help="連 hands.cn-dev.uk 一起保護。這是規劃窗唯一的 VPS 通道,"
                             "設錯就自己鎖自己,先確認客戶端送得出 header 再加")
    args = parser.parse_args()
    {"plan": cmd_plan, "apply": cmd_apply,
     "status": cmd_status, "rollback": cmd_rollback}[args.command](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
