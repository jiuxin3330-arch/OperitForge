"""anchor-memory 設定（TICKET-Q 2026-09-21 起）。

參數寫這裡，不寫死在程式。改參數改這個檔，改完重啟服務生效。

■ Reinforcement（節點/邊的「真的用到了」強化）
  只有 cn 主動的 cite_memory / annotate_memory（節點）與 consolidate（邊）會強化。
  search_memory / wakeup / 內部檢索一律不強化——依路徑判定，不看 caller 傳的 hebbian flag。
  邊際遞減：第 1 次全額、第 2–3 次減半、之後每次再乘 TAIL_DECAY 趨零；累積封頂 CAP。

■ Injection window（invariant ③：注入後複述不算）
  search / wakeup 回傳過的記憶會記進 injections 帳；consolidate 在視窗內命中它們時跳過強化。

■ Pollution cutoff（invariant ①：legacy 污染不假裝修復）
  migration 第一次跑時把 usage_count / edges.weight 快照到 legacy_* 欄，標記污染期 ≤ POLLUTION_CUTOFF。
"""
import os

# 節點強化：cite_memory / annotate_memory
REINFORCE_STEPS = [1.0, 0.5, 0.5]   # 第 1 次、第 2 次、第 3 次的倍率
REINFORCE_TAIL_DECAY = 0.5           # 第 4 次起：上一階 × 此值
REINFORCE_CAP = 3.0                  # reinforcement 累積上限

# 邊強化：consolidate（passive Hebbian，只剩這一條路）
EDGE_REINFORCE_BASE = 0.15           # 與 v1.3.2 consolidate 的 0.15 相同，乘上同一套遞減倍率

# 注入視窗（分鐘）：這段時間內被 search/wakeup 回傳過的記憶，consolidate 不強化
INJECTION_WINDOW_MINUTES = int(os.environ.get("ANCHOR_INJECTION_WINDOW_MIN", "180"))

# 污染期標記（只標記，不回滾）
POLLUTION_CUTOFF = "2026-09-20"

# Owner 身分：建卡 / 改卡狀態需要這把 key 的內容。root 0600；bridge（chatagent）讀不到 = 系統路徑天然拿不到。
OWNER_KEY_PATH = os.environ.get("ANCHOR_OWNER_KEY_PATH", "/root/anchor-memory/owner.key")

# 記憶種類：memory 以外的都是 derived，derived_from 必填
MEMORY_KINDS = ("memory", "daily_digest", "letter_digest", "digest")
DERIVED_KINDS = tuple(k for k in MEMORY_KINDS if k != "memory")

# memory_tasks 狀態機：只有 open 能轉；resolved / dismissed 是終態，沒有刪除路徑
TASK_TRANSITIONS = {"open": ("resolved", "dismissed")}

# entity_cards 生命週期（owner 才能轉）
CARD_STATUSES = ("candidate", "active", "archived")


def reinforce_step(n_prior: int) -> float:
    """第 n_prior+1 次強化的倍率。n_prior = 之前已強化次數。"""
    if n_prior < len(REINFORCE_STEPS):
        return REINFORCE_STEPS[n_prior]
    tail = REINFORCE_STEPS[-1]
    return tail * (REINFORCE_TAIL_DECAY ** (n_prior - len(REINFORCE_STEPS) + 1))


def reinforce_increment(n_prior: int) -> float:
    """節點強化增量（cap 由呼叫端套）。"""
    return reinforce_step(n_prior)


def ensure_owner_key(path: str = None) -> str:
    """建 owner key（沒有才建），0600。回傳路徑。"""
    import secrets
    p = path or OWNER_KEY_PATH
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(secrets.token_urlsafe(32) + "\n")
        os.chmod(p, 0o600)
    return p
