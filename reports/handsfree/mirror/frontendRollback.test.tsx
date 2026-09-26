import React from "react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FrontendRollback, FrontendRollbackView, ROLLBACK_PATH, ROLLBACK_REASON } from "./FrontendRollback";

const noop = () => {};
const view = (phase: Parameters<typeof FrontendRollbackView>[0]["phase"]) =>
  renderToStaticMarkup(<FrontendRollbackView phase={phase} busy={false} onStart={noop} onConfirm={noop} onCancel={noop} onReload={noop} />);

describe("frontend rollback card", () => {
  it("hides until the owner-only status probe succeeds", () => {
    expect(renderToStaticMarkup(<FrontendRollback />)).toBe("");
  });
  it("needs a second confirm tap before sending", () => {
    expect(view("idle")).toContain(">回滾前端</button>");
    expect(view("idle")).not.toContain("確定回滾");
    expect(view("confirm")).toContain("確定回滾");
    expect(view("confirm")).toContain("取消");
  });
  it("never claims success from the flag alone and always links the rescue page", () => {
    expect(view("consumed")).toContain("60 秒內");
    for (const phase of ["idle", "confirm", "waiting", "consumed", "slow", "error"] as const) {
      expect(view(phase)).toContain('href="/rollback.html"');
    }
  });
  it("targets the owner flag route with a JSON string reason", () => {
    expect(ROLLBACK_PATH).toBe("/api/v2/owner/frontend-rollback");
    expect(JSON.stringify(ROLLBACK_REASON)).toMatch(/^".+"$/);
    expect(JSON.stringify(ROLLBACK_REASON).length).toBeLessThan(512);
  });
  it("sits right after the toolbox without touching it", () => {
    const app = readFileSync(resolve(process.cwd(), "frontend", "src", "App.tsx"), "utf8");
    expect(app).toMatch(/<Toolbox \/>\s*<FrontendRollback \/>/);
  });
});
