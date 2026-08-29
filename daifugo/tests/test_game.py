"""狀態機整合測試:模擬完整牌局不卡死、名次與計分正確。"""
import random
import sys
import unittest

sys.path.insert(0, "/srv/daifugo/app")
import game  # noqa: E402
import rules  # noqa: E402


def legal_moves(room, seat):
    """窮舉該座位所有合法出牌(單張與同 rank 組)。"""
    hand = room.hands[seat]
    moves = []
    # 單張
    for c in hand:
        ok, _ = rules.validate_play(hand, [c], room.table, room.revolution,
                                    room.settings["wonder"])
        if ok:
            moves.append([c])
    # 同 rank 組(含 Joker 補)
    by_rank = {}
    jokers = [c for c in hand if rules.is_joker(c)]
    for c in hand:
        r = rules.card_rank(c)
        if r:
            by_rank.setdefault(r, []).append(c)
    for r, cs in by_rank.items():
        for size in (2, 3, 4):
            pool = cs + jokers
            if len(pool) >= size and len(cs) >= 1:
                combo = (cs + jokers)[:size]
                ok, _ = rules.validate_play(hand, combo, room.table,
                                            room.revolution, room.settings["wonder"])
                if ok:
                    moves.append(combo)
    return moves


class TestFullRound(unittest.TestCase):
    def _play_out(self, n_players, seed, settings=None):
        random.seed(seed)
        game.SCORES_FILE = game.Path("/tmp/daifugo-test-scores.json")
        game.SCORES_FILE.unlink(missing_ok=True)
        room = game.Room()
        tokens = [room.join(f"p{i}", "🐭", "#fff") for i in range(n_players)]
        room.start(tokens[0], settings or {})
        guard = 0
        while room.phase == "playing":
            guard += 1
            self.assertLess(guard, 2000, "牌局卡死(超過 2000 步)")
            seat = room.turn
            moves = legal_moves(room, seat)
            if moves and (room.table is None or random.random() < 0.8):
                room.play(tokens[seat], random.choice(moves))
            elif room.table is not None:
                room.pass_turn(tokens[seat])
            else:
                self.assertTrue(moves, "自由出卻無合法牌?")
        return room

    def test_three_player_rounds(self):
        for seed in range(8):
            room = self._play_out(3, seed)
            self.assertEqual(room.phase, "round_end")
            self.assertEqual(len(room.finished_order), 3)
            self.assertEqual(set(room.last_titles.values()),
                             {"大富豪", "平民", "大貧民"})

    def test_four_player_rounds(self):
        for seed in range(8):
            room = self._play_out(4, seed)
            self.assertEqual(len(room.finished_order), 4)
            self.assertEqual(set(room.last_titles.values()),
                             {"大富豪", "富豪", "平民", "大貧民"})

    def test_scores_accumulate(self):
        room = self._play_out(3, 99)
        self.assertEqual(sum(room.scores.values()), 4)  # 3+1+0

    def test_second_round_poor_gets_wonder_and_leads(self):
        random.seed(5)
        game.SCORES_FILE = game.Path("/tmp/daifugo-test-scores.json")
        game.SCORES_FILE.unlink(missing_ok=True)
        room = game.Room()
        tokens = [room.join(f"p{i}", "🐭", "#fff") for i in range(3)]
        room.start(tokens[0], {})
        # 快速打完一局
        guard = 0
        while room.phase == "playing":
            guard += 1
            assert guard < 2000
            seat = room.turn
            moves = legal_moves(room, seat)
            if moves:
                room.play(tokens[seat], moves[0])
            else:
                room.pass_turn(tokens[seat])
        poor = next(s for s, t in room.last_titles.items() if t == "大貧民")
        room.start(tokens[0], {})
        self.assertEqual(room.turn, poor)          # 大貧民先出
        self.assertIn("WO1", room.hands[poor])     # 固定得一張 Wonder

    def test_tribute_flow(self):
        random.seed(11)
        game.SCORES_FILE = game.Path("/tmp/daifugo-test-scores.json")
        game.SCORES_FILE.unlink(missing_ok=True)
        room = game.Room()
        tokens = [room.join(f"p{i}", "🐭", "#fff") for i in range(3)]
        room.start(tokens[0], {"tribute": True})
        guard = 0
        while room.phase == "playing":
            guard += 1
            assert guard < 2000
            seat = room.turn
            moves = legal_moves(room, seat)
            if moves:
                room.play(tokens[seat], moves[0])
            else:
                room.pass_turn(tokens[seat])
        room.start(tokens[0], {})
        self.assertEqual(room.phase, "tribute")
        rich = room.pending_tribute["rich"]
        card = room.hands[rich][0]
        room.tribute_return(tokens[rich], card)
        self.assertEqual(room.phase, "playing")


if __name__ == "__main__":
    unittest.main(verbosity=1)
