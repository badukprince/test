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


def _crop_inner_roi(cell: np.ndarray, margin_ratio: float = 0.18) -> np.ndarray:
    """Ignore cell borders so neighbor square edges do not dominate metrics."""
    ch, cw = cell.shape[:2]
    if ch < 4 or cw < 4:
        return cell
    my = max(1, int(ch * margin_ratio))
    mx = max(1, int(cw * margin_ratio))
    return cell[my : ch - my, mx : cw - mx]


def _cell_occupancy_score(gray_roi: np.ndarray) -> Tuple[float, float, float]:
    """
    Returns (score, lap_var, brightness_mean).
    score combines Laplacian variance (structure) and mean gradient (edges).
    """
    if gray_roi.size == 0:
        return 0.0, 0.0, 0.0

    g = cv2.GaussianBlur(gray_roi, (3, 3), 0)
    lap = cv2.Laplacian(g, cv2.CV_64F)
    lap_var = float(lap.var())

    gx = cv2.Sobel(g, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_64F, 0, 1, ksize=3)
    grad_mean = float(np.mean(np.sqrt(gx * gx + gy * gy)))

    brightness = float(np.mean(g))
    # Laplacian reacts to piece contours; gradient reinforces ring edges.
    score = lap_var + 35.0 * grad_mean
    return score, lap_var, brightness


def _mad_threshold(scores: np.ndarray, k: float = 3.2) -> float:
    """Robust split when most squares are empty and a few contain pieces."""
    med = float(np.median(scores))
    mad = float(np.median(np.abs(scores - med)))
    if mad < 1e-3:
        mad = float(np.std(scores)) * 0.35 + 1e-3
    return med + k * mad


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

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    scores = np.zeros((8, 8), dtype=np.float64)
    brightness = np.zeros((8, 8), dtype=np.float64)

    for r in range(8):
        for c in range(8):
            y1, y2 = r * cell_h, (r + 1) * cell_h
            x1, x2 = c * cell_w, (c + 1) * cell_w
            cell_gray = blurred[y1:y2, x1:x2]
            inner = _crop_inner_roi(cell_gray)
            sc, _, br = _cell_occupancy_score(inner)
            scores[r, c] = sc
            brightness[r, c] = br

    flat = scores.reshape(-1)
    threshold = _mad_threshold(flat, k=3.2)

    # If the board is very uniform, MAD threshold can be too low → many false positives.
    q75, q25 = np.percentile(flat, 75), np.percentile(flat, 25)
    iqr_floor = float(q75 + 0.85 * max(q75 - q25, 1e-6))
    threshold = max(threshold, iqr_floor)

    board_matrix = _empty_board_matrix()
    occupancy_count = 0

    for r in range(8):
        for c in range(8):
            if scores[r, c] > threshold:
                occupancy_count += 1
                board_matrix[r][c] = "P" if brightness[r][c] > 120 else "p"

    if occupancy_count == 0:
        return board_matrix, None, "No clear pieces detected from image heuristic"

    fen = _matrix_to_fen(board_matrix)
    note = (
        f"Detected {occupancy_count} occupied squares (inner-cell Laplacian+gradient score, "
        "robust threshold). Piece letters are brightness-based approximations, not classification."
    )
    return board_matrix, fen, note
