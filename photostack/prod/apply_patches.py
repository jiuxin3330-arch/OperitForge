#!/usr/bin/env python3
"""PhotoStack 蓋章版(2026-09-01)正式版補丁——精確字串替換,找不到或多於一處就整包失敗不落盤。"""
import sys
from pathlib import Path

ROOT = Path("/srv/chatnest-next/frontend")

PATCHES = []


def patch(path, old, new):
    PATCHES.append((path, old, new))


# ── App.tsx ──────────────────────────────────────────────────────────────

patch("src/App.tsx",
r'''import { createContext, Fragment, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";''',
r'''import { createContext, Fragment, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";''')

patch("src/App.tsx",
r'''import { MessagePhotoStack } from "./MessagePhotoStack";''',
r'''import { MessagePhotoStack } from "./MessagePhotoStack";
import type { PhotoStackApi } from "./MessagePhotoStack";
import { ChatPhotoStack } from "./ChatPhotoStack";
import { FLY_EASE, clearFlip, flipTranslate, stackPoseInfo, stackPoseTransform } from "./photoStackFly";''')

patch("src/App.tsx",
r'''function MessageAttachments({ items }: { items?: MessageAttachment[] }) {
  if (!items?.length) return null;
  // PhotoStack 替換案:圖片一律走 in-app 檢視(不再開新分頁);多圖=微信式堆疊卡。
  const images = items.filter((item) => item.mime_type.startsWith("image/"));
  const files = items.filter((item) => !item.mime_type.startsWith("image/"));
  const viewerImages = images.map((item) => ({
    src: `/api/v2/attachments/${item.id}`,
    name: item.original_name,
  }));
  return (
    <div className="message-attachments">
      {images.length > 1 ? (
        <MessagePhotoStack
          images={viewerImages.map((item) => item.src)}
          onTap={(index) => openChatPhotoViewer(viewerImages, index)}
        />
      ) : images.length === 1 ? (
        <button
          className="attachment-image-button"
          onClick={() => openChatPhotoViewer(viewerImages, 0)}
          type="button"
        >
          <img
            alt={images[0].original_name}
            className="attachment-image"
            loading="lazy"
            src={viewerImages[0].src}
          />
        </button>
      ) : null}
      {files.map((item) => {''',
r'''function messageImages(items?: MessageAttachment[]) {
  return (items ?? []).filter((item) => item.mime_type.startsWith("image/"));
}

/* PhotoStack 蓋章版(2026-09-01 糯糯定稿):圖片搬出氣泡——照片流獨立掛在氣泡下方,
   多圖=堆疊卡+展開/收起(一列),單圖=獨立縮圖;檔案列留在氣泡內。 */
function MessagePhotoFlow({ items, side }: { items?: MessageAttachment[]; side: string }) {
  const images = messageImages(items);
  if (!images.length) return null;
  const viewerImages = images.map((item) => ({
    src: `/api/v2/attachments/${item.id}`,
    name: item.original_name,
  }));
  return (
    <div className={`message-photo-flow ${side}`}>
      {images.length > 1 ? (
        <ChatPhotoStack
          images={viewerImages.map((item) => item.src)}
          onTap={(index) => openChatPhotoViewer(viewerImages, index)}
        />
      ) : (
        <button
          className="attachment-image-button"
          onClick={() => openChatPhotoViewer(viewerImages, 0)}
          type="button"
        >
          <img
            alt={images[0].original_name}
            className="attachment-image"
            loading="lazy"
            src={viewerImages[0].src}
          />
        </button>
      )}
    </div>
  );
}

function MessageAttachments({ items }: { items?: MessageAttachment[] }) {
  const files = (items ?? []).filter((item) => !item.mime_type.startsWith("image/"));
  if (!files.length) return null;
  return (
    <div className="message-attachments">
      {files.map((item) => {''')

patch("src/App.tsx",
r'''          <AssistantMessageExtras
            message={message}
            onNavigateGallerySource={onNavigateGallerySource}
          />
        </div>
      )}
    </>
  );
}''',
r'''          <AssistantMessageExtras
            message={message}
            onNavigateGallerySource={onNavigateGallerySource}
          />
        </div>
      )}
      <MessagePhotoFlow items={message.attachments} side={message.actor_id} />
    </>
  );
}''')

patch("src/App.tsx",
r'''            )}
          </article>
          {!!replyVersions.length && replyVersionIndex >= 0 && (''',
r'''            )}
          </article>
          {message.actor_id === "user" && (
            <MessagePhotoFlow items={message.attachments} side="user" />
          )}
          {!!replyVersions.length && replyVersionIndex >= 0 && (''')

patch("src/App.tsx",
r'''function PhotoStackCard({
  stack,
  open,
  onToggle,
  onPhoto,
  onRename,
  onDelete,
}: {
  stack: GalleryStack;
  open: boolean;
  onToggle: () => void;
  onPhoto: (photo: GalleryPhoto) => void;
  onRename?: () => void;
  onDelete?: () => void;
}) {
  // 微信式堆疊卡(糯糯裁定 2026-08-31):卡上直接跟手翻頁,點單張進大圖;
  // 卡上最多疊 9 張(全部照片在展開網格),空堆疊保留資料夾佔位。
  const deckPhotos = stack.photos.slice(0, 9);
  return (
    <article className={`photo-stack-card${open ? " open" : ""}`} data-stack-id={stack.id}>
      <div className="photo-stack-summary photo-stack-summary-wechat">
        {deckPhotos.length ? (
          <MessagePhotoStack
            height={158}
            images={deckPhotos.map((photo) => `/api/v2/gallery/photos/${photo.id}/image`)}
            onTap={(index) => onPhoto(deckPhotos[index])}
            width={118}
          />
        ) : (
          <span className="photo-stack-deck" data-empty="true" aria-hidden="true">
            <span className="photo-stack-empty-cover"><UiIcon name="folder" /></span>
          </span>
        )}
        <button type="button" className="photo-stack-copy-button" aria-expanded={open} onClick={onToggle}>
          <span className="photo-stack-copy">
            <strong>{stack.label}</strong>
            <small>{stack.photos.length} 張{stack.subtitle && stack.subtitle !== `${stack.photos.length} 張照片` ? ` · ${stack.subtitle}` : ""}</small>
          </span>
          <span className="photo-stack-chevron"><UiIcon name="chevron" /></span>
        </button>
      </div>
      <div className="photo-stack-reveal" aria-hidden={!open}>
        <div className="photo-stack-reveal-clip">
          {stack.editable && (
            <div className="photo-stack-owner-actions">
              <button type="button" onClick={onRename} aria-label={`重新命名 ${stack.label}`}><UiIcon name="edit" /><span>改名</span></button>
              <button type="button" className="danger" onClick={onDelete} aria-label={`刪除堆疊 ${stack.label}`}><UiIcon name="close" /><span>刪除堆疊</span></button>
            </div>
          )}
          <div className="gallery-grid photo-stack-grid">
            {stack.photos.map((photo, index) => (
              <button
                className="collection-photo-thumb photo-stack-item"
                key={photo.id}
                onClick={() => onPhoto(photo)}
                aria-label={`放大檢視 ${photo.note || photo.original_name}`}
                style={{ "--photo-index": Math.min(index, 12) } as CSSProperties}
              >
                <img src={`/api/v2/gallery/photos/${photo.id}/image`} alt={photo.note || photo.original_name} />
                <span>{photo.note || photo.original_name}</span>
              </button>
            ))}
          </div>
          {!stack.photos.length && <div className="empty compact photo-stack-empty">這個堆疊還是空的。<span>從照片檢視裡把喜歡的照片加入。</span></div>}
        </div>
      </div>
    </article>
  );
}''',
r'''function PhotoStackCard({
  stack,
  gone,
  onExpand,
  onPhoto,
  apiRef,
  cardRef,
}: {
  stack: GalleryStack;
  gone: boolean;
  onExpand: () => void;
  onPhoto: (photo: GalleryPhoto) => void;
  apiRef: { current: PhotoStackApi | null };
  cardRef: (el: HTMLElement | null) => void;
}) {
  // 蓋章版(2026-09-01 糯糯定稿):直式相冊卡——堆疊上、月份/張數小字置中在底部(無箭頭);
  // 卡上最多疊 9 張,點文字飛散展開,點卡片跟手翻頁/看大圖。展開時整格讓位(gone)。
  const deckPhotos = stack.photos.slice(0, 9);
  return (
    <article
      className={`photo-stack-card${gone ? " gone" : ""}`}
      data-stack-id={stack.id}
      ref={cardRef}
    >
      {deckPhotos.length ? (
        <MessagePhotoStack
          apiRef={apiRef}
          height={158}
          images={deckPhotos.map((photo) => `/api/v2/gallery/photos/${photo.id}/image`)}
          onTap={(index) => onPhoto(deckPhotos[index])}
          width={118}
        />
      ) : (
        <span aria-hidden="true" className="photo-stack-empty-tile"><UiIcon name="folder" /></span>
      )}
      <button aria-expanded={gone} className="photo-stack-caption" onClick={onExpand} type="button">
        <strong>{stack.label}</strong>
        <small>{stack.photos.length} 張{stack.subtitle && stack.subtitle !== `${stack.photos.length} 張照片` ? ` · ${stack.subtitle}` : ""}</small>
      </button>
    </article>
  );
}

/* 相簿蓋章版(2026-09-01 糯糯定稿):相冊並排一排兩本;點底部文字=開源同款飛散展開
 * (兩列、佔整排,旁邊的相冊被推下去);收起=第一張照片底部透明熱區或兩列中間間隔條
 * (照片上不放任何遮擋按鈕);替身按側歸位飛回,落地幀=靜態堆疊(vendor README 筆記)。 */
function GalleryStackFlyList({
  stacks,
  openId,
  setOpenId,
  onPhoto,
  actionsFor,
}: {
  stacks: GalleryStack[];
  openId: string | null;
  setOpenId: Dispatch<SetStateAction<string | null>>;
  onPhoto: (photo: GalleryPhoto) => void;
  actionsFor: (stack: GalleryStack) => React.ReactNode;
}) {
  const cardEls = useRef(new Map<string, HTMLElement>());
  const apis = useRef(new Map<string, { current: PhotoStackApi | null }>());
  const revealRef = useRef<HTMLDivElement>(null);
  const busyRef = useRef(false);
  const pendingOpenRef = useRef<string | null>(null);
  const flyRef = useRef<
    | { kind: "expand"; sRect: DOMRect; cur: number; others: HTMLElement[]; before: DOMRect[] }
    | {
        kind: "collapse";
        id: string;
        cur: number;
        clones: Array<{ el: HTMLElement; rect: DOMRect }>;
        others: HTMLElement[];
        before: DOMRect[];
      }
    | null
  >(null);

  function apiFor(id: string) {
    let ref = apis.current.get(id);
    if (!ref) {
      ref = { current: null };
      apis.current.set(id, ref);
    }
    return ref;
  }
  function stageOf(id: string): HTMLElement | null {
    const card = cardEls.current.get(id);
    return card?.querySelector<HTMLElement>(".pstack-stage") ?? card ?? null;
  }
  function otherCards(id: string): HTMLElement[] {
    return stacks
      .filter((stack) => stack.id !== id)
      .map((stack) => cardEls.current.get(stack.id))
      .filter((el): el is HTMLElement => Boolean(el));
  }

  function requestExpand(id: string) {
    if (busyRef.current || openId === id) return;
    const stage = stageOf(id);
    if (!stage) {
      setOpenId(id);
      return;
    }
    busyRef.current = true;
    const others = otherCards(id);
    flyRef.current = {
      kind: "expand",
      sRect: stage.getBoundingClientRect(),
      cur: apiFor(id).current?.index ?? 0,
      others,
      before: others.map((el) => el.getBoundingClientRect()),
    };
    setOpenId(id);
  }

  function requestCollapse() {
    if (busyRef.current || !openId) return;
    busyRef.current = true;
    const reveal = revealRef.current;
    const cells = reveal
      ? Array.from(reveal.querySelectorAll<HTMLElement>(".album-fly-cell"))
      : [];
    /* 替身接管每張卡的視覺(fixed+transform):版面歸版面、飛行歸飛行 */
    const clones = cells.map((cell, i) => {
      const rect = cell.getBoundingClientRect();
      const el = document.createElement("div");
      el.className = "album-fly-clone";
      el.style.left = rect.left + "px";
      el.style.top = rect.top + "px";
      el.style.width = rect.width + "px";
      el.style.height = rect.height + "px";
      el.style.zIndex = String(300 - i);
      const img = document.createElement("img");
      img.src = cell.querySelector("img")?.src ?? "";
      img.alt = "";
      el.appendChild(img);
      document.body.appendChild(el);
      return { el, rect };
    });
    const others = otherCards(openId);
    flyRef.current = {
      kind: "collapse",
      id: openId,
      cur: apiFor(openId).current?.index ?? 0,
      clones,
      others,
      before: others.map((el) => el.getBoundingClientRect()),
    };
    setOpenId(null);
  }

  useLayoutEffect(() => {
    const fly = flyRef.current;
    flyRef.current = null;
    if (!fly) return;
    if (fly.kind === "expand") {
      const reveal = revealRef.current;
      if (!reveal) {
        busyRef.current = false;
        return;
      }
      flipTranslate(fly.others, fly.before);
      const cells = Array.from(reveal.querySelectorAll<HTMLElement>(".album-fly-cell"));
      const rects = cells.map((cell) => cell.getBoundingClientRect());
      cells.forEach((cell, i) => {
        const info = stackPoseInfo(i, fly.cur, cells.length);
        cell.style.transition = "none";
        cell.style.transform = stackPoseTransform(fly.sRect, rects[i], info);
        cell.style.zIndex = String(100 - info.depth);
        cell.style.opacity = info.visible ? "1" : "0";
      });
      const actions = reveal.querySelector<HTMLElement>(".album-fly-actions");
      if (actions) actions.style.opacity = "0";
      void reveal.offsetHeight;
      cells.forEach((cell, i) => {
        cell.style.transition = `transform ${280 + 45 * Math.min(i, 10)}ms ${FLY_EASE}, opacity 120ms`;
        cell.style.transform = "";
        cell.style.opacity = "1";
      });
      if (actions) {
        requestAnimationFrame(() => {
          actions.style.transition = "opacity .2s .25s";
          actions.style.opacity = "1";
        });
      }
      window.setTimeout(() => {
        clearFlip(fly.others);
        busyRef.current = false;
      }, 280 + 45 * Math.min(Math.max(cells.length - 1, 0), 10) + 80);
      return;
    }
    /* collapse:版面一步恢復;堆疊若在畫面外就近帶回(替身是 fixed,視覺不斷) */
    const card = cardEls.current.get(fly.id);
    card?.scrollIntoView({ block: "nearest" });
    const stage = stageOf(fly.id);
    const sRect = stage?.getBoundingClientRect() ?? null;
    const stageStack = card?.querySelector<HTMLElement>(".pstack-stage") ?? null;
    if (stageStack) stageStack.style.opacity = "0";
    flipTranslate(fly.others, fly.before);
    fly.clones.forEach((clone, i) => {
      void clone.el.offsetWidth;
      if (!sRect) {
        clone.el.remove();
        return;
      }
      const info = stackPoseInfo(i, fly.cur, fly.clones.length);
      clone.el.style.transition = `transform 300ms ${FLY_EASE}, opacity 130ms 170ms`;
      clone.el.style.transform = stackPoseTransform(sRect, clone.rect, info);
      clone.el.style.zIndex = String(300 - info.depth);
      if (!info.visible) clone.el.style.opacity = "0";
    });
    window.setTimeout(() => {
      if (stageStack) {
        stageStack.style.transition = "opacity .13s";
        stageStack.style.opacity = "1";
      }
    }, 200);
    window.setTimeout(() => {
      fly.clones.forEach((clone) => clone.el.remove());
      if (stageStack) {
        stageStack.style.transition = "";
        stageStack.style.opacity = "";
      }
      clearFlip(fly.others);
      busyRef.current = false;
      const pending = pendingOpenRef.current;
      pendingOpenRef.current = null;
      if (pending) requestExpand(pending);
    }, 330);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openId]);

  const openIdx = stacks.findIndex((stack) => stack.id === openId);
  const children: React.ReactNode[] = stacks.map((stack) => (
    <PhotoStackCard
      apiRef={apiFor(stack.id)}
      cardRef={(el) => {
        if (el) cardEls.current.set(stack.id, el);
        else cardEls.current.delete(stack.id);
      }}
      gone={stack.id === openId}
      key={stack.id}
      onExpand={() => {
        if (openId && openId !== stack.id) {
          pendingOpenRef.current = stack.id;
          requestCollapse();
        } else {
          requestExpand(stack.id);
        }
      }}
      onPhoto={onPhoto}
      stack={stack}
    />
  ));
  if (openIdx >= 0) {
    const openStack = stacks[openIdx];
    children.splice(openIdx & ~1, 0, (
      <div className="album-fly-reveal" key={`reveal-${openStack.id}`} ref={revealRef}>
        <div className="album-fly-grid">
          {openStack.photos.map((photo, index) => (
            <button
              aria-label={`放大檢視 ${photo.note || photo.original_name}`}
              className="album-fly-cell"
              key={photo.id}
              onClick={() => onPhoto(photo)}
              type="button"
            >
              <img
                alt={photo.note || photo.original_name}
                loading="lazy"
                src={`/api/v2/gallery/photos/${photo.id}/image`}
              />
              {index === 0 && (
                <span
                  aria-label="收起相冊"
                  className="album-fly-hotzone"
                  onClick={(event) => {
                    event.stopPropagation();
                    requestCollapse();
                  }}
                  role="button"
                />
              )}
            </button>
          ))}
          {openStack.photos.length > 1 && (
            <button
              aria-label="收起相冊"
              className="album-fly-gap"
              onClick={() => requestCollapse()}
              type="button"
            />
          )}
        </div>
        {!openStack.photos.length && (
          <div className="empty compact photo-stack-empty">
            這個堆疊還是空的。<span>從照片檢視裡把喜歡的照片加入。</span>
          </div>
        )}
        <div className="album-fly-actions">{actionsFor(openStack)}</div>
      </div>
    ));
  }
  return <div className="photo-stack-list">{children}</div>;
}''')

patch("src/App.tsx",
r'''          <div className="photo-stack-list">
            {photoStacks.map((stack) => {
              const album = stack.albumId ? data.albums.find((item) => item.id === stack.albumId) : undefined;
              return (
                <PhotoStackCard
                  key={stack.id}
                  stack={stack}
                  open={openPhotoStackId === stack.id}
                  onToggle={() => setOpenPhotoStackId((current) => current === stack.id ? null : stack.id)}
                  onPhoto={setPreviewPhoto}
                  onRename={album ? () => openAlbumEditor("rename", album) : undefined}
                  onDelete={album ? () => void deleteAlbum(album) : undefined}
                />
              );
            })}
          </div>''',
r'''          <GalleryStackFlyList
            actionsFor={(stack) => {
              const album = stack.albumId ? data.albums.find((item) => item.id === stack.albumId) : undefined;
              if (!stack.editable || !album) return null;
              return (
                <>
                  <button type="button" onClick={() => openAlbumEditor("rename", album)} aria-label={`重新命名 ${stack.label}`}><UiIcon name="edit" /><span>改名</span></button>
                  <button type="button" className="danger" onClick={() => void deleteAlbum(album)} aria-label={`刪除堆疊 ${stack.label}`}><UiIcon name="close" /><span>刪除堆疊</span></button>
                </>
              );
            }}
            onPhoto={setPreviewPhoto}
            openId={openPhotoStackId}
            setOpenId={setOpenPhotoStackId}
            stacks={photoStacks}
          />''')

# ── styles.css:尾段「相簿堆疊卡微信化」整段換成蓋章版 ────────────────────

patch("src/styles.css",
r'''/* ── 相簿堆疊卡微信化(2026-08-31 糯糯裁定,與聊天堆疊同款)── */
.photo-stack-summary-wechat {
  grid-template-columns: auto minmax(0, 1fr);
  gap: 13px;
  padding: 12px 6px;
}
.photo-stack-summary-wechat:is(:focus-visible, :active) {
  background: transparent;
  box-shadow: none;
}
.photo-stack-copy-button {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 24px;
  align-items: center;
  gap: 9px;
  min-width: 0;
  width: 100%;
  align-self: stretch;
  border: 0;
  background: transparent;
  padding: 12px 2px;
  text-align: left;
  color: inherit;
  cursor: pointer;
  border-radius: 15px;
}
.photo-stack-copy-button:is(:focus-visible, :active) {
  outline: 0;
  background: color-mix(in srgb, var(--nest-text), transparent 96%);
  box-shadow: inset 1.5px 1.5px 4px color-mix(in srgb, var(--nest-shadow), transparent 28%);
}''',
r'''/* ── PhotoStack 蓋章版(2026-09-01 糯糯定稿)──
   聊天:圖片搬出氣泡、堆疊+展開/收起(一列 112)、按鈕貼卡內側、無角標。
   相簿:相冊並排一排兩本、底部小字置中無箭頭、飛散展開兩列推走旁鄰、
   收起=第一張照片底部透明熱區+兩列中間間隔條(照片上不放任何遮擋按鈕)。 */

/* 聊天照片流:獨立掛在氣泡下方 */
.message-photo-flow { position: relative; width: 100%; }
.message-photo-flow .attachment-image {
  max-width: min(260px, 100%);
  border-radius: 12px;
  display: block;
}
.message-photo-flow.user .attachment-image-button { margin-left: auto; }
html[data-viewpoint="ai"] .message-photo-flow.user .attachment-image-button { margin-left: 0; margin-right: auto; }
html[data-viewpoint="ai"] .message-photo-flow.mumu .attachment-image-button,
html[data-viewpoint="ai"] .message-photo-flow.coco .attachment-image-button { margin-left: auto; }
/* 糯糯訊息的照片流是氣泡的兄弟節點:對齊規則照抄 .message.user */
.message-list > .message-photo-flow.user,
.live-turn-timeline .message-photo-flow.user {
  width: min(82%, 590px);
  align-self: flex-end;
  margin-right: 2px;
}
html[data-show-own-avatar="true"] .message-list > .message-photo-flow.user,
html[data-show-own-avatar="true"] .live-turn-timeline .message-photo-flow.user {
  margin-right: 38px;
}
html[data-viewpoint="ai"] .message-list > .message-photo-flow.user,
html[data-viewpoint="ai"] .live-turn-timeline .message-photo-flow.user {
  align-self: flex-start;
}
@media (max-width: 520px) {
  .message-list > .message-photo-flow.user,
  .live-turn-timeline .message-photo-flow.user { width: min(86%, 640px); }
}

/* 堆疊+展開/收起容器(高度由 JS 動畫管理) */
.cpf-area { position: relative; height: 190px; }
.cpf-row {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  transition: opacity .15s;
}
.message-photo-flow.user .cpf-row { justify-content: flex-end; }
html[data-viewpoint="ai"] .message-photo-flow.user .cpf-row { justify-content: flex-start; }
html[data-viewpoint="ai"] .message-photo-flow.mumu .cpf-row,
html[data-viewpoint="ai"] .message-photo-flow.coco .cpf-row { justify-content: flex-end; }
.cpf-area.open .cpf-row { opacity: 0; pointer-events: none; }
.cpf-slot {
  position: absolute;
  display: flex;
  align-items: center;
  z-index: 130;
  transition: opacity .2s;
}
.cpf-pill {
  border: 0;
  cursor: pointer;
  background: rgb(0 0 0 / .38);
  color: rgb(242 240 217 / .92);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  font-size: 12px;
  padding: 6px 12px;
  border-radius: 999px;
  box-shadow: 0 2px 8px rgb(0 0 0 / .25);
  white-space: nowrap;
}
.cpf-pill:active { transform: scale(.95); }
/* 展開=一列,卡片比堆疊小一號(聊天要同時看字) */
.cpf-grid {
  display: grid;
  grid-template-columns: 112px;
  gap: 9px;
  width: fit-content;
}
.cpf-grid[hidden] { display: none; }
.message-photo-flow.user .cpf-grid { margin-left: auto; }
html[data-viewpoint="ai"] .message-photo-flow.user .cpf-grid { margin-left: 0; margin-right: auto; }
html[data-viewpoint="ai"] .message-photo-flow.mumu .cpf-grid,
html[data-viewpoint="ai"] .message-photo-flow.coco .cpf-grid { margin-left: auto; }
.cpf-cell {
  border: 0;
  padding: 0;
  cursor: zoom-in;
  position: relative;
  width: 112px;
  aspect-ratio: 3 / 4;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 3px 14px rgb(0 0 0 / .22);
  will-change: transform;
  background: var(--nest-surface);
}
.cpf-cell img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  pointer-events: none;
}

/* 相簿:相冊並排一排兩本 */
.photo-stack-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px 12px;
  padding: 4px 2px;
}
.photo-stack-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 9px;
  min-width: 0;
  border: 0;
  background: none;
  padding: 0;
  box-shadow: none;
}
.photo-stack-card.gone { display: none; }
.photo-stack-caption {
  border: 0;
  background: none;
  color: inherit;
  cursor: pointer;
  padding: 2px 6px;
  max-width: 100%;
  text-align: center;
}
.photo-stack-caption strong {
  display: block;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .4px;
}
.photo-stack-caption small {
  display: block;
  margin-top: 1px;
  font-size: 10.5px;
  color: var(--nest-muted);
}
.photo-stack-empty-tile {
  width: 118px;
  height: 158px;
  border-radius: 14px;
  border: 1px dashed var(--nest-line);
  display: grid;
  place-items: center;
  color: var(--nest-muted);
}
.photo-stack-empty-tile svg { width: 26px; height: 26px; }

/* 相冊飛散展開:兩列、佔整排、無盒子;聯動全走 transform */
.album-fly-reveal { grid-column: 1 / -1; position: relative; z-index: 5; }
.album-fly-grid {
  position: relative;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px 18px;
  padding: 2px;
}
.album-fly-cell {
  border: 0;
  padding: 0;
  cursor: zoom-in;
  position: relative;
  aspect-ratio: 3 / 4;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 3px 14px rgb(0 0 0 / .22);
  will-change: transform;
  background: var(--nest-surface);
}
.album-fly-cell img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  pointer-events: none;
}
/* 收起入口①:第一張照片底部——同位置、透明熱區,無任何按鈕、不遮照片 */
.album-fly-hotzone {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 34%;
  background: transparent;
  cursor: pointer;
}
/* 收起入口②:兩列中間的間隔區,整條可點(照片很多時就近收) */
.album-fly-gap {
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 30px;
  transform: translateX(-50%);
  border: 0;
  padding: 0;
  background: transparent;
  cursor: pointer;
  z-index: 3;
}
.album-fly-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 12px;
  transition: opacity .2s;
}
.album-fly-actions:empty { display: none; }
.album-fly-actions button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid var(--nest-line);
  background: transparent;
  color: var(--nest-muted);
  font-size: 12px;
  padding: 5px 12px;
  border-radius: 999px;
  cursor: pointer;
}
.album-fly-actions button.danger {
  color: var(--nest-danger);
  border-color: color-mix(in srgb, var(--nest-danger), transparent 55%);
}
.album-fly-actions button svg { width: 14px; height: 14px; }
/* 收起用的飛行替身:fixed+transform,不碰版面 */
.album-fly-clone {
  position: fixed;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 3px 14px rgb(0 0 0 / .25);
  pointer-events: none;
  will-change: transform;
  z-index: 250;
}
.album-fly-clone img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

html[data-reduced-motion="true"] .cpf-cell,
html[data-reduced-motion="true"] .cpf-row,
html[data-reduced-motion="true"] .cpf-area,
html[data-reduced-motion="true"] .album-fly-cell,
html[data-reduced-motion="true"] .album-fly-clone,
html[data-reduced-motion="true"] .photo-stack-card {
  transition: none !important;
}''')

# ── sw 版本同步 bump v157 → v158 ─────────────────────────────────────────

patch("public/sw.js",
'const SHELL_CACHE = "chatnest-next-shell-v157";',
'const SHELL_CACHE = "chatnest-next-shell-v158";')

patch("src/main.tsx",
'navigator.serviceWorker.register("/sw.js?v=157", { updateViaCache: "none" }).catch(() => undefined);',
'navigator.serviceWorker.register("/sw.js?v=158", { updateViaCache: "none" }).catch(() => undefined);')

# ── 合約測試同步(蓋章版) ─────────────────────────────────────────────────

patch("src/collectionPhotoStacks.test.ts",
r'''  it("offers the four owner-approved groupings and expands physical photo stacks", () => {
    for (const label of ["來源", "時間", "自定義堆疊", "收藏狀態"]) expect(app).toContain(`'${label}'`);
    expect(app).toContain("buildGalleryStacks(photoGroupMode, data.photos, data.albums)");
    expect(app).toContain('className={`photo-stack-card${open ? " open" : ""}`}');
    expect(styles).toMatch(/\.photo-stack-card\.open \.photo-stack-reveal\s*\{[^}]*grid-template-rows:\s*1fr/s);
    expect(styles).toContain("@keyframes photo-stack-deal-in");
    expect(styles).toMatch(/animation-delay:\s*calc\(var\(--photo-index, 0\) \* 34ms\)/);
  });''',
r'''  it("offers the four owner-approved groupings and expands stacks with the fly-out animation", () => {
    for (const label of ["來源", "時間", "自定義堆疊", "收藏狀態"]) expect(app).toContain(`'${label}'`);
    expect(app).toContain("buildGalleryStacks(photoGroupMode, data.photos, data.albums)");
    // 2026-09-01 蓋章:相冊並排一排兩本;展開=飛散兩列佔整排,旁鄰被推走;收起=按側歸位替身
    expect(styles).toMatch(/\.photo-stack-list\s*\{[^}]*repeat\(2, 1fr\)/s);
    expect(styles).toMatch(/\.album-fly-grid\s*\{[^}]*repeat\(2, 1fr\)/s);
    expect(app).toContain("GalleryStackFlyList");
    expect(app).toContain("stackPoseTransform");
  });''')

patch("src/collectionPhotoStacks.test.ts",
r'''  it("renders gallery stacks as WeChat-style decks with a two-column expanded grid", () => {
    // 2026-08-31 糯糯裁定:堆疊卡=微信式跟手翻頁(點單張進大圖),展開網格固定兩列
    expect(app).toMatch(/photo-stack-summary-wechat/);
    expect(app).toMatch(/<MessagePhotoStack[\s\S]{0,200}gallery\/photos/);
    expect(app).toContain("stack.photos.slice(0, 9)");
    expect(styles).toMatch(/\.photo-stack-grid\s*\{[^}]*repeat\(2, minmax\(0, 1fr\)\)/s);
    expect(app).toContain('onTap={(index) => onPhoto(deckPhotos[index])}');
  });''',
r'''  it("renders decks with the caption below and no covering buttons on photos", () => {
    // 2026-09-01 蓋章:底部小字置中無箭頭;照片上不放任何遮擋按鈕(收起=透明熱區+中間間隔條)
    expect(app).toMatch(/<MessagePhotoStack[\s\S]{0,220}gallery\/photos/);
    expect(app).toContain("stack.photos.slice(0, 9)");
    expect(app).toContain('onTap={(index) => onPhoto(deckPhotos[index])}');
    expect(app).toContain('className="photo-stack-caption"');
    expect(app).toContain('className="album-fly-hotzone"');
    expect(app).toContain('className="album-fly-gap"');
    expect(styles).toMatch(/\.album-fly-hotzone\s*\{[^}]*background:\s*transparent/s);
  });''')

patch("src/messagePhotoStackUi.test.ts",
r'''  it("chat attachments route through MessagePhotoStack and the in-app viewer", () => {
    expect(app).toContain("<MessagePhotoStack");
    expect(app).toContain("openChatPhotoViewer(viewerImages, index)");
  });
});''',
r'''  it("chat attachments route through MessagePhotoStack and the in-app viewer", () => {
    expect(app).toContain("<MessagePhotoStack");
    expect(app).toContain("openChatPhotoViewer(viewerImages, index)");
  });

  it("keeps photos outside the bubble with expand/collapse and no counter badge", () => {
    // 2026-09-01 蓋章:圖片搬出氣泡(照片流獨立)、聊天展開一列、無 n/N 角標
    expect(stack).toContain("counter: false");
    expect(app).toContain("MessagePhotoFlow");
    expect(app).toContain("<ChatPhotoStack");
    expect(app).toContain('side="user"');
  });
});''')


def main():
    changed = {}
    for rel, old, new in PATCHES:
        path = ROOT / rel
        text = changed.get(path, path.read_text(encoding="utf-8"))
        count = text.count(old)
        if count != 1:
            print(f"FAIL: {rel}: pattern found {count} times (expected 1)\n--- pattern head ---\n{old[:200]}")
            sys.exit(1)
        changed[path] = text.replace(old, new)
    for path, text in changed.items():
        path.write_text(text, encoding="utf-8")
        print(f"patched {path}")
    print(f"OK: {len(PATCHES)} patches applied across {len(changed)} files")


if __name__ == "__main__":
    main()
