// 手帳翻頁（2026-09-29）：拓印眼前這一頁，沿左側書脊翻頁。前翻＝掀過去；回翻＝上一頁立起倒回來蓋上。
// 純 CSS 3D、零依賴、零外連。減少動態＝直接跳頁；低階裝置或實測掉幀＝降級成滑動。
export type LeafTurn = "flip" | "slide" | "none";

let degraded = false;
let slowTurns = 0;
const MIN_FPS = 40;

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return true;
  return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) || document.documentElement.dataset.reducedMotion === "true";
}

export function isLowEndDevice(): boolean {
  if (typeof navigator === "undefined") return true;
  const nav = navigator as Navigator & { deviceMemory?: number };
  return (typeof nav.deviceMemory === "number" && nav.deviceMemory <= 2) || (navigator.hardwareConcurrency > 0 && navigator.hardwareConcurrency <= 2);
}

// 拓印：複製目前看得到的頁面（去掉 id、不可互動、不進無障礙樹）
function rubbing(page: HTMLElement): HTMLElement {
  const paper = page.cloneNode(true) as HTMLElement;
  paper.removeAttribute("data-testid");
  paper.querySelectorAll("[id]").forEach((element) => element.removeAttribute("id"));
  // 章節標籤釘在書邊，不跟著紙翻
  paper.querySelectorAll(".handbook-tabs").forEach((element) => element.remove());
  paper.setAttribute("inert", "");
  paper.classList.add("handbook-leaf-paper");
  Object.assign(paper.style, { height: `${page.scrollHeight}px`, transform: `translateY(${-page.scrollTop}px)` });
  return paper;
}

function sheet(className: string, dir: string, box: Record<string, string>): HTMLDivElement {
  const element = document.createElement("div");
  element.className = className;
  element.dataset.dir = dir;
  element.setAttribute("aria-hidden", "true");
  Object.assign(element.style, box);
  return element;
}

// 前翻：眼前這頁從右緣掀起、沿左側書脊翻過去，新的一頁已在底下。
// 回翻（前翻的鏡像）：先把眼前這頁拓印壓著，等上一頁畫好後拓印它，
// 讓這張「已翻過的頁」從左緣書脊立起、向右倒回來蓋上。
export function turnLeaf(page: HTMLElement | null, dir: "next" | "prev"): LeafTurn {
  if (prefersReducedMotion()) return "none";
  if (!page || degraded || isLowEndDevice()) return "slide";
  const rect = page.getBoundingClientRect();
  if (rect.width < 10 || rect.height < 10) return "slide";
  const box = { top: `${rect.top}px`, left: `${rect.left}px`, width: `${rect.width}px`, height: `${rect.height}px` };

  // 書脊附近落在底頁上的影子
  const cast = sheet("handbook-leaf-cast", dir, box);
  const leaf = sheet("handbook-leaf", dir, box);
  const shade = document.createElement("div");
  shade.className = "handbook-leaf-shade";
  let under: HTMLDivElement | null = null;

  // 實測幀率：連續兩次掉到 MIN_FPS 以下，之後改用滑動（一次偶發卡頓不算）
  let frames = 0;
  let started = 0;
  let raf = 0;
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    cancelAnimationFrame(raf);
    const fps = frames / Math.max((performance.now() - started) / 1000, 0.001);
    slowTurns = fps < MIN_FPS ? slowTurns + 1 : 0;
    if (slowTurns >= 2) degraded = true;
    (window as Window & { __handbookFlipFps?: number }).__handbookFlipFps = Math.round(fps);
    leaf.remove();
    cast.remove();
    under?.remove();
  };
  const play = () => {
    leaf.append(rubbing(page), shade);
    document.body.append(leaf);
    started = performance.now();
    raf = requestAnimationFrame(function tick() { frames += 1; raf = requestAnimationFrame(tick); });
    leaf.addEventListener("animationend", finish, { once: true });
    window.setTimeout(finish, 1400);
  };

  if (dir === "next") {
    document.body.append(cast);
    play();
    return "flip";
  }
  // 回翻：底頁先壓住眼前這一頁，上一頁畫好（含日頁回到頁首）後才拓印它倒回來
  under = sheet("handbook-leaf-under", dir, box);
  under.append(rubbing(page));
  document.body.append(under, cast);
  window.setTimeout(play, 90);
  return "flip";
}

export function isFlipDegraded(): boolean { return degraded; }
