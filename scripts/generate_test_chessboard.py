"""
Synthetic top-down chessboard PNG for /analyze/image testing.

Draws an 8x8 board plus a few high-contrast circular "pieces" so the
heuristic (Canny edge density) reliably detects occupancy.
"""

from pathlib import Path

import cv2
import numpy as np

SIZE = 800
CELL = SIZE // 8

# BGR — warm wood-like light/dark squares
LIGHT = (235, 210, 180)
DARK = (120, 85, 55)


def draw_piece(img: np.ndarray, row: int, col: int, bright_piece: bool) -> None:
    cy = row * CELL + CELL // 2
    cx = col * CELL + CELL // 2
    radius = int(CELL * 0.32)
    if bright_piece:
        fill = (250, 250, 250)
        ring = (40, 40, 40)
    else:
        fill = (35, 35, 35)
        ring = (220, 220, 220)
    cv2.circle(img, (cx, cy), radius, ring, 4)
    cv2.circle(img, (cx, cy), max(radius - 3, 1), fill, -1)


def main() -> None:
    img = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    for r in range(8):
        for c in range(8):
            color = LIGHT if (r + c) % 2 == 0 else DARK
            y1, x1 = r * CELL, c * CELL
            img[y1 : y1 + CELL, x1 : x1 + CELL] = color

    # (row, col, bright): image row 0 = top rank; a1 ≈ bottom-left (7, 0)
    placements = [
        (7, 0, True),
        (7, 1, False),
        (0, 4, True),
        (3, 3, False),
        (4, 4, True),
    ]
    for row, col, bright in placements:
        draw_piece(img, row, col, bright)

    # Run from project root: `python scripts/generate_test_chessboard.py`
    out_dir = Path(__file__).resolve().parent.parent / "test_assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "test_chessboard_topdown.png"
    # cv2.imwrite often fails on Windows when the path contains non-ASCII characters.
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("cv2.imencode failed for PNG")
    out_path.write_bytes(buf.tobytes())
    print(f"Wrote {out_path.resolve()}")


if __name__ == "__main__":
    main()
