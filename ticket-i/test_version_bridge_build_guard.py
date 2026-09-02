"""TICKET-I:build 腳本的漂移護欄(A 段)與回填驗收(B 段)。

runtime 曾經領先 patch 源碼而沒人發現,直到有人打算重 build。那次沒炸,
是因為施工者先 build 到臨時目錄比對 —— 運氣加紀律,不是設計。
前半鎖住「腳本自己會做那個比對」,後半鎖住「回填過的檔案真的重現得出來」。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path("/root/chatnest-next/scripts")
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_version_bridge_runtime import (  # noqa: E402
    _drift_report,
    _is_build_ignored,
    _manifest_sha_drift,
)


def _write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_no_drift_when_runtime_matches_build(tmp_path):
    staging, target = tmp_path / "staging", tmp_path / "target"
    for root in (staging, target):
        _write(root, "app/main.py", "print('same')\n")
    drifted, backups = _drift_report(staging, target)
    assert drifted == []
    assert backups == 0


def test_first_build_has_nothing_to_protect(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "app/main.py", "print('new')\n")
    assert _drift_report(staging, tmp_path / "does-not-exist") == ([], 0)


def test_changed_file_is_reported_with_line_count(tmp_path):
    staging, target = tmp_path / "staging", tmp_path / "target"
    _write(staging, "app/usage.py", "a\nb\n")
    _write(target, "app/usage.py", "a\nb\nc\n")
    drifted, _ = _drift_report(staging, target)
    assert len(drifted) == 1
    assert "app/usage.py" in drifted[0]
    assert "1 行" in drifted[0]


def test_runtime_only_file_is_reported_as_about_to_be_deleted(tmp_path):
    # autonomy_tool.py 就是這一類:manifest 沒記它,只比 sha 永遠看不見它。
    staging, target = tmp_path / "staging", tmp_path / "target"
    _write(staging, "app/main.py", "x\n")
    _write(target, "app/main.py", "x\n")
    _write(target, "app/autonomy_tool.py", "TOOL = 1\n")
    drifted, _ = _drift_report(staging, target)
    assert len(drifted) == 1
    assert "app/autonomy_tool.py" in drifted[0]
    assert "刪掉" in drifted[0]


def test_backup_files_are_counted_but_never_block_the_build(tmp_path):
    # build 本來就不收 *.bak*。把十幾個施工回滾點列進主清單,
    # 只會淹掉真正該看的那幾個檔。
    assert _is_build_ignored("main.py.bak-preview-1788340030")
    assert _is_build_ignored("claude.py.bak.20260814-193219")
    assert _is_build_ignored("main.cpython-312.pyc")
    assert not _is_build_ignored("autonomy_tool.py")

    staging, target = tmp_path / "staging", tmp_path / "target"
    _write(staging, "app/main.py", "x\n")
    _write(target, "app/main.py", "x\n")
    _write(target, "app/main.py.bak-something", "old\n")
    drifted, backups = _drift_report(staging, target)
    assert drifted == []
    assert backups == 1


def test_manifest_sha_drift_reports_a_lying_manifest(tmp_path):
    target = tmp_path / "target"
    _write(target, "app/main.py", "real content\n")
    _write(target, "app/actor.py", "actor\n")
    (target / "runtime-manifest.json").write_text(
        json.dumps(
            {
                "runtime_main_sha256": "deadbeef" * 8,
                "runtime_actor_sha256": __import__("hashlib")
                .sha256(b"actor\n")
                .hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    stale = _manifest_sha_drift(target)
    assert len(stale) == 1
    assert "app/main.py" in stale[0]


@pytest.mark.skipif(
    not Path("/root/chatnest/full-stack/app/main.py").is_file(),
    reason="需要 legacy 源碼才能真的 build",
)
def test_build_refuses_to_overwrite_a_drifted_runtime(tmp_path):
    """端到端:真的跑腳本,確認它擋得住,而且擋住之後 target 原封不動。"""
    target = tmp_path / "runtime"
    first = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_version_bridge_runtime.py"),
         "--target", str(target)],
        capture_output=True, text=True,
    )
    assert first.returncode == 0, first.stderr
    # 確認這是一次真的 build,不是空跑成功:產物要是 patch 過的
    built_main = (target / "app" / "main.py").read_text(encoding="utf-8")
    assert "CHATNEST_VERSION_BRIDGE" in built_main
    assert (target / "runtime-manifest.json").is_file()

    # 模擬一條沒回填的熱修
    hotfix = target / "app" / "only_in_runtime.py"
    hotfix.write_text("HOTFIX = True\n", encoding="utf-8")

    blocked = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_version_bridge_runtime.py"),
         "--target", str(target)],
        capture_output=True, text=True,
    )
    assert blocked.returncode != 0
    assert "拒絕覆蓋" in blocked.stderr
    assert "only_in_runtime.py" in blocked.stderr
    assert "TICKET_I_runtime_drift_backport.md" in blocked.stderr
    assert hotfix.is_file(), "被擋下來了卻還是動了 target"

    forced = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_version_bridge_runtime.py"),
         "--target", str(target), "--overwrite-drifted-runtime"],
        capture_output=True, text=True,
    )
    assert forced.returncode == 0, forced.stderr
    assert not hotfix.is_file(), "明講要覆蓋了卻沒覆蓋"


RUNTIME = Path("/root/chatnest-next/runtime/version-bridge-app")

# TICKET-I B2(9/15 之後):人格敏感區,這一輪不碰。
B2_PENDING = {"app/claude.py", "app/easter_egg.py", "PERSONA.md"}


def _sentinel_insensitive(text: str) -> tuple[str, ...]:
    """把檔尾的 patch 哨兵抽出來排序,其餘照原樣。

    哨兵是註解,順序不影響行為。runtime 現在的排列是「build 一次、之後熱修兩次」
    的歷史痕跡;build 產出的順序才是規範的。兩者要真正對齊,得等 B 全部收工後
    跑一次授權重 build —— 在那之前這裡不該因為註解的排列而紅。
    """
    lines = text.splitlines()
    body = [ln for ln in lines if not ln.startswith("# CHATNEST_VERSION_BRIDGE")]
    sentinels = sorted(ln for ln in lines if ln.startswith("# CHATNEST_VERSION_BRIDGE"))
    return tuple(body), tuple(sentinels)


@pytest.mark.skipif(
    not (RUNTIME / "app" / "main.py").is_file()
    or not Path("/root/chatnest/full-stack/app/main.py").is_file(),
    reason="需要 legacy 源碼與現行 runtime 才能驗收回填",
)
def test_b1_backports_leave_only_the_b2_files_drifted(tmp_path):
    """B1 驗收:回填過的檔案,build 產物要跟 runtime 一模一樣。

    這條會隨 B2 收工而自然收斂 —— 到時候剩餘漂移是空的,斷言仍然成立。
    """
    target = tmp_path / "runtime"
    built = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_version_bridge_runtime.py"),
         "--target", str(target)],
        capture_output=True, text=True,
    )
    assert built.returncode == 0, built.stderr

    # 回填過的三個檔:逐字相同
    for name in ("app/usage.py", "app/memory_bridge.py", "app/autonomy_tool.py"):
        assert (target / name).read_bytes() == (RUNTIME / name).read_bytes(), (
            f"{name} 回填後仍與 runtime 不同"
        )

    # main.py:實質內容相同,只容許哨兵排列不同
    assert _sentinel_insensitive(
        (target / "app" / "main.py").read_text(encoding="utf-8")
    ) == _sentinel_insensitive(
        (RUNTIME / "app" / "main.py").read_text(encoding="utf-8")
    )

    # 其餘漂移不得超出 B2 待辦
    drifted, _ = _drift_report(target, RUNTIME)
    names = {line.strip().split(" ——")[0] for line in drifted}
    assert names <= B2_PENDING | {"app/main.py"}, f"冒出 B2 以外的漂移:{names}"


@pytest.mark.skipif(
    not Path("/root/chatnest-next/bridge-extras").is_dir(),
    reason="需要 bridge-extras 目錄",
)
def test_bridge_extras_reach_the_build_and_get_recorded(tmp_path):
    """autonomy_tool.py 只屬於 bridge。裁定(乙):放程式碼、build 複製、manifest 記 sha。"""
    target = tmp_path / "runtime"
    built = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_version_bridge_runtime.py"),
         "--target", str(target)],
        capture_output=True, text=True,
    )
    assert built.returncode == 0, built.stderr

    extras = sorted(p.name for p in Path("/root/chatnest-next/bridge-extras").glob("*.py"))
    assert "autonomy_tool.py" in extras

    manifest = json.loads((target / "runtime-manifest.json").read_text(encoding="utf-8"))
    recorded = manifest.get("bridge_extras") or {}
    for name in extras:
        copied = target / "app" / name
        assert copied.is_file(), f"{name} 沒有進到 build 產物"
        assert recorded.get(name), f"manifest 沒有記 {name} 的 sha"
