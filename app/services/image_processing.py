from typing import List, Optional, Tuple

import cv2
import numpy as np


def _empty_board_matrix() -> List[List[str]]:
    return [["." for _ in range(8)] for _ in range(8)]


def _matrix_to_fen(board_matrix: List[List[str]]) -> str:
    fen_rows: List[str] = []
    for row in board_matrix:
        empty_count = 0
        row_fen = ""
        for cell in row:
            if cell == ".":
                empty_count += 1
            else:
                if empty_count:
                    row_fen += str(empty_count)
                    empty_count = 0
                row_fen += cell
        if empty_count:
            row_fen += str(empty_count)
        fen_rows.append(row_fen)
    return "/".join(fen_rows) + " w - - 0 1"


def extract_board_from_image_bytes(image_bytes: bytes) -> Tuple[List[List[str]], Optional[str], str]:
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Invalid image file")

    h, w = img.shape[:2]
    cell_h = h // 8
    cell_w = w // 8
    if cell_h == 0 or cell_w == 0:
        raise ValueError("Image too small to split into 8x8 grid")

    board_matrix = _empty_board_matrix()
    occupancy_count = 0

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    for r in range(8):
        for c in range(8):
            y1, y2 = r * cell_h, (r + 1) * cell_h
            x1, x2 = c * cell_w, (c + 1) * cell_w
            cell = blurred[y1:y2, x1:x2]

            edges = cv2.Canny(cell, 30, 120)
            edge_density = float(np.mean(edges > 0))
            brightness = float(np.mean(cell))

            # Practical heuristic:
            # high edge density suggests a piece-like contour on a square.
            if edge_density > 0.08:
                occupancy_count += 1
                board_matrix[r][c] = "P" if brightness > 120 else "p"

    if occupancy_count == 0:
        return board_matrix, None, "No clear pieces detected from image heuristic"

    fen = _matrix_to_fen(board_matrix)
    note = (
        "Heuristic image extraction used; detected occupied squares are approximated "
        "as pawns by brightness."
    )
    return board_matrix, fen, note
