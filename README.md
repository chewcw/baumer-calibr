# baumer-calibration

Simple CLI to calibrate Baumer VCXx.2 / VCXU.2 cameras (OpenCV) and store the results in the camera's
`boCalibrationData` features (Users Guide §11.19), so downstream apps read `K + dist + rvec/tvec`
from the camera itself instead of a sidecar YAML.

> The camera does **not** calibrate itself. Per manual §11.19: *"Calibration must be performed using
> external software"* — this tool is that external software (OpenCV), and the camera is the storage.

## Install

Requires Python >=3.11,<3.14 (neoAPI wheel caps at cp313).

```bash
uv sync --python 3.11          # or: pip install -e .
uv sync --python 3.11 --extra dev   # + pytest
```

### neoAPI (needed for `capture` / `upload` / `read` / camera `verify`)

The Baumer Python binding is in `vendor/`. Install the bundled wheel — **never** `pip install neoapi`
from PyPI (different vendor, same name):

```bash
mkdir -p /tmp/neoapi && tar xzf vendor/Baumer_neoAPI_*_python.tar.gz -C /tmp/neoapi
uv pip install /tmp/neoapi/wheel/*.whl
```

`calibrate`, `make-board` and folder-based `verify` work without neoAPI/camera.

## Usage

```bash
# 1. printable target (checkerboard or Charuco), then print it flat (no scaling)
baumer-calib make-board --pattern charuco --nx 7 --ny 5 --square-px 200 --out board.png
baumer-calib make-board --pattern checkerboard --nx 9 --ny 6 --out board.png

# 2. grab >=15-20 views: fill frame, vary tilt/depth, keep all corners visible
baumer-calib capture --out shots -n 20 --pattern checkerboard --pattern-size 9x6 --square 25

# 3. calibrate -> YAML sidecar (works on any image folder, no camera needed)
baumer-calib calibrate shots --pattern checkerboard --pattern-size 9x6 --square 25 \
    --focal 16 --aperture 45 --out calib.yaml

# 4. upload into camera boCalibrationData + persist (boCalibrationDataSave, UserSet1)
baumer-calib upload calib.yaml --focal 16 --aperture 45

# 5. read back from camera and compare
baumer-calib read

# 6. undistort preview: from live camera, or from a folder
baumer-calib verify calib.yaml                    # live camera
baumer-calib verify calib.yaml --source shots     # offline, writes undistorted_*.png
```

`--square` / `--focal` are in **mm**, `--aperture` in **degrees**, `--exposure` in **µs**.
`--device` selects a specific camera when several are connected; accepts a serial number or an IP address (GigE); `--no-userset` skips `UserSetSave`.

## What gets written (§11.19 mapping)

| OpenCV result | Camera feature |
|---|---|
| `cameraMatrix` 3x3 | `boCalibrationMatrixSelector=Camera Matrix` + `boCalibrationMatrixValueSelector=Value 11..33` + `boCalibrationMatrixValue` |
| `getOptimalNewCameraMatrix(...)` | same, `Selector=New Camera Matrix` |
| `distCoeffs (k1,k2,p1,p2,k3)` | `boGeometryDistortionValueSelector=k1,k2,k3,p1,p2` + `boGeometryDistortionValue` |
| best-view `rvec`, `tvec` | `boCalibrationVectorSelector=rvec/tvec` + `ValueSelector=Value 1..3` + `boCalibrationVectorValue` |
| lens datasheet | `boCalibrationFocalLength`, `boCalibrationAngularAperture` |

Write sequence: `boCalibrationDataConfigurationMode=On` → all selectors/values →
`boCalibrationDataSave` (Execute) → `UserSetSelector=UserSet1` + `UserSetSave` → mode `Off`.

**Note (doc vs hardware):** §11.19 lists `MatrixValue/VectorValue/DistortionValue` as *read only*.
The tool writes them with `ConfigurationMode=On` — the hypothesis is they become writable in config
mode. If a write raises `not writable`, run `baumer-calib read` first to confirm feature presence and
report back; fallback is storing YAML sidecar only (the camera path just fails loudly).

The YAML sidecar additionally keeps **all** per-view `rvecs_all` / `tvecs_all` and per-view errors;
only the best-RMS view goes into the camera (camera stores one rvec/tvec pair).

## Calibration quality checklist

- >=15 accepted views, ideally 20-30; RMS well under 1 px (`RMS=` printed by `calibrate`).
- Squares >= 20x20 px on sensor, >= 6x8 squares visible (same rule as Camera Explorer §10.7).
- Vary pose: tilt around both axes, two rotations of the board, distances — pure translations hurt
  the distortion solve.
- The Baumer **SmartGrid** PDFs in `/opt/baumer-camera-explorer/bin/calibration/` also work with the
  checkerboard detector if printed at exact scale; Charuco is more forgiving of partial views.
- This is unrelated to Camera Explorer's *Shading Correction* / *Distortion Correction* files
  (§10.6-10.7) — those are Explorer-only preview corrections, not `boCalibrationData`.

## Development

```bash
uv run --python 3.11 --extra dev pytest -q    # 6 tests
```

Tests cover: synthetic `projectPoints` views recovering known `K` (<1px), YAML roundtrip, pattern
detection on rendered boards (checkerboard + Charuco), OpenCV↔Baumer dist coeff ordering, and a
mocked-feature test asserting the upload touches every `boCalibrationData` feature in the §11.19
order.

No camera required for tests or `calibrate`; `capture/upload/read` degrade to a clear install hint if
neoapi is missing.

## Standalone builds & releases

`scripts/build.py` produces a self-contained executable bundle (PyInstaller `--onedir`, no Python
required on target):

```bash
uv run python scripts/build.py            # version from pyproject
BUILD_VERSION=v0.1.0 uv run python scripts/build.py   # or from git tag
```

Output: `dist/baumer-calib/` plus `dist/baumer-calib-<version>-<os>-<arch>.tar.gz|.zip` and a
`.sha256` sidecar. The script auto-detects the platform, installs the matching vendor neoAPI wheel
(Linux/Windows; macOS builds offline-only since Baumer ships no macOS wheel), runs a smoke test on
the produced binary, and fails loudly if anything is off.

CI: `.github/workflows/build.yml` runs tests + builds on **ubuntu-22.04, windows-latest,
macos-latest** for every push/PR, and on a `v*` tag additionally creates a **GitHub Release** with
all three archives + checksums and install instructions:

```bash
git tag v0.1.0 && git push origin v0.1.0
```


