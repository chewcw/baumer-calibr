"""CLI: baumer-calib capture|calibrate|upload|verify|make-board|read"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np


def _to_gray(img: np.ndarray) -> np.ndarray:
    """Normalize any camera/disk frame to 2D uint8 single-channel gray.

    Baumer neoAPI Mono8 ``GetNPArray()`` returns ``(H, W, 1)`` (ndim==3,
    1 channel), not ``(H, W)``. The old ``img if img.ndim == 2 else
    cvtColor(BGR2GRAY)`` check sent that (H,W,1) frame into
    ``COLOR_BGR2GRAY`` (expects 3/4 channels) -> ``scn is 1`` crash.
    """
    a = np.asarray(img)
    if a.ndim == 2:
        gray = a
    elif a.ndim == 3:
        c = a.shape[2]
        if c == 1:
            gray = np.ascontiguousarray(a[:, :, 0])
        elif c == 3:
            gray = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
        elif c == 4:
            gray = cv2.cvtColor(a, cv2.COLOR_BGRA2GRAY)
        else:
            raise ValueError(f"unsupported image shape {a.shape} dtype={a.dtype}")
    else:
        raise ValueError(f"unsupported image shape {a.shape} dtype={a.dtype}")
    if gray.dtype != np.uint8:
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return np.ascontiguousarray(gray)


def _gray_to_bgr(gray: np.ndarray) -> np.ndarray:
    g = _to_gray(gray)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)


def _cmd_capture(a) -> int:
    from baumer_calib.neo_camera import NeoCamera
    from baumer_calib.patterns import detect, parse_pattern_size

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    psize = parse_pattern_size(a.pattern_size)
    cam = NeoCamera().connect(a.device or "")
    try:
        cam.setup_capture(a.pixel_format, a.exposure)
        saved = 0
        print(
            f"aim {a.pattern} {a.pattern_size} at camera, [space]=save [q]=quit n={a.n}"
        )
        while saved < a.n:
            frame = cam.grab_np()
            print(
                f"[capture] frame shape={np.shape(frame)} "
                f"dtype={np.asarray(frame).dtype} cv2={cv2.__version__}",
                flush=True,
            )
            gray = _to_gray(frame)
            det = detect(gray, a.pattern, psize, a.square, a.marker, a.aruco_dict)
            color = (0, 255, 0) if det.ok else (0, 0, 255)
            vis = _gray_to_bgr(gray)
            cv2.putText(
                vis,
                f"{saved}/{a.n} {det.info}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
            )
            if det.ok and det.image_points is not None:
                cv2.drawChessboardCorners(vis, psize, det.image_points, True)
            cv2.imshow("baumer-calib capture", vis)
            key = cv2.waitKey(30) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord(" ") and det.ok:
                p = out / f"img_{saved:03d}.png"
                cv2.imwrite(str(p), frame)
                saved += 1
                print(f"[{saved}/{a.n}] {p} {det.info}")
        print(f"saved {saved} -> {out}")
        return 0 if saved >= 3 else 2
    finally:
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        cam.disconnect()


def _iter_images(folder: Path):
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() in (".png", ".bmp", ".jpg", ".jpeg", ".tiff", ".tif"):
            img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
            if img is not None:
                yield p, img


def _cmd_calibrate(a) -> int:
    from baumer_calib.patterns import detect, parse_pattern_size
    from baumer_calib.calibrator import calibrate
    from baumer_calib.storage import save_yaml

    folder = Path(a.images)
    psize = parse_pattern_size(a.pattern_size)
    objp_list, imgp_list, size = [], [], None
    used, skipped = 0, 0
    for p, img in _iter_images(folder):
        gray = _to_gray(img)
        size = (gray.shape[1], gray.shape[0])
        det = detect(gray, a.pattern, psize, a.square, a.marker, a.aruco_dict)
        if det.ok:
            objp_list.append(det.object_points)
            imgp_list.append(det.image_points)
            used += 1
        else:
            skipped += 1
            print(f"skip {p.name}: {det.info}")
    print(f"valid {used}, skipped {skipped}")
    res = calibrate(objp_list, imgp_list, size, a.pattern, a.square, a.alpha)
    res.focal_length_mm = a.focal
    res.angular_aperture_deg = a.aperture
    save_yaml(res, a.out)
    print(f"RMS={res.rms_error:.4f}px size={res.image_size} -> {a.out}")
    print("K=\n", np.asarray(res.camera_matrix))
    print("dist(k1,k2,p1,p2,k3)=", np.ravel(res.dist_coeffs))
    print("best rvec=", np.ravel(res.rvec), " tvec=", np.ravel(res.tvec))
    return 0


def _cmd_upload(a) -> int:
    from baumer_calib.neo_camera import NeoCamera
    from baumer_calib.storage import load_yaml

    res = load_yaml(a.calib)
    if a.focal:
        res.focal_length_mm = a.focal
    if a.aperture:
        res.angular_aperture_deg = a.aperture
    cam = NeoCamera().connect(a.device or "")
    try:
        cam.upload(
            res,
            res.focal_length_mm,
            res.angular_aperture_deg,
            persist_userset=not a.no_userset,
        )
        print("uploaded K/newK/rvec/tvec/dist + metadata, saved to camera")
        return 0
    finally:
        cam.disconnect()


def _cmd_read(a) -> int:
    from baumer_calib.neo_camera import NeoCamera

    cam = NeoCamera().connect(a.device or "")
    try:
        print("Camera Matrix:\n", cam.read_matrix("Camera Matrix"))
        print("New Camera Matrix:\n", cam.read_matrix("New Camera Matrix"))
        print("rvec:", cam.read_vector("rvec"))
        print("tvec:", cam.read_vector("tvec"))
        print("dist:", cam.read_distortion())
        try:
            print("focal:", cam._feat("boCalibrationFocalLength").Get())
            print("aperture:", cam._feat("boCalibrationAngularAperture").Get())
        except Exception as e:
            print(f"(metadata unreadable: {e})")
        return 0
    finally:
        cam.disconnect()


def _cmd_verify(a) -> int:
    from baumer_calib.neo_camera import NeoCamera
    from baumer_calib.storage import load_yaml

    res = load_yaml(a.calib)
    K = np.asarray(res.camera_matrix, float)
    dist = np.asarray(res.dist_coeffs, float)
    newK = np.asarray(res.new_camera_matrix, float)
    if a.source == "camera":
        cam = NeoCamera().connect(a.device or "")
        try:
            cam.setup_capture()
            while True:
                frame = cam.grab_np()
                gray = _to_gray(frame)
                und = cv2.undistort(gray, K, dist, None, newK)
                cv2.imshow(
                    "left=raw right=undistorted [q]=quit",
                    np.hstack([_gray_to_bgr(gray), _gray_to_bgr(und)]),
                )
                if cv2.waitKey(30) & 0xFF in (ord("q"), 27):
                    break
        finally:
            cam.disconnect()
            cv2.destroyAllWindows()
    else:
        for p, img in _iter_images(Path(a.source)):
            und = cv2.undistort(img, K, dist, None, newK)
            out = str(Path(a.source) / f"undistorted_{p.name}")
            cv2.imwrite(out, und)
            print(f"{p.name} -> {out}")
    return 0


def _cmd_board(a) -> int:
    from baumer_calib.patterns import (
        make_checkerboard_image,
        make_charuco_board_image,
    )

    if a.pattern == "charuco":
        img = make_charuco_board_image(a.nx, a.ny, a.square_px, 0.75, a.aruco_dict)
    else:
        img = make_checkerboard_image(a.nx, a.ny, a.square_px)
    cv2.imwrite(a.out, img)
    print(f"{a.pattern} {a.nx}x{a.ny} -> {a.out} ({img.shape[1]}x{img.shape[0]}px)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    from baumer_calib import __version__

    p = argparse.ArgumentParser(
        prog="baumer-calib",
        description="Calibrate Baumer camera, store in boCalibrationData",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("capture", help="grab N pattern images from camera")
    c.add_argument("--out", default="shots")
    c.add_argument("-n", type=int, default=20)
    c.add_argument(
        "--pattern", choices=["checkerboard", "charuco"], default="checkerboard"
    )
    c.add_argument("--pattern-size", default="9x6")
    c.add_argument("--square", type=float, default=25.0)
    c.add_argument("--marker", type=float, default=0.0)
    c.add_argument("--aruco-dict", default="DICT_5X5_100")
    c.add_argument("--device", default="")
    c.add_argument("--pixel-format", default="Mono8")
    c.add_argument("--exposure", type=float, default=10000.0)
    c.set_defaults(func=_cmd_capture)

    c = sub.add_parser("calibrate", help="calibrate from image folder -> yaml")
    c.add_argument("images")
    c.add_argument("--out", default="calib.yaml")
    c.add_argument(
        "--pattern", choices=["checkerboard", "charuco"], default="checkerboard"
    )
    c.add_argument("--pattern-size", default="9x6")
    c.add_argument("--square", type=float, default=25.0)
    c.add_argument("--marker", type=float, default=0.0)
    c.add_argument("--aruco-dict", default="DICT_5X5_100")
    c.add_argument("--alpha", type=float, default=0.0)
    c.add_argument("--focal", type=float, default=0.0)
    c.add_argument("--aperture", type=float, default=0.0)
    c.set_defaults(func=_cmd_calibrate)

    c = sub.add_parser("upload", help="write yaml -> camera boCalibrationData")
    c.add_argument("calib")
    c.add_argument("--device", default="")
    c.add_argument("--focal", type=float, default=0.0)
    c.add_argument("--aperture", type=float, default=0.0)
    c.add_argument("--no-userset", action="store_true")
    c.set_defaults(func=_cmd_upload)

    c = sub.add_parser("read", help="read back boCalibrationData")
    c.add_argument("--device", default="")
    c.set_defaults(func=_cmd_read)

    c = sub.add_parser("verify", help="undistort preview from camera or folder")
    c.add_argument("calib")
    c.add_argument("--source", default="camera")
    c.add_argument("--device", default="")
    c.set_defaults(func=_cmd_verify)

    c = sub.add_parser("make-board", help="render printable pattern PNG")
    c.add_argument("--pattern", choices=["checkerboard", "charuco"], default="charuco")
    c.add_argument("--nx", type=int, default=7)
    c.add_argument("--ny", type=int, default=5)
    c.add_argument("--square-px", type=int, default=200)
    c.add_argument("--aruco-dict", default="DICT_5X5_100")
    c.add_argument("--out", default="board.png")
    c.set_defaults(func=_cmd_board)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except Exception:
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
