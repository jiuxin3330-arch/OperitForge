"""在與 chatnest-next 相同的 systemd 沙箱裡,實測兩條寫回磁碟的路徑。

9/2 的 500 就是死在這裡:程式以 root 跑,但 ProtectSystem=strict 讓
/srv/mumu-server 對它是唯讀的。以身分推斷能力(「是 root 所以寫得進去」)
測不出這件事,只有真的在同一個 mount namespace 裡寫一次才算數。
"""
import sys
sys.path.insert(0, "/srv/chatnest-next/backend")
from app import stackchan_gallery as sg

PHOTO_ID = sys.argv[1]
ok = True

def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    ok = ok and cond

status, image = sg._locate(PHOTO_ID)
check(f"起始在 pending/ (status={status})", status == "pending" and image is not None)

check("設永久 → 搬到 saved/", sg.set_permanent_on_disk(PHOTO_ID, True))
status, image = sg._locate(PHOTO_ID)
check("實體檔真的在 saved/", status == "saved" and image is not None)
check("metadata 一起搬過去", image.with_suffix(".json").is_file())

check("改回暫存 → 搬回 pending/", sg.set_permanent_on_disk(PHOTO_ID, False))
status, image = sg._locate(PHOTO_ID)
check("實體檔真的回到 pending/", status == "pending")

check("刪除 → delete_on_disk 回報有刪到", sg.delete_on_disk(PHOTO_ID))
status, image = sg._locate(PHOTO_ID)
check("磁碟上真的不見了", image is None)

print("RESULT=" + ("OK" if ok else "BROKEN"))
sys.exit(0 if ok else 1)
