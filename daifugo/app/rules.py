"""大富豪(Daifugo)規則引擎 — 純函數模組,無 IO、無全域狀態。

TICKET-E 紅線:規則邏輯獨立 + 單元測試必寫。
牌表示:字串
  一般牌:rank+suit,如 "3C" "10D" "JH" "QS" "KC" "AS" "2H"
  Joker:"JO1" "JO2"(最強,可當任意 rank 配組)
  Wonder:"WO1" "WO2"(P5X 原創:壓過任何牌、出後強制清場)
"""
from __future__ import annotations

import random

SUITS = ["C", "D", "H", "S"]  # 梅花/方塊/紅心/黑桃
RANKS = ["3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2"]
# 正常序:3 最小、2 最大;革命時反轉。Joker 恆為最強(常見房規,P5X 同)。
RANK_STRENGTH = {r: i for i, r in enumerate(RANKS)}  # 3→0 ... 2→12
JOKERS = ("JO1", "JO2")
WONDERS = ("WO1", "WO2")

TITLES_4 = ["大富豪", "富豪", "平民", "大貧民"]
TITLES_3 = ["大富豪", "平民", "大貧民"]


def is_joker(card: str) -> bool:
    return card in JOKERS


def is_wonder(card: str) -> bool:
    return card in WONDERS


def card_rank(card: str) -> str | None:
    """一般牌的 rank;Joker/Wonder 回 None。"""
    if is_joker(card) or is_wonder(card):
        return None
    return card[:-1]


def build_deck(include_wonders: bool = True) -> list[str]:
    deck = [r + s for r in RANKS for s in SUITS] + list(JOKERS)
    if include_wonders:
        deck += list(WONDERS)
    return deck


def deal(deck: list[str], num_players: int, rng: random.Random | None = None) -> list[list[str]]:
    """洗牌發完為止(前面的座位可能多一張,正常)。"""
    rng = rng or random.Random()
    cards = deck[:]
    rng.shuffle(cards)
    hands: list[list[str]] = [[] for _ in range(num_players)]
    for i, c in enumerate(cards):
        hands[i % num_players].append(c)
    return hands


def strength(rank: str, revolution: bool) -> int:
    """rank 的比較強度(越大越強)。革命時反轉。Joker/Wonder 不走這裡。"""
    base = RANK_STRENGTH[rank]
    return (len(RANKS) - 1 - base) if revolution else base


JOKER_STRENGTH = len(RANKS)  # 恆強於任何 rank(革命亦然)


def group_rank(cards: list[str]) -> str | None:
    """一組牌的等效 rank:全同 rank(Joker 當萬用配牌)。

    合法組合回 rank 字串;全 Joker 組合回 "JOKER";含 Wonder 或不合法回 None。
    """
    if not cards:
        return None
    if any(is_wonder(c) for c in cards):
        return None  # Wonder 只能單出,由 validate_play 特判
    ranks = {card_rank(c) for c in cards if not is_joker(c)}
    if len(ranks) == 0:
        return "JOKER"  # 全 Joker(1 或 2 張)
    if len(ranks) == 1:
        return ranks.pop()
    return None


def group_strength(cards: list[str], revolution: bool) -> int | None:
    """一組牌的比較強度;不合法回 None。"""
    r = group_rank(cards)
    if r is None:
        return None
    if r == "JOKER":
        return JOKER_STRENGTH
    return strength(r, revolution)


def validate_play(
    hand: list[str],
    cards: list[str],
    table: list[str] | None,
    revolution: bool,
    wonder_enabled: bool = True,
) -> tuple[bool, str]:
    """驗證出牌。table=None 表示自由出(場上乾淨)。回 (ok, 原因)。"""
    if not cards:
        return False, "沒有選牌"
    if len(set(cards)) != len(cards):
        return False, "重複的牌"
    for c in cards:
        if c not in hand:
            return False, "手上沒有這張牌"

    wonder_cards = [c for c in cards if is_wonder(c)]
    if wonder_cards:
        if not wonder_enabled:
            return False, "本局未啟用 Wonder"
        if len(cards) != 1:
            return False, "Wonder 只能單獨出"
        return True, ""  # Wonder 壓過任何牌型,含空場

    gs = group_strength(cards, revolution)
    if gs is None:
        return False, "牌型不合法(要同數字,Joker 可配)"

    if table is None:
        return True, ""

    if any(is_wonder(c) for c in table):
        return False, "Wonder 之後必須清場(不應跟牌)"

    if len(cards) != len(table):
        return False, f"要出 {len(table)} 張"

    ts = group_strength(table, revolution)
    if ts is None:  # 理論上不會發生:場上的牌必然合法
        return True, ""
    if gs <= ts:
        return False, "沒有比場上大"
    return True, ""


def play_effects(cards: list[str], wonder_enabled: bool, eight_cut: bool, revolution_enabled: bool) -> dict:
    """出牌後的特殊效果(純判定,不改狀態)。"""
    effects = {"clear": False, "revolution_toggle": False, "wonder": False}
    if any(is_wonder(c) for c in cards) and wonder_enabled:
        effects["clear"] = True
        effects["wonder"] = True
        return effects
    if eight_cut and any(card_rank(c) == "8" for c in cards):
        effects["clear"] = True
    if revolution_enabled and len(cards) == 4 and group_rank(cards) not in (None, "JOKER"):
        effects["revolution_toggle"] = True
    return effects


def titles_for(num_players: int) -> list[str]:
    return TITLES_4 if num_players >= 4 else TITLES_3


def assign_titles(finish_order: list[int], num_players: int) -> dict[int, str]:
    """finish_order:座位號按出完先後。回 座位→頭銜。"""
    titles = titles_for(num_players)
    return {seat: titles[i] for i, seat in enumerate(finish_order)}


def tribute_exchange(poor_hand: list[str], rich_give: str | None, revolution: bool = False) -> str:
    """上供:大貧民手中最強的一張(Joker > Wonder 不上供 > 一般牌)。

    回應上供的牌;Wonder 不在上供範圍(它是清場牌不是點數牌)。
    rich_give 由大富豪自選,不在此函數職責。
    """
    candidates = [c for c in poor_hand if not is_wonder(c)]
    if not candidates:
        return poor_hand[0]

    def key(c: str) -> int:
        if is_joker(c):
            return JOKER_STRENGTH
        return strength(card_rank(c), revolution)

    return max(candidates, key=key)


def first_leader(hands: list[list[str]]) -> int:
    """首局:持梅花3者先出;梅花3在誰手上誰先。理論上必有(整副發完)。"""
    for seat, hand in enumerate(hands):
        if "3C" in hand:
            return seat
    return 0
