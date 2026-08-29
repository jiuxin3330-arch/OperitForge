"""TICKET-E 規則引擎單元測試(工單必寫清單全覆蓋)。"""
import random
import sys
import unittest

sys.path.insert(0, "/srv/daifugo/app")
import rules  # noqa: E402


class TestCompare(unittest.TestCase):
    """比大小"""

    def test_basic_order(self):
        self.assertLess(rules.strength("3", False), rules.strength("4", False))
        self.assertLess(rules.strength("K", False), rules.strength("A", False))
        self.assertLess(rules.strength("A", False), rules.strength("2", False))

    def test_follow_must_be_bigger(self):
        hand = ["5H", "9C"]
        ok, _ = rules.validate_play(hand, ["9C"], ["8D"], revolution=False)
        self.assertTrue(ok)
        ok, why = rules.validate_play(hand, ["5H"], ["8D"], revolution=False)
        self.assertFalse(ok)
        self.assertIn("沒有比場上大", why)

    def test_equal_rank_not_bigger(self):
        ok, _ = rules.validate_play(["8H"], ["8H"], ["8D"], revolution=False)
        self.assertFalse(ok)

    def test_count_must_match(self):
        hand = ["9C", "9D"]
        ok, why = rules.validate_play(hand, ["9C", "9D"], ["8D"], revolution=False)
        self.assertFalse(ok)
        self.assertIn("1 張", why)


class TestJoker(unittest.TestCase):
    """Joker 配對 + 單張最強"""

    def test_joker_pairs_with_any(self):
        hand = ["9C", "JO1"]
        ok, _ = rules.validate_play(hand, ["9C", "JO1"], ["8D", "8H"], revolution=False)
        self.assertTrue(ok)

    def test_joker_single_beats_two(self):
        ok, _ = rules.validate_play(["JO1"], ["JO1"], ["2S"], revolution=False)
        self.assertTrue(ok)

    def test_two_beats_nothing_after_joker(self):
        ok, _ = rules.validate_play(["2S"], ["2S"], ["JO1"], revolution=False)
        self.assertFalse(ok)

    def test_mixed_ranks_illegal(self):
        ok, why = rules.validate_play(["9C", "8D"], ["9C", "8D"], None, revolution=False)
        self.assertFalse(ok)
        self.assertIn("牌型不合法", why)


class TestRevolution(unittest.TestCase):
    """革命反轉下的比大小"""

    def test_reversed_compare(self):
        # 革命下 3 比 2 強
        self.assertGreater(rules.strength("3", True), rules.strength("2", True))
        ok, _ = rules.validate_play(["3H"], ["3H"], ["5D"], revolution=True)
        self.assertTrue(ok)
        ok, _ = rules.validate_play(["2H"], ["2H"], ["5D"], revolution=True)
        self.assertFalse(ok)

    def test_joker_still_strongest_in_revolution(self):
        ok, _ = rules.validate_play(["JO1"], ["JO1"], ["3S"], revolution=True)
        self.assertTrue(ok)

    def test_four_of_kind_triggers(self):
        fx = rules.play_effects(["9C", "9D", "9H", "9S"], True, True, True)
        self.assertTrue(fx["revolution_toggle"])

    def test_four_with_joker_triggers(self):
        fx = rules.play_effects(["9C", "9D", "9H", "JO1"], True, True, True)
        self.assertTrue(fx["revolution_toggle"])

    def test_disabled_no_trigger(self):
        fx = rules.play_effects(["9C", "9D", "9H", "9S"], True, True, False)
        self.assertFalse(fx["revolution_toggle"])


class TestEightCut(unittest.TestCase):
    """8切清場"""

    def test_single_eight_clears(self):
        fx = rules.play_effects(["8D"], True, True, True)
        self.assertTrue(fx["clear"])

    def test_pair_eight_clears(self):
        fx = rules.play_effects(["8D", "8H"], True, True, True)
        self.assertTrue(fx["clear"])

    def test_eight_cut_disabled(self):
        fx = rules.play_effects(["8D"], True, False, True)
        self.assertFalse(fx["clear"])

    def test_non_eight_no_clear(self):
        fx = rules.play_effects(["9D"], True, True, True)
        self.assertFalse(fx["clear"])


class TestWonder(unittest.TestCase):
    """Wonder 壓場"""

    def test_wonder_beats_anything(self):
        ok, _ = rules.validate_play(["WO1"], ["WO1"], ["JO1"], revolution=False)
        self.assertTrue(ok)
        ok, _ = rules.validate_play(["WO1"], ["WO1"], ["2S", "2H"], revolution=False)
        self.assertTrue(ok)  # 張數不同也壓得過

    def test_wonder_forces_clear(self):
        fx = rules.play_effects(["WO1"], True, True, True)
        self.assertTrue(fx["clear"])
        self.assertTrue(fx["wonder"])

    def test_wonder_must_be_single(self):
        ok, why = rules.validate_play(["WO1", "9C"], ["WO1", "9C"], None, revolution=False)
        self.assertFalse(ok)
        self.assertIn("單獨", why)

    def test_nothing_follows_wonder(self):
        ok, why = rules.validate_play(["JO1"], ["JO1"], ["WO1"], revolution=False)
        self.assertFalse(ok)

    def test_wonder_disabled(self):
        ok, why = rules.validate_play(["WO1"], ["WO1"], None, revolution=False, wonder_enabled=False)
        self.assertFalse(ok)


class TestSpade3Reversal(unittest.TestCase):
    """P5X 黑桃3 反殺單張 Joker"""

    def test_spade3_beats_single_joker(self):
        ok, _ = rules.validate_play(["3S"], ["3S"], ["JO1"], revolution=False)
        self.assertTrue(ok)

    def test_other_threes_do_not(self):
        ok, _ = rules.validate_play(["3H"], ["3H"], ["JO1"], revolution=False)
        self.assertFalse(ok)

    def test_not_against_joker_pair(self):
        ok, _ = rules.validate_play(["3S"], ["3S"], ["JO1", "JO2"], revolution=False)
        self.assertFalse(ok)

    def test_works_in_revolution(self):
        ok, _ = rules.validate_play(["3S"], ["3S"], ["JO2"], revolution=True)
        self.assertTrue(ok)

    def test_spade3_still_weak_normally(self):
        ok, _ = rules.validate_play(["3S"], ["3S"], ["4D"], revolution=False)
        self.assertFalse(ok)

    def test_helper(self):
        self.assertTrue(rules.spade3_reversal(["3S"], ["JO1"]))
        self.assertFalse(rules.spade3_reversal(["3S"], None))
        self.assertFalse(rules.spade3_reversal(["3S", "3H"], ["JO1"]))


class TestPassClear(unittest.TestCase):
    """全 PASS 清場後自由出(引擎面:table=None 時任何合法組可出)"""

    def test_free_lead_any_count(self):
        ok, _ = rules.validate_play(["4C", "4D"], ["4C", "4D"], None, revolution=False)
        self.assertTrue(ok)
        ok, _ = rules.validate_play(["4C"], ["4C"], None, revolution=False)
        self.assertTrue(ok)


class TestTitles(unittest.TestCase):
    """名次判定"""

    def test_four_players(self):
        t = rules.assign_titles([2, 0, 3, 1], 4)
        self.assertEqual(t[2], "大富豪")
        self.assertEqual(t[0], "富豪")
        self.assertEqual(t[3], "平民")
        self.assertEqual(t[1], "大貧民")

    def test_three_players(self):
        t = rules.assign_titles([1, 0, 2], 3)
        self.assertEqual(t[1], "大富豪")
        self.assertEqual(t[0], "平民")
        self.assertEqual(t[2], "大貧民")


class TestTribute(unittest.TestCase):
    """上供下貢交換"""

    def test_gives_strongest(self):
        self.assertEqual(rules.tribute_exchange(["5H", "2D", "KC"], None), "2D")

    def test_joker_is_strongest(self):
        self.assertEqual(rules.tribute_exchange(["2D", "JO1", "KC"], None), "JO1")

    def test_wonder_not_tributed(self):
        self.assertEqual(rules.tribute_exchange(["WO1", "5H", "9C"], None), "9C")

    def test_revolution_reverses(self):
        self.assertEqual(rules.tribute_exchange(["5H", "2D", "3C"], None, revolution=True), "3C")


class TestDeal(unittest.TestCase):
    """發牌完整性 + 首局梅花3"""

    def test_deal_all_cards(self):
        deck = rules.build_deck(include_wonders=True)
        self.assertEqual(len(deck), 56)
        hands = rules.deal(deck, 3, random.Random(42))
        self.assertEqual(sum(len(h) for h in hands), 56)
        self.assertEqual(sorted(len(h) for h in hands), [18, 19, 19])
        # 無重複
        allc = [c for h in hands for c in h]
        self.assertEqual(len(set(allc)), 56)

    def test_first_leader_has_diamond3(self):
        deck = rules.build_deck()
        hands = rules.deal(deck, 4, random.Random(7))
        leader = rules.first_leader(hands)
        self.assertIn("3D", hands[leader])


if __name__ == "__main__":
    unittest.main(verbosity=1)
