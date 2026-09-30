import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { api, ApiError } from "./api";
import "./FriendsRoster.css";

// 筆友名冊（TICKET-W，2026-09-30 放手窗視覺）：通訊錄形式。
// 硬牆：cn 敘述四欄＋status 永遠純文字；Owner 只改 name/email/aliases 與既有實體卡 ID；沒有刪除；不代 cn 入冊；不觸發掃信。
export type Friend = {
  id: string; name: string; email: string; aliases: string[];
  relationship_label: string; met_context: string; confirmed_origin: string;
  boundaries: string; status: string; entity_card_id: string | null;
  created_by?: string; updated_by?: string; created_at?: string; updated_at: string;
};
export type FriendLead = { id: string; name: string; email: string; updated_at?: string };
export type EntityCard = { id: string; name: string; status: string; updated_at: string };
const base = "/api/v2/owner/friends";

export const PAGE_NOTE = "關係、來路與邊界由牧牧自己確認與填寫。";
export const CARD_PRINCIPLE = "名冊是聯絡索引，不是記憶實體卡；登記名冊不代表建立實體卡。";
export const LEAD_SAVED = "線索已記下，待牧牧確認。尚未加入正式名冊。";

// 只送使用者實際改過的允許欄，避免踩到 cn 的唯讀欄或覆蓋他同時更新的敘述
export function contactChanges(friend: Friend, name: string, email: string, aliases: string) {
  const next = { name: name.trim(), email: email.trim(), aliases: aliases.split("\n").map(s => s.trim()).filter(Boolean) };
  return Object.fromEntries((Object.keys(next) as (keyof typeof next)[])
    .filter(key => JSON.stringify(next[key]) !== JSON.stringify(friend[key])).map(key => [key, next[key]]));
}

// 後端錯誤碼逐一翻成人話；任何失敗都不樂觀顯示成功
export function saveErrorText(error: unknown, kind: "contact" | "card" | "lead") {
  if (error instanceof ApiError) {
    if (error.status === 409) return "這個地址已登記給另一位朋友，這次沒有寫入。";
    if (error.status === 422) return kind === "card" ? "找不到這張實體卡或格式不符，這次沒有寫入。" : "格式不符（名字不可空白、地址格式或長度超過上限），這次沒有寫入。";
    if (error.status === 403) return "這筆變更沒有被接受，也沒有寫入任何內容；請重新讀取後再試。";
    if (error.status === 404) return "找不到這位朋友，名冊可能已更新；請重新讀取。";
    if (error.status === 503) return "目前無法確認實體卡，原本的連結保留不變。";
    if (error.status === 401) return "登入已過期，請重新登入後再試。";
  }
  return kind === "lead" ? "未能確認儲存結果，名字與地址已保留，可再試一次。" : "未能確認儲存結果，填寫內容已保留；可重試或重新讀取。";
}

const TONES = ["butter", "aqua", "lavender", "blush", "honey", "sage"];
// 頭像底色只由 id 決定，不代表任何排名或親疏
export function toneFor(id: string) { let h = 0; for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0; return TONES[h % TONES.length]; }
export function initialOf(name: string) { const ch = [...name.trim()][0] || "?"; return /[a-z]/i.test(ch) ? ch.toUpperCase() : ch; }
export function matchFriend(friend: Friend, query: string) {
  const q = query.trim().toLowerCase(); if (!q) return true;
  return [friend.name, friend.email, ...friend.aliases].some(v => v.toLowerCase().includes(q));
}
const day = (iso?: string) => (iso || "").slice(0, 10);

function Icon({ name }: { name: "search" | "back" | "copy" | "edit" | "plus" | "link" | "refresh" | "chevron" | "close" }) {
  const p = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  if (name === "search") return <svg {...p}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></svg>;
  if (name === "back") return <svg {...p}><path d="M15 5l-7 7 7 7" /></svg>;
  if (name === "chevron") return <svg {...p}><path d="M9 5l7 7-7 7" /></svg>;
  if (name === "copy") return <svg {...p}><rect x="8.5" y="8.5" width="11" height="11" rx="2.5" /><path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2" /></svg>;
  if (name === "edit") return <svg {...p}><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="m13.5 6.5 4 4" /></svg>;
  if (name === "plus") return <svg {...p}><path d="M12 5v14M5 12h14" /></svg>;
  if (name === "link") return <svg {...p}><path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1" /><path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1" /></svg>;
  if (name === "refresh") return <svg {...p}><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v5h-5" /></svg>;
  return <svg {...p}><path d="M6 6l12 12M18 6 6 18" /></svg>;
}

function Avatar({ friend, size = "sm" }: { friend: Pick<Friend, "id" | "name">; size?: "sm" | "lg" }) {
  return <span className="friend-avatar" data-size={size} data-tone={toneFor(friend.id)} aria-hidden="true">{initialOf(friend.name)}</span>;
}

function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", key); return () => document.removeEventListener("keydown", key);
  }, [onClose]);
  return createPortal(<div className="friend-sheet-overlay" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="friend-sheet" role="dialog" aria-modal="true" aria-label={title}>
      <header><h3>{title}</h3><button type="button" className="friend-icon-button" onClick={onClose} aria-label={`關閉${title}`}><Icon name="close" /></button></header>
      {children}
    </section>
  </div>, document.body);
}

function ContactEditor({ friend, onSaved, onCancel }: { friend: Friend; onSaved: (value: Friend) => void; onCancel: () => void }) {
  const [name, setName] = useState(friend.name);
  const [email, setEmail] = useState(friend.email);
  const [aliases, setAliases] = useState(friend.aliases.join("\n"));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { setName(friend.name); setEmail(friend.email); setAliases(friend.aliases.join("\n")); }, [friend]);
  async function save(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    const body = contactChanges(friend, name, email, aliases);
    if (!Object.keys(body).length) { setMessage("沒有變更。"); return; }
    setBusy(true); setError(""); setMessage("");
    try {
      const saved = await api<Friend>(`${base}/${encodeURIComponent(friend.id)}`, { method: "PATCH", body: JSON.stringify(body) });
      onSaved(saved);
    } catch (err) { setError(saveErrorText(err, "contact")); }
    finally { setBusy(false); }
  }
  return <form onSubmit={event => void save(event)} className="friend-form" aria-label="編輯聯絡資料">
    <label>名字<input required maxLength={80} value={name} disabled={busy} onChange={e => setName(e.target.value)} /></label>
    <label>Email<input required type="email" maxLength={254} value={email} disabled={busy} onChange={e => setEmail(e.target.value)} /></label>
    <label>別名（一行一個）<textarea rows={3} value={aliases} disabled={busy} onChange={e => setAliases(e.target.value)} /></label>
    <div className="friend-form-actions">
      <button type="button" className="friend-button" data-kind="quiet" disabled={busy} onClick={onCancel}>取消</button>
      <button className="friend-button" data-kind="primary" disabled={busy || !name.trim()}>{busy ? "儲存中…" : "儲存聯絡資料"}</button>
    </div>
    {message && <p role="status" className="friend-note">{message}</p>}{error && <p role="alert" className="friend-error">{error}</p>}
  </form>;
}

function CardPicker({ friend, onSaved, onClose }: { friend: Friend; onSaved: (value: Friend) => void; onClose: () => void }) {
  const [cards, setCards] = useState<EntityCard[] | null>(null);
  const [available, setAvailable] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [choice, setChoice] = useState(friend.entity_card_id || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function load() {
    setLoadError("");
    try {
      const data = await api<{ entity_cards: EntityCard[]; entity_cards_available: boolean }>(base + "/entity-cards");
      setCards(Array.isArray(data.entity_cards) ? data.entity_cards : []); setAvailable(Boolean(data.entity_cards_available));
    } catch { setLoadError("實體卡清單讀取失敗，原本的連結保留不變。"); }
  }
  useEffect(() => { void load(); }, []);
  async function link(id: string | null) {
    if (busy) return; setBusy(true); setError("");
    try { const saved = await api<Friend>(`${base}/${encodeURIComponent(friend.id)}`, { method: "PATCH", body: JSON.stringify({ entity_card_id: id }) }); onSaved(saved); onClose(); }
    catch (err) { setError(saveErrorText(err, "card")); }
    finally { setBusy(false); }
  }
  return <Sheet title="連結實體卡" onClose={onClose}>
    <p className="friend-note">{CARD_PRINCIPLE}</p>
    <p className="friend-note">只從已存在的卡片中親自選擇；不會依名字自動配對。</p>
    {!cards && !loadError && <p role="status" className="friend-note">正在讀取實體卡…</p>}
    {loadError && <p role="alert" className="friend-error">{loadError} <button type="button" className="friend-text-button" onClick={() => void load()}>重試</button></p>}
    {cards && !available && <p role="alert" className="friend-error">目前無法讀取實體卡來源，原本的連結保留不變。</p>}
    {cards && available && cards.length === 0 && <p className="friend-note">目前沒有可選的實體卡。</p>}
    {cards && cards.length > 0 && <div className="friend-card-options" role="radiogroup" aria-label="實體卡">
      {cards.map(card => <label key={card.id} className="friend-card-option" data-checked={choice === card.id ? "true" : "false"}>
        <input type="radio" name="entity-card" value={card.id} checked={choice === card.id} onChange={() => setChoice(card.id)} />
        <span><strong>{card.name}</strong><small>{card.id}{card.status ? ` · ${card.status}` : ""}</small></span>
      </label>)}
    </div>}
    {error && <p role="alert" className="friend-error">{error}</p>}
    <div className="friend-form-actions">
      {friend.entity_card_id && <button type="button" className="friend-button" data-kind="quiet" disabled={busy} onClick={() => void link(null)}>解除連結</button>}
      <button type="button" className="friend-button" data-kind="primary" disabled={busy || !choice || choice === friend.entity_card_id || !cards?.some(card => card.id === choice)} onClick={() => void link(choice)}>{busy ? "儲存中…" : "連結這張卡"}</button>
    </div>
  </Sheet>;
}

export function FriendDetail({ friend, cardName, onSaved, onBack }: { friend: Friend; cardName?: string | null; onSaved: (value: Friend) => void; onBack: () => void }) {
  const [editing, setEditing] = useState(false);
  const [picking, setPicking] = useState(false);
  const [copied, setCopied] = useState("");
  const [savedNote, setSavedNote] = useState("");
  const narratives: Array<[string, string]> = [["相遇與第一印象", friend.met_context], ["牧牧確認的來路", friend.confirmed_origin], ["這條線的邊界", friend.boundaries]];
  async function copy() {
    try { await navigator.clipboard.writeText(friend.email); setCopied("已複製地址"); }
    catch { setCopied("無法自動複製，請長按地址手動複製"); }
    window.setTimeout(() => setCopied(""), 2200);
  }
  return <article className="friend-detail" aria-label={`${friend.name} 的聯絡人卡`}>
    <button type="button" className="friend-back" onClick={onBack}><Icon name="back" /><span>名冊</span></button>
    <header className="friend-hero">
      <Avatar friend={friend} size="lg" />
      <h2>{friend.name}</h2>
      <p className="friend-hero-label">{friend.relationship_label || "關係描述待牧牧填寫"}</p>
      {friend.status && <p className="friend-status">{friend.status}</p>}
    </header>
    <div className="friend-actions">
      <button type="button" className="friend-action" onClick={() => void copy()} disabled={!friend.email}><Icon name="copy" /><span>複製地址</span></button>
      <button type="button" className="friend-action" onClick={() => { setEditing(value => !value); setSavedNote(""); }} aria-pressed={editing}><Icon name="edit" /><span>編輯</span></button>
      <button type="button" className="friend-action" onClick={() => setPicking(true)}><Icon name="link" /><span>實體卡</span></button>
    </div>
    {copied && <p role="status" className="friend-note friend-center">{copied}</p>}
    <section className="friend-block" aria-label="聯絡資料">
      {editing ? <ContactEditor friend={friend} onCancel={() => setEditing(false)} onSaved={saved => { onSaved(saved); setEditing(false); setSavedNote("聯絡資料已儲存。"); }} /> : <dl className="friend-fields">
        <div><dt>Email</dt><dd className="friend-mono">{friend.email || "尚未填寫"}</dd></div>
        <div><dt>別名</dt><dd>{friend.aliases.length ? <span className="friend-chips">{friend.aliases.map(alias => <span key={alias}>{alias}</span>)}</span> : "沒有別名"}</dd></div>
        <div><dt>實體卡</dt><dd>{friend.entity_card_id ? (cardName ? <>{cardName} <small className="friend-mono">{friend.entity_card_id}</small></> : <>目前無法確認這張卡 <small className="friend-mono">{friend.entity_card_id}</small></>) : "未連結"}</dd></div>
      </dl>}
      {savedNote && !editing && <p role="status" className="friend-note">{savedNote}</p>}
    </section>
    {narratives.map(([label, value]) => <section key={label} className="friend-block friend-story" aria-label={label}>
      <h3>{label}</h3>
      <p>{value || "尚未填寫"}</p>
    </section>)}
    <p className="friend-note friend-center">{PAGE_NOTE}</p>
    {friend.updated_at && <p className="friend-meta">更新於 {day(friend.updated_at)}</p>}
    {picking && <CardPicker friend={friend} onClose={() => setPicking(false)} onSaved={saved => { onSaved(saved); setSavedNote(saved.entity_card_id ? "實體卡連結已儲存。" : "已解除實體卡連結。"); }} />}
  </article>;
}

function LeadSheet({ onSaved, onClose }: { onSaved: (lead: FriendLead) => void; onClose: () => void }) {
  const [name, setName] = useState(""); const [email, setEmail] = useState("");
  const [saving, setSaving] = useState(false); const [notice, setNotice] = useState(""); const [error, setError] = useState("");
  async function suggest(event: FormEvent) {
    event.preventDefault(); if (saving) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const saved = await api<FriendLead>(base + "/suggestions", { method: "POST", body: JSON.stringify({ name: name.trim(), email: email.trim() }) });
      onSaved(saved); setName(""); setEmail(""); setNotice(LEAD_SAVED);
    } catch (err) { setError(saveErrorText(err, "lead")); }
    finally { setSaving(false); }
  }
  return <Sheet title="補一位朋友的線索" onClose={onClose}>
    <form className="friend-form" onSubmit={event => void suggest(event)}>
      <p className="friend-note">妳可以補名字與地址，讓牧牧確認後再入冊。</p>
      <label>名字<input required maxLength={80} value={name} disabled={saving} onChange={e => setName(e.target.value)} /></label>
      <label>Email<input required type="email" maxLength={254} value={email} disabled={saving} onChange={e => setEmail(e.target.value)} /></label>
      <div className="friend-form-actions"><button className="friend-button" data-kind="primary" disabled={saving || !name.trim()}>{saving ? "儲存中…" : "記下線索"}</button></div>
      {error && <p role="alert" className="friend-error">{error}</p>}{notice && <p role="status" className="friend-note">{notice}</p>}
    </form>
  </Sheet>;
}

export function FriendsRoster() {
  const [friends, setFriends] = useState<Friend[] | null>(null);
  const [leads, setLeads] = useState<FriendLead[]>([]);
  const [cards, setCards] = useState<EntityCard[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState("");
  const [adding, setAdding] = useState(false);
  const topRef = useRef<HTMLDivElement>(null);
  async function load() {
    setLoading(true); setError("");
    try {
      const [roster, suggestions] = await Promise.all([api<{ friends: Friend[] }>(base), api<{ suggestions: FriendLead[] }>(base + "/suggestions")]);
      if (!Array.isArray(roster.friends) || !Array.isArray(suggestions.suggestions)) throw new Error();
      setFriends(roster.friends); setLeads(suggestions.suggestions);
    } catch { setError("名冊讀取失敗，請重試。"); }
    finally { setLoading(false); }
    // 實體卡名稱只用來顯示；讀不到時保留 ID、顯示無法確認
    api<{ entity_cards: EntityCard[]; entity_cards_available: boolean }>(base + "/entity-cards")
      .then(data => setCards(data.entity_cards_available && Array.isArray(data.entity_cards) ? data.entity_cards : null))
      .catch(() => setCards(null));
  }
  useEffect(() => { void load(); }, []);
  const shown = useMemo(() => (friends || []).filter(friend => matchFriend(friend, query)), [friends, query]);
  const open = friends?.find(friend => friend.id === openId);
  useEffect(() => { topRef.current?.closest(".panel")?.scrollTo({ top: 0 }); }, [openId]);
  const replace = (saved: Friend) => setFriends(previous => previous?.map(p => p.id === saved.id ? saved : p) ?? []);
  return <section className="panel friends-panel" aria-label="筆友名冊">
    <div ref={topRef} />
    {open ? <FriendDetail friend={open} cardName={open.entity_card_id ? cards?.find(card => card.id === open.entity_card_id)?.name ?? null : null} onSaved={replace} onBack={() => setOpenId("")} /> : <>
      <header className="friends-head">
        <div><h2>筆友名冊</h2><p className="friend-note">記下名字，也留著相識的來路。</p></div>
        <button type="button" className="friend-icon-button" disabled={loading} onClick={() => void load()} aria-label="重新讀取"><Icon name="refresh" /></button>
      </header>
      <label className="friend-search"><Icon name="search" /><input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="搜尋名字、別名或地址" aria-label="搜尋朋友" /></label>
      {loading && !friends && <p role="status" className="friend-note">正在翻開名冊…</p>}
      {error && <p role="alert" className="friend-error">{error} <button type="button" className="friend-text-button" onClick={() => void load()}>重試</button></p>}
      {friends && <p className="friend-count">{friends.length} 位朋友{leads.length ? ` · ${leads.length} 條線索待確認` : ""}</p>}
      {friends?.length === 0 && <p className="friend-empty">牧牧還沒有確認入冊的朋友。可以先補名字與地址線索。</p>}
      {friends && friends.length > 0 && shown.length === 0 && <p className="friend-empty">找不到符合的朋友。</p>}
      {shown.length > 0 && <ul className="friends-list" aria-label="已入冊的朋友">
        {shown.map(friend => <li key={friend.id}><button type="button" className="friend-row" onClick={() => setOpenId(friend.id)}>
          <Avatar friend={friend} />
          <span className="friend-row-text"><strong>{friend.name}</strong><small>{friend.relationship_label || "關係描述待牧牧填寫"}</small></span>
          {friend.entity_card_id && <span className="friend-card-dot" title="已連結實體卡" aria-label="已連結實體卡" />}
          <Icon name="chevron" />
        </button></li>)}
      </ul>}
      <button type="button" className="friend-add-lead" onClick={() => setAdding(true)}><Icon name="plus" /><span>補一位朋友的線索</span></button>
      {leads.length > 0 && <section className="friend-leads" aria-label="待牧牧確認">
        <h3>待牧牧確認</h3>
        <ul>{leads.map(lead => <li key={lead.id}><Avatar friend={lead} /><span className="friend-row-text"><strong>{lead.name}</strong><small className="friend-mono">{lead.email}</small></span><em>線索</em></li>)}</ul>
      </section>}
      <p className="friend-note friend-center">{PAGE_NOTE}</p>
    </>}
    {adding && <LeadSheet onClose={() => setAdding(false)} onSaved={saved => setLeads(previous => [...previous.filter(p => p.id !== saved.id), saved])} />}
  </section>;
}
