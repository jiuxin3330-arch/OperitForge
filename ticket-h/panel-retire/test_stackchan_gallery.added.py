"""TICKET-H 第 4 項新增的後端合約測試。

實際位置:backend/tests/test_stackchan_gallery.py 檔尾(附加,原有 24 條不動)。
這裡留一份獨立的,方便對照 diff。
"""


def test_legacy_stackchan_photo_endpoints_are_retired(client, auth):
    # 2026-09-02 裁定:StackChan 照片併入相簿、廢棄獨立面板、單一入口。
    # 這五個端點只服務過那個面板;鎖住它們,以免哪天被無意間接回來。
    #
    # 斷言鎖在「路由表裡沒有這些路徑」,不是鎖某個狀態碼:生產有前端 dist 時
    # main.py 會掛一個 SPA fallback(@app.get("/{path:path}")),把所有不存在的
    # GET 接去 index.html 回 200;測試環境沒有 dist,同一個請求是 404。
    # 硬寫 404 會綠在測試環境、卻描述不了生產,那就不是在測這件事。
    from app.main import app as fastapi_app

    live = [
        route.path
        for route in fastapi_app.routes
        if getattr(route, "path", "").startswith("/api/v2/stackchan")
    ]
    assert live == [], f"舊的 StackChan 照片端點又回來了:{live}"

    # 非 GET 方法沒有 fallback 可躲,直接驗行為:不被接受
    photo_id = "20260902T000000Z_abcdef0123"
    for method, path in [
        ("post", f"/api/v2/stackchan/photos/{photo_id}/keep"),
        ("patch", f"/api/v2/stackchan/photos/{photo_id}/category"),
        ("delete", f"/api/v2/stackchan/photos/{photo_id}"),
    ]:
        response = getattr(client, method)(path, headers=auth)
        assert response.status_code in (404, 405), f"{method.upper()} {path} 還活著"

    # GET 就算被 fallback 接住,也不准回照片資料。
    # 兩種環境的回應不同(測試 404 的 JSON detail / 生產 200 的 index.html),
    # 共同的事實只有一個:裡面沒有照片清單。
    listing = client.get("/api/v2/stackchan/photos", headers=auth)
    try:
        body = listing.json()
    except ValueError:
        body = None
    assert not isinstance(body, dict) or "photos" not in body

    # 正向對照:繼任的相簿入口必須還在,否則上面那些只是整台壞掉
    assert client.get("/api/v2/gallery", headers=auth).status_code == 200
