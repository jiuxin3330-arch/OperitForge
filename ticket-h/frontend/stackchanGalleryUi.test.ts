// @ts-nocheck -- Vitest executes this source contract in Node.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const root = resolve(process.cwd(), "frontend", "src");
const app = readFileSync(resolve(root, "App.tsx"), "utf8");
const styles = readFileSync(resolve(root, "styles.css"), "utf8");
const main = readFileSync(resolve(process.cwd(), "backend", "app", "main.py"), "utf8");

describe("TICKET-H:相簿裡的 StackChan 照片", () => {
  it("刪除鍵只對 StackChan 照片出現,而且在動作列最左", () => {
    // 2026-09-02 蓋章:糯糯是右撇,刪除放最左最不容易誤觸。
    const actions = app.slice(app.indexOf('<div className="photo-actions">'));
    const row = actions.slice(0, actions.indexOf("</div>"));
    const deleteAt = row.indexOf('aria-label="刪除照片"');
    expect(deleteAt).toBeGreaterThanOrEqual(0);
    for (const later of ['aria-label="回原訊息"', 'aria-label="加入堆疊"', 'aria-label="帶回聊天"']) {
      expect(row.indexOf(later)).toBeGreaterThan(deleteAt);
    }
    expect(row).toMatch(/previewPhoto\.source\.kind === "stackchan" && <button[^>]*aria-label="刪除照片"/);
  });

  it("動作鍵只留 icon,名稱靠 aria-label 與 title 撐住", () => {
    // 2026-09-02 蓋章:不要文字,只要 icon。拿掉文字不能連名字一起拿掉。
    const actions = app.slice(app.indexOf('<div className="photo-actions">'));
    const row = actions.slice(0, actions.indexOf("</div>"));
    expect(row).not.toMatch(/<span>(永久收藏|改為暫存|加入堆疊|帶回聊天|回原訊息|刪除)<\/span>/);
    for (const label of ["刪除照片", "加入堆疊", "帶回聊天"]) {
      expect(row).toContain(`aria-label="${label}"`);
      expect(row).toContain(`title="${label === "刪除照片" ? "刪除" : label}"`);
    }
    expect(styles).toMatch(/\.collection-photo-action:not\(\.photo-delete-choice\)\s*\{[^}]*min-width:\s*46px/s);
  });

  it("刪除要先展開確認條,並說明實體檔也會一起消失", () => {
    // 2026-09-02 蓋章:B 案。刪除連 /srv/mumu-server/photos 的檔案一起刪,沒有復原。
    expect(app).toContain("photo-delete-confirm");
    expect(app).toMatch(/StackChan 上的檔案也會一起消失/);
    expect(app).toMatch(/setDeleteArming\(\(armed\) => !armed\)/);
    expect(app).toMatch(/removeStackchanPhoto\(previewPhoto\)/);
    // 換一張照片要把確認收起來,不能把上一張的狀態黏過去
    expect(app).toMatch(/setDeleteArming\(false\); \}, \[previewPhoto\?\.id\]/);
  });

  it("相簿會自己更新,不必殺掉 app 重開", () => {
    // 2026-09-02 糯糯回報:拍完要殺 app 重開才看得到新照片。
    // 驗收情境是「拍一張,什麼都不做,盯著相簿看它出現」——那時 visibilitychange
    // 不會觸發,所以回前台重載之外還要有看得見時的輪詢。
    expect(app).toMatch(/window\.setInterval\(refresh, 20000\)/);
    expect(app).toMatch(/document\.addEventListener\("visibilitychange", refresh\)/);
    expect(app).toMatch(/window\.addEventListener\("pageshow", refresh\)/);
    expect(app).toMatch(/if \(document\.visibilityState !== "visible"\) return;/);
  });

  it("動作鍵與確認卡片是純平面:不留新擬態突起,也不留任何框線", () => {
    // 2026-09-02 蓋章:「按鍵直接刪除新擬態突起」「提示的框線要刪,完全不能出現」。
    // 更進一步的美化是美化窗的工作,這裡只鎖住這兩條硬要求。
    const confirmCard = styles.slice(styles.indexOf(".photo-delete-confirm {"));
    expect(confirmCard.slice(0, confirmCard.indexOf("}"))).not.toMatch(/box-shadow|border(?!-radius)/);
    const flat = styles.slice(styles.indexOf("拿掉新擬態突起"));
    expect(flat).toMatch(/\.collection-photo-action\s*\{[^}]*box-shadow:\s*none/s);
    expect(flat).toMatch(/background:\s*var\(--nest-surface\)/);
    // 沒有陰影就得自己畫聚焦框,否則鍵盤操作看不出焦點在哪
    expect(flat).toMatch(/:focus-visible[^{]*\{[^}]*outline:\s*2px solid/s);
  });

  it("後端只讓 StackChan 照片被刪,而且連實體檔一起刪", () => {
    expect(main).toContain('@app.delete("/api/v2/gallery/photos/{photo_id}")');
    expect(main).toContain("stackchan_gallery.delete_on_disk(source_ref)");
    expect(main).toContain("only StackChan photos can be deleted from the gallery");
    // 相簿設永久要寫回實體檔;寫不成就整筆退回,不留兩邊各說各話
    expect(main).toContain("stackchan_gallery.set_permanent_on_disk(");
    expect(main).toMatch(/status_code=409/);
  });
});
