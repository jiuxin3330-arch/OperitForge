import io, sys

TSX = "/srv/chatnest-next/frontend/src/nestConsole.tsx"
CSS = "/srv/chatnest-next/frontend/src/styles.css"

def rep(text, old, new, label):
    assert text.count(old) == 1, f"FAIL {label}: count={text.count(old)}"
    return text.replace(old, new)

# ---------- nestConsole.tsx ----------
t = io.open(TSX, encoding="utf-8").read()

t = rep(t,
" * 抽屜只是純 UI 包裝,資料流與 api 呼叫不變。\n",
" * 抽屜只是純 UI 包裝,資料流與 api 呼叫不變。\n"
" * S3(打樣 v4 定稿):時間線細項——點事件展開筆記紙細項卡\n"
" *(變化值/引文=待釐清原因/完整時間+狀態),純 UI state,資料流不變。\n",
"tsx-header")

t = rep(t,
"""function shortDate(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return `${d.getMonth() + 1}/${d.getDate()}`;
  } catch {
    return "";
  }
}
""",
"""function shortDate(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return `${d.getMonth() + 1}/${d.getDate()}`;
  } catch {
    return "";
  }
}
function fullTime(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${d.getMonth() + 1}/${d.getDate()} ${hh}:${mm}`;
  } catch {
    return "";
  }
}
""",
"tsx-fulltime")

t = rep(t,
"""  const toggleDrawer = (k: DrawerKey) =>
    setDrawerOpen((d) => ({ ...d, [k]: !d[k] }));
""",
"""  const toggleDrawer = (k: DrawerKey) =>
    setDrawerOpen((d) => ({ ...d, [k]: !d[k] }));

  /* S3 時間線細項(純 UI state):點事件展開,一次一條,不持久化 */
  const [expandedEventId, setExpandedEventId] = useState<number | null>(null);
  const toggleEventDetail = (id: number) =>
    setExpandedEventId((cur) => (cur === id ? null : id));
""",
"tsx-state")

OLD_MAP = """                eventsToShow.map((ev) => (
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
"""
NEW_MAP = """                eventsToShow.map((ev) => {
                  const expanded = expandedEventId === ev.event_id;
                  return (
                    <div
                      key={ev.event_id}
                      className={`nest-event nest-impact-${ev.impact}${expanded ? " is-expanded" : ""}`}
                      role="button"
                      tabIndex={0}
                      aria-expanded={expanded}
                      onClick={() => toggleEventDetail(ev.event_id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          toggleEventDetail(ev.event_id);
                        }
                      }}
                    >
                      <div className="nest-event-body">
                        <div className="nest-event-line">{ev.summary || ev.value_after}</div>
                        <div className="nest-event-meta">
                          {friendlySubject(ev.subject_id)} · {ev.impact} · {friendlyAuthority(ev.authority)}
                          {shortDate(ev.occurred_at) && ` · ${shortDate(ev.occurred_at)}`}
                          {ev.escalated ? <span className="nest-state-warn"> · 待釐清</span> : null}
                        </div>
                        <div className="nest-event-detail-wrap" aria-hidden={!expanded}>
                          <div className="nest-event-detail">
                            <div className="nest-event-detail-inner">
                              <div className="nest-ed-value">{ev.value_after}</div>
                              {ev.escalated && ev.escalation_reason ? (
                                <div className="nest-ed-quote">{ev.escalation_reason}</div>
                              ) : null}
                              <div className="nest-ed-foot">
                                {fullTime(ev.occurred_at)}
                                {" · "}
                                {ev.escalated ? (
                                  <span className="nest-ed-warn">待釐清</span>
                                ) : (
                                  "已歸檔"
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })
"""
t = rep(t, OLD_MAP, NEW_MAP, "tsx-map")
io.open(TSX, "w", encoding="utf-8").write(t)

# ---------- styles.css ----------
c = io.open(CSS, encoding="utf-8").read()

OLD_TL = """.nest-events {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 8px;
  position: relative;
}
.nest-events::before {
  content: '';
  position: absolute;
  left: 3px; top: 8px; bottom: 8px;
  width: 1px;
  background: var(--nest-line);
}
.nest-event {
  display: flex;
  padding: 6px 4px 6px 6px;
  align-items: flex-start;
  position: relative;
}
.nest-event::before {
  content: '';
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--nest-muted);
  opacity: 0.6;
  margin: 6px 10px 0 -3px;
  flex: 0 0 6px;
}
"""
NEW_TL = """.nest-events {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 10px;
  position: relative;
}
/* S3:串珠時間線——線從珠後穿過,珠外圍 bg 色圈讓珠與線分開(糯糯定案) */
.nest-events::before {
  content: '';
  position: absolute;
  left: 12.75px; top: 10px; bottom: 10px;
  width: 1.5px;
  background: var(--nest-line-soft);
  z-index: 0;
}
.nest-event {
  display: flex;
  padding: 7px 4px 7px 0;
  align-items: flex-start;
  position: relative;
  cursor: pointer;
}
.nest-event::before {
  content: '';
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--nest-muted);
  margin: 5px 9px 0 0;
  flex: 0 0 7px;
  position: relative;
  z-index: 1;
  box-shadow: 0 0 0 3px var(--nest-bg);
  transition: transform 0.2s cubic-bezier(0.23, 1, 0.32, 1);
}
.nest-event.is-expanded::before { transform: scale(1.4); }
"""
c = rep(c, OLD_TL, NEW_TL, "css-timeline")

S3_BLOCK = """
/* ==== S3:時間線細項(打樣 s3-proofing-v4 定稿) =============================
   點事件展開筆記紙細項卡:變化值(墨綠灰)/引文=待釐清原因/完整時間+狀態。
   純 UI 展開;筆記紙橫線 20px 行距,background-color 與 background-image
   分開寫(S2 教訓 4)。 */
.nest-event.is-expanded .nest-event-line {
  display: block;
  -webkit-line-clamp: unset;
  overflow: visible;
}
.nest-event-detail-wrap {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.28s cubic-bezier(0.32, 0.72, 0, 1);
}
.nest-event.is-expanded .nest-event-detail-wrap { grid-template-rows: 1fr; }
.nest-event-detail { overflow: hidden; min-height: 0; }
.nest-event-detail-inner {
  margin: 8px 0 4px;
  padding: 12px 14px 10px 28px;
  position: relative;
  background-color: var(--nest-paper-note);
  border-radius: 10px;
  background-image: repeating-linear-gradient(to bottom, transparent 0 19px, var(--nest-line-soft) 19px 20px);
  background-position: 0 12px;
}
/* 活頁打孔:左側兩顆背景色圓 */
.nest-event-detail-inner::before,
.nest-event-detail-inner::after {
  content: '';
  position: absolute;
  left: 9px;
  width: 8px; height: 8px;
  border-radius: 50%;
  background-color: var(--nest-bg);
}
.nest-event-detail-inner::before { top: 22%; }
.nest-event-detail-inner::after { top: 68%; }
.nest-ed-value {
  font-size: 12.5px;
  line-height: 20px;
  color: #515a4e;
}
html[data-theme="dark"] .nest-ed-value { color: var(--nest-ink-on-cream); }
.nest-ed-quote {
  font-size: 11px;
  font-style: italic;
  color: #78806f;
  line-height: 20px;
  border-left: 2px solid color-mix(in srgb, var(--nest-butterfly) 55%, transparent);
  padding-left: 9px;
}
.nest-ed-foot {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 10px;
  line-height: 20px;
  color: var(--nest-muted);
  opacity: 0.85;
  letter-spacing: 0.04em;
}
.nest-ed-warn { color: #c05a2e; }
html[data-theme="dark"] .nest-ed-warn { color: #f09a6b; }

html[data-reduced-motion="true"] .nest-event-detail-wrap,
html[data-reduced-motion="true"] .nest-event::before {
  transition: none;
}
"""
assert ".nest-ed-value" not in c, "FAIL css-append: already present"
c = c.rstrip("\n") + "\n" + S3_BLOCK
io.open(CSS, "w", encoding="utf-8").write(c)

print("s3 source patch ok")
