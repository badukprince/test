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


def _cell_features(inner_bgr: np.ndarray) -> Tuple[float, float, float, float, float]:
    """
    Returns:
      (occupancy_score, foreground_ratio, edge_density, piece_brightness_delta, piece_gray_abs)
    """
    if inner_bgr.size == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0

    bg = _estimate_square_bg(inner_bgr)
    gray = cv2.cvtColor(inner_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(g, 40, 120)
    edge_density = float(np.mean(edges > 0))

    lap_var = float(cv2.Laplacian(g, cv2.CV_64F).var())
    std_gray = float(np.std(g))

    diff = np.linalg.norm(inner_bgr.astype(np.float32) - bg, axis=2)
    diff_thr = max(16.0, float(np.percentile(diff, 70)))
    raw_mask = (diff > diff_thr).astype(np.uint8)

    # Remove tiny texture dots and keep piece-like connected components.
    raw_mask = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    raw_mask = cv2.morphologyEx(raw_mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(raw_mask, connectivity=8)
    cleaned = np.zeros_like(raw_mask, dtype=np.uint8)
    h, w = raw_mask.shape[:2]
    min_area = max(10, int(h * w * 0.018))
    for i in range(1, num_labels):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area >= min_area:
            cleaned[labels == i] = 1

    fg_mask = cleaned.astype(bool)
    fg_ratio = float(np.mean(fg_mask))

    bg_gray = float(np.mean(cv2.cvtColor(np.uint8([[bg]]), cv2.COLOR_BGR2GRAY)))
    if np.any(fg_mask):
        piece_gray = float(np.mean(g[fg_mask]))
    else:
        piece_gray = float(np.mean(g))
    piece_delta = piece_gray - bg_gray

    # Weighted score: plain square is almost constant; piece square has shape/textures.
    score = std_gray + (lap_var / 120.0) + (9.0 * edge_density) + (7.0 * fg_ratio)
    return score, fg_ratio, edge_density, piece_delta, piece_gray


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


def _split_two_clusters(values: np.ndarray) -> float:
    """
    1D two-cluster split for piece brightness.
    Returns threshold between dark and bright clusters.
    """
    if values.size == 0:
        return 130.0
    if values.size == 1:
        return float(values[0])

    a = float(np.min(values))
    b = float(np.max(values))
    if abs(b - a) < 1e-6:
        return a

    for _ in range(12):
        ta = values[np.abs(values - a) <= np.abs(values - b)]
        tb = values[np.abs(values - a) > np.abs(values - b)]
        if ta.size:
            a = float(np.mean(ta))
        if tb.size:
            b = float(np.mean(tb))
        if abs(a - b) < 1e-3:
            break
    lo, hi = sorted((a, b))
    return (lo + hi) * 0.5


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
    piece_grays = np.zeros((8, 8), dtype=np.float64)

    for r in range(8):
        for c in range(8):
            y1, y2 = r * cell_h, (r + 1) * cell_h
            x1, x2 = c * cell_w, (c + 1) * cell_w
            cell_bgr = img[y1:y2, x1:x2]
            inner = _crop_inner_roi(cell_bgr, margin_ratio=0.16)
            sc, fr, ed, pd, pg = _cell_features(inner)
            scores[r, c] = sc
            fg_ratios[r, c] = fr
            edge_densities[r, c] = ed
            piece_deltas[r, c] = pd
            piece_grays[r, c] = pg

    flat = scores.reshape(-1)
    mad_thr = _mad_threshold(flat, k=2.6)
    otsu_thr = _otsu_threshold(flat)
    p50 = float(np.percentile(flat, 50))
    p60 = float(np.percentile(flat, 60))
    if p50 > 5.0:
        # Opening-like dense positions (many occupied squares):
        # split high/low groups around the middle band.
        threshold = max(otsu_thr, 0.5 * (p50 + p60))
    else:
        # Sparse positions: keep sensitivity for few pieces.
        threshold = min(mad_thr, otsu_thr)

    board_matrix = _empty_board_matrix()
    occupancy_count = 0
    occupied_coords: List[Tuple[int, int]] = []

    for r in range(8):
        for c in range(8):
            strong_fg = fg_ratios[r, c] > 0.06 and edge_densities[r, c] > 0.01
            if scores[r, c] > threshold or strong_fg:
                occupancy_count += 1
                occupied_coords.append((r, c))

    if occupancy_count == 0:
        return board_matrix, None, "No clear pieces detected from image heuristic"

    # Color estimation:
    # use piece brightness clustering among occupied cells to avoid square-color flipping.
    occ_gray_values = np.array([piece_grays[r, c] for r, c in occupied_coords], dtype=np.float64)
    color_thr = _split_two_clusters(occ_gray_values)
    for r, c in occupied_coords:
        board_matrix[r][c] = "P" if piece_grays[r, c] >= color_thr else "p"

    # Half-board majority correction:
    # chess screenshots often place one side mainly on top half and the other on bottom half.
    # This fixes alternating mislabels caused by square color contrast.
    if occupancy_count >= 20:
        top_cells = [board_matrix[r][c] for r, c in occupied_coords if r <= 3]
        bottom_cells = [board_matrix[r][c] for r, c in occupied_coords if r >= 4]
        if len(top_cells) >= 6 and len(bottom_cells) >= 6:
            top_white = sum(1 for x in top_cells if x == "P")
            top_black = len(top_cells) - top_white
            bottom_white = sum(1 for x in bottom_cells if x == "P")
            bottom_black = len(bottom_cells) - bottom_white
            top_major = "P" if top_white >= top_black else "p"
            bottom_major = "P" if bottom_white >= bottom_black else "p"
            if top_major != bottom_major:
                for r, c in occupied_coords:
                    board_matrix[r][c] = top_major if r <= 3 else bottom_major

    # Opening-like fallback:
    # If pieces are concentrated on top/bottom bands and mixed labels still remain,
    # force consistent top/bottom color by average piece brightness per band.
    top_band = [(r, c) for r, c in occupied_coords if r <= 2]
    bottom_band = [(r, c) for r, c in occupied_coords if r >= 5]
    middle_band = [(r, c) for r, c in occupied_coords if 3 <= r <= 4]
    if occupancy_count >= 24 and len(top_band) >= 10 and len(bottom_band) >= 10 and len(middle_band) <= 6:
        top_mean = float(np.mean([piece_grays[r, c] for r, c in top_band]))
        bottom_mean = float(np.mean([piece_grays[r, c] for r, c in bottom_band]))
        top_color = "P" if top_mean > bottom_mean else "p"
        bottom_color = "p" if top_color == "P" else "P"
        for r, c in top_band:
            board_matrix[r][c] = top_color
        for r, c in bottom_band:
            board_matrix[r][c] = bottom_color

    fen = _matrix_to_fen(board_matrix)
    note = (
        f"Detected {occupancy_count} occupied squares (cell background subtraction + contour/texture scoring). "
        "Piece colors are inferred by global brightness clustering of detected pieces."
    )
    return board_matrix, fen, note
