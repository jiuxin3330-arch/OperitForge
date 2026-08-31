import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { MessagePhotoStack } from "./MessagePhotoStack";
import type { PhotoStackApi } from "./MessagePhotoStack";
import { FLY_EASE, stackPoseInfo, stackPoseTransform } from "./photoStackFly";

const STACK_H = 190;

/** 聊天多圖：堆疊卡＋「展開/收起」（蓋章版 2026-09-01 糯糯定稿）。
 * 展開＝一列 112 卡（比堆疊小，聊天要同時看字，卡不能大）；
 * 按鈕浮在堆疊卡內側垂直置中（A 案定案），內側由幾何判定，不吃視角設定；
 * 起飛/收起按側歸位，頭尾幀＝靜態堆疊（vendor README「展開/收起動畫」筆記）。 */
export function ChatPhotoStack({
  images,
  onTap,
}: {
  images: string[];
  onTap: (index: number) => void;
}) {
  const areaRef = useRef<HTMLDivElement>(null);
  const rowRef = useRef<HTMLDivElement>(null);
  const slotRef = useRef<HTMLDivElement>(null);
  const pillRef = useRef<HTMLButtonElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const apiRef = useRef<PhotoStackApi | null>(null);
  const openRef = useRef(false);
  const busyRef = useRef(false);
  const [open, setOpen] = useState(false);
  const [gridShown, setGridShown] = useState(false);
  const [pillLabel, setPillLabel] = useState(`展開 ${images.length}`);

  function stageEl(): HTMLElement | null {
    return rowRef.current?.querySelector<HTMLElement>(".pstack-stage") ?? null;
  }

  /* 收合態按鈕擺位：貼堆疊卡內側（靠訊息流中央那側）、垂直置中 */
  function placeCollapsedPill() {
    const area = areaRef.current;
    const slot = slotRef.current;
    const stage = stageEl();
    if (!area || !slot || !stage || openRef.current) return;
    const a = area.getBoundingClientRect();
    const s = stage.getBoundingClientRect();
    if (!a.width || !s.width) return;
    slot.style.top = "0px";
    slot.style.height = STACK_H + "px";
    if (s.left + s.width / 2 > a.left + a.width / 2) {
      slot.style.right = (a.right - s.left + 10) + "px";
      slot.style.left = "auto";
    } else {
      slot.style.left = (s.right - a.left + 10) + "px";
      slot.style.right = "auto";
    }
  }

  const imagesKey = images.join("|");
  useEffect(() => {
    if (areaRef.current) areaRef.current.style.height = STACK_H + "px";
    placeCollapsedPill();
    const onResize = () => placeCollapsedPill();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imagesKey]);

  function expand() {
    const area = areaRef.current;
    const grid = gridRef.current;
    const slot = slotRef.current;
    const pill = pillRef.current;
    const stage = stageEl();
    if (!area || !grid || !slot || !pill || !stage) return;
    busyRef.current = true;
    openRef.current = true;
    const sRect = stage.getBoundingClientRect();
    const cur = apiRef.current?.index ?? 0;
    /* 按鈕先鎖在原位再淡出（定位規則切換不可有瞬移） */
    const pRect = pill.getBoundingClientRect();
    const aRect = area.getBoundingClientRect();
    slot.style.top = (pRect.top - aRect.top) + "px";
    slot.style.left = (pRect.left - aRect.left) + "px";
    slot.style.right = "auto";
    slot.style.height = "auto";
    slot.style.opacity = "0";
    flushSync(() => {
      setOpen(true);
      setGridShown(true);
    });

    const cells = Array.from(grid.children).filter(
      (el): el is HTMLElement => el instanceof HTMLElement,
    );
    const rects = cells.map((cell) => cell.getBoundingClientRect());
    cells.forEach((cell, i) => {
      const info = stackPoseInfo(i, cur, cells.length);
      cell.style.transition = "none";
      cell.style.transform = stackPoseTransform(sRect, rects[i], info);
      cell.style.zIndex = String(100 - info.depth);
      cell.style.opacity = info.visible ? "1" : "0";
    });
    void grid.offsetHeight;
    cells.forEach((cell, i) => {
      cell.style.transition = `transform ${280 + 45 * Math.min(i, 10)}ms ${FLY_EASE}, opacity 120ms`;
      cell.style.transform = "";
      cell.style.opacity = "1";
    });
    area.style.transition = `height 320ms ${FLY_EASE}`;
    area.style.height = grid.offsetHeight + "px";

    window.setTimeout(() => {
      /* 「收起」貼第一張卡內側、垂直置中（微信同款） */
      const r0 = cells[0]?.getBoundingClientRect();
      const a2 = area.getBoundingClientRect();
      if (r0 && a2.width) {
        slot.style.top = (r0.top - a2.top + r0.height / 2 - 14) + "px";
        slot.style.height = "auto";
        if (r0.left + r0.width / 2 > a2.left + a2.width / 2) {
          slot.style.right = (a2.right - r0.left + 8) + "px";
          slot.style.left = "auto";
        } else {
          slot.style.left = (r0.right - a2.left + 8) + "px";
          slot.style.right = "auto";
        }
      }
      setPillLabel("收起");
      slot.style.opacity = "1";
    }, 200);
    window.setTimeout(() => {
      busyRef.current = false;
    }, 280 + 45 * Math.min(cells.length - 1, 10) + 60);
  }

  function collapse() {
    const area = areaRef.current;
    const grid = gridRef.current;
    const slot = slotRef.current;
    const stage = stageEl();
    if (!area || !grid || !slot || !stage) return;
    busyRef.current = true;
    openRef.current = false;
    const sRect = stage.getBoundingClientRect();
    const cur = apiRef.current?.index ?? 0;
    const cells = Array.from(grid.children).filter(
      (el): el is HTMLElement => el instanceof HTMLElement,
    );
    const rects = cells.map((cell) => cell.getBoundingClientRect());
    /* 按側歸位：每張卡收向自己該在的探邊姿態，落地幀＝靜態堆疊，深層卡末段淡出被遮 */
    cells.forEach((cell, i) => {
      const info = stackPoseInfo(i, cur, cells.length);
      cell.style.transition = `transform 300ms ${FLY_EASE}, opacity 130ms 170ms`;
      cell.style.transform = stackPoseTransform(sRect, rects[i], info);
      cell.style.zIndex = String(100 - info.depth);
      if (!info.visible) cell.style.opacity = "0";
    });
    area.style.transition = `height 300ms ${FLY_EASE}`;
    area.style.height = STACK_H + "px";
    slot.style.opacity = "0";
    window.setTimeout(() => setOpen(false), 190);
    window.setTimeout(() => {
      cells.forEach((cell) => {
        cell.style.transition = "none";
        cell.style.transform = "";
        cell.style.opacity = "";
      });
      slot.style.top = "";
      slot.style.left = "";
      slot.style.right = "";
      slot.style.height = "";
      setGridShown(false);
      setPillLabel(`展開 ${images.length}`);
      placeCollapsedPill();
      slot.style.opacity = "1";
      busyRef.current = false;
    }, 350);
  }

  return (
    <div className={`cpf-area${open ? " open" : ""}`} ref={areaRef}>
      <div className="cpf-row" ref={rowRef}>
        <MessagePhotoStack apiRef={apiRef} images={images} onTap={onTap} />
      </div>
      <div className="cpf-slot" ref={slotRef}>
        <button
          aria-expanded={open}
          className="cpf-pill"
          onClick={() => {
            if (busyRef.current) return;
            if (openRef.current) collapse();
            else expand();
          }}
          ref={pillRef}
          type="button"
        >
          {pillLabel}
        </button>
      </div>
      <div className="cpf-grid" hidden={!gridShown} ref={gridRef}>
        {images.map((src, index) => (
          <button
            aria-label={`放大檢視照片 ${index + 1}`}
            className="cpf-cell"
            key={`${src}-${index}`}
            onClick={() => onTap(index)}
            type="button"
          >
            <img alt="" draggable={false} loading="lazy" src={src} />
          </button>
        ))}
      </div>
    </div>
  );
}
