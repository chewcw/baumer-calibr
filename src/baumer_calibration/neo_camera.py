"""neoAPI camera backend.

Install first (wheel caps at cp3.13, so project pins python <3.14):
    untar vendor/Baumer_neoAPI_*_python.tar.gz, then pip install wheel/*.whl
    (NOT PyPI 'neoapi' - different vendor!)

Manual 11.19 write flow (hypothesis: Matrix/Vector/Distortion values become
writable with boCalibrationDataConfigurationMode=On; doc lists them RO):
    1. ConfigurationMode = On
    2. selectors + values, 3. boCalibrationDataSave, 4. mode Off
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

MATRIX_CELLS = [
    "Value 11",
    "Value 12",
    "Value 13",
    "Value 21",
    "Value 22",
    "Value 23",
    "Value 31",
    "Value 32",
    "Value 33",
]
DIST_KEYS = ["k1", "k2", "k3", "p1", "p2"]


def _get_neoapi():
    try:
        import neoapi
    except ImportError as e:
        raise RuntimeError(
            "neoapi not installed. Untar vendor/Baumer_neoAPI_*_python.tar.gz and "
            "pip install the wheel inside wheel/. Do NOT pip install 'neoapi' from PyPI."
        ) from e
    return neoapi


@dataclass
class NeoCamera:
    cam: object = None
    serial: str = ""

    def connect(self, serial: str = "") -> "NeoCamera":
        neoapi = _get_neoapi()
        self.serial = serial
        self.cam = neoapi.Cam()
        if serial:
            self.cam.Connect(serial)
        else:
            self.cam.Connect()
        return self

    def disconnect(self):
        try:
            if self.cam is not None:
                self.cam.Disconnect()
        except Exception:
            pass
        self.cam = None

    def setup_capture(self, pixel_format: str = "Mono8", exposure_us: float = 10000.0):
        f = self.cam.f
        try:
            if f.PixelFormat.GetEnumValueList().IsReadable(pixel_format):
                f.PixelFormat.SetString(pixel_format)
        except Exception:
            pass
        try:
            f.ExposureTime.Set(float(exposure_us))
        except Exception:
            pass

    def grab_np(self) -> np.ndarray:
        img = self.cam.GetImage()
        if img.IsEmpty():
            raise RuntimeError("empty frame")
        return np.ascontiguousarray(img.GetNPArray())

    def _feat(self, name: str):
        try:
            return getattr(self.cam.f, name)
        except Exception as e:
            raise RuntimeError(f"camera lacks feature {name}: {e}") from e

    def set_config_mode(self, on: bool = True):
        self._feat("boCalibrationDataConfigurationMode").SetString(
            "On" if on else "Off"
        )

    @staticmethod
    def _set_float(feat, value: float, label: str):
        for meth in ("Set", "SetDouble", "SetValue"):
            if hasattr(feat, meth):
                try:
                    getattr(feat, meth)(float(value))
                    return
                except Exception:
                    continue
        raise RuntimeError(
            f"feature {label} not writable (tried Set/SetDouble). "
            "Is boCalibrationDataConfigurationMode=On?"
        )

    def write_matrix(self, matrix: np.ndarray, which: str = "Camera Matrix"):
        sel = self._feat("boCalibrationMatrixSelector")
        vsel = self._feat("boCalibrationMatrixValueSelector")
        val = self._feat("boCalibrationMatrixValue")
        sel.SetString(which)
        m = np.asarray(matrix, float).reshape(3, 3)
        for cell, v in zip(MATRIX_CELLS, m.ravel()):
            vsel.SetString(cell)
            self._set_float(val, float(v), f"{which}/{cell}")

    def write_vector(self, vec: np.ndarray, which: str):
        sel = self._feat("boCalibrationVectorSelector")
        vsel = self._feat("boCalibrationVectorValueSelector")
        val = self._feat("boCalibrationVectorValue")
        sel.SetString(which)  # rvec | tvec
        for i, v in enumerate(np.ravel(vec)[:3], start=1):
            vsel.SetString(f"Value {i}")
            self._set_float(val, float(v), f"{which}[{i}]")

    def write_distortion(self, dist_bo_order: dict) -> None:
        sel = self._feat("boGeometryDistortionValueSelector")
        val = self._feat("boGeometryDistortionValue")
        for k in DIST_KEYS:
            sel.SetString(k)
            self._set_float(val, float(dist_bo_order[k]), f"dist/{k}")

    def write_metadata(self, focal_mm: float, aperture_deg: float) -> None:
        if focal_mm:
            self._set_float(
                self._feat("boCalibrationFocalLength"), float(focal_mm), "focal"
            )
        if aperture_deg:
            self._set_float(
                self._feat("boCalibrationAngularAperture"),
                float(aperture_deg),
                "aperture",
            )

    def save(self, persist_userset: bool = True) -> None:
        self._feat("boCalibrationDataSave").Execute()
        if persist_userset:
            try:
                self.cam.f.UserSetSelector.SetString("UserSet1")
                self.cam.f.UserSetSave.Execute()
            except Exception:
                pass

    @staticmethod
    def _get_float(feat) -> float:
        if hasattr(feat, "Get"):
            return float(feat.Get())
        return float(feat.GetDouble())

    def read_matrix(self, which: str = "Camera Matrix") -> np.ndarray:
        sel = self._feat("boCalibrationMatrixSelector")
        vsel = self._feat("boCalibrationMatrixValueSelector")
        val = self._feat("boCalibrationMatrixValue")
        sel.SetString(which)
        out = []
        for cell in MATRIX_CELLS:
            vsel.SetString(cell)
            out.append(self._get_float(val))
        return np.array(out, float).reshape(3, 3)

    def read_vector(self, which: str) -> np.ndarray:
        sel = self._feat("boCalibrationVectorSelector")
        vsel = self._feat("boCalibrationVectorValueSelector")
        val = self._feat("boCalibrationVectorValue")
        sel.SetString(which)
        out = []
        for i in (1, 2, 3):
            vsel.SetString(f"Value {i}")
            out.append(self._get_float(val))
        return np.array(out, float)

    def read_distortion(self) -> dict:
        sel = self._feat("boGeometryDistortionValueSelector")
        val = self._feat("boGeometryDistortionValue")
        d: dict = {}
        for k in DIST_KEYS:
            sel.SetString(k)
            d[k] = self._get_float(val)
        return d

    def upload(
        self,
        res,
        focal_mm: float = 0.0,
        aperture_deg: float = 0.0,
        persist_userset: bool = True,
    ) -> None:
        self.set_config_mode(True)
        try:
            self.write_matrix(res.camera_matrix, "Camera Matrix")
            self.write_matrix(res.new_camera_matrix, "New Camera Matrix")
            self.write_vector(res.rvec, "rvec")
            self.write_vector(res.tvec, "tvec")
            self.write_distortion(res.dist_bo_order)
            self.write_metadata(
                focal_mm or res.focal_length_mm,
                aperture_deg or res.angular_aperture_deg,
            )
        finally:
            try:
                self.save(persist_userset)
            finally:
                self.set_config_mode(False)
