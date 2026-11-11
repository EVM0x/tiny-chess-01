# tiny-chess-01 — a chess engine in 4,096 bytes

`main.py` is a self-contained chess engine: 4,043 bytes, one file, standard library
only, no model calls. It reads nothing but `MAKEFUN_ENV_URL` and its own bytes.

## How it fits

`main.py` is an lzma payload with its unpacker. The engine source is compressed to
3,184 bytes, base85-encoded to 4,043 bytes total including the unpacker line:

```python
import lzma,base64;exec(lzma.decompress(base64.b85decode(b'...')))
```

## The engine

- **Board**: 0x88 squares, 128-entry array, pieces 1..6 white / 9..14 black.
- **Move encoding**: 16 bits — from(6) to(6) promotion(4).
- **Zobrist hashing**: seeded `Random(0x5EED)`, so it is identical on every run;
  castling rights, en passant file and side to move are hashed too.
- **Move generation**: pseudo-legal, then filtered for king safety. The filter is
  skipped when a node has more than 8 moves, where mate and stalemate cannot occur.
- **Search**: iterative deepening PVS, transposition table with exact/lower/upper
  bounds, null-move pruning with verification, late move reductions, killer moves
  and history heuristic, quiescence search over captures.
- **Evaluation**: material, piece-square tables (midgame and endgame king tables
  blended by phase), bishop pair, tempo.
- **Anti-repetition**: the root skips moves that return to a position already seen
  in the game, which is what lets it convert won endgames instead of shuffling.
- **Determinism**: every decision comes from the position, the game's moves and the
  trial seed. No wall clock is read, so the replay is byte-identical.
- **Budget**: 20,000 nodes a move, roughly 1.5 s on one CPU, well under the 10 s
  move limit and the 3,600 s trial budget.

## Bugs found and fixed while tuning

1. Castling Zobrist keys were computed after the rook had moved, so every castling
   move poisoned the transposition table.
2. The node budget aborted the search by raising an exception, which left the board
   half-unmade; it is a flag now.
3. The transposition table's bound test was inverted, which cut off on stale bounds.
4. Move generation was pseudo-legal only, so mate and stalemate were never detected
   and the engine stalemated won endgames; legality filtering fixed the conversion.

MIT licensed.
