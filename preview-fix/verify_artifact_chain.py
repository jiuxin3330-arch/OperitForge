"""實測 backend → bridge → HOME 這條鏈,用的是生產同一支 gateway 與同一組憑證。

跑法(VPS):

    cd /srv/chatnest-next
    set -a; . /root/chatnest-next/runtime/mumu-live.env; set +a
    .venv/bin/python scripts/verify_artifact_chain.py

不 monkeypatch 任何東西,也不印任何憑證內容。
2026-09-02 交付時的結果:全部 PASS(RESULT=OK)。
"""
import asyncio
import sys

sys.path.insert(0, "/srv/chatnest-next/backend")

from app.gateways import VersionBridgeGateway

FILES = [
    ("catch-butterfly.html", "9/1 新檔,原本打不開的那張"),
    ("mumu_phone.html", "8/19 手機模擬器(回歸)"),
    ("anniversary_4months.html", "7/17 四個月紀念(回歸)"),
    ("qixi_late_gift.html", "8/20 七夕遲來禮物(回歸)"),
    ("test.html", "test"),
]


async def main() -> int:
    gateway = VersionBridgeGateway()
    ok = True
    for name, note in FILES:
        response = await gateway.request("GET", f"artifact/{name}", params={})
        if response.status_code != 200:
            print(f"FAIL {response.status_code} {name} — {note}")
            ok = False
            continue
        html = response.json().get("html", "")
        if not html.strip():
            print(f"FAIL empty {name} — {note}")
            ok = False
            continue
        print(f"PASS {name:28s} {len(html):>6d} chars — {note}")

    # 白名單:這條 gateway 不是通用代理
    from fastapi import HTTPException
    for blocked in ("chat", "sessions", "profile"):
        try:
            await gateway.request("GET", blocked, params={})
        except HTTPException as exc:
            print(f"PASS 白名單擋下 {blocked} ({exc.status_code})")
        else:
            print(f"FAIL 白名單沒擋 {blocked}")
            ok = False

    # 不存在的檔案要 404,不是 500
    response = await gateway.request("GET", "artifact/no-such-file.html", params={})
    if response.status_code == 404:
        print("PASS 不存在的 artifact 回 404")
    else:
        print(f"FAIL 不存在的 artifact 回 {response.status_code}")
        ok = False

    print("RESULT=" + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


raise SystemExit(asyncio.run(main()))
