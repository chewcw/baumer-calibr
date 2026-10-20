"""Shared data model: what calibrateCamera produces + what boCalibrationData stores.

Baumer Users Guide §11.19 mapping (distortion coefficients in Baumer selector order):
- Camera Matrix (3x3)     <-> camera_matrix
- Camera Matrix (3x3)     <-> camera_matrix
- New Camera Matrix (3x3) <-> new_camera_matrix (cv2.getOptimalNewCameraMatrix)
- k1,k2,k3,p1,p2          <-> dist_coeffs stored as (k1,k2,p1,p2,k3) in OpenCV order
- rvec/tvec (vec3)        <-> best-view pose; full per-view arrays kept in YAML only
- focal_length_mm, angular_aperture_deg <-> manual metadata
"""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np


@dataclass
class CalibrationResult:
    camera_matrix: np.ndarray  # 3x3
    dist_coeffs: np.ndarray  # shape (5,) in OpenCV order (k1,k2,p1,p2,k3)
    new_camera_matrix: np.ndarray  # 3x3
    image_size: tuple[int, int]  # (w, h)
    rms_error: float
    rvec: np.ndarray  # shape (3,) best view
    tvec: np.ndarray  # shape (3,) best view
    rvecs_all: list[np.ndarray] = field(default_factory=list)
    tvecs_all: list[np.ndarray] = field(default_factory=list)
    per_view_errors: list[float] = field(default_factory=list)
    focal_length_mm: float = 0.0
    angular_aperture_deg: float = 0.0
    pattern: str = ""
    square_size_mm: float = 0.0

    @property
    def dist_bo_order(self) -> dict[str, float]:
        """Return distortion dict in Baumer selector order k1,k2,k3,p1,p2."""
        k1, k2, p1, p2, k3 = (float(v) for v in np.ravel(self.dist_coeffs)[:5])
        return {"k1": k1, "k2": k2, "k3": k3, "p1": p1, "p2": p2}

    @classmethod
    def dist_from_bo_order(cls, d: dict[str, float]) -> np.ndarray:
        """Build OpenCV (k1,k2,p1,p2,k3) vector from Baumer-order dict."""
        return np.array([[d["k1"], d["k2"], d["p1"], d["p2"], d["k3"]]], dtype=float)
