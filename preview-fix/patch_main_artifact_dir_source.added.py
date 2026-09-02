"""① 新增到 scripts/version_bridge_runtime_patch.py 的 patch 函式。

實際位置:插在 `patch_main_heartbeat_source` 之前。
同時掛進 scripts/build_version_bridge_runtime.py:

    from version_bridge_runtime_patch import (
        ...
        patch_main_artifact_dir_source,   # ← 加在 import 清單
        patch_main_context_source,
        ...
    )

    text = patch_main_context_source(text)
    text = patch_main_artifact_dir_source(text)          # ← 加在 patch 鏈

    manifest = {
        ...
        "artifact_dir_from_home": True,                  # ← 加在 manifest
    }

runtime/version-bridge-app/app/main.py 的那一行不是手打的,
是直接呼叫本函式產生的,所以兩邊逐字一致。
"""


_MAIN_ARTIFACT_DIR_OLD = '_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts"'
_MAIN_ARTIFACT_DIR_NEW = '_ARTIFACT_DIR = Path(os.environ.get("HOME") or Path(__file__).resolve().parent.parent) / "artifacts"'


def patch_main_artifact_dir_source(source: str) -> str:
    """Serve artifacts from the bridge's own HOME, which is where cn writes them.

    cn runs with HOME=<data>/version-bridge/home and a cwd of the runtime app dir,
    so his relative ``artifacts/x.html`` lands in HOME. Before this patch the
    endpoint looked next to the runtime app instead, and found nothing.
    Reading his own HOME keeps this inside the bridge's chatagent identity —
    no root process needs to reach into that 0700 directory.
    """
    if "CHATNEST_VERSION_BRIDGE_MAIN_ARTIFACT_DIR_V1" in source:
        return source
    if _MAIN_ARTIFACT_DIR_OLD not in source:
        raise RuntimeError("Legacy artifact dir shape changed; refusing bridge patch")
    source = source.replace(_MAIN_ARTIFACT_DIR_OLD, _MAIN_ARTIFACT_DIR_NEW, 1)
    return source + "\n# CHATNEST_VERSION_BRIDGE_MAIN_ARTIFACT_DIR_V1\n"
