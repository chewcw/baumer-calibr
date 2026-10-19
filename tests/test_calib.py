import cv2
import numpy as np

from baumer_calibration.calibrator import calibrate
from baumer_calibration.models import CalibrationResult
from baumer_calibration.patterns import detect, make_checkerboard_image
from baumer_calibration.storage import load_yaml, save_yaml


def _synth_views(n=12, seed=0):
    K = np.array([[1200, 0, 640], [0, 1200, 480], [0, 0, 1]], float)
    dist = np.array([0.1, -0.05, 0.001, 0.002, 0.0], float)
    cols, rows, sq = 9, 6, 25.0
    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * sq
    rng = np.random.default_rng(seed)
    ol, il = [], []
    for _ in range(n):
        r = rng.normal(0, 0.3, 3)
        t = np.array([rng.normal(0, 40), rng.normal(0, 40), 600 + rng.normal(0, 80)])
        imgp, _ = cv2.projectPoints(objp, r, t, K, dist)
        ol.append(objp)
        il.append(imgp.astype(np.float32))
    return ol, il, K, dist


def test_calibrate_recovers_known_K():
    ol, il, K, _ = _synth_views()
    res = calibrate(ol, il, (1280, 960), "checkerboard", 25.0)
    assert res.rms_error < 0.01
    assert np.abs(res.camera_matrix - K).max() < 1.0
    assert res.rvec.shape == (3,) and res.tvec.shape == (3,)
    assert len(res.rvecs_all) == 12 and len(res.tvecs_all) == 12
    # bo order mapping
    bo = res.dist_bo_order
    assert set(bo) == {"k1", "k2", "k3", "p1", "p2"}


def test_yaml_roundtrip(tmp_path):
    ol, il, _, _ = _synth_views()
    res = calibrate(ol, il, (1280, 960))
    p = tmp_path / "c.yaml"
    save_yaml(res, p)
    r2 = load_yaml(p)
    assert np.allclose(r2.camera_matrix, res.camera_matrix)
    assert np.allclose(np.ravel(r2.dist_coeffs), np.ravel(res.dist_coeffs))
    assert np.allclose(np.ravel(r2.rvec), np.ravel(res.rvec))
    assert np.allclose(np.ravel(r2.tvec), np.ravel(res.tvec))
    assert len(r2.rvecs_all) == len(res.rvecs_all)


def test_detect_rendered_checkerboard():
    img = make_checkerboard_image(9, 6, 100)
    d = detect(img, "checkerboard", (9, 6), 25.0)
    assert d.ok and d.image_points is not None
    assert d.object_points.shape == (54, 3)


def test_detect_rendered_charuco():
    # regression: legacy cv2.aruco.interpolateCornersCharuco removed in OpenCV 5
    from baumer_calibration.patterns import make_charuco_board_image
    img = make_charuco_board_image(7, 5, 150, 0.75, "DICT_5X5_100")
    d = detect(img, "charuco", (7, 5), 30.0, 22.5)
    assert d.ok and d.image_points is not None
    assert d.object_points.shape[0] == d.image_points.reshape(-1, 2).shape[0]
    assert d.object_points.shape[1] == 3


def test_dist_order_helpers():
    bo = {"k1": 0.1, "k2": -0.05, "k3": 0.01, "p1": 0.001, "p2": 0.002}
    v = CalibrationResult.dist_from_bo_order(bo)
    assert list(np.ravel(v)) == [0.1, -0.05, 0.001, 0.002, 0.01]
