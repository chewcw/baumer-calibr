"""YAML sidecar: full calibration incl. all rvecs/tvecs (camera keeps best only)."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import yaml

from baumer_calibration.models import CalibrationResult


def save_yaml(res: CalibrationResult, path: str | Path) -> Path:
    p = Path(path)
    d = res.dist_bo_order
    data = {
        "pattern": res.pattern,
        "square_size_mm": res.square_size_mm,
        "image_size": {"width": res.image_size[0], "height": res.image_size[1]},
        "rms_error": res.rms_error,
        "camera_matrix": np.asarray(res.camera_matrix, float).reshape(3, 3).tolist(),
        "new_camera_matrix": np.asarray(res.new_camera_matrix, float).reshape(3, 3).tolist(),
        "dist_coeffs_opencv_order_k1_k2_p1_p2_k3": [float(v) for v in np.ravel(res.dist_coeffs)[:5]],
        "dist_coeffs_baumer_order": d,
        "rvec_best": [float(v) for v in np.ravel(res.rvec)[:3]],
        "tvec_best": [float(v) for v in np.ravel(res.tvec)[:3]],
        "rvecs_all": [[float(v) for v in np.ravel(r)] for r in res.rvecs_all],
        "tvecs_all": [[float(v) for v in np.ravel(t)] for t in res.tvecs_all],
        "per_view_errors": [float(e) for e in res.per_view_errors],
        "focal_length_mm": res.focal_length_mm,
        "angular_aperture_deg": res.angular_aperture_deg,
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    return p


def load_yaml(path: str | Path) -> CalibrationResult:
    data = yaml.safe_load(Path(path).read_text())
    bo = data["dist_coeffs_baumer_order"]
    dist = CalibrationResult.dist_from_bo_order(bo)
    return CalibrationResult(
        camera_matrix=np.array(data["camera_matrix"], float),
        dist_coeffs=np.array(dist, float).reshape(-1)[:5],
        new_camera_matrix=np.array(data["new_camera_matrix"], float),
        image_size=(int(data["image_size"]["width"]), int(data["image_size"]["height"])),
        rms_error=float(data["rms_error"]),
        rvec=np.array(data["rvec_best"], float).reshape(3),
        tvec=np.array(data["tvec_best"], float).reshape(3),
        rvecs_all=[np.array(r, float).reshape(3) for r in data.get("rvecs_all", [])],
        tvecs_all=[np.array(t, float).reshape(3) for t in data.get("tvecs_all", [])],
        per_view_errors=[float(e) for e in data.get("per_view_errors", [])],
        focal_length_mm=float(data.get("focal_length_mm", 0.0)),
        angular_aperture_deg=float(data.get("angular_aperture_deg", 0.0)),
        pattern=str(data.get("pattern", "")),
        square_size_mm=float(data.get("square_size_mm", 0.0)),
    )
