from typing import Dict, List, Tuple

import chess

from app.core.config import settings

PIECE_VALUES: Dict[int, float] = {
    chess.PAWN: 1.0,
    chess.KNIGHT: 3.0,
    chess.BISHOP: 3.0,
    chess.ROOK: 5.0,
    chess.QUEEN: 9.0,
    chess.KING: 0.0,
}

CENTER_SQUARES = [chess.D4, chess.E4, chess.D5, chess.E5]
NEAR_CENTER_SQUARES = [
    chess.C3,
    chess.D3,
    chess.E3,
    chess.F3,
    chess.C4,
    chess.F4,
    chess.C5,
    chess.F5,
    chess.C6,
    chess.D6,
    chess.E6,
    chess.F6,
]


def _material_score(board: chess.Board) -> float:
    score = 0.0
    for piece_type, value in PIECE_VALUES.items():
        score += len(board.pieces(piece_type, chess.WHITE)) * value
        score -= len(board.pieces(piece_type, chess.BLACK)) * value
    return score


def _center_control_score(board: chess.Board) -> float:
    score = 0.0
    for square in CENTER_SQUARES:
        white_attackers = len(board.attackers(chess.WHITE, square))
        black_attackers = len(board.attackers(chess.BLACK, square))
        score += (white_attackers - black_attackers) * settings.center_bonus
    return score


def _positional_square_score(board: chess.Board) -> float:
    """
    Lightweight positional term:
    reward occupying central and near-central squares.
    """
    score = 0.0

    for square in CENTER_SQUARES:
        piece = board.piece_at(square)
        if piece is None:
            continue
        score += 0.30 if piece.color == chess.WHITE else -0.30

    for square in NEAR_CENTER_SQUARES:
        piece = board.piece_at(square)
        if piece is None:
            continue
        score += 0.12 if piece.color == chess.WHITE else -0.12

    return score


def evaluate_fen(fen: str) -> Tuple[float, str, List[str], Dict[str, str | bool]]:
    board = chess.Board(fen)
    reasoning_parts: List[str] = []
    status: Dict[str, str | bool] = {
        "is_check": False,
        "is_checkmate": False,
        "check_side": "none",
    }

    score = _material_score(board)
    reasoning_parts.append(f"material score: {score:+.2f}")

    center_score = _center_control_score(board)
    score += center_score
    reasoning_parts.append(f"center control bonus: {center_score:+.2f}")

    positional_score = _positional_square_score(board)
    score += positional_score
    reasoning_parts.append(f"positional bonus (center occupancy): {positional_score:+.2f}")

    if board.is_checkmate():
        status["is_checkmate"] = True
        if board.turn == chess.WHITE:
            score = -settings.checkmate_score
            reasoning_parts.append("checkmate detected: white to move is mated")
            status["check_side"] = "white"
        else:
            score = settings.checkmate_score
            reasoning_parts.append("checkmate detected: black to move is mated")
            status["check_side"] = "black"
    elif board.is_check():
        status["is_check"] = True
        if board.turn == chess.WHITE:
            score -= settings.check_bonus
            reasoning_parts.append("white king is in check")
            status["check_side"] = "white"
        else:
            score += settings.check_bonus
            reasoning_parts.append("black king is in check")
            status["check_side"] = "black"

    if score > 0.3:
        advantage = "white"
    elif score < -0.3:
        advantage = "black"
    else:
        advantage = "equal"

    return round(score, 2), advantage, reasoning_parts, status


def get_piece_counts(fen: str) -> Tuple[int, int, int]:
    board = chess.Board(fen)
    white_count = sum(1 for p in board.piece_map().values() if p.color == chess.WHITE)
    black_count = sum(1 for p in board.piece_map().values() if p.color == chess.BLACK)
    return white_count + black_count, white_count, black_count
