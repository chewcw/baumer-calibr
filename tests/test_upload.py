"""Verify upload() touches every boCalibrationData feature in the right order."""

import numpy as np

from baumer_calib.models import CalibrationResult
from baumer_calib.neo_camera import NeoCamera


class FakeFeat:
    def __init__(self, log, name):
        self._log = log
        self._name = name

    def SetString(self, v):
        self._log.append((self._name, "SetString", v))

    def Set(self, v):
        self._log.append((self._name, "Set", v))

    def Execute(self):
        self._log.append((self._name, "Execute", None))


class FakeF:
    def __init__(self, log):
        self._log = log

    def __getattr__(self, name):
        return FakeFeat(self._log, name)


def test_upload_sequence():
    log: list = []
    cam = NeoCamera()
    cam.cam = type("C", (), {"f": FakeF(log)})()
    res = CalibrationResult(
        camera_matrix=np.eye(3) * 1000
        + np.array([[0, 0, 320], [0, 0, 240], [0, 0, -999]]),
        dist_coeffs=np.array([0.1, -0.05, 0.001, 0.002, 0.01]),
        new_camera_matrix=np.eye(3),
        image_size=(640, 480),
        rms_error=0.2,
        rvec=np.array([0.1, 0.2, 0.3]),
        tvec=np.array([10.0, 20.0, 500.0]),
    )
    cam.upload(res, focal_mm=16.0, aperture_deg=45.0, persist_userset=False)
    names = [n for n, _, _ in log]
    for expect in [
        "boCalibrationDataConfigurationMode",
        "boCalibrationMatrixSelector",
        "boCalibrationMatrixValueSelector",
        "boCalibrationMatrixValue",
        "boCalibrationVectorSelector",
        "boCalibrationVectorValueSelector",
        "boCalibrationVectorValue",
        "boGeometryDistortionValueSelector",
        "boGeometryDistortionValue",
        "boCalibrationFocalLength",
        "boCalibrationAngularAperture",
        "boCalibrationDataSave",
    ]:
        assert expect in names, f"missing {expect}"
    # rvec + tvec selectors both used
    vals = [v for n, m, v in log if n == "boCalibrationVectorSelector"]
    assert vals == ["rvec", "tvec"]
