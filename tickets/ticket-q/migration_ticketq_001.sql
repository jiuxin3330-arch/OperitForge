-- TICKET-Q migration 001（對照版）。
-- 正本是程式碼：anchor_ext.TicketQMixin._migrate_ticketq()，由 AnchorDB._init_tables() 在服務啟動時冪等執行。
-- 這份 SQL 只供審閱，不要手動對生產 DB 跑（跑了會讓「污染快照時間 = 止血時刻」這件事失真）。

CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);

-- Q1：乾淨的 reinforcement 訊號 + legacy 快照
ALTER TABLE memories ADD COLUMN reinforced_count   INTEGER DEFAULT 0;
ALTER TABLE memories ADD COLUMN reinforcement      REAL DEFAULT 0.0;
ALTER TABLE memories ADD COLUMN last_reinforced    TEXT;
ALTER TABLE memories ADD COLUMN legacy_usage_count INTEGER;
ALTER TABLE edges    ADD COLUMN hebb_count         INTEGER DEFAULT 0;
ALTER TABLE edges    ADD COLUMN legacy_weight      REAL;

-- Q4：digest schema
ALTER TABLE memories ADD COLUMN kind         TEXT DEFAULT 'memory';
ALTER TABLE memories ADD COLUMN derived_from TEXT;   -- JSON list

-- Q1 invariant ③：注入帳
CREATE TABLE IF NOT EXISTS injections (
    memory_id        TEXT PRIMARY KEY,
    last_injected_at TEXT NOT NULL,
    last_path        TEXT NOT NULL,      -- search | wakeup
    last_caller      TEXT DEFAULT 'unknown',  -- local | external | dream_pass | unknown（只供審計）
    count            INTEGER DEFAULT 1
);

-- Q2
CREATE TABLE IF NOT EXISTS memory_tasks (
    id          TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL,
    intent      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',   -- open | resolved | dismissed
    created_at  TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT,
    reason      TEXT,
    result_ref  TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON memory_tasks(status);

-- Q3
CREATE TABLE IF NOT EXISTS entity_cards (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    status      TEXT NOT NULL DEFAULT 'candidate',  -- candidate | active | archived
    what        TEXT NOT NULL,
    why         TEXT NOT NULL,
    timeline    TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS card_facts (
    id            TEXT PRIMARY KEY,
    card_id       TEXT NOT NULL REFERENCES entity_cards(id),
    field         TEXT NOT NULL,
    value         TEXT NOT NULL,
    valid_from    TEXT NOT NULL,
    valid_until   TEXT,                 -- NULL = 現行
    superseded_by TEXT,                 -- 指向取代它的 fact id
    provenance    TEXT NOT NULL,        -- 來源 memory / event id
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_card ON card_facts(card_id);
CREATE INDEX IF NOT EXISTS idx_facts_prov ON card_facts(provenance);

-- Q4 lineage（雙向索引）
CREATE TABLE IF NOT EXISTS memory_lineage (
    derived_id TEXT NOT NULL,
    source_id  TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (derived_id, source_id)
);
CREATE INDEX IF NOT EXISTS idx_lineage_source ON memory_lineage(source_id);

-- 一次性污染快照（只在 schema_meta 沒有 pollution_snapshot_at 時做）
UPDATE memories SET legacy_usage_count = usage_count;
UPDATE edges    SET legacy_weight = weight;
INSERT OR REPLACE INTO schema_meta VALUES ('pollution_cutoff',     '2026-09-20', strftime('%Y-%m-%dT%H:%M:%f','now'));
INSERT OR REPLACE INTO schema_meta VALUES ('pollution_snapshot_at', strftime('%Y-%m-%dT%H:%M:%f','now'), strftime('%Y-%m-%dT%H:%M:%f','now'));
INSERT OR REPLACE INTO schema_meta VALUES ('ticketq_schema',       '1', strftime('%Y-%m-%dT%H:%M:%f','now'));
