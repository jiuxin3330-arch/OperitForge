/**
 * 記憶頁的兩扇門 · 檔案室房間內部(工單 B S3)
 * 依 wireframe 定案的方案 α:走廊 + 兩扇門(AM 日記 / NM 檔案室)
 * 遵守 OWNER_UI_INTERACTION_DECISIONS + chatnest 憲法:
 * - 米白基底、只有小卡允許配色
 * - 新擬態只給按鈕
 * - 手機 390px 優先
 * - 不出現工程術語(subject_id 用 friendlySubject 轉中文)
 */
import { useCallback, useEffect, useState } from "react";
import {
  consoleApproveProposal,
  consoleListEvents,
  consoleListProposals,
  consoleListStates,
  consoleRejectProposal,
  consoleSearchEvents,
} from "./api";
import type {
  ConsoleEvent,
  ConsoleProposal,
  ConsoleState,
  ConsoleVolatility,
} from "./api";

/* ---- 中文顯示映射(工程 id → 給糯糯看的名字) ---------------------------- */

const SUBJECT_LABELS: Record<string, string> = {
  "owner.schedule": "作息",
  "owner.work_study": "打工",
  "owner.creative": "創作",
  "owner.creative.commissions": "委託",
  "owner.preferences": "偏好",
  "owner.daily_life": "日常",
  "relationship.current_status": "關係現況",
  "relationship.agreements": "關係約定",
  "chatnest.active_frontend": "聊天前端",
  "chatnest.agent_sdk": "Agent SDK",
  "chatnest.agent_bridge": "Agent 橋接",
  "devices.and_tools": "設備與工具",
  "infra.vps": "基礎設施",
  "social.penpals": "筆友",
  "social.galatea_garden": "花園",
  "misc.other": "其他",
  "nest_memory.phase": "檔案室進度",
};

const AUTHORITY_LABELS: Record<string, string> = {
  owner_direct_statement: "糯糯陳述",
  owner_confirmation: "糯糯確認",
  owner_decision: "糯糯決定",
  owner_correction: "糯糯糾正",
  assistant_claim: "牧牧記錄",
  assistant_inference: "牧牧推測",
  system_verified_state: "系統驗證",
  quoted_third_party: "第三方",
  external_document: "外部",
  tool_result: "工具結果",
};

const FRESH_LABELS: Record<string, string> = {
  active_fresh: "新鮮",
  active_aging: "稍舊",
  stale_active: "已久未確認",
  disputed: "待釐清",
  tentative: "暫定",
};

const STATUS_LABELS: Record<string, string> = {
  active: "",
  disputed: "有衝突",
  tentative: "暫定",
};

const AUTH_TONE: Record<string, "owner" | "assistant" | "system" | "other"> = {
  owner_direct_statement: "owner",
  owner_confirmation: "owner",
  owner_decision: "owner",
  owner_correction: "owner",
  assistant_claim: "assistant",
  assistant_inference: "assistant",
  system_verified_state: "system",
};

function friendlySubject(key: string): string {
  return SUBJECT_LABELS[key] || key;
}
function friendlyAuthority(a: string): string {
  return AUTHORITY_LABELS[a] || a;
}
function friendlyFresh(f: string): string {
  return FRESH_LABELS[f] || f;
}
function friendlyStatus(s: string): string {
  return STATUS_LABELS[s] ?? s;
}
function authTone(a: string): string {
  return AUTH_TONE[a] || "other";
}
function shortDate(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return `${d.getMonth() + 1}/${d.getDate()}`;
  } catch {
    return "";
  }
}

/* ---- 走廊(方案 α) ------------------------------------------------------ */

export interface NestCorridorCounts {
  states: number;
  proposals: number;
  loaded: boolean;
}

export function MemoryCorridor({
  onEnterDiary,
  onEnterArchive,
  counts,
}: {
  onEnterDiary: () => void;
  onEnterArchive: () => void;
  counts: NestCorridorCounts;
}) {
  return (
    <div className="nest-corridor">
      <div className="nest-corridor-lede">選一扇進去</div>
      <div className="nest-doors">
        <button
          type="button"
          className="nest-door"
          onClick={onEnterDiary}
          aria-label="日記(AM)"
        >
          <div className="nest-door-glyph" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6 4h9l3 3v13H6z" />
              <path d="M9 10h6M9 13h6M9 16h4" />
            </svg>
          </div>
          <div className="nest-door-body">
            <div className="nest-door-title">
              <span className="nest-door-name">日記</span>
              <span className="nest-door-abbr">AM</span>
            </div>
            <p className="nest-door-sub">你自己想起來、寫下來的。</p>
          </div>
        </button>

        <button
          type="button"
          className="nest-door"
          onClick={onEnterArchive}
          aria-label="檔案室(NM)"
        >
          <div className="nest-door-glyph" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <rect x="4" y="6" width="16" height="14" rx="1.5" />
              <path d="M4 10h16M8 6V4h8v2" />
              <path d="M11 14h2" />
            </svg>
          </div>
          <div className="nest-door-body">
            <div className="nest-door-title">
              <span className="nest-door-name">檔案室</span>
              <span className="nest-door-abbr">NM</span>
            </div>
            <p className="nest-door-sub">系統整理的登記簿。備你查,不是你的記憶。</p>
            {counts.loaded && (
              <div className="nest-door-meta">
                <span>{counts.states} 條登記</span>
                {counts.proposals > 0 && (
                  <span className="nest-dot-badge">
                    <span className="nest-dot" />
                    {counts.proposals} 待審
                  </span>
                )}
              </div>
            )}
          </div>
        </button>
      </div>
      <div className="nest-corridor-foot">兩者不互相冒充、互相補充。</div>
    </div>
  );
}

/* ---- 檔案室房間內部 ----------------------------------------------------- */

export function NestArchive({
  onBack,
  onStatus,
  onCountsChange,
}: {
  onBack: () => void;
  onStatus: (v: string) => void;
  onCountsChange?: (c: { states: number; proposals: number }) => void;
}) {
  const [proposals, setProposals] = useState<ConsoleProposal[]>([]);
  const [states, setStates] = useState<ConsoleState[]>([]);
  const [events, setEvents] = useState<ConsoleEvent[]>([]);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<ConsoleEvent[] | null>(null);
  const [approveTarget, setApproveTarget] = useState<ConsoleProposal | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [p, s, e] = await Promise.all([
        consoleListProposals("pending"),
        consoleListStates(),
        consoleListEvents(20),
      ]);
      setProposals(p.items);
      setStates(s.items);
      setEvents(e.items);
      onCountsChange?.({ states: s.items.length, proposals: p.items.length });
    } catch (err) {
      onStatus(err instanceof Error ? err.message : "檔案室讀取失敗");
    } finally {
      setLoading(false);
    }
  }, [onStatus, onCountsChange]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function submitSearch() {
    const q = query.trim();
    if (!q) {
      setSearchResults(null);
      return;
    }
    try {
      const r = await consoleSearchEvents(q, 20);
      setSearchResults(r.items);
    } catch (err) {
      onStatus(err instanceof Error ? err.message : "搜尋失敗");
    }
  }

  async function reject(p: ConsoleProposal) {
    if (busyId !== null) return;
    setBusyId(p.id);
    try {
      await consoleRejectProposal(p.id);
      onStatus(`已駁回:${friendlySubject(p.proposed_key)}`);
      await reload();
    } catch (err) {
      onStatus(err instanceof Error ? err.message : "駁回失敗");
    } finally {
      setBusyId(null);
    }
  }

  async function approveWith(vol: ConsoleVolatility) {
    if (!approveTarget || busyId !== null) return;
    const p = approveTarget;
    setBusyId(p.id);
    try {
      await consoleApproveProposal(p.id, { volatility: vol });
      onStatus(`已批准:${friendlySubject(p.proposed_key)}(${vol})`);
      setApproveTarget(null);
      await reload();
    } catch (err) {
      onStatus(err instanceof Error ? err.message : "批准失敗");
    } finally {
      setBusyId(null);
    }
  }

  const eventsToShow = searchResults ?? events;
  const searchActive = searchResults !== null;

  return (
    <div className="nest-archive">
      <div className="nest-archive-head">
        <button
          type="button"
          className="nest-back"
          onClick={onBack}
          aria-label="回走廊"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 6l-6 6l6 6" />
          </svg>
        </button>
        <div className="nest-crumb">
          <span>記憶</span>
          <span className="nest-crumb-sep">›</span>
          <span className="nest-crumb-curr">檔案室</span>
        </div>
      </div>

      <div className="nest-search">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-4 -4" />
        </svg>
        <input
          type="text"
          className="nest-search-input"
          value={query}
          placeholder="搜尋事件、主題、引文"
          onChange={(e) => {
            setQuery(e.target.value);
            if (!e.target.value.trim()) setSearchResults(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void submitSearch();
            }
          }}
          aria-label="搜尋"
        />
        {searchActive && (
          <button
            type="button"
            className="nest-clear"
            onClick={() => {
              setQuery("");
              setSearchResults(null);
            }}
            aria-label="清除搜尋"
          >
            ×
          </button>
        )}
      </div>

      {/* 現況登記 */}
      <div className="nest-section-head">
        <h3>現況登記</h3>
        <span className="nest-section-count">{states.length} 條</span>
      </div>
      <div className="nest-state-list">
        {loading && states.length === 0 ? (
          <div className="nest-empty">讀取中…</div>
        ) : states.length === 0 ? (
          <div className="nest-empty">還沒有登記。</div>
        ) : (
          states.map((s) => (
            <div key={s.subject_id} className={`nest-state-row nest-status-${s.status}`}>
              <div className={`nest-state-bar nest-auth-${authTone(s.authority)}`} aria-hidden="true" />
              <div className="nest-state-body">
                <div className="nest-state-name">{friendlySubject(s.subject_id)}</div>
                <div className="nest-state-value">{s.current_value}</div>
                <div className="nest-state-meta">
                  {friendlyAuthority(s.authority)} · {friendlyFresh(s.freshness)}
                  {shortDate(s.observed_at) && ` · ${shortDate(s.observed_at)}`}
                  {friendlyStatus(s.status) && (
                    <span className="nest-state-warn"> · {friendlyStatus(s.status)}</span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* 事件時間軸 */}
      <div className="nest-section-head">
        <h3>{searchActive ? "搜尋結果" : "最近事件"}</h3>
        <span className="nest-section-count">{eventsToShow.length} 條</span>
      </div>
      <div className="nest-events">
        {eventsToShow.length === 0 ? (
          <div className="nest-empty">{searchActive ? "查無事件。" : "還沒有事件。"}</div>
        ) : (
          eventsToShow.map((ev) => (
            <div key={ev.event_id} className={`nest-event nest-impact-${ev.impact}`}>
              <div className="nest-event-body">
                <div className="nest-event-line">{ev.summary || ev.value_after}</div>
                <div className="nest-event-meta">
                  {friendlySubject(ev.subject_id)} · {ev.impact} · {friendlyAuthority(ev.authority)}
                  {shortDate(ev.occurred_at) && ` · ${shortDate(ev.occurred_at)}`}
                  {ev.escalated ? <span className="nest-state-warn"> · 待釐清</span> : null}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* 待審提案 */}
      <div className="nest-section-head">
        <h3>待審提案</h3>
        <span className="nest-section-count">{proposals.length} 條</span>
      </div>
      {proposals.length === 0 ? (
        <div className="nest-empty">目前沒有待審。</div>
      ) : (
        proposals.map((p) => (
          <article key={p.id} className="nest-proposal">
            <div className="nest-proposal-tag">書記官提議新增主題</div>
            <div className="nest-proposal-name">{friendlySubject(p.proposed_key)}</div>
            <code className="nest-proposal-code">{p.proposed_key}</code>
            {p.reason && <p className="nest-proposal-reason">{p.reason}</p>}
            {p.example_quote && (
              <p className="nest-proposal-quote">「{p.example_quote}」</p>
            )}
            <div className="nest-proposal-actions">
              <button
                type="button"
                className="nest-btn"
                onClick={() => void reject(p)}
                disabled={busyId !== null}
              >
                駁回
              </button>
              <button
                type="button"
                className="nest-btn nest-btn-primary"
                onClick={() => setApproveTarget(p)}
                disabled={busyId !== null}
              >
                批准 · 選頻率
              </button>
            </div>
          </article>
        ))
      )}

      {/* 批准的 volatility 選擇 sheet */}
      {approveTarget && (
        <div
          className="nest-modal-scrim"
          onClick={() => busyId === null && setApproveTarget(null)}
        >
          <div className="nest-modal" onClick={(e) => e.stopPropagation()}>
            <h4>批准「{friendlySubject(approveTarget.proposed_key)}」</h4>
            <p className="nest-modal-hint">
              選一個更新頻率:這決定書記官多久重新確認一次它的鮮度。
            </p>
            <div className="nest-vol-list">
              <button
                type="button"
                className="nest-vol"
                onClick={() => void approveWith("stable")}
                disabled={busyId !== null}
              >
                <b>穩定</b>
                <small>幾乎不變的事實(身分、關係基礎)</small>
              </button>
              <button
                type="button"
                className="nest-vol"
                onClick={() => void approveWith("semi_stable")}
                disabled={busyId !== null}
              >
                <b>半穩定</b>
                <small>會變但不常變 · 建議大部分主題</small>
              </button>
              <button
                type="button"
                className="nest-vol"
                onClick={() => void approveWith("volatile")}
                disabled={busyId !== null}
              >
                <b>易變</b>
                <small>作息、心情這類幾天就變</small>
              </button>
              <button
                type="button"
                className="nest-vol"
                onClick={() => void approveWith("ephemeral")}
                disabled={busyId !== null}
              >
                <b>短暫</b>
                <small>一次性事件、當下狀態</small>
              </button>
            </div>
            <div className="nest-modal-actions">
              <button
                type="button"
                className="nest-btn"
                onClick={() => setApproveTarget(null)}
                disabled={busyId !== null}
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---- 走廊的計數 hook(輕量預抓,讓兩扇門的 badge 一進去就顯示)---------- */

export function useNestCounts(active: boolean): NestCorridorCounts {
  const [counts, setCounts] = useState<NestCorridorCounts>({
    states: 0,
    proposals: 0,
    loaded: false,
  });
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    void (async () => {
      try {
        const [s, p] = await Promise.all([
          consoleListStates(),
          consoleListProposals("pending"),
        ]);
        if (!cancelled) {
          setCounts({ states: s.items.length, proposals: p.items.length, loaded: true });
        }
      } catch {
        if (!cancelled) setCounts({ states: 0, proposals: 0, loaded: true });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [active]);
  return counts;
}

