import io

CSS = "/srv/chatnest-next/frontend/src/styles.css"
SW = "/srv/chatnest-next/frontend/public/sw.js"

def rep(text, old, new, label):
    assert text.count(old) == 1, f"FAIL {label}: count={text.count(old)}"
    return text.replace(old, new)

c = io.open(CSS, encoding="utf-8").read()

# 1) .nest-btn 家族:奶油 -> 米白(糯糯 S4 定案「全部米白」,駁回/取消跟著改)
c = rep(c,
"""  color: var(--nest-ink-on-cream);
  background: var(--nest-archive-cream);
  cursor: pointer;
  box-shadow: var(--nest-raise-sm);""",
"""  color: var(--nest-text);
  background: var(--nest-bg);
  cursor: pointer;
  box-shadow: var(--nest-raise-sm);""",
"btn-mibai")

# 2) .nest-back 新擬態化(米白定案,去框線)
c = rep(c,
""".nest-back {
  width: 32px; height: 32px;
  display: grid;
  place-items: center;
  background: var(--nest-surface-strong);
  border: 1px solid var(--nest-line);
  border-radius: 50%;
  color: var(--nest-text);
  cursor: pointer;
  padding: 0;
}
.nest-back:hover, .nest-back:focus-visible {
  outline: none;
  background: var(--nest-surface);
}""",
""".nest-back {
  width: 34px; height: 34px;
  display: grid;
  place-items: center;
  background: var(--nest-bg);
  border: 0;
  border-radius: 50%;
  color: var(--nest-text);
  cursor: pointer;
  padding: 0;
  box-shadow: var(--nest-raise-sm);
  transition: transform 0.15s cubic-bezier(0.23, 1, 0.32, 1), box-shadow 0.15s ease;
}
.nest-back:hover, .nest-back:focus-visible {
  outline: none;
}
.nest-back:active {
  transform: scale(0.94);
  box-shadow: var(--nest-press);
}""",
"back-neu")

# 3) .nest-vol 新擬態化(米白定案,去框線)
c = rep(c,
""".nest-vol {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px 14px;
  background: var(--nest-surface);
  border: 1px solid var(--nest-line);
  border-radius: 12px;
  text-align: left;
  cursor: pointer;
  color: var(--nest-text);
  font: inherit;
}
.nest-vol:hover, .nest-vol:focus-visible { outline: none; background: var(--nest-ticket-hi); }""",
""".nest-vol {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px 14px;
  background: var(--nest-bg);
  border: 0;
  border-radius: 12px;
  text-align: left;
  cursor: pointer;
  color: var(--nest-text);
  font: inherit;
  box-shadow: var(--nest-raise-sm);
  transition: transform 0.13s cubic-bezier(0.23, 1, 0.32, 1), box-shadow 0.13s ease;
}
.nest-vol:hover, .nest-vol:focus-visible { outline: none; }
.nest-vol:active {
  transform: scale(0.98);
  box-shadow: var(--nest-press);
}""",
"vol-neu")

# 4) 票券卡:奶油 -> 筆記紙色(案B 定案)
c = rep(c,
""".nest-proposal {
  position: relative;
  background: var(--nest-archive-cream);""",
""".nest-proposal {
  position: relative;
  background: var(--nest-paper-note);""",
"proposal-note")

# 5) 選頻率 sheet 開啟動效(打樣定稿:scrim 淡入+sheet 上滑,抽屜曲線)
S4_BLOCK = """
/* ==== S4:選頻率 sheet 開啟動效(打樣 s4-proofing-v2 定稿) ================ */
@keyframes nest-scrim-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes nest-sheet-up { from { transform: translateY(26px); } to { transform: translateY(0); } }
.nest-modal-scrim { animation: nest-scrim-in 0.22s ease both; }
.nest-modal { animation: nest-sheet-up 0.32s cubic-bezier(0.32, 0.72, 0, 1) both; }
html[data-reduced-motion="true"] .nest-modal-scrim,
html[data-reduced-motion="true"] .nest-modal { animation: none; }
"""
assert "nest-sheet-up" not in c, "FAIL s4-append: already present"
c = c.rstrip("\n") + "\n" + S4_BLOCK
io.open(CSS, "w", encoding="utf-8").write(c)

s = io.open(SW, encoding="utf-8").read()
old = "chatnest-next-shell-v152"
assert s.count(old) >= 1, "sw marker missing"
io.open(SW, "w", encoding="utf-8").write(s.replace(old, "chatnest-next-shell-v153"))

print("s4 patch ok, sw v152 -> v153")
