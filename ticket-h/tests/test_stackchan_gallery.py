"""TICKET-H:StackChan 照片 ↔ 相簿對帳的規則測試。

這支管線會**刪檔案**(相簿刪除要連實體檔一起刪),也會**刪資料列**
(磁碟上沒有的就從相簿移除)。這種東西不能靠線上試錯,規則要先用測試釘死。

特別鎖住三件容易錯的事:
1. 磁碟是唯一事實來源——磁碟沒有的,相簿要移除;但**沒有 source_ref 的舊資料
   不能被當成「磁碟沒有」而誤刪**(相簿裡有一筆 7/20 的遺留 stackchan 照片)。
2. 「改為暫存」要重設檔案 mtime。stackchan-mcp 的 60 天清除看的是 mtime,
   不重設的話,一張放很久的照片被改回暫存會在下一次清除時立刻消失。
3. 暫存照片計入自動配額,超過軟上限要跳過而不是硬塞,更不能因為塞不下就刪磁碟。
"""
from __future__ import annotations

import errno
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import stackchan_gallery


SCHEMA = """
CREATE TABLE gallery_photos (
  id TEXT PRIMARY KEY,
  album_id TEXT,
  source_type TEXT NOT NULL,
  source_ref TEXT,
  source_message_id TEXT,
  original_name TEXT NOT NULL,
  stored_name TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  permanent INTEGER NOT NULL DEFAULT 0,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""

JPEG = b"\xff\xd8\xff\xe0" + b"nuonuo" * 40 + b"\xff\xd9"


@pytest.fixture()
def photos(tmp_path, monkeypatch):
    root = tmp_path / "photos"
    pending = root / "pending"
    saved = root / "saved"
    pending.mkdir(parents=True)
    saved.mkdir(parents=True)
    monkeypatch.setenv("STACKCHAN_PHOTO_ROOT", str(root))

    class Disk:
        pending_dir = pending
        saved_dir = saved

        def put(self, photo_id: str, status: str = "pending", **metadata) -> Path:
            directory = pending if status == "pending" else saved
            image = directory / f"{photo_id}.jpg"
            image.write_bytes(JPEG)
            payload = {"id": photo_id, "status": status,
                       "created_at": datetime.now(timezone.utc).isoformat()}
            payload.update(metadata)
            image.with_suffix(".json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return image

    return Disk()


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    yield connection
    connection.close()


@pytest.fixture()
def gallery_root(tmp_path):
    root = tmp_path / "gallery"
    root.mkdir()
    return root


def run(conn, gallery_root, cap: int = 10_000_000):
    return stackchan_gallery.sync(conn, gallery_root=gallery_root, soft_cap_bytes=cap)


def rows(conn):
    return conn.execute(
        "SELECT source_ref,permanent,note,stored_name,byte_size FROM gallery_photos "
        "ORDER BY source_ref"
    ).fetchall()


# --- 拍了沒刪就要進相簿 -----------------------------------------------------

def test_pending_photo_lands_in_gallery_as_transient(photos, conn, gallery_root):
    photos.put("20260901T091829Z_aaa", question="老婆帶我出門了！看看外面是什麼風景？")

    result = run(conn, gallery_root)

    assert result.added == ["20260901T091829Z_aaa"]
    (row,) = rows(conn)
    assert row["permanent"] == 0, "拍了還沒決定 = 相簿的暫存"
    assert "看看外面" in row["note"], "拍照當下的提問就是最好的說明"
    assert (gallery_root / row["stored_name"]).read_bytes() == JPEG


def test_saved_photo_lands_as_permanent(photos, conn, gallery_root):
    photos.put("kept", status="saved")
    run(conn, gallery_root)
    assert rows(conn)[0]["permanent"] == 1


def test_category_goes_into_note_not_a_new_ui(photos, conn, gallery_root):
    """R1:category 併進相簿來源分組,不另立分類 UI;有值就寫進 note。"""
    photos.put("withcat", question="這是什麼", category="花")
    run(conn, gallery_root)
    assert "分類:花" in rows(conn)[0]["note"]


def test_sync_is_idempotent(photos, conn, gallery_root):
    photos.put("once")
    run(conn, gallery_root)
    second = run(conn, gallery_root)
    assert second.added == [] and len(rows(conn)) == 1, "每分鐘跑一次不能一直長新的"


# --- 狀態同步 ---------------------------------------------------------------

def test_keep_promotes_existing_row(photos, conn, gallery_root):
    image = photos.put("promoteme")
    run(conn, gallery_root)
    assert rows(conn)[0]["permanent"] == 0
    # cn 用工具 keep:檔案搬到 saved/
    image.replace(photos.saved_dir / image.name)
    image.with_suffix(".json").replace(photos.saved_dir / f"{image.stem}.json")

    result = run(conn, gallery_root)

    assert result.promoted == ["promoteme"]
    assert rows(conn)[0]["permanent"] == 1


def test_delete_removes_row_and_reports_stale_file(photos, conn, gallery_root):
    image = photos.put("deleteme")
    run(conn, gallery_root)
    stored = rows(conn)[0]["stored_name"]
    image.unlink()
    image.with_suffix(".json").unlink()

    result = run(conn, gallery_root)

    assert result.removed == ["deleteme"]
    assert rows(conn) == [], "磁碟沒有了,相簿不該留死卡"
    assert result.stale_files == [stored], "相簿的檔案也要一起收掉"


def test_expiry_is_just_another_disappearance(photos, conn, gallery_root):
    """60 天到期是 stackchan-mcp 直接刪檔,對帳看到的就是「檔案不見了」。"""
    image = photos.put("expired")
    run(conn, gallery_root)
    image.unlink(); image.with_suffix(".json").unlink()
    assert run(conn, gallery_root).removed == ["expired"]


# --- 不能誤傷的東西 ---------------------------------------------------------

def test_legacy_row_without_source_ref_is_never_touched(photos, conn, gallery_root):
    """相簿裡有一筆 7/20 的遺留 stackchan 照片,沒有 source_ref 對不上磁碟。

    它不是「磁碟上被刪掉的照片」,是來歷不明但可能有意義的東西——不准刪。
    """
    conn.execute(
        "INSERT INTO gallery_photos VALUES('legacy1',NULL,'stackchan','',NULL,'a.jpg',"
        "'stored-a.jpg','image/jpeg',10,'x','',1,'mumu','2026-07-20T00:00:00Z')")

    result = run(conn, gallery_root)

    assert result.removed == []
    assert conn.execute("SELECT 1 FROM gallery_photos WHERE id='legacy1'").fetchone()


def test_other_sources_are_out_of_scope(photos, conn, gallery_root):
    conn.execute(
        "INSERT INTO gallery_photos VALUES('chat1',NULL,'chat','',NULL,'a.jpg',"
        "'stored-c.jpg','image/jpeg',10,'x','',0,'user','2026-09-01T00:00:00Z')")
    run(conn, gallery_root)
    assert conn.execute("SELECT 1 FROM gallery_photos WHERE id='chat1'").fetchone()


def test_soft_cap_skips_instead_of_forcing_or_deleting(photos, conn, gallery_root):
    photos.put("toobig")
    result = run(conn, gallery_root, cap=10)
    assert result.skipped_soft_cap == ["toobig"]
    assert rows(conn) == []
    assert (photos.pending_dir / "toobig.jpg").is_file(), "塞不進相簿不代表可以刪磁碟"


def test_freed_bytes_from_removals_count_toward_the_cap(photos, conn, gallery_root):
    """先移除再新增:騰出來的空間要能讓新的那張進得來。"""
    old = photos.put("old")
    run(conn, gallery_root, cap=len(JPEG) + 10)
    old.unlink(); old.with_suffix(".json").unlink()
    photos.put("new")

    result = run(conn, gallery_root, cap=len(JPEG) + 10)

    assert result.removed == ["old"] and result.added == ["new"]


# --- 反方向:相簿的動作寫回實體檔 -------------------------------------------

def test_set_permanent_moves_file_to_saved(photos, conn, gallery_root):
    photos.put("tosave")
    assert stackchan_gallery.set_permanent_on_disk("tosave", True) is True
    assert (photos.saved_dir / "tosave.jpg").is_file()
    assert not (photos.pending_dir / "tosave.jpg").exists()
    meta = json.loads((photos.saved_dir / "tosave.json").read_text(encoding="utf-8"))
    assert meta["status"] == "saved" and meta["expires_at"] is None


def test_demote_resets_mtime_so_it_is_not_swept_immediately(photos, conn, gallery_root):
    """把久放的照片改回暫存,不能讓它下一次清除就消失。

    stackchan-mcp 的 _cleanup_expired_pending() 是比對檔案 mtime,不是 expires_at。
    """
    image = photos.put("oldkeep", status="saved")
    ancient = time.time() - 200 * 86400
    os.utime(image, (ancient, ancient))

    assert stackchan_gallery.set_permanent_on_disk("oldkeep", False) is True

    moved = photos.pending_dir / "oldkeep.jpg"
    assert moved.is_file()
    assert moved.stat().st_mtime > time.time() - 60, "mtime 沒重設,下次清除就沒了"
    meta = json.loads((photos.pending_dir / "oldkeep.json").read_text(encoding="utf-8"))
    assert meta["status"] == "pending" and meta["expires_at"]


def test_set_permanent_is_a_noop_when_already_in_place(photos, conn, gallery_root):
    photos.put("already", status="saved")
    assert stackchan_gallery.set_permanent_on_disk("already", True) is True
    assert (photos.saved_dir / "already.jpg").is_file()


def test_set_permanent_reports_missing_photo(photos, conn, gallery_root):
    assert stackchan_gallery.set_permanent_on_disk("ghost", True) is False


def test_delete_on_disk_removes_image_and_metadata(photos, conn, gallery_root):
    photos.put("bye")
    assert stackchan_gallery.delete_on_disk("bye") is True
    assert not (photos.pending_dir / "bye.jpg").exists()
    assert not (photos.pending_dir / "bye.json").exists()
    assert stackchan_gallery.delete_on_disk("bye") is False


def test_delete_on_disk_covers_both_directories(photos, conn, gallery_root):
    photos.put("dup", status="pending")
    photos.put("dup2", status="saved")
    assert stackchan_gallery.delete_on_disk("dup2") is True
    assert not (photos.saved_dir / "dup2.jpg").exists()


# --- 端點層:相簿的動作要真的寫回實體檔(R1) ---------------------------------

def _stackchan_photo_on_disk(tmp_path: Path, photo_id: str, status: str = "pending") -> Path:
    """conftest 已把 STACKCHAN_PHOTO_ROOT 指到 tmp,這裡照那個位置放檔。"""
    directory = tmp_path / "stackchan-photos" / status
    directory.mkdir(parents=True, exist_ok=True)
    image = directory / f"{photo_id}.jpg"
    image.write_bytes(JPEG)
    image.with_suffix(".json").write_text(
        json.dumps({"id": photo_id, "status": status}, ensure_ascii=False), encoding="utf-8")
    return image


def _upload_stackchan(client, auth, photo_id: str):
    return client.post(
        "/api/v2/gallery/photos",
        headers=auth,
        data={"source_type": "stackchan", "source_ref": photo_id, "note": "測試"},
        files={"file": (f"{photo_id}.jpg", JPEG, "image/jpeg")},
    )


def test_marking_permanent_moves_the_real_file(client, auth, tmp_path):
    photo_id = "20260902T000000Z_endpoint"
    _stackchan_photo_on_disk(tmp_path, photo_id)
    created = _upload_stackchan(client, auth, photo_id).json()

    response = client.patch(
        f"/api/v2/gallery/photos/{created['id']}", headers=auth, json={"permanent": True})

    assert response.status_code == 200
    assert response.json()["permanent"] is True
    root = tmp_path / "stackchan-photos"
    assert (root / "saved" / f"{photo_id}.jpg").is_file(), "相簿按永久,實體檔要進 saved/"
    assert not (root / "pending" / f"{photo_id}.jpg").exists()


def test_marking_permanent_fails_loudly_when_the_file_is_gone(client, auth, tmp_path):
    """磁碟才是事實來源。檔案不在了就不要在相簿裡假裝設定成功。"""
    created = _upload_stackchan(client, auth, "20260902T000000Z_ghost").json()

    response = client.patch(
        f"/api/v2/gallery/photos/{created['id']}", headers=auth, json={"permanent": True})

    assert response.status_code == 409


def test_deleting_from_gallery_removes_the_real_file(client, auth, tmp_path):
    photo_id = "20260902T000000Z_bye"
    _stackchan_photo_on_disk(tmp_path, photo_id)
    created = _upload_stackchan(client, auth, photo_id).json()

    response = client.delete(f"/api/v2/gallery/photos/{created['id']}", headers=auth)

    assert response.status_code == 200
    root = tmp_path / "stackchan-photos"
    assert not (root / "pending" / f"{photo_id}.jpg").exists()
    assert not (root / "pending" / f"{photo_id}.json").exists()
    listing = client.get("/api/v2/gallery", headers=auth).json()
    assert all(p["id"] != created["id"] for p in listing["photos"])


def test_delete_endpoint_refuses_non_stackchan_photos(client, auth):
    """相簿其他來源原本就沒有刪除功能,要不要開是另一個決定,不在本工單。"""
    created = client.post(
        "/api/v2/gallery/photos",
        headers=auth,
        data={"source_type": "chat", "note": "x"},
        files={"file": ("x.jpg", JPEG, "image/jpeg")},
    )
    if created.status_code != 200:
        pytest.skip("chat 照片需要來源訊息,這裡只驗擋門邏輯")
    response = client.delete(f"/api/v2/gallery/photos/{created.json()['id']}", headers=auth)
    assert response.status_code == 400


def test_missing_photo_root_never_wipes_the_gallery(photos, conn, gallery_root, monkeypatch, tmp_path):
    """照片目錄讀不到時,不准把相簿裡的 StackChan 照片當成「已被刪除」。

    掛載掉、路徑改了、服務搬家都會讓 scan_disk() 回空的。
    分不出「真的一張都沒有」和「根本讀不到」的時候,寧可什麼都不做。
    """
    photos.put("precious")
    run(conn, gallery_root)
    assert len(rows(conn)) == 1

    monkeypatch.setenv("STACKCHAN_PHOTO_ROOT", str(tmp_path / "not-mounted"))
    result = run(conn, gallery_root)

    assert result.skipped_missing_root is True
    assert result.removed == []
    assert len(rows(conn)) == 1, "目錄讀不到就把相簿清空 = 最糟的失敗方式"


# --- 端點層:磁碟寫不進去的時候(9/2 事故) -----------------------------------
#
# 9/2 上線後刪除回 500,空白的 Internal Server Error。原因不在程式邏輯,
# 而在 backend 的 systemd 沙箱 ProtectSystem=strict 只開了
# ReadWritePaths=/root/chatnest-next/data,/srv/mumu-server 對它是唯讀的。
# 我當時查到「backend 以 root 跑」就判斷權限沒問題——以身分推斷能力,沒有真的寫一次。
#
# 沙箱設定本身測不進 pytest(那是部署層的事,改用
# ticket-h/verify_disk_writeback.py 在同規格的 systemd 沙箱裡實測)。
# 這裡鎖的是**寫不進去的時候端點要怎麼表現**:
#   1. 回 409 且訊息看得懂,不是空白 500;
#   2. DB 不准動。反過來做(相簿刪了、檔案還在)不是「至少成功一半」,
#      下一輪對帳會照磁碟把它放回來,變成刪了又出現的鬼打牆。

def _read_only_error(*_args, **_kwargs):
    raise OSError(errno.EROFS, "Read-only file system")


def test_delete_surfaces_filesystem_failure_and_keeps_the_row(client, auth, tmp_path, monkeypatch):
    photo_id = "20260902T000000Z_readonly_del"
    image = _stackchan_photo_on_disk(tmp_path, photo_id)
    created = _upload_stackchan(client, auth, photo_id).json()
    monkeypatch.setattr(stackchan_gallery, "delete_on_disk", _read_only_error)

    response = client.delete(f"/api/v2/gallery/photos/{created['id']}", headers=auth)

    assert response.status_code == 409, "檔案系統失敗不該變成空白的 500"
    assert "Read-only file system" in response.json()["detail"], "訊息要說得出是什麼壞了"
    assert image.is_file(), "檔案本來就沒刪掉"
    listing = client.get("/api/v2/gallery", headers=auth).json()
    assert any(p["id"] == created["id"] for p in listing["photos"]), (
        "磁碟刪不掉卻把 DB 列刪了 = 下一輪對帳又把它放回來"
    )


def test_marking_permanent_surfaces_filesystem_failure_and_keeps_the_state(
    client, auth, tmp_path, monkeypatch
):
    photo_id = "20260902T000000Z_readonly_keep"
    _stackchan_photo_on_disk(tmp_path, photo_id)
    created = _upload_stackchan(client, auth, photo_id).json()
    monkeypatch.setattr(stackchan_gallery, "set_permanent_on_disk", _read_only_error)

    response = client.patch(
        f"/api/v2/gallery/photos/{created['id']}", headers=auth, json={"permanent": True})

    assert response.status_code == 409
    assert "Read-only file system" in response.json()["detail"]
    root = tmp_path / "stackchan-photos"
    assert (root / "pending" / f"{photo_id}.jpg").is_file()
    current = client.get("/api/v2/gallery", headers=auth).json()
    entry = next(p for p in current["photos"] if p["id"] == created["id"])
    assert entry["permanent"] is False, "磁碟沒搬成,相簿不准自己說已經永久收藏了"
