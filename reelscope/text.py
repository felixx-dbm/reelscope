import shutil
import subprocess
from pathlib import Path

from PIL import Image


def ocr(img: Path, langs: list[str]) -> list[dict]:
    """On-screen text with position and height relative to the frame (0..1, origin top-left)."""
    try:
        from ocrmac import ocrmac
    except ImportError:
        return _tesseract(img)
    res = ocrmac.OCR(str(img), recognition_level="accurate", language_preference=langs).recognize()
    out = []
    for text, conf, (x, y, w, h) in res:
        if conf < 0.4 or len(text.strip()) < 2:
            continue
        # Vision boxes use a bottom-left origin.
        out.append({"text": text.strip(), "conf": round(float(conf), 2), "x": round(x, 3), "y": round(1 - y - h, 3), "w": round(w, 3), "h": round(h, 3)})
    return out


def _tesseract(img: Path) -> list[dict]:
    if not shutil.which("tesseract"):
        return []
    res = subprocess.run(["tesseract", str(img), "-", "--psm", "11", "tsv"], capture_output=True, text=True)
    W, H = Image.open(img).size
    out = []
    for line in res.stdout.splitlines()[1:]:
        p = line.split("\t")
        if len(p) == 12 and p[11].strip() and float(p[10]) > 60:
            x, y, w, h = (int(v) for v in p[6:10])
            out.append({"text": p[11].strip(), "conf": round(float(p[10]) / 100, 2), "x": round(x / W, 3), "y": round(y / H, 3), "w": round(w / W, 3), "h": round(h / H, 3)})
    return out


def region(item: dict) -> str:
    cx, cy = item["x"] + item["w"] / 2, item["y"] + item["h"] / 2
    v = "top" if cy < 0.33 else "bottom" if cy > 0.66 else "middle"
    h = "left" if cx < 0.33 else "right" if cx > 0.66 else "center"
    return f"{v}-{h}"
