"""StackChan 照片 ↔ 相簿的對帳(TICKET-H)。

糯糯的設計意圖(工單原話,以此為準):「只要拍了沒有立刻刪除就要進相簿ㄛ！」

## 為什麼是「對帳」而不是在拍照當下推一筆

StackChan 照片有三條會改變狀態的路徑:
  ① 拍照落地      —— ota_server.py `_store_pending_photo()` 寫進 pending/
  ② cn 用工具決定 —— stackchan-mcp 的 photo_keep(pending→saved)/ photo_delete
  ③ 60 天到期     —— stackchan-mcp 的 `_cleanup_expired_pending()` 直接刪檔

要在每一條上都掛一個「順便通知相簿」,等於改動 StackChan 既有行為
(工單邊界明文禁止),而且只要漏掉一條,相簿就會留下指向已刪檔案的死卡。

所以改成單向對帳:**磁碟是唯一事實來源,相簿跟著它走。**
三條路徑一條都不用改;漏了也會在下一輪自動補回來;
「回填既有 12 張」也不是特例,只是第一次跑而已。

## 反方向

相簿按「永久收藏」/「刪除」要寫回實體檔(R1),由 `set_permanent_on_disk()`
與 `delete_on_disk()` 在端點裡同步處理。寫完之後下一輪對帳會確認兩邊一致
——所以就算寫回失敗,狀態也只是回到磁碟說的那個,不會兩邊各說各話。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

DEFAULT_PHOTO_ROOT = Path("/srv/mumu-server/photos")


def photo_root() -> Path:
    """每次呼叫都重讀環境變數,不在 import 當下就把路徑釘死。

    釘死的代價實測過:背景對帳迴圈會在**測試啟動 app 時**去讀真正的
    /srv/mumu-server/photos,把 12 張生產照片灌進測試資料庫,
    連帶弄壞三個跟軟上限、堆疊計數有關的既有測試。
    背景工作不該伸手到設定範圍以外——用 STACKCHAN_PHOTO_ROOT 指到別處就好。
    """
    return Path(os.environ.get("STACKCHAN_PHOTO_ROOT") or DEFAULT_PHOTO_ROOT)


def pending_dir() -> Path:
    return photo_root() / "pending"


def saved_dir() -> Path:
    return photo_root() / "saved"

# 與 stackchan-mcp 的 PHOTO_RETENTION_DAYS 對齊。這裡只在「相簿把照片改回暫存」
# 時用來寫 expires_at;真正的清除仍由 stackchan-mcp 依檔案 mtime 執行。
RETENTION_DAYS = 60

SOURCE_TYPE = "stackchan"
CREATED_BY = "mumu"


@dataclass
class SyncResult:
    added: list[str] = field(default_factory=list)
    promoted: list[str] = field(default_factory=list)
    demoted: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    skipped_soft_cap: list[str] = field(default_factory=list)
    stale_files: list[str] = field(default_factory=list)
    skipped_missing_root: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.added or self.promoted or self.demoted or self.removed)

    def as_dict(self) -> dict[str, Any]:
        return {
            "added": len(self.added),
            "promoted": len(self.promoted),
            "demoted": len(self.demoted),
            "removed": len(self.removed),
            "skipped_soft_cap": len(self.skipped_soft_cap),
            "skipped_missing_root": self.skipped_missing_root,
        }


def _read_metadata(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def scan_disk() -> dict[str, dict[str, Any]]:
    """回傳 {photo_id: {"status", "image", "metadata"}}。磁碟是事實來源。"""
    found: dict[str, dict[str, Any]] = {}
    for status, directory in (("pending", pending_dir()), ("saved", saved_dir())):
        if not directory.is_dir():
            continue
        for image in sorted(directory.glob("*.jpg")):
            photo_id = image.stem
            found[photo_id] = {
                "status": status,
                "image": image,
                "metadata": _read_metadata(image.with_suffix(".json")),
            }
    return found


def _note_for(metadata: dict[str, Any]) -> str:
    """拍照當下的提問就是最好的說明;category 併進來(R1:不另立分類 UI)。"""
    parts = [str(metadata.get("question") or "").strip()]
    category = str(metadata.get("category") or "").strip()
    if category:
        parts.append(f"分類:{category}")
    return " · ".join(p for p in parts if p)[:512]


def _created_at_for(metadata: dict[str, Any], image: Path) -> str:
    created = str(metadata.get("created_at") or "").strip()
    if created:
        return created
    try:
        stamp = datetime.fromtimestamp(image.stat().st_mtime, tz=timezone.utc)
    except OSError:
        stamp = datetime.now(timezone.utc)
    return stamp.isoformat(timespec="microseconds")


def sync(conn: Any, *, gallery_root: Path, soft_cap_bytes: int) -> SyncResult:
    """把相簿裡的 StackChan 照片對齊磁碟。呼叫端負責 transaction 與刪檔。"""
    result = SyncResult()

    # 安全閥:照片目錄整個不見(掛載掉、路徑改了、服務搬家)時,「磁碟上什麼都沒有」
    # 這個結論是錯的,照著做會把相簿裡的 StackChan 照片全部刪掉。
    # 分不出「真的一張都沒有」和「根本讀不到」的時候,寧可什麼都不做。
    root = photo_root()
    if not root.is_dir():
        result.skipped_missing_root = True
        return result

    disk = scan_disk()

    rows = conn.execute(
        "SELECT id,source_ref,permanent,stored_name,byte_size FROM gallery_photos "
        "WHERE source_type=?",
        (SOURCE_TYPE,),
    ).fetchall()
    by_ref: dict[str, Any] = {}
    for row in rows:
        ref = str(row["source_ref"] or "").strip()
        if not ref:
            # 沒有 source_ref 就對不上磁碟(7/20 的遺留那筆)。不碰它,
            # 免得把來歷不明但可能有意義的照片刪掉。
            continue
        by_ref[ref] = row

    # 先處理移除:騰出來的位元組要能算進下面的軟上限判斷
    for ref, row in by_ref.items():
        if ref in disk:
            continue
        conn.execute("DELETE FROM gallery_photos WHERE id=?", (row["id"],))
        result.removed.append(ref)
        result.stale_files.append(str(row["stored_name"]))

    usage_row = conn.execute(
        "SELECT COALESCE(SUM(byte_size),0) AS total FROM gallery_photos"
    ).fetchone()
    usage = int(usage_row["total"])

    for photo_id, info in sorted(disk.items()):
        row = by_ref.get(photo_id)
        want_permanent = 1 if info["status"] == "saved" else 0

        if row is not None and photo_id not in result.removed:
            if int(row["permanent"]) != want_permanent:
                conn.execute(
                    "UPDATE gallery_photos SET permanent=? WHERE id=?",
                    (want_permanent, row["id"]),
                )
                (result.promoted if want_permanent else result.demoted).append(photo_id)
            continue

        image: Path = info["image"]
        try:
            content = image.read_bytes()
        except OSError:
            continue

        # 暫存照片計入自動配額(工單邊界)。超過就跳過,下一輪再試——
        # 不硬塞,也不因為塞不下就把它從磁碟刪掉。
        if soft_cap_bytes and usage + len(content) > soft_cap_bytes:
            result.skipped_soft_cap.append(photo_id)
            continue

        gallery_id = f"photo_{uuid4().hex}"
        stored_name = f"{gallery_id}-{photo_id}.jpg"
        destination = (gallery_root / stored_name).resolve()
        if destination.parent != gallery_root.resolve():
            continue
        gallery_root.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

        metadata = info["metadata"]
        conn.execute(
            """INSERT INTO gallery_photos
               (id,album_id,source_type,source_ref,source_message_id,original_name,
                stored_name,mime_type,byte_size,sha256,note,permanent,created_by,created_at)
               VALUES(?,NULL,?,?,NULL,?,?,?,?,?,?,?,?,?)""",
            (
                gallery_id,
                SOURCE_TYPE,
                photo_id,
                f"{photo_id}.jpg",
                stored_name,
                "image/jpeg",
                len(content),
                hashlib.sha256(content).hexdigest(),
                _note_for(metadata),
                want_permanent,
                CREATED_BY,
                _created_at_for(metadata, image),
            ),
        )
        usage += len(content)
        result.added.append(photo_id)

    return result


# --------------------------------------------------------------------------
# 反方向:相簿的動作寫回實體檔(R1)
# --------------------------------------------------------------------------

def _locate(photo_id: str) -> tuple[str | None, Path | None]:
    for status, directory in (("pending", pending_dir()), ("saved", saved_dir())):
        image = directory / f"{photo_id}.jpg"
        if image.is_file():
            return status, image
    return None, None


def set_permanent_on_disk(photo_id: str, permanent: bool) -> bool:
    """相簿設永久 → pending/ 搬到 saved/;改回暫存 → 搬回 pending/。"""
    status, image = _locate(photo_id)
    if not image:
        return False
    target_dir = saved_dir() if permanent else pending_dir()
    if (status == "saved") == bool(permanent):
        return True

    target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata_path = image.with_suffix(".json")
    metadata = _read_metadata(metadata_path)
    metadata.setdefault("id", photo_id)

    if permanent:
        metadata.update({
            "status": "saved",
            "kept_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": None,
        })
    else:
        expires = datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)
        metadata.update({
            "status": "pending",
            "kept_at": None,
            "expires_at": expires.isoformat(),
            "retention_days": RETENTION_DAYS,
        })

    target_image = target_dir / image.name
    shutil.move(str(image), str(target_image))
    (target_dir / metadata_path.name).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata_path.unlink(missing_ok=True)
    os.chmod(target_image, 0o600)
    os.chmod(target_dir / metadata_path.name, 0o600)

    if not permanent:
        # stackchan-mcp 的 60 天清除是看檔案 mtime,不是看 expires_at。
        # 搬回 pending 時 mtime 會沿用舊值,一張放了很久的照片會在下一次
        # 清除時立刻消失——那不是「改回暫存」該有的意思。重設 mtime,
        # 讓它從現在起重新算 60 天。
        now = time.time()
        os.utime(target_image, (now, now))
        os.utime(target_dir / metadata_path.name, (now, now))
    return True


def delete_on_disk(photo_id: str) -> bool:
    """相簿刪除 → 實體檔連 .json 一起刪(pending 與 saved 都清)。"""
    removed = False
    for directory in (pending_dir(), saved_dir()):
        image = directory / f"{photo_id}.jpg"
        if image.is_file():
            image.unlink(missing_ok=True)
            image.with_suffix(".json").unlink(missing_ok=True)
            removed = True
    return removed
