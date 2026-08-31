import { useEffect, useRef } from "react";
import "./vendor/photostack/photo-stack.css";
import PhotoStackVendor from "./vendor/photostack/photo-stack.js";

/** Wren036/PhotoStack 的 React 掛載殼:微信式堆疊照片卡(多圖訊息用)。
 * vendor 檔含 module.exports,bundler 會走 CJS 分支,必須吃 default export——
 * 不能只靠 window.PhotoStack(sw v155 空白卡事故的根因)。
 * 建構子拿不到時 fallback 成普通縮圖列,永不空白。 */
const PhotoStackCtor =
  PhotoStackVendor ?? (typeof window !== "undefined" ? window.PhotoStack : undefined);

export type PhotoStackApi = { readonly index: number };

export function MessagePhotoStack({
  images,
  onTap,
  width,
  height,
  apiRef,
}: {
  images: string[];
  onTap: (index: number) => void;
  width?: number;
  height?: number;
  apiRef?: { current: PhotoStackApi | null };
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const tapRef = useRef(onTap);
  tapRef.current = onTap;
  const key = images.join("|");

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !PhotoStackCtor || !images.length) return;
    // 角標(n/N)不開:糯糯裁定 2026-09-01「照片下面不要有 1/6,純照片就好」
    const stack = new PhotoStackCtor(host, images, {
      counter: false,
      onTap: (index: number) => tapRef.current(index),
      ...(width ? { width } : {}),
      ...(height ? { height } : {}),
    });
    if (apiRef) {
      apiRef.current = {
        get index() {
          return stack.index as number;
        },
      };
    }
    return () => {
      if (apiRef) apiRef.current = null;
      stack.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, width, height]);

  if (!PhotoStackCtor) {
    return (
      <>
        {images.map((src, index) => (
          <button
            className="attachment-image-button"
            key={`${src}-${index}`}
            onClick={() => tapRef.current(index)}
            type="button"
          >
            <img alt="" className="attachment-image" loading="lazy" src={src} />
          </button>
        ))}
      </>
    );
  }
  return <div className="photo-stack-host" ref={hostRef} />;
}
