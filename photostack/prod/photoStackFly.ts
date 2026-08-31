/** PhotoStack 展開/收起共用幾何（蓋章版 2026-09-01）。
 * 姿態公式與 vendor photo-stack.js `_apply` 一致（peek 15/12、rot 2.2、scale 0.08），
 * 起飛與落地幀都等於靜態堆疊的渲染，格子/替身交接零跳變
 * （規格來源：vendor README「展開/收起動畫」筆記——按側歸位、隱形卡自探邊位出發）。 */

export const FLY_EASE = "cubic-bezier(.2,.7,.3,1)";

export type StackPose = {
  peekX: number;
  rot: number;
  sc: number;
  depth: number;
  visible: boolean;
};

export function stackPoseInfo(i: number, cur: number, n: number): StackPose {
  const raw = i - cur;
  // 邊界配額轉移:首張時右側可見兩層、末張時左側可見兩層(vendor _lr 同語意)
  const maxR = cur === 0 ? 2 : 1;
  const maxL = cur === n - 1 ? 2 : 1;
  const visible = raw === 0 ||
    (raw > 0 && raw <= Math.min(maxR, n - 1 - cur)) ||
    (raw < 0 && -raw <= Math.min(maxL, cur));
  const d = Math.max(-2, Math.min(2, raw));
  return {
    peekX: d === 0 ? 0 : d > 0 ? 15 + (d - 1) * 12 : -(15 + (-d - 1) * 12),
    rot: d * 2.2,
    sc: 1 - 0.08 * Math.abs(d),
    depth: Math.abs(raw),
    visible,
  };
}

export function stackPoseTransform(sRect: DOMRect, r: DOMRect, info: StackPose): string {
  return "translate(" +
    (((sRect.left + sRect.width / 2) - (r.left + r.width / 2)) + info.peekX) + "px," +
    ((sRect.top + sRect.height / 2) - (r.top + r.height / 2)) + "px) " +
    "rotate(" + info.rot + "deg) " +
    "scale(" + (sRect.width / r.width * info.sc) + "," + (sRect.height / r.height * info.sc) + ")";
}

/** 版面聯動（README「下方內容聯動」）：記舊位 → 版面改完 → 從舊位平移回新位。 */
export function flipTranslate(els: HTMLElement[], before: DOMRect[]) {
  els.forEach((el, k) => {
    const r = el.getBoundingClientRect();
    const dx = before[k].left - r.left;
    const dy = before[k].top - r.top;
    if (!dx && !dy) return;
    el.style.transition = "none";
    el.style.transform = "translate(" + dx + "px," + dy + "px)";
  });
  void document.body.offsetHeight;
  els.forEach((el) => {
    el.style.transition = "transform 300ms " + FLY_EASE;
    el.style.transform = "";
  });
}

export function clearFlip(els: HTMLElement[]) {
  els.forEach((el) => {
    el.style.transition = "";
    el.style.transform = "";
  });
}
