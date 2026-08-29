"""大富豪 — 單房間牌局狀態機。伺服器權威:手牌只回給本人。"""
from __future__ import annotations

import json
import random
import secrets
import time
from pathlib import Path

import rules

SCORES_FILE = Path("/srv/daifugo/state/scores.json")
SCORE_BY_PLACE = {0: 3, 1: 2, 2: 1, 3: 0}  # 名次→加分(3人取 0/1/2)
MAX_PLAYERS = 4
MIN_PLAYERS = 3


class GameError(Exception):
    pass


class Player:
    def __init__(self, token: str, name: str, emoji: str, color: str):
        self.token = token
        self.name = name
        self.emoji = emoji
        self.color = color
        self.connected = True
        self.last_seen = time.time()
        self.last_action = ""  # 本輪最後動作:出牌/PASS(顯示用)


class Room:
    def __init__(self):
        self.players: list[Player] = []          # index = 座位
        self.phase = "lobby"                      # lobby / tribute / playing / round_end
        self.settings = {"wonder": True, "eight_cut": True,
                         "revolution": False, "tribute": False}
        self.round_no = 0
        self.hands: list[list[str]] = []
        self.table: list[str] | None = None       # 場上最後一手
        self.table_by: int | None = None          # 最後出牌座位
        self.turn: int | None = None
        self.revolution = False
        self.finished_order: list[int] = []
        self.last_titles: dict[int, str] = {}     # 上局 座位→頭銜
        self.pending_tribute: dict | None = None  # {"poor":, "rich":, "card":}
        self.fx_seq = 0
        self.last_fx: dict | None = None          # {"seq","kind","by"} 前端動畫用
        self.scores = self._load_scores()
        self.log: list[str] = []

    # ---- 持久化(只有累計分,牌局本身不落地)----
    def _load_scores(self) -> dict[str, int]:
        try:
            return json.loads(SCORES_FILE.read_text())
        except Exception:
            return {}

    def _save_scores(self):
        try:
            SCORES_FILE.write_text(json.dumps(self.scores, ensure_ascii=False))
        except OSError:
            pass

    # ---- 進場/重連 ----
    def join(self, name: str, emoji: str, color: str) -> str:
        if self.phase != "lobby":
            raise GameError("牌局進行中,等下一局開始前再進")
        if len(self.players) >= MAX_PLAYERS:
            raise GameError("滿座了(4 人)")
        name = name.strip()[:12]
        if not name:
            raise GameError("要取個名字")
        if any(p.name == name for p in self.players):
            raise GameError("名字被用了")
        token = secrets.token_urlsafe(24)
        self.players.append(Player(token, name, emoji, color))
        self._note(f"{name} 進場")
        return token

    def seat_of(self, token: str) -> int | None:
        for i, p in enumerate(self.players):
            if p.token == token:
                return i
        return None

    def touch(self, token: str, connected: bool):
        seat = self.seat_of(token)
        if seat is not None:
            self.players[seat].connected = connected
            self.players[seat].last_seen = time.time()

    # ---- 開局 ----
    def start(self, token: str, settings: dict | None = None):
        if self.phase not in ("lobby", "round_end"):
            raise GameError("牌局已在進行")
        if self.seat_of(token) != 0:
            raise GameError("只有房主(第一位進場者)能開始")
        if len(self.players) < MIN_PLAYERS:
            raise GameError(f"至少 {MIN_PLAYERS} 人才能開局")
        if settings:
            for k in self.settings:
                if k in settings:
                    self.settings[k] = bool(settings[k])
        self._deal_round()

    def _deal_round(self):
        n = len(self.players)
        self.round_no += 1
        deck = rules.build_deck(include_wonders=self.settings["wonder"])
        self.hands = rules.deal(deck, n, random.Random())
        self.revolution = False
        self.table = None
        self.table_by = None
        for p in self.players:
            p.last_action = ""
        prev_titles = self.last_titles
        self.finished_order = []
        self.pending_tribute = None

        poor_seat = next((s for s, t in prev_titles.items() if t == "大貧民"), None)
        rich_seat = next((s for s, t in prev_titles.items() if t == "大富豪"), None)
        if poor_seat is not None and poor_seat >= n:
            poor_seat = None
        if rich_seat is not None and rich_seat >= n:
            rich_seat = None

        # Wonder:第二局起大貧民固定得一張(另一張維持隨機)
        if self.settings["wonder"] and self.round_no >= 2 and poor_seat is not None:
            holder = next((s for s, h in enumerate(self.hands) if "WO1" in h), None)
            if holder is not None and holder != poor_seat:
                give_back = random.choice(
                    [c for c in self.hands[poor_seat] if not rules.is_wonder(c)])
                self.hands[holder].remove("WO1")
                self.hands[holder].append(give_back)
                self.hands[poor_seat].remove(give_back)
                self.hands[poor_seat].append("WO1")

        # 上供下貢:大貧民自動獻最大牌,等大富豪回贈
        if (self.settings["tribute"] and self.round_no >= 2
                and poor_seat is not None and rich_seat is not None):
            card = rules.tribute_exchange(self.hands[poor_seat], None)
            self.hands[poor_seat].remove(card)
            self.hands[rich_seat].append(card)
            self.pending_tribute = {"poor": poor_seat, "rich": rich_seat, "card": card}
            self.phase = "tribute"
            self.turn = rich_seat
            self._note(f"{self.players[poor_seat].name} 上供,等 {self.players[rich_seat].name} 回贈")
            return

        self._begin_play(poor_seat)

    def _begin_play(self, poor_seat: int | None):
        self.phase = "playing"
        if self.round_no == 1 or poor_seat is None:
            self.turn = rules.first_leader(self.hands)
        else:
            self.turn = poor_seat  # 第二局起大貧民先出
        self._note(f"第 {self.round_no} 局開始,{self.players[self.turn].name} 先出")

    def tribute_return(self, token: str, card: str):
        if self.phase != "tribute" or not self.pending_tribute:
            raise GameError("現在不是回贈階段")
        rich = self.pending_tribute["rich"]
        if self.seat_of(token) != rich:
            raise GameError("要由大富豪回贈")
        if card not in self.hands[rich]:
            raise GameError("手上沒有這張牌")
        poor = self.pending_tribute["poor"]
        self.hands[rich].remove(card)
        self.hands[poor].append(card)
        self._note(f"{self.players[rich].name} 回贈一張")
        self.pending_tribute = None
        self._begin_play(poor)

    # ---- 出牌 ----
    def _active_seats(self) -> list[int]:
        return [s for s in range(len(self.players))
                if s not in self.finished_order]

    def _next_active(self, seat: int) -> int:
        n = len(self.players)
        s = (seat + 1) % n
        while s in self.finished_order:
            s = (s + 1) % n
        return s

    def play(self, token: str, cards: list[str]):
        seat = self._require_turn(token)
        ok, why = rules.validate_play(
            self.hands[seat], cards, self.table, self.revolution,
            wonder_enabled=self.settings["wonder"])
        if not ok:
            raise GameError(why)
        fx = rules.play_effects(
            cards, self.settings["wonder"], self.settings["eight_cut"],
            self.settings["revolution"])
        if rules.spade3_reversal(cards, self.table):
            fx["clear"] = True
            fx["spade3"] = True
        for c in cards:
            self.hands[seat].remove(c)
        if fx["revolution_toggle"]:
            self.revolution = not self.revolution
            self._note("革命!大小反轉")
            self._push_fx("revolution", seat)
        if fx["wonder"]:
            self._push_fx("wonder", seat)
        elif fx.get("spade3"):
            self._push_fx("spade3", seat)
            self._note("黑桃3 反殺 Joker!")
        elif fx["clear"]:
            self._push_fx("eight_cut", seat)
        elif any(rules.is_joker(c) for c in cards):
            self._push_fx("joker", seat)
        label = "Wonder!" if fx["wonder"] else "+".join(cards)
        self._note(f"{self.players[seat].name} 出 {label}")
        self.players[seat].last_action = "wonder" if fx["wonder"] else f"出 {len(cards)} 張"

        finished_now = not self.hands[seat]
        if finished_now:
            self.finished_order.append(seat)
            self._note(f"{self.players[seat].name} 出完了!")

        if len(self._active_seats()) <= 1:
            self._end_round()
            return

        if fx["clear"]:
            self.table = None
            self.table_by = None
            self.turn = seat if not finished_now else self._next_active(seat)
        else:
            self.table = cards
            self.table_by = seat
            self.turn = self._next_active(seat)

    def pass_turn(self, token: str):
        seat = self._require_turn(token)
        if self.table is None:
            raise GameError("自由出牌時不能 PASS")
        self._note(f"{self.players[seat].name} PASS")
        self.players[seat].last_action = "PASS"
        nxt = self._next_active(seat)
        # 繞回最後出牌者(或其已出完)=其他人全沒壓 → 清場自由出
        if nxt == self.table_by:
            self.table = None
            self.table_by = None
            self.turn = nxt
            self._note("全員 PASS,清場")
            self._push_fx("all_pass", seat)
        elif self.table_by in self.finished_order and self._passes_back_past(seat):
            self.table = None
            self.table_by = None
            self.turn = nxt
            self._note("全員 PASS,清場")
            self._push_fx("all_pass", seat)
        else:
            self.turn = nxt

    def _passes_back_past(self, seat: int) -> bool:
        """最後出牌者已出完:輪轉一圈回到其下家即視為全 PASS。"""
        return self._next_active(seat) == self._next_active(self.table_by)

    def _require_turn(self, token: str) -> int:
        if self.phase != "playing":
            raise GameError("牌局不在進行中")
        seat = self.seat_of(token)
        if seat is None:
            raise GameError("你不在這桌")
        if seat != self.turn:
            raise GameError("還沒輪到你")
        return seat

    # ---- 局末 ----
    def _end_round(self):
        remaining = self._active_seats()
        if remaining:
            self.finished_order.append(remaining[0])
        n = len(self.players)
        self.last_titles = rules.assign_titles(self.finished_order, n)
        places = {seat: i for i, seat in enumerate(self.finished_order)}
        for seat, place in places.items():
            name = self.players[seat].name
            # 4 人:3/2/1/0;3 人:3/1/0(大富豪/平民/大貧民)
            pts = SCORE_BY_PLACE[place] if n >= 4 else {0: 3, 1: 1, 2: 0}[place]
            self.scores[name] = self.scores.get(name, 0) + pts
        self._save_scores()
        self.phase = "round_end"
        self.turn = None
        title_str = " / ".join(
            f"{self.players[s].name}={t}" for s, t in self.last_titles.items())
        self._note(f"本局結束:{title_str}")

    # ---- 狀態輸出(個人化:只給自己手牌)----
    def state_for(self, token: str | None) -> dict:
        seat = self.seat_of(token) if token else None
        return {
            "phase": self.phase,
            "round": self.round_no,
            "settings": self.settings,
            "revolution": self.revolution,
            "players": [
                {"seat": i, "name": p.name, "emoji": p.emoji, "color": p.color,
                 "connected": p.connected,
                 "cards_left": len(self.hands[i]) if i < len(self.hands) else 0,
                 "finished": i in self.finished_order,
                 "title": self.last_titles.get(i, ""),
                 "last_action": p.last_action,
                 "score": self.scores.get(p.name, 0)}
                for i, p in enumerate(self.players)
            ],
            "table": self.table,
            "table_by": self.table_by,
            "turn": self.turn,
            "fx": self.last_fx,
            "you": {
                "seat": seat,
                "hand": sorted(
                    self.hands[seat],
                    key=lambda c: (rules.JOKER_STRENGTH + 1) if rules.is_wonder(c)
                    else rules.JOKER_STRENGTH if rules.is_joker(c)
                    else rules.strength(rules.card_rank(c), self.revolution),
                ) if seat is not None and seat < len(self.hands) else [],
                "is_host": seat == 0,
            } if seat is not None else None,
            "tribute": (
                {"rich": self.pending_tribute["rich"],
                 "poor": self.pending_tribute["poor"]}
                if self.pending_tribute else None),
            "log": self.log[-12:],
        }

    def _push_fx(self, kind: str, by: int):
        self.fx_seq += 1
        self.last_fx = {"seq": self.fx_seq, "kind": kind, "by": by}

    def _note(self, msg: str):
        self.log.append(msg)
        if len(self.log) > 60:
            self.log = self.log[-60:]
