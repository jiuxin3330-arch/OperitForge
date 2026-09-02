// TICKET-H 第 4 項新增的前端合約測試。
//
// 實際位置:frontend/src/stackchanGalleryUi.test.ts 檔尾(附加,原有 6 條不動)。
// 檔頭既有的三個常數是這一段依賴的來源:
//   const root   = resolve(process.cwd(), "frontend", "src");
//   const app    = readFileSync(resolve(root, "App.tsx"), "utf8");
//   const styles = readFileSync(resolve(root, "styles.css"), "utf8");
//   const main   = readFileSync(resolve(process.cwd(), "backend", "app", "main.py"), "utf8");
//
// 測試要從專案根 /srv/chatnest-next 跑,不是從 frontend/ 底下。

describe("TICKET-H:舊 StackChan 面板已下線", () => {
  // 2026-09-02 裁定:併入相簿、廢棄獨立面板、單一入口。
  // 相簿驗收通過後才拆,拆完要有東西擋著它長回來。
  it("App.tsx 不再有 StackChanPanel 與它的路由分支", () => {
    expect(app).not.toContain("StackChanPanel");
    expect(app).not.toMatch(/view === "stackchan"/);
  });

  it("View 型別不再收 stackchan,舊網址不會有東西接", () => {
    const viewType = app.slice(app.indexOf("type View ="));
    expect(viewType.slice(0, viewType.indexOf(";"))).not.toContain('"stackchan"');
  });

  it("前端不再呼叫舊的照片端點", () => {
    expect(app).not.toContain("/api/v2/stackchan/photos");
  });

  it("後端五個舊端點都已移除", () => {
    expect(main).not.toMatch(/@app\.\w+\("\/api\/v2\/stackchan/);
  });

  it("面板的專屬樣式一起收掉,共用的 push 樣式不受牽連", () => {
    expect(styles).not.toContain("stackchan-panel");
    expect(styles).not.toContain("stackchan-grid");
    expect(styles).not.toContain("stackchan-card");
    expect(styles).toContain(".push-actions");
  });
});
