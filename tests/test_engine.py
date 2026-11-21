"""Tests for the packed engine.

`main.py` is an lzma payload plus its unpacker, and its module body ends in
`while 1:` talking to the make.fun server — so the engine has never been
exercised by anything except live games. These tests unpack the payload the same
way the file does, stop at the network loop, and check the engine half directly.

The reference for move generation is `python-chess`, a well-tested implementation.
Perft is the standard test for a chess engine: it counts leaf nodes of the legal
move tree, so any error in castling rights, en passant, promotion, pins or check
detection shows up as a wrong count. The classic six positions cover exactly
those cases.

An import guard was measured and rejected: `while"__main__"==__name__:` with a
lazy `MAKEFUN_ENV_URL` rebuilds the payload to 4115-4127 bytes, over the 4,096 the
repository promises. `test_the_file_stays_within_its_budget` protects that
promise instead.

Run: python3 -m unittest discover -s tests -v
"""

import base64
import hashlib
import lzma
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAIN = os.path.join(ROOT, "main.py")
BUDGET = 4096

try:
    import chess
except ImportError:  # pragma: no cover
    chess = None

PAYLOAD = re.compile(rb"b85decode\(b'([^']+)'\)")


def read_main():
    with open(MAIN, "rb") as fh:
        return fh.read()


def unpack():
    """The engine source, without the network loop at the end of the module."""
    raw = read_main()
    match = PAYLOAD.search(raw)
    if not match:
        raise AssertionError("main.py does not carry a b85 lzma payload")
    source = lzma.decompress(base64.b85decode(match.group(1))).decode("utf-8")
    cut = source.find("\nwhile 1:")
    if cut < 0:
        raise AssertionError("the module body no longer ends in a `while 1:` loop")
    return source[:cut] + "\n"


def engine():
    """The unpacked source, executed in its own namespace."""
    # The engine reads this at line four; it is only used by the network loop
    # that unpack() cuts off, but the read happens before the cut.
    os.environ.setdefault("MAKEFUN_ENV_URL", "http://127.0.0.1:9/")
    ns = {"__name__": "engine"}
    exec(compile(unpack(), "engine", "exec"), ns)
    return ns


ENGINE = engine()
Po = ENGINE["Po"]
uc = ENGINE["uc"]
u1 = ENGINE["u1"]
u2 = ENGINE["u2"]

STARTPOS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
POS3 = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
POS4 = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"
POS5 = "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8"
POS6 = "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P3/2NP1N2/PPP1QPPP/R4RK1 w - - 0 10"


def perft(position, depth):
    if depth == 0:
        return 1
    nodes = 0
    for move in position.L():
        undo = position.mo(move)
        nodes += perft(position, depth - 1)
        position.un(move, undo)
    return nodes


def reference_perft(board, depth):
    if depth == 0:
        return 1
    nodes = 0
    for move in board.legal_moves:
        board.push(move)
        nodes += reference_perft(board, depth - 1)
        board.pop()
    return nodes


# ---------------------------------------------------------------------------
# the artifact itself
# ---------------------------------------------------------------------------

class ArtifactTest(unittest.TestCase):
    def test_the_file_stays_within_its_budget(self):
        size = len(read_main())
        self.assertLessEqual(size, BUDGET, "main.py is %d bytes, over the %d budget" % (size, BUDGET))

    def test_the_unpacker_is_the_whole_file(self):
        raw = read_main()
        self.assertTrue(raw.startswith(b"import lzma,base64;exec("), raw[:40])
        self.assertEqual(raw.count(b"\n"), 1, "the payload must stay on one line")

    def test_the_payload_unpacks_to_importable_python(self):
        source = unpack()
        compile(source, "engine", "exec")
        self.assertIn("class Po", source)

    def test_unpacking_is_deterministic(self):
        first = hashlib.sha256(unpack().encode()).hexdigest()
        second = hashlib.sha256(unpack().encode()).hexdigest()
        self.assertEqual(first, second)

    def test_the_module_body_still_ends_in_a_network_loop(self):
        # The loop is the reason the engine half is cut off above it. If the loop
        # ever changes shape, unpack() stops finding it and raises, rather than
        # silently testing nothing.
        source = lzma.decompress(base64.b85decode(PAYLOAD.search(read_main()).group(1))).decode()
        self.assertIn("\nwhile 1:", source)
        self.assertTrue(source.rstrip().endswith('w=pt("/move",{"game":w["game"],"move":m})'))


# ---------------------------------------------------------------------------
# board, move encoding
# ---------------------------------------------------------------------------

class PositionTest(unittest.TestCase):
    def test_a_square_round_trips_through_its_name(self):
        for square in range(128):
            if square & 0x88:
                continue
            self.assertEqual(u2(u1(square)), square, u1(square))

    def test_square_names_are_the_usual_ones(self):
        self.assertEqual(u1(0), "a1")
        self.assertEqual(u1(7), "h1")
        self.assertEqual(u1(112), "a8")
        self.assertEqual(u1(119), "h8")
        self.assertEqual(u1(20), "e2")
        self.assertEqual(u1(36), "e3")
        self.assertEqual(u1(52), "e4")

    def test_the_start_position_is_read_out_of_its_fen(self):
        p = Po(STARTPOS)
        self.assertEqual(p.y, 0)
        self.assertEqual(p.cr, 15)
        self.assertEqual(p.ep, -1)
        self.assertEqual(p.g, [4, 116])
        self.assertEqual(len(p.oc), 32)
        self.assertEqual(p.b[0], 4)    # a1 rook
        self.assertEqual(p.b[4], 6)    # e1 king
        self.assertEqual(p.b[20], 1)   # e2 pawn
        self.assertEqual(p.b[100], 9)  # e7 pawn
        self.assertEqual(p.b[116], 14)  # e8 black king

    def test_the_castling_field_is_read_as_four_bits(self):
        self.assertEqual(Po(STARTPOS).cr, 15)
        self.assertEqual(Po(STARTPOS.replace("KQkq", "Kq")).cr, 1 | 8)
        self.assertEqual(Po(STARTPOS.replace("KQkq", "-")).cr, 0)

    def test_an_en_passant_square_is_read_from_the_fen(self):
        p = Po("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1")
        self.assertEqual(p.ep, u2("e3"))

    def test_a_move_encodes_from_to_and_promotion(self):
        move = 20 << 12 | 52 << 4
        self.assertEqual(uc(move), "e2e4")
        promoted = 100 << 12 | 116 << 4 | 5
        self.assertEqual(uc(promoted), "e7e8q")

    def test_the_hash_is_the_same_for_the_same_position(self):
        self.assertEqual(Po(KIWIPETE).h, Po(KIWIPETE).h)

    def test_the_hash_differs_when_the_side_to_move_differs(self):
        self.assertNotEqual(Po(STARTPOS).h, Po(STARTPOS.replace(" w ", " b ")).h)

    def test_the_hash_differs_when_the_castling_rights_differ(self):
        self.assertNotEqual(Po(STARTPOS).h, Po(STARTPOS.replace("KQkq", "KQk")).h)

    def test_the_hash_differs_when_the_en_passant_file_differs(self):
        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq %s 0 1"
        self.assertNotEqual(Po(fen % "e3").h, Po(fen % "d3").h)


# ---------------------------------------------------------------------------
# move generation against python-chess
# ---------------------------------------------------------------------------

class LegalMoveTest(unittest.TestCase):
    def test_the_start_position_has_twenty_moves(self):
        self.assertEqual(len(Po(STARTPOS).L()), 20)

    def test_a_position_with_no_legal_move_has_none(self):
        # Kh8 is mated by Qg7, supported by Kf7: g8 and h7 are both covered.
        fen = "7k/5KQ1/8/8/8/8/8/8 b - - 0 1"
        self.assertEqual(Po(fen).L(), [])
        if chess is not None:
            self.assertTrue(chess.Board(fen).is_checkmate())

    def test_a_promotion_offers_four_pieces(self):
        p = Po("8/4P3/8/8/8/8/8/K6k w - - 0 1")
        promos = sorted(uc(m) for m in p.L() if m & 15)
        self.assertEqual(promos, ["e7e8b", "e7e8n", "e7e8q", "e7e8r"])

    def test_castling_is_generated_only_when_the_rights_allow_it(self):
        self.assertIn("e1g1", [uc(m) for m in Po(KIWIPETE).L()])
        self.assertIn("e1c1", [uc(m) for m in Po(KIWIPETE).L()])
        without = KIWIPETE.replace("KQkq", "-")
        moves = [uc(m) for m in Po(without).L()]
        self.assertNotIn("e1g1", moves)
        self.assertNotIn("e1c1", moves)

    def test_castling_through_an_attacked_square_is_not_generated(self):
        # A rook on f8 covers f1, so white may not castle short.
        p = Po("4kr2/8/8/8/8/8/8/R3K2R w KQ - 0 1")
        moves = [uc(m) for m in p.L()]
        self.assertNotIn("e1g1", moves)
        self.assertIn("e1c1", moves)

    def test_castling_is_not_generated_out_of_check(self):
        # A rook on e8 checks the white king.
        p = Po("4r2k/8/8/8/8/8/8/R3K2R w KQ - 0 1")
        moves = [uc(m) for m in p.L()]
        self.assertNotIn("e1g1", moves)
        self.assertNotIn("e1c1", moves)

    def test_en_passant_is_generated_and_removes_the_right_pawn(self):
        p = Po("8/8/8/3pP3/8/8/8/K6k w - d6 0 1")
        moves = [uc(m) for m in p.L()]
        self.assertIn("e5d6", moves)
        move = [m for m in p.L() if uc(m) == "e5d6"][0]
        undo = p.mo(move)
        self.assertEqual(p.b[u2("d5")], 0, "the captured pawn must leave the board")
        self.assertEqual(p.b[u2("d6")], 1, "the capturing pawn must land on d6")
        p.un(move, undo)
        self.assertEqual(p.b[u2("d5")], 9, "unmake must put the black pawn back")
        self.assertEqual(p.b[u2("e5")], 1)

    def test_a_pinned_piece_may_not_leave_the_line(self):
        # The knight on e2 is pinned by the rook on e8.
        p = Po("4r2k/8/8/8/8/8/4N3/4K3 w - - 0 1")
        moves = [uc(m) for m in p.L()]
        self.assertFalse([m for m in moves if m.startswith("e2")], moves)

    def test_unmake_restores_the_position_exactly(self):
        p = Po(KIWIPETE)
        before = (list(p.b), p.cr, p.ep, list(p.g), p.h, p.y, sorted(p.oc))
        for move in p.L():
            undo = p.mo(move)
            p.un(move, undo)
            after = (list(p.b), p.cr, p.ep, list(p.g), p.h, p.y, sorted(p.oc))
            self.assertEqual(after, before, uc(move))

    def test_the_engine_and_python_chess_agree_on_every_legal_move(self):
        if chess is None:
            self.skipTest("python-chess is not installed")
        for fen in (STARTPOS, KIWIPETE, POS3, POS4, POS5, POS6):
            mine = sorted(uc(m) for m in Po(fen).L())
            theirs = sorted(m.uci() for m in chess.Board(fen).legal_moves)
            self.assertEqual(mine, theirs, fen)


# ---------------------------------------------------------------------------
# perft: the leaf-node counts of the legal move tree
# ---------------------------------------------------------------------------

@unittest.skipIf(chess is None, "python-chess is not installed")
class PerftTest(unittest.TestCase):
    SHALLOW = (STARTPOS, KIWIPETE, POS3, POS4, POS5, POS6)

    def test_depth_one_matches_the_reference_on_every_position(self):
        for fen in self.SHALLOW:
            self.assertEqual(perft(Po(fen), 1), reference_perft(chess.Board(fen), 1), fen)

    def test_depth_two_matches_the_reference_on_every_position(self):
        for fen in self.SHALLOW:
            self.assertEqual(perft(Po(fen), 2), reference_perft(chess.Board(fen), 2), fen)

    def test_the_start_position_matches_the_published_counts(self):
        p = Po(STARTPOS)
        self.assertEqual(perft(p, 1), 20)
        self.assertEqual(perft(p, 2), 400)
        self.assertEqual(perft(p, 3), 8902)

    def test_kiwipete_matches_the_published_counts(self):
        p = Po(KIWIPETE)
        self.assertEqual(perft(p, 1), 48)
        self.assertEqual(perft(p, 2), 2039)
        self.assertEqual(perft(p, 3), 97862)

    def test_the_endgame_position_matches_the_published_counts(self):
        p = Po(POS3)
        self.assertEqual(perft(p, 1), 14)
        self.assertEqual(perft(p, 2), 191)
        self.assertEqual(perft(p, 3), 2812)

    def test_the_promotion_position_matches_the_published_counts(self):
        p = Po(POS4)
        self.assertEqual(perft(p, 1), 6)
        self.assertEqual(perft(p, 2), 264)
        self.assertEqual(perft(p, 3), 9467)

    def test_the_check_heavy_position_matches_the_published_counts(self):
        p = Po(POS5)
        self.assertEqual(perft(p, 1), 44)
        self.assertEqual(perft(p, 2), 1486)
        self.assertEqual(perft(p, 3), 62379)

    def test_perft_does_not_disturb_the_position(self):
        p = Po(KIWIPETE)
        before = (list(p.b), p.cr, p.ep, list(p.g), p.h, p.y, sorted(p.oc))
        perft(p, 2)
        after = (list(p.b), p.cr, p.ep, list(p.g), p.h, p.y, sorted(p.oc))
        self.assertEqual(after, before)


# ---------------------------------------------------------------------------
# the search finds a mate and a legal move
# ---------------------------------------------------------------------------

class SearchTest(unittest.TestCase):
    def test_the_search_finds_a_mate_in_one(self):
        # Ra8 is mate: the black king on g8 has no square off the eighth rank.
        fen = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
        p = Po(fen)
        ENGINE["ND"][0] = 0
        ENGINE["LM"][0] = 60000
        ENGINE["AB"][0] = 0
        ENGINE["TT"][:] = [None] * 65536
        move = ENGINE["BM"](p, 60000)
        self.assertEqual(uc(move), "a1a8")

    def test_the_chosen_move_is_always_legal(self):
        for fen in (STARTPOS, KIWIPETE, POS3, POS5):
            p = Po(fen)
            ENGINE["ND"][0] = 0
            ENGINE["LM"][0] = 3000
            ENGINE["AB"][0] = 0
            ENGINE["TT"][:] = [None] * 65536
            move = ENGINE["BM"](p, 3000)
            self.assertIn(uc(move), [uc(m) for m in p.L()], fen)

    def test_the_same_position_gets_the_same_move_twice(self):
        # Zobrist keys come from Random(0x5EED), so the search must be repeatable.
        moves = []
        for _ in range(2):
            p = Po(KIWIPETE)
            ENGINE["ND"][0] = 0
            ENGINE["LM"][0] = 4000
            ENGINE["AB"][0] = 0
            ENGINE["TT"][:] = [None] * 65536
            ENGINE["GH"].clear()
            ENGINE["PS"].clear()
            moves.append(uc(ENGINE["BM"](p, 4000)))
        self.assertEqual(moves[0], moves[1])


if __name__ == "__main__":
    unittest.main()
