"""Server-side QR decoding from a phone photo (OpenCV), with explicit, reported fallbacks.

Returns a QRResult instead of a bare string so the caller can tell 'nothing found' from 'two different codes in the
photo' (never guess between labels) and from 'image format not readable' (e.g. HEIC without the optional decoder).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

HEIF_AVAILABLE = False
try:  # optional: pillow-heif lets the server read iPhone HEIC photos
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    HEIF_AVAILABLE = True
except Exception:  # noqa: BLE001
    pass

MAX_SIDE = 2400


@dataclass
class QRResult:
    values: list = field(default_factory=list)   # distinct decoded strings, in detection order
    status: str = "NOT_DETECTED"                 # OK | AMBIGUOUS | NOT_DETECTED | IMAGE_UNREADABLE | HEIC_UNSUPPORTED
    strategy: str = ""
    detail: str = ""

    @property
    def value(self) -> str:
        return self.values[0] if len(self.values) == 1 else ""


def is_heic(raw: bytes) -> bool:
    return raw[4:8] == b"ftyp" and raw[8:12] in (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1")


def load_bgr(raw: bytes):
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is not None:
        return img, ""
    if is_heic(raw):
        if not HEIF_AVAILABLE:
            return None, "HEIC"
    try:
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
        return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR), "pillow"
    except Exception:  # noqa: BLE001
        return None, "UNREADABLE"


def _distinct(vals):
    out = []
    for v in vals:
        v = (v or "").strip()
        if v and v not in out:
            out.append(v)
    return out


def decode_qr(raw: bytes) -> QRResult:
    import cv2
    img, how = load_bgr(raw)
    if img is None:
        if how == "HEIC":
            return QRResult(status="HEIC_UNSUPPORTED", detail="HEIC photo but the server has no HEIC decoder (install pillow-heif)")
        return QRResult(status="IMAGE_UNREADABLE", detail="image could not be decoded")
    h, w = img.shape[:2]
    if max(h, w) > MAX_SIDE:
        s = MAX_SIDE / max(h, w)
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    det = cv2.QRCodeDetector()

    def passes():
        yield "direct", img
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        yield "clahe", cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
        yield "upscale2x", cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        blur = cv2.GaussianBlur(gray, (0, 0), 3)
        yield "unsharp", cv2.addWeighted(gray, 2.5, blur, -1.5, 0)
        yield "otsu", cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    for name, im in passes():
        vals = []
        try:
            ok, multi, _, _ = det.detectAndDecodeMulti(im)
            if ok:
                vals = _distinct(multi)
        except Exception:  # noqa: BLE001
            pass
        if not vals:
            try:
                vals = _distinct([det.detectAndDecode(im)[0]])
            except Exception:  # noqa: BLE001
                vals = []
        if vals:
            return QRResult(values=vals, status="OK" if len(vals) == 1 else "AMBIGUOUS", strategy=name,
                            detail="" if len(vals) == 1 else f"{len(vals)} different QR codes in one photo")
    return QRResult(status="NOT_DETECTED", detail="no QR decoded by any pass")
