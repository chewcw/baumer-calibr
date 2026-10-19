"""Pattern detection: checkerboard + ChArUco, both supported (user wants both).

Checkerboard: --pattern checkerboard --pattern-size 9x6 (inner corners) --square 25.0 (mm)
ChArUco:      --pattern charuco --pattern-size 7x5 (squares) --square 30.0 --marker 22.0
              --aruco-dict DICT_5X5_100 (default)
"""
from __future__ import annotations

from dataclasses import dataclass
import cv2
import numpy as np


ARUCO_DICTS = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
    "DICT_4X4_1000": cv2.aruco.DICT_4X4_1000,
    "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250": cv2.aruco.DICT_5X5_250,
    "DICT_5X5_1000": cv2.aruco.DICT_5X5_1000,
    "DICT_6X6_250": cv2.aruco.DICT_6X6_250,
    "DICT_7X7_100": cv2.aruco.DICT_7X7_100,
}


@dataclass
class Detection:
    ok: bool
    image_points: np.ndarray | None   # (N,1,2) float32
    object_points: np.ndarray | None  # (N,3) float32
    debug_frame: np.ndarray | None = None  # annotated BGR for preview
    info: str = ""


def parse_pattern_size(s: str) -> tuple[int, int]:
    a, b = s.lower().replace("x", " ").replace(",", " ").split()
    return int(a), int(b)


def checkerboard_object_points(cols: int, rows: int, square: float) -> np.ndarray:
    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square
    return objp


def detect_checkerboard(gray: np.ndarray, cols: int, rows: int, square: float) -> Detection:
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
    ret, corners = cv2.findChessboardCorners(gray, (cols, rows), flags)
    if not ret:
        return Detection(False, None, None, info="corners not found")
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
    return Detection(True, corners, checkerboard_object_points(cols, rows, square),
                     info=f"{len(corners)} corners")


def _charuco_board(squares_x: int, squares_y: int, square_len: float,
                   marker_len: float, dict_name: str):
    aruco_dict = cv2.aruco.getPredefinedDictionary(
        ARUCO_DICTS.get(dict_name, cv2.aruco.DICT_5X5_100))
    # mm units keep parity with checkerboard path
    board = cv2.aruco.CharucoBoard((squares_x, squares_y), square_len, marker_len, aruco_dict)
    return board, aruco_dict


def detect_charuco(gray: np.ndarray, squares_x: int, squares_y: int,
                   square_len: float, marker_len: float, dict_name: str) -> Detection:
    board, aruco_dict = _charuco_board(squares_x, squares_y, square_len, marker_len, dict_name)
    # CharucoDetector replaces legacy interpolateCornersCharuco (removed in OpenCV 5)
    detector = cv2.aruco.CharucoDetector(board)
    charuco_corners, charuco_ids, marker_corners, marker_ids = detector.detectBoard(gray)
    if marker_ids is None or len(marker_ids) < 4:
        return Detection(False, None, None, info="too few markers")
    if charuco_corners is None or len(charuco_corners) < 6 or charuco_ids is None:
        return Detection(False, None, None, info="too few charuco corners")
    objp, imgp = board.matchImagePoints(charuco_corners, charuco_ids)
    return Detection(True, imgp.reshape(-1, 1, 2).astype(np.float32),
                     objp.astype(np.float32), info=f"{len(imgp)} charuco corners")


def detect(gray: np.ndarray, pattern: str, pattern_size: tuple[int, int],
           square: float, marker: float = 0.0,
           aruco_dict: str = "DICT_5X5_100") -> Detection:
    if pattern == "charuco":
        return detect_charuco(gray, pattern_size[0], pattern_size[1],
                              square, marker or square * 0.75, aruco_dict)
    return detect_checkerboard(gray, pattern_size[0], pattern_size[1], square)


def make_charuco_board_image(squares_x: int, squares_y: int, square_px: int,
                             marker_ratio: float, dict_name: str) -> np.ndarray:
    """Render a printable ChArUco board (PNG)."""
    board, aruco_dict = _charuco_board(squares_x, squares_y, 1.0, marker_ratio, dict_name)
    w, h = squares_x * square_px, squares_y * square_px
    return board.generateImage((w, h))


def make_checkerboard_image(cols_inner: int, rows_inner: int, square_px: int) -> np.ndarray:
    """Render a printable checkerboard (PNG). cols/rows = inner corners."""
    cols, rows = cols_inner + 1, rows_inner + 1
    img = np.ones((rows * square_px, cols * square_px), np.uint8) * 255
    for y in range(rows):
        for x in range(cols):
            if (x + y) % 2 == 0:
                img[y * square_px:(y + 1) * square_px, x * square_px:(x + 1) * square_px] = 0
    return img
