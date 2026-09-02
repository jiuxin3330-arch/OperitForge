"""TICKET-I A 段:build 腳本的漂移護欄。

runtime 曾經領先 patch 源碼而沒人發現,直到有人打算重 build。那次沒炸,
是因為施工者先 build 到臨時目錄比對 —— 運氣加紀律,不是設計。
這裡鎖住「腳本自己會做那個比對」。
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
