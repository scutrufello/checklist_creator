"""User-uploaded card photos: storage, auto-crop, and SMB-safe writes."""
from __future__ import annotations

import io
import logging
import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

PhotoSide = Literal["front", "back"]
VALID_PHOTO_SIDES = frozenset({"front", "back"})

CARD_ASPECT = 5 / 7  # width / height
MAX_LONG_EDGE = 1200
USER_UPLOADS_DIR = "user-uploads"
STAGING_DIR = ".staging"


@dataclass
class CropBox:
    x: int
    y: int
    width: int
    height: int

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class ProcessUploadResult:
    original_rel: str
    preview_rel: str
    suggested_crop: CropBox
    auto_detected: bool


def user_photos_enabled(config: dict) -> bool:
    return bool(config.get("features", {}).get("user_card_photos", False))


def _sid_dir(tcdb_sid: int | str) -> str:
    return os.path.join(USER_UPLOADS_DIR, str(tcdb_sid))


def _normalize_side(side: str) -> PhotoSide:
    s = (side or "front").strip().lower()
    if s not in VALID_PHOTO_SIDES:
        raise ValueError("side must be 'front' or 'back'")
    return s  # type: ignore[return-value]


def _file_stem(card_id: int, side: PhotoSide) -> str:
    return f"card-{card_id}-{side}"


def staging_paths(
    image_root: str, tcdb_sid: int | str, card_id: int, side: PhotoSide = "front"
) -> dict[str, str]:
    base = os.path.join(image_root, _sid_dir(tcdb_sid), STAGING_DIR)
    stem = _file_stem(card_id, side)
    return {
        "dir": base,
        "original": os.path.join(base, f"{stem}-original.jpg"),
        "preview": os.path.join(base, f"{stem}-preview.jpg"),
        "original_rel": os.path.join(_sid_dir(tcdb_sid), STAGING_DIR, f"{stem}-original.jpg"),
        "preview_rel": os.path.join(_sid_dir(tcdb_sid), STAGING_DIR, f"{stem}-preview.jpg"),
    }


def final_paths(
    image_root: str, tcdb_sid: int | str, card_id: int, side: PhotoSide = "front"
) -> dict[str, str]:
    base = os.path.join(image_root, _sid_dir(tcdb_sid))
    stem = _file_stem(card_id, side)
    return {
        "processed": os.path.join(base, f"{stem}.jpg"),
        "original": os.path.join(base, f"{stem}-original.jpg"),
        "processed_rel": os.path.join(_sid_dir(tcdb_sid), f"{stem}.jpg"),
        "original_rel": os.path.join(_sid_dir(tcdb_sid), f"{stem}-original.jpg"),
    }


def write_bytes(path: str, data: bytes) -> None:
    """Write to image root; use devagent group when SMB mount is not writable."""
    directory = os.path.dirname(path)
    if os.path.isdir(directory) and os.access(directory, os.W_OK):
        with open(path, "wb") as fh:
            fh.write(data)
        return

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        cmd = (
            f"mkdir -p {shlex.quote(directory)} && "
            f"cp {shlex.quote(tmp_path)} {shlex.quote(path)}"
        )
        result = subprocess.run(
            ["sg", "devagent", "-c", cmd],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise OSError(
                f"Failed to write {path} via devagent: {result.stderr.strip() or result.stdout}"
            )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def remove_path(path: str) -> None:
    if not os.path.isfile(path):
        return
    try:
        os.unlink(path)
        return
    except OSError:
        pass
    subprocess.run(
        ["sg", "devagent", "-c", f"rm -f {shlex.quote(path)}"],
        capture_output=True,
        text=True,
    )


def _load_bgr(data: bytes):
    import numpy as np
    import cv2

    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _encode_jpeg(bgr, quality: int = 90) -> bytes:
    import cv2

    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise ValueError("JPEG encode failed")
    return buf.tobytes()


def _order_quad_points(pts):
    import numpy as np

    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _detect_quad(bgr):
    import cv2
    import numpy as np

    h, w = bgr.shape[:2]
    scale = 1.0
    if max(h, w) > 1600:
        scale = 1600 / max(h, w)
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)))
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 0)
    edged = cv2.Canny(gray, 40, 140)
    contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:12]
    img_area = bgr.shape[0] * bgr.shape[1]
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < img_area * 0.08:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) == 4:
            pts = approx.reshape(4, 2).astype("float32") / scale
            return _order_quad_points(pts)
    return None


def _warp_card(bgr, quad):
    import cv2
    import numpy as np

    (tl, tr, br, bl) = quad
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_w = int(max(width_a, width_b))
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_h = int(max(height_a, height_b))
    if max_w < 40 or max_h < 40:
        return None
    dst = np.array(
        [[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(quad.astype("float32"), dst)
    return cv2.warpPerspective(bgr, matrix, (max_w, max_h))


def _fit_aspect_and_resize(bgr):
    import cv2

    h, w = bgr.shape[:2]
    target_w = min(w, int(h * CARD_ASPECT))
    target_h = min(h, int(w / CARD_ASPECT))
    x0 = max(0, (w - target_w) // 2)
    y0 = max(0, (h - target_h) // 2)
    cropped = bgr[y0 : y0 + target_h, x0 : x0 + target_w]
    long_edge = max(cropped.shape[0], cropped.shape[1])
    if long_edge > MAX_LONG_EDGE:
        scale = MAX_LONG_EDGE / long_edge
        cropped = cv2.resize(
            cropped,
            (int(cropped.shape[1] * scale), int(cropped.shape[0] * scale)),
            interpolation=cv2.INTER_AREA,
        )
    return cropped


def _quad_to_crop_box(quad, img_w: int, img_h: int) -> CropBox:
    import numpy as np

    xs = quad[:, 0]
    ys = quad[:, 1]
    x0 = int(max(0, np.min(xs)))
    y0 = int(max(0, np.min(ys)))
    x1 = int(min(img_w, np.max(xs)))
    y1 = int(min(img_h, np.max(ys)))
    return CropBox(x=x0, y=y0, width=max(1, x1 - x0), height=max(1, y1 - y0))


def _center_crop_box(w: int, h: int) -> CropBox:
    if w / h > CARD_ASPECT:
        crop_h = h
        crop_w = int(h * CARD_ASPECT)
    else:
        crop_w = w
        crop_h = int(w / CARD_ASPECT)
    return CropBox(
        x=(w - crop_w) // 2,
        y=(h - crop_h) // 2,
        width=crop_w,
        height=crop_h,
    )


def process_upload(
    data: bytes,
    image_root: str,
    tcdb_sid: int | str,
    card_id: int,
    side: PhotoSide = "front",
) -> ProcessUploadResult:
    side = _normalize_side(side)
    bgr = _load_bgr(data)
    if bgr is None:
        raise ValueError("Could not decode image (use JPEG or PNG)")

    paths = staging_paths(image_root, tcdb_sid, card_id, side)
    write_bytes(paths["original"], data)

    h, w = bgr.shape[:2]
    quad = _detect_quad(bgr)
    auto_detected = quad is not None
    if quad is not None:
        warped = _warp_card(bgr, quad)
        preview = _fit_aspect_and_resize(warped) if warped is not None else _fit_aspect_and_resize(bgr)
        suggested = _quad_to_crop_box(quad, w, h)
    else:
        preview = _fit_aspect_and_resize(bgr)
        suggested = _center_crop_box(w, h)

    write_bytes(paths["preview"], _encode_jpeg(preview))
    return ProcessUploadResult(
        original_rel=paths["original_rel"].replace("\\", "/"),
        preview_rel=paths["preview_rel"].replace("\\", "/"),
        suggested_crop=suggested,
        auto_detected=auto_detected,
    )


def apply_crop_from_original(
    image_root: str,
    tcdb_sid: int | str,
    card_id: int,
    crop: CropBox,
    side: PhotoSide = "front",
) -> str:
    side = _normalize_side(side)
    paths = staging_paths(image_root, tcdb_sid, card_id, side)
    if not os.path.isfile(paths["original"]):
        raise FileNotFoundError("Staging original not found; upload again")

    with open(paths["original"], "rb") as fh:
        bgr = _load_bgr(fh.read())
    if bgr is None:
        raise ValueError("Could not read staging original")

    h, w = bgr.shape[:2]
    x0 = max(0, min(w - 1, crop.x))
    y0 = max(0, min(h - 1, crop.y))
    x1 = max(x0 + 1, min(w, crop.x + crop.width))
    y1 = max(y0 + 1, min(h, crop.y + crop.height))
    cropped = bgr[y0:y1, x0:x1]
    final = _fit_aspect_and_resize(cropped)

    finals = final_paths(image_root, tcdb_sid, card_id, side)
    write_bytes(finals["processed"], _encode_jpeg(final))
    # Keep original backup for rollback / re-crop
    write_bytes(finals["original"], open(paths["original"], "rb").read())

    remove_path(paths["original"])
    remove_path(paths["preview"])
    return finals["processed_rel"].replace("\\", "/")


def delete_user_photo(
    image_root: str,
    tcdb_sid: int | str,
    card_id: int,
    side: PhotoSide = "front",
) -> None:
    side = _normalize_side(side)
    finals = final_paths(image_root, tcdb_sid, card_id, side)
    staging = staging_paths(image_root, tcdb_sid, card_id, side)
    for path in (
        finals["processed"],
        finals["original"],
        staging["original"],
        staging["preview"],
    ):
        remove_path(path)


def delete_user_front(image_root: str, tcdb_sid: int | str, card_id: int) -> None:
    """Backward-compatible alias."""
    delete_user_photo(image_root, tcdb_sid, card_id, "front")
