"""Calibration math: thin wrapper over cv2.calibrateCamera.

Selects the best view (lowest per-view reprojection error) for rvec/tvec
storage in the camera; keeps all views in the YAML sidecar.
"""

from __future__ import annotations

import cv2
import numpy as np

from baumer_calib.models import CalibrationResult


def calibrate(
    objpoints: list[np.ndarray],
    imgpoints: list[np.ndarray],
    image_size: tuple[int, int],
    pattern: str = "",
    square_size_mm: float = 0.0,
    alpha: float = 0.0,
) -> CalibrationResult:
    if len(objpoints) < 3:
        raise ValueError(f"need >=3 valid views, got {len(objpoints)}")
    ret, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        objpoints, imgpoints, image_size, None, None
    )
    # per-view RMS (numpy to avoid OpenCV shape/type mismatch between
    # findChessboardCorners' (N,1,2) and projectPoints' (N,2) outputs)
    errors: list[float] = []
    for i in range(len(objpoints)):
        proj, _ = cv2.projectPoints(objpoints[i], rvecs[i], tvecs[i], K, dist)
        a = np.asarray(imgpoints[i], float).reshape(-1, 2)
        b = np.asarray(proj, float).reshape(-1, 2)
        err = float(np.sqrt(np.sum((a - b) ** 2) / max(len(a), 1)))
        errors.append(err)
    best = int(np.argmin(errors))
    h, w = image_size[1], image_size[0]
    newK, _roi = cv2.getOptimalNewCameraMatrix(K, dist, (w, h), alpha)
    return CalibrationResult(
        camera_matrix=np.asarray(K, float),
        dist_coeffs=np.asarray(dist, float).reshape(-1)[:5],
        new_camera_matrix=np.asarray(newK, float),
        image_size=(w, h),
        rms_error=float(ret),
        rvec=np.asarray(rvecs[best], float).reshape(3),
        tvec=np.asarray(tvecs[best], float).reshape(3),
        rvecs_all=[np.asarray(r, float).reshape(3) for r in rvecs],
        tvecs_all=[np.asarray(t, float).reshape(3) for t in tvecs],
        per_view_errors=errors,
        pattern=pattern,
        square_size_mm=square_size_mm,
    )
