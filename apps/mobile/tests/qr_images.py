"""Generate REAL QR images (qrcode library, same call the label generator uses) and wrap them in photo-like conditions.
No decoder is stubbed anywhere in the tests that use this module."""
import cv2
import numpy as np
import qrcode

BG = (150, 140, 130)


def qr_array(payload: str, box_size=10):
    return np.array(qrcode.make(payload, box_size=box_size).convert("RGB"))


def photo_like(qr, W=1600, H=1200, scale=0.25, angle=0, persp=0.0, blur=0.0, noise=0.0, jpeg=95, contrast=1.0, pos=(0.5, 0.5), seed=1) -> bytes:
    rng = np.random.default_rng(seed)
    grad = np.linspace(0.7, 1.1, W)[None, :, None]
    bg = (np.full((H, W, 3), BG, np.float32) * grad).clip(0, 255).astype(np.uint8)
    s = int(min(W, H) * scale)
    q = cv2.resize(qr, (s, s), interpolation=cv2.INTER_AREA)
    pad = cv2.copyMakeBorder(q, s // 10, s // 10, s // 10, s // 10, cv2.BORDER_CONSTANT, value=(235, 235, 230))
    h, w = pad.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += nw / 2 - w / 2
    M[1, 2] += nh / 2 - h / 2
    rot = cv2.warpAffine(pad, M, (nw, nh), borderValue=BG)
    if persp:
        src = np.float32([[0, 0], [nw, 0], [nw, nh], [0, nh]])
        d = persp * nw
        dst = np.float32([[d, d * 0.5], [nw - d * 0.3, 0], [nw, nh], [0, nh - d]])
        rot = cv2.warpPerspective(rot, cv2.getPerspectiveTransform(src, dst), (nw, nh), borderValue=BG)
    x, y = int((W - nw) * pos[0]), int((H - nh) * pos[1])
    bg[y:y + nh, x:x + nw] = rot
    img = bg.astype(np.float32)
    if contrast != 1.0:
        img = (img - 128) * contrast + 128
    if noise:
        img += rng.normal(0, noise, img.shape)
    img = img.clip(0, 255).astype(np.uint8)
    if blur:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
    assert ok
    return buf.tobytes()


def raw_image(img_bgr, ext=".jpg") -> bytes:
    ok, buf = cv2.imencode(ext, img_bgr)
    assert ok
    return buf.tobytes()
