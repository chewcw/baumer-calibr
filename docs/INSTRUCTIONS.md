# Operating instructions for baumer-calibration

The baumer-calibration program calculates the optical properties of one Baumer camera.
The program reads images of a printed pattern board.
From these images it calculates the camera matrix, the distortion coefficients, and the board pose.
The program writes the result to a YAML file and to the camera.
Every action below has a "Why" statement. Read the "Why" statement before you change an action.

## 1. Terms

| Term | Meaning |
|---|---|
| pattern board | A printed sheet with a grid of equal squares. The tool detects this grid in each image. |
| camera matrix (K) | A 3x3 matrix. It holds the focal lengths and the optical center of the camera, in pixels. |
| distortion coefficients | Five numbers: k1, k2, k3, p1, p2. They describe how the lens bends straight lines. |
| rvec, tvec | The rotation and the position of the board for one image. Rotation is an axis-angle vector. Translation is in millimeters. |
| RMS error | The average reprojection error, in pixels. Small values mean a good fit. |
| New Camera Matrix | A second matrix for the undistorted image. The tool calculates it from K, the distortion, and alpha. |
| alpha | A number from 0 to 1. It controls the trade-off between dark corners and cropped pixels. |
| boCalibrationData | The camera features that store calibration data. The camera manual describes them in section 11.19. |
| YAML file | The file calib.yaml. It holds all results of one calibration run. |

## 2. Before you start

### 2.1 Install the program (source runs only)

```bash
uv sync --extra dev
```

Why: The project needs Python 3.11, 3.12, or 3.13. The Baumer neoAPI wheel does not install on Python 3.14 or newer.

### 2.2 Install the Baumer neoAPI wheel (camera steps only)

```bash
mkdir -p /tmp/neoapi && tar xzf vendor/Baumer_neoAPI_*_python.tar.gz -C /tmp/neoapi
uv pip install /tmp/neoapi/wheel/*.whl
```

On Windows, expand `vendor/Baumer_neoAPI_1.6.0_win_x86_64_python.zip` and install the `.whl` file from its `wheel` folder.

Why: The steps capture, upload, and read need the Baumer SDK. Never install the PyPI package with the name `neoapi`. That package comes from a different vendor and breaks the camera connection.

### 2.3 Install the camera driver (Windows only)

Run `drivers/USB/Windows10_11/usbdriver-1_2_22-win-x86_64.msi` from the vendor zip. For GigE cameras, install the filter driver from `drivers/filterdriver/`.

Why: Windows needs a vendor driver to open the camera. Linux needs no driver. On Linux, copy `drivers/udev_rules/` to `/etc/udev/rules.d/` when non-root users must open the camera.

### 2.4 Check the camera connection

1. Connect the camera cable and the power.
2. Check that the camera appears in the network or in the USB device list.
3. Give the camera a static IP address when you use GigE. The tool `gevipconfig` is in the vendor zip.

Why: The program opens the first camera it finds. Use `--serial` when the computer has several cameras. The serial number selects one camera.

Note: You do not need Baumer Camera Explorer. The drivers and the network tool ship inside the vendor archive.

## 3. Print the pattern board

### 3.1 Render the board file

Checkerboard:

```bash
baumer-calib make-board --pattern checkerboard --nx 9 --ny 6 --square-px 120 --out board.png
```

Charuco:

```bash
baumer-calib make-board --pattern charuco --nx 7 --ny 5 --out board.png
```

Why: `--nx` and `--ny` are the counts of inner corners in one row and one column. The detector counts inner corners, so the calibrate step must use the same values.

### 3.2 Print the board

1. Print the file at 100 percent scale.
2. Switch off "fit to page" and "scale to fit".
3. Mount the print on a flat rigid surface.
4. Do not bend or fold the print.

Why: The square size is the length reference of the result. A print scale error becomes an error in the focal length and in the board distance.

### 3.3 Choose the pattern type

Use the charuco pattern when the camera sees only part of the board or when hands can cover the board.

Why: Each charuco corner has a fixed identifier. The detector finds the corner identity even when the view is partial. A checkerboard needs the full grid in view.

## 4. Capture images from the camera

### 4.1 Start the capture

```bash
baumer-calib capture --out shots -n 25 --pattern checkerboard --pattern-size 9x6 --square 25
```

Why: `-n` is the number of accepted images. The program saves one image for each press of the space bar.

### 4.2 Frame the board during capture

1. Fill most of the image with the board.
2. Keep the whole board inside the image.
3. Press the space bar only when the overlay shows green and all corners.
4. Press `q` to stop the capture.

Why: A green overlay means the detector sees the full pattern. Images with a red overlay have no usable corner data.

### 4.3 Collect enough views

1. Accept at least 15 images. 25 images give a more stable result.
2. Tilt the board around two different axes.
3. Change the distance between camera and board.
4. Place the board near each edge and in the center of the image.
5. Rotate the board between 0 and 90 degrees.

Why: The solver needs many different board orientations. Tilt separates the focal length from the distortion. Distance changes separate the focal length from the board size. Views from one position only give an unstable result.

### 4.4 Keep the images sharp

1. Add light or increase the exposure time when the image is dark.
2. Hold the board still during the exposure.
3. Focus the lens before the capture and do not touch it after that.

Why: Blur moves the detected corner positions. Corner errors become errors in the calibration result.

## 5. Calculate the calibration

### 5.1 Run the calibrate step

```bash
baumer-calib calibrate shots --pattern checkerboard --pattern-size 9x6 --square 25 \
    --focal 16 --aperture 45 --alpha 0 --out calib.yaml
```

Why: The program detects the pattern in each image of the folder `shots`. It then solves one least-squares problem over all images. The solve minimizes the distance between detected corners and predicted corners.

### 5.2 Set the flags

| Flag | Value | Why |
|---|---|---|
| `--pattern-size` | `9x6` | The count of inner corners. It must match the make-board values and the printed board. |
| `--square` | `25` | The real size of one square in millimeters. This value sets the length unit of the result. |
| `--focal`, `--aperture` | lens data sheet values | Metadata for the lens. The upload step stores them in the camera features for focal length and angular aperture. |
| `--alpha` | `0` or `1` | Use 0 to crop to valid pixels. Use 1 to keep all pixels. Dark corners can appear when you use 1. |

### 5.3 Read the result

The program prints the RMS reprojection error in pixels.

Accept the result when the RMS is smaller than 1 pixel.

Why: The RMS value measures the average distance between detected and predicted corners. A large RMS means bad images, wrong flag values, or too few views.

## 6. Check the calibration result

### 6.1 Create undistorted images

```bash
baumer-calib verify calib.yaml --source shots
```

The program writes one `undistorted_*.png` file for each image in `shots`.

### 6.2 Compare the images

1. Open one original image and one undistorted image.
2. Compare the straight edges of the board and the frame of the print.
3. Reject the calibration when lines are still curved.

Why: A good calibration makes straight lines look straight. Curved lines in the output show a bad fit. Do not upload a result with an RMS above 1 pixel. Capture new images instead.

## 7. Store the calibration in the camera

### 7.1 Run the upload

```bash
baumer-calib upload calib.yaml --focal 16 --aperture 45
```

### 7.2 What the upload does

1. The upload sets `boCalibrationDataConfigurationMode` to `On`.
2. It writes the camera matrix, the new camera matrix, `rvec`, `tvec`, and the five distortion coefficients.
3. It executes `boCalibrationDataSave`.
4. It saves the data in `UserSet1`.
5. It sets `boCalibrationDataConfigurationMode` to `Off`.

Why: The configuration mode protects the stored data from accidental changes. `boCalibrationDataSave` writes the data to the camera memory. `UserSet1` keeps the data after you remove power.

### 7.3 Read the data from the camera

```bash
baumer-calib read
```

Why: The read step proves that the camera accepted all values. Compare the printed matrix with the matrix in `calib.yaml`.

### 7.4 When a write fails

The manual lists the value features as read only. The tool writes them while the configuration mode is `On`. The write can fail on some camera models. Keep the YAML file when the write fails, and report the error message.

Why: Downstream programs can read the YAML file with the same data. The camera storage is a convenience, not a requirement.

## 8. Apply the correction in your application

### 8.1 Understand the two parts

The upload step stores the data in the camera. The upload does not change the image stream. Your application must apply the correction to each image.

Why: The camera sends the raw sensor image. The correction is a per-pixel remap, and the application owns that step.

### 8.2 Build the correction code

```python
import cv2
import numpy as np
import yaml

c = yaml.safe_load(open("calib.yaml"))
K = np.array(c["camera_matrix"])
dist = np.ravel(c["dist_coeffs_opencv_order_k1_k2_p1_p2_k3"])
newK = np.array(c["new_camera_matrix"])
w, h = c["image_size"]["width"], c["image_size"]["height"]

# Build the maps one time at start-up.
map1, map2 = cv2.initUndistortRectifyMap(K, dist, None, newK, (w, h), cv2.CV_32FC1)

# Apply the correction to each frame.
undistorted = cv2.remap(frame, map1, map2, cv2.INTER_LINEAR)
```

Why: The camera matrix and the distortion coefficients do not change while the lens does not move. The map build is expensive, so you do it one time. Each frame then needs only one call of `remap`.

### 8.3 Use the camera data instead of the file

Your application can read K, the distortion coefficients, and the new camera matrix from the camera features with the selector features of section 11.19.

Why: The calibration then travels with the camera. One YAML file per camera is no longer needed.

## 9. Rules for a new calibration

Do a new calibration when one of these events happens:

1. You remove the lens or replace the lens.
2. You change the focus or the zoom setting.
3. You drop the camera or hit the lens.
4. You change the resolution or the region of interest.
5. You change the image size in your application.

Why: The calibration describes one exact optical path. Any change in that optical path changes the distortion. Old coefficients then add error instead of removing it.

## 10. Common failures

| Message or sign | Cause | Action |
|---|---|---|
| `neoapi not installed` | The vendor wheel is missing in this environment. | Do step 2.2. Install the wheel from `vendor/`. |
| `No device with '' found` | No camera connection, no driver, or wrong camera selected. | Check cable and power. Do step 2.3 on Windows. Use `--serial` to select a camera. |
| `corners not found` | The board is too small, blurred, or covered. | Move the board closer. Add light. Keep the full board in view. |
| `need >=3 valid views, got 0` | The detector found no pattern in any image. | Check `--pattern`, `--pattern-size`, and the printed board. |
| `feature not writable` | The camera rejects the write of a value feature. | Do step 7.4. Keep the YAML file and report the message. |
| Curved lines in the output images | The calibration does not fit. | Check the print scale and the flag values. Capture new images. |
| RMS above 1 pixel | Too few views, blur, or wrong flags. | Apply the rules of step 4 and calibrate again. |

## 11. Build a standalone program (optional)

### 11.1 Build for this computer

```bash
uv run python scripts/build.py
```

Why: The build creates one folder `dist/baumer-calib/` with the program, Python, OpenCV, and neoAPI inside. The target computer needs no Python installation. The build runs a test of the program and creates a checksum file.

### 11.2 Release for all operating systems

```bash
git tag v0.1.0 && git push origin v0.1.0
```

Why: The version tag starts the GitHub workflow. The workflow builds for Linux, Windows, and macOS. The workflow then creates a GitHub release with three archives and three checksum files.

### 11.3 Platform notes

| Platform | Camera steps | Why |
|---|---|---|
| Linux x86-64 | Full function | The vendor archive contains the Linux wheel. |
| Windows 10/11 x64 | Full function after driver install | The vendor archive contains the Windows wheel and the drivers. |
| macOS arm64 | Offline steps only: calibrate, make-board, undistort a folder of images | Baumer delivers no neoAPI wheel for macOS. |

End of document.






