"""
Pure functions for Tic Tac Toe game logic — board lives as a 9-char string.

This module has NO Django imports so it's trivially unit-testable and
reusable from both REST views and WebSocket consumers.
"""

from __future__ import annotations

import random
from typing import Optional

WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # cols
    (0, 4, 8), (2, 4, 6),             # diagonals
]


def check_winner(board: str) -> Optional[str]:
    """Return 'X', 'O', 'draw', or None if game continues."""
    for a, b, c in WIN_LINES:
        if board[a] != "." and board[a] == board[b] == board[c]:
            return board[a]
    if "." not in board:
        return "draw"
    return None


def apply_move(board: str, position: int, mark: str) -> str:
    """Return a new board string with `mark` placed at `position`."""
    if not (0 <= position < 9):
        raise ValueError("position must be 0..8")
    if board[position] != ".":
        raise ValueError("cell is already occupied")
    if mark not in ("X", "O"):
        raise ValueError("mark must be X or O")
    return board[:position] + mark + board[position + 1:]


def available_positions(board: str) -> list[int]:
    return [i for i, c in enumerate(board) if c == "."]


# --- AI strategies ---

def ai_easy(board: str, ai_mark: str) -> int:
    """Pure random — beginner-friendly opponent."""
    return random.choice(available_positions(board))


def ai_medium(board: str, ai_mark: str) -> int:
    """Win if you can, block if you must, else random.

    This is the classic 'one-ply lookahead' bot: it's not perfect, but it
    feels intelligent because it never misses an immediate win or block.
    """
    opponent = "O" if ai_mark == "X" else "X"

    # 1. Take a winning move.
    for pos in available_positions(board):
        if check_winner(apply_move(board, pos, ai_mark)) == ai_mark:
            return pos

    # 2. Block an opponent winning move.
    for pos in available_positions(board):
        if check_winner(apply_move(board, pos, opponent)) == opponent:
            return pos

    # 3. Prefer center, then corners, then edges.
    for pos in (4, 0, 2, 6, 8, 1, 3, 5, 7):
        if board[pos] == ".":
            return pos
    raise RuntimeError("no available moves")  # unreachable


def ai_hard(board: str, ai_mark: str) -> int:
    """Minimax — unbeatable. Best result vs perfect play is a draw."""
    opponent = "O" if ai_mark == "X" else "X"

    def score(b: str, depth: int, maximizing: bool) -> tuple[int, int]:
        """Returns (score, best_position). Depth penalises slow wins."""
        winner = check_winner(b)
        if winner == ai_mark:
            return 10 - depth, -1
        if winner == opponent:
            return depth - 10, -1
        if winner == "draw":
            return 0, -1

        best_pos = -1
        if maximizing:
            best_val = -999
            for pos in available_positions(b):
                val, _ = score(apply_move(b, pos, ai_mark), depth + 1, False)
                if val > best_val:
                    best_val, best_pos = val, pos
        else:
            best_val = 999
            for pos in available_positions(b):
                val, _ = score(apply_move(b, pos, opponent), depth + 1, True)
                if val < best_val:
                    best_val, best_pos = val, pos
        return best_val, best_pos

    _, pos = score(board, 0, True)
    return pos


AI_DIFFICULTY = {
    "ai_easy": ai_easy,
    "ai_medium": ai_medium,
    "ai_hard": ai_hard,
}


def pick_ai_move(board: str, ai_mark: str, mode: str) -> int:
    """Dispatch by game mode."""
    fn = AI_DIFFICULTY.get(mode)
    if fn is None:
        raise ValueError(f"not an AI mode: {mode}")
    return fn(board, ai_mark)
