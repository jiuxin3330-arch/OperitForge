import { useEffect, useRef, useState } from "react";
import { api } from "./api";

// 放手實驗第 0 步：Owner 一鍵把前端換回上一版快照。
// 前端只送旗標（owner + CSRF），真正換版由 root watcher 執行；旗標被取走 ≠ 保證成功（可能被 60 秒限速略過）。
export const ROLLBACK_PATH = "/api/v2/owner/frontend-rollback";
export const ROLLBACK_REASON = "Owner 從設定頁按下回滾前端";
export type RollbackStatus = { status: "idle" | "pending" | "consumed"; requested_at: string | null; outcome: string | null };
type Phase = "idle" | "confirm" | "sending" | "waiting" | "consumed" | "slow" | "error";

function validStatus(value: unknown): value is RollbackStatus {
  const v = value as RollbackStatus;
  return !!v && typeof v === "object" && ["idle", "pending", "consumed"].includes(v.status);
}

export function FrontendRollbackView({ phase, busy, onStart, onConfirm, onCancel, onReload }: {
  phase: Phase; busy: boolean; onStart: () => void; onConfirm: () => void; onCancel: () => void; onReload: () => void;
}) {
  return <div className="card settings-card rollback-card" data-testid="frontend-rollback-card">
    <div className="settings-card-heading"><span aria-hidden="true" /><div><h3>回滾前端</h3><p>畫面出問題時，把前端換回上一版。只換畫面，聊天與資料都不會動。</p></div></div>
    {phase === "idle" && <button type="button" className="danger" onClick={onStart}>回滾前端</button>}
    {phase === "confirm" && <div className="rollback-confirm">
      <p>確定要把前端換回上一版嗎？</p>
      <button type="button" className="danger" disabled={busy} onClick={onConfirm}>確定回滾</button>
      <button type="button" className="secondary" disabled={busy} onClick={onCancel}>取消</button>
    </div>}
    {phase === "sending" && <p role="status">送出中…</p>}
    {phase === "waiting" && <p role="status">已送出，等伺服器換版…</p>}
    {phase === "consumed" && <>
      <p role="status">伺服器已收下請求。重新整理後就是上一版；如果看起來沒變，可能是 60 秒內剛回滾過。</p>
      <button type="button" className="primary" onClick={onReload}>重新整理</button>
    </>}
    {phase === "slow" && <p role="status">請求已送出，伺服器還沒處理完。等一下再重新整理看看。</p>}
    {phase === "error" && <><p role="alert">沒有送出成功，請再試一次。</p><button type="button" className="secondary" onClick={onCancel}>返回</button></>}
    <small>設定頁打不開時，可以直接開 <a href="/rollback.html">/rollback.html</a> 救生頁。</small>
  </div>;
}

export function FrontendRollback() {
  const [allowed, setAllowed] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    api<unknown>(ROLLBACK_PATH).then(v => { if (alive.current && validStatus(v)) setAllowed(true); })
      .catch(() => undefined); // 非 Owner（401/403）或讀不到：整張卡不出現
    return () => { alive.current = false; };
  }, []);
  async function confirm() {
    setPhase("sending");
    try {
      await api<unknown>(ROLLBACK_PATH, { method: "POST", body: JSON.stringify(ROLLBACK_REASON) }, [202]);
    } catch {
      if (alive.current) setPhase("error");
      return;
    }
    setPhase("waiting");
    for (let i = 0; i < 20 && alive.current; i += 1) {
      await new Promise(resolve => setTimeout(resolve, 1500));
      try {
        const s = await api<unknown>(ROLLBACK_PATH);
        if (validStatus(s) && s.status === "consumed") { if (alive.current) setPhase("consumed"); return; }
      } catch { /* 換版瞬間可能短暫失敗，繼續等 */ }
    }
    if (alive.current) setPhase("slow");
  }
  if (!allowed) return null;
  return <FrontendRollbackView phase={phase} busy={phase === "sending"}
    onStart={() => setPhase("confirm")} onConfirm={() => void confirm()} onCancel={() => setPhase("idle")}
    onReload={() => window.location.reload()} />;
}
