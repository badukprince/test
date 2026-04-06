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


def _estimate_square_bg(inner_bgr: np.ndarray) -> np.ndarray:
    """
    Estimate plain-square color from 4 corner patches in a cell.
    Works well for top-down rendered boards (e.g., chess.com screenshots).
    """
    h, w = inner_bgr.shape[:2]
    py = max(2, int(h * 0.16))
    px = max(2, int(w * 0.16))

    patches = [
        inner_bgr[0:py, 0:px],
        inner_bgr[0:py, w - px : w],
        inner_bgr[h - py : h, 0:px],
        inner_bgr[h - py : h, w - px : w],
    ]
    stacked = np.concatenate([p.reshape(-1, 3) for p in patches], axis=0)
    return np.median(stacked, axis=0).astype(np.float32)


def _cell_features(inner_bgr: np.ndarray) -> Tuple[float, float, float, float]:
    """
    Returns:
      (occupancy_score, foreground_ratio, edge_density, piece_brightness_delta)
    """
    if inner_bgr.size == 0:
        return 0.0, 0.0, 0.0, 0.0

    bg = _estimate_square_bg(inner_bgr)
    gray = cv2.cvtColor(inner_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(g, 40, 120)
    edge_density = float(np.mean(edges > 0))

    lap_var = float(cv2.Laplacian(g, cv2.CV_64F).var())
    std_gray = float(np.std(g))

    diff = np.linalg.norm(inner_bgr.astype(np.float32) - bg, axis=2)
    diff_thr = max(18.0, float(np.percentile(diff, 72)))
    fg_mask = diff > diff_thr
    fg_ratio = float(np.mean(fg_mask))

    bg_gray = float(np.mean(cv2.cvtColor(np.uint8([[bg]]), cv2.COLOR_BGR2GRAY)))
    if np.any(fg_mask):
        piece_gray = float(np.mean(g[fg_mask]))
    else:
        piece_gray = float(np.mean(g))
    piece_delta = piece_gray - bg_gray

    # Weighted score: plain square is almost constant; piece square has shape/textures.
    score = std_gray + (lap_var / 120.0) + (12.0 * edge_density) + (2.0 * fg_ratio)
    return score, fg_ratio, edge_density, piece_delta


def _mad_threshold(scores: np.ndarray, k: float = 3.2) -> float:
    """Robust split when most squares are empty and a few contain pieces."""
    med = float(np.median(scores))
    mad = float(np.median(np.abs(scores - med)))
    if mad < 1e-3:
        mad = float(np.std(scores)) * 0.35 + 1e-3
    return med + k * mad


def _otsu_threshold(scores: np.ndarray) -> float:
    min_v = float(np.min(scores))
    max_v = float(np.max(scores))
    if max_v - min_v < 1e-6:
        return max_v + 1.0

    norm = ((scores - min_v) / (max_v - min_v) * 255.0).astype(np.uint8)
    otsu_v, _ = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return min_v + (max_v - min_v) * (float(otsu_v) / 255.0)


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

    scores = np.zeros((8, 8), dtype=np.float64)
    fg_ratios = np.zeros((8, 8), dtype=np.float64)
    edge_densities = np.zeros((8, 8), dtype=np.float64)
    piece_deltas = np.zeros((8, 8), dtype=np.float64)

    for r in range(8):
        for c in range(8):
            y1, y2 = r * cell_h, (r + 1) * cell_h
            x1, x2 = c * cell_w, (c + 1) * cell_w
            cell_bgr = img[y1:y2, x1:x2]
            inner = _crop_inner_roi(cell_bgr, margin_ratio=0.16)
            sc, fr, ed, pd = _cell_features(inner)
            scores[r, c] = sc
            fg_ratios[r, c] = fr
            edge_densities[r, c] = ed
            piece_deltas[r, c] = pd

    flat = scores.reshape(-1)
    mad_thr = _mad_threshold(flat, k=2.6)
    otsu_thr = _otsu_threshold(flat)
    threshold = min(mad_thr, otsu_thr)

    board_matrix = _empty_board_matrix()
    occupancy_count = 0

    for r in range(8):
        for c in range(8):
            strong_fg = fg_ratios[r, c] > 0.13 and edge_densities[r, c] > 0.015
            if scores[r, c] > threshold or strong_fg:
                occupancy_count += 1
                board_matrix[r][c] = "P" if piece_deltas[r, c] >= 0 else "p"

    if occupancy_count == 0:
        return board_matrix, None, "No clear pieces detected from image heuristic"

    fen = _matrix_to_fen(board_matrix)
    note = (
        f"Detected {occupancy_count} occupied squares (cell background subtraction + contour/texture scoring). "
        "Piece letters are light/dark approximations, not exact piece classification."
    )
    return board_matrix, fen, note
