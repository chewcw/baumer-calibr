"""baumer_calib: simple CLI to calibrate Baumer cameras.

Pipeline: capture (neoAPI) -> calibrate (OpenCV) -> upload (boCalibrationData) -> verify.
The camera itself cannot self-calibrate (Baumer Users Guide §11.19 requires external
software), so this tool is that external software and the camera stores the result.
"""

from baumer_calib.models import CalibrationResult

__all__ = ["CalibrationResult"]
