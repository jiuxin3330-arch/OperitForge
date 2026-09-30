import fs from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { CARD_PRINCIPLE, contactChanges, FriendDetail, LEAD_SAVED, matchFriend, PAGE_NOTE, saveErrorText, toneFor, type Friend } from "./FriendsRoster";

const source = fs.readFileSync(new URL("./FriendsRoster.tsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("./FriendsRoster.css", import.meta.url), "utf8");
const app = fs.readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
const friend: Friend = { id: "f1", name: "海風", email: "sea@example.test", aliases: ["小海"], relationship_label: "筆友",
  met_context: "相遇", confirmed_origin: "來路", boundaries: "邊界", status: "近況", entity_card_id: null, updated_at: "2026-09-30T00:00:00Z" };

describe("筆友名冊（TICKET-W）", () => {
  it("Owner edits only changed contact fields, preserving cn narratives", () => {
    expect(contactChanges(friend, "海風", "sea@example.test", "小海")).toEqual({});
    expect(contactChanges(friend, "海風", "sea@example.test", "小海\n海仔")).toEqual({ aliases: ["小海", "海仔"] });
    expect(contactChanges(friend, "  晚風 ", "sea@example.test", "小海")).toEqual({ name: "晚風" });
  });
  it("shows cn narratives and status as plain text, never as inputs", () => {
    const html = renderToStaticMarkup(<FriendDetail friend={{ ...friend, boundaries: "<script>bad</script>", status: "<b>x</b>" }} onSaved={() => {}} onBack={() => {}} />);
    expect(html).toContain("&lt;script&gt;"); expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;b&gt;x&lt;/b&gt;");
    expect(html).not.toMatch(/<input|<textarea|contenteditable/);
    expect(html).toContain(PAGE_NOTE);
    for (const label of ["相遇與第一印象", "牧牧確認的來路", "這條線的邊界"]) expect(html).toContain(label);
  });
  it("keeps the fixed copy word for word", () => {
    expect(PAGE_NOTE).toBe("關係、來路與邊界由牧牧自己確認與填寫。");
    expect(CARD_PRINCIPLE).toBe("名冊是聯絡索引，不是記憶實體卡；登記名冊不代表建立實體卡。");
    expect(LEAD_SAVED).toBe("線索已記下，待牧牧確認。尚未加入正式名冊。");
  });
  it("offers exactly three Owner contact inputs and an explicit entity card choice", () => {
    expect((source.match(/<input required maxLength=\{80\}/g) || []).length).toBe(2); // 編輯名字＋線索名字
    expect(source).toContain('<label>別名（一行一個）<textarea');
    expect(source).toContain('JSON.stringify({ entity_card_id: id })');
    // 送出的內容只有允許欄：PATCH 只有 contactChanges 的結果或 entity_card_id
    const bodies = source.match(/body: JSON\.stringify\([^)]*\)/g) || [];
    expect(bodies.length).toBeGreaterThan(0);
    for (const body of bodies) expect(body).not.toMatch(/relationship_label|met_context|confirmed_origin|boundaries|status/);
  });
  it("never deletes, never enrols on cn's behalf, never scans mail", () => {
    expect(source).not.toMatch(/method:\s*"DELETE"/);
    expect(source).not.toMatch(/>[^<{]*刪除[^<]*</); // 畫面上沒有刪除按鈕
    expect(source).not.toMatch(/method:\s*"POST",[^)]*base\)|api<[^>]*>\(base,\s*\{\s*method:\s*"POST"/);
    expect(source).not.toMatch(/gmail|scan|imap|\/tools\//i);
    expect(source).toContain('base + "/suggestions", { method: "POST", body: JSON.stringify({ name: name.trim(), email: email.trim() }) }');
  });
  it("maps each backend error to its own message and never shows success on failure", () => {
    const text = (status: number) => saveErrorText(new ApiError(status, "x"), "contact");
    expect(text(409)).toContain("已登記給另一位朋友");
    expect(text(422)).toContain("格式不符");
    expect(text(403)).toContain("沒有寫入任何內容");
    expect(text(404)).toContain("找不到這位朋友");
    expect(saveErrorText(new ApiError(503, "x"), "card")).toContain("原本的連結保留不變");
    expect(saveErrorText(new TypeError("network"), "contact")).toContain("填寫內容已保留");
  });
  it("searches names, aliases and addresses; avatar tone depends only on id", () => {
    expect(matchFriend(friend, "小海")).toBe(true);
    expect(matchFriend(friend, "SEA@")).toBe(true);
    expect(matchFriend(friend, "山")).toBe(false);
    expect(toneFor("f1")).toBe(toneFor("f1"));
  });
  it("is its own side-nav page, not part of settings", () => {
    expect(app).toContain('["friends", "筆友名冊", "mail"]');
    expect(app).toContain('{view === "friends" && <FriendsRoster />}');
  });
  it("separates with shadow and space, not borders", () => {
    expect(css).not.toMatch(/border(-top|-bottom|-left|-right)?:\s*[1-9]/);
    expect(css).not.toMatch(/0 -1px 0/);
  });
  it("keeps the search field transparent over the global dark input rule", () => {
    expect(css).toContain('.friends-panel .friend-search input[type="search"] {');
    expect(css).toMatch(/\.friends-panel \.friend-search input\[type="search"\] \{[^}]*background: transparent/);
  });
});
