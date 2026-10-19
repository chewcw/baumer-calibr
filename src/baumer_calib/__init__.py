"""baumer_calib: simple CLI to calibrate Baumer cameras.

Pipeline: capture (neoAPI) -> calibrate (OpenCV) -> upload (boCalibrationData) -> verify.
See Baumer VCXG.2/VCXU.2 manual section 11.19.
"""

from baumer_calib.models import CalibrationResult

__all__ = ["CalibrationResult"]
