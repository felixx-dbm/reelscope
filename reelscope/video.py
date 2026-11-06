from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

W = 256


@dataclass
class FrameStats:
    luma: np.ndarray
    contrast: np.ndarray
    sat: np.ndarray
    diff: np.ndarray
    hist: np.ndarray
    tx: np.ndarray
    ty: np.ndarray
    scale: np.ndarray
    rot: np.ndarray
    hists: np.ndarray


@dataclass
class Shot:
    index: int
    start: int
    end: int
    transition_in: str
    burst: bool = False
    motion: str = "static"
    motion_detail: dict = field(default_factory=dict)
    look: dict = field(default_factory=dict)
    text: list = field(default_factory=list)
    keyframes: dict = field(default_factory=dict)


def scan(path: Path) -> tuple[FrameStats, float]:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    rows: list[tuple] = []
    hists: list[np.ndarray] = []
    prev_gray = None
    prev_hist = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h = int(frame.shape[0] * W / frame.shape[1])
        small = cv2.resize(frame, (W, h), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 4], [0, 180, 0, 256, 0, 256])
        cv2.normalize(hist, hist)
        hist = hist.flatten()
        diff = hdist = 0.0
        tx = ty = rot = 0.0
        scale = 1.0
        if prev_gray is not None:
            diff = float(np.abs(gray.astype(np.int16) - prev_gray.astype(np.int16)).mean() / 255)
            hdist = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
            pts = cv2.goodFeaturesToTrack(prev_gray, 150, 0.01, 6)
            if pts is not None and len(pts) >= 8:
                nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray, pts, None)
                good = st.flatten() == 1
                if good.sum() >= 8:
                    m, _ = cv2.estimateAffinePartial2D(pts[good], nxt[good], method=cv2.RANSAC)
                    if m is not None:
                        scale = float(np.hypot(m[0, 0], m[1, 0]))
                        rot = float(np.degrees(np.arctan2(m[1, 0], m[0, 0])))
                        tx, ty = float(m[0, 2] / W), float(m[1, 2] / W)
        rows.append((gray.mean() / 255, gray.std() / 255, hsv[..., 1].mean() / 255, diff, hdist, tx, ty, scale, rot))
        hists.append(hist)
        prev_gray, prev_hist = gray, hist
    cap.release()
    a = np.array(rows, dtype=float).T
    return FrameStats(*a, hists=np.array(hists)), fps


def _local_median(x: np.ndarray, r: int) -> np.ndarray:
    out = np.empty_like(x)
    for i in range(len(x)):
        win = np.concatenate([x[max(0, i - r) : i], x[i + 1 : i + 1 + r]])
        out[i] = np.median(win) if len(win) else 0
    return out


def detect(st: FrameStats, fps: float, sensitivity: float = 1.0) -> dict:
    n = len(st.luma)
    score = 0.5 * np.minimum(1, st.diff * 4) + 0.5 * st.hist
    med = _local_median(score, 7)
    thr = 0.28 / sensitivity
    cuts = [
        i for i in range(1, n)
        if score[i] > thr and score[i] > 2.5 * med[i] + 0.04
        and score[i] >= score[i - 1] and (i + 1 >= n or score[i] >= score[i + 1])
    ]

    white = (st.luma > 0.82) & (np.r_[0, np.diff(st.luma)] > 0.2) | (st.luma > 0.9)
    black = st.luma < 0.04
    flashes = _runs(white)
    blacks = _runs(black)

    # A flash produces a spike in and out; collapse those into a single flash transition.
    flash_frames = {f for a, b in flashes for f in range(a - 1, b + 2)}
    merged: list[tuple[int, str]] = []
    for c in cuts:
        kind = "flash" if c in flash_frames else "black" if any(a - 1 <= c <= b + 1 for a, b in blacks) else "hard"
        if merged and kind == "flash" and merged[-1][1] == "flash" and c - merged[-1][0] <= 8:
            continue
        merged.append((c, kind))

    hard = {c for c, _ in merged}
    soft = []
    for i in range(6, n - 6):
        if any(abs(i - c) <= 6 for c in hard):
            continue
        across = cv2.compareHist(st.hists[i - 6].astype(np.float32), st.hists[i + 6].astype(np.float32), cv2.HISTCMP_BHATTACHARYYA)
        if across > 0.55 and score[i - 6 : i + 6].max() < thr:
            if not soft or i - soft[-1] > 12:
                soft.append(i)
    for s in soft:
        merged.append((s, "soft"))
    merged.sort()

    bounds = [(0, "start")] + merged
    shots = []
    for k, (s, kind) in enumerate(bounds):
        e = bounds[k + 1][0] if k + 1 < len(bounds) else n
        if e > s:
            shots.append(Shot(len(shots), s, e, kind))

    bursts = []
    run_start = None
    for k in range(len(shots)):
        short = shots[k].end - shots[k].start <= 3
        if short and run_start is None:
            run_start = k
        if (not short or k == len(shots) - 1) and run_start is not None:
            last = k - 1 if not short else k
            if last - run_start + 1 >= 3:
                bursts.append((shots[run_start].start, shots[last].end))
                for s in shots[run_start : last + 1]:
                    s.burst = True
            run_start = None

    for s in shots:
        _motion(s, st, fps)

    activity = np.convolve(score, np.ones(9) / 9, "same")
    active = [(a, b) for a, b in _runs(activity > 0.3) if b - a >= 6]
    return {
        "score": score,
        "activity": active,
        "shots": shots,
        "flashes": flashes,
        "blacks": blacks,
        "bursts": bursts,
    }


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    out = []
    i = 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j + 1 < len(mask) and mask[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def _motion(shot: Shot, st: FrameStats, fps: float) -> None:
    a, b = shot.start + 1, shot.end
    if b - a < 2:
        shot.motion = "flash-frame" if b - a < 1 else "static"
        return
    tx, ty, sc, rot = st.tx[a:b], st.ty[a:b], st.scale[a:b], st.rot[a:b]
    zoom = float(np.exp(np.log(np.clip(sc, 0.5, 2)).mean() * fps) - 1)
    pan, tilt = float(tx.mean() * fps), float(ty.mean() * fps)
    spin = float(rot.mean() * fps)
    k = 5
    jitter = 0.0
    if len(tx) > k:
        smooth = np.convolve(tx, np.ones(k) / k, "same")
        smooth_y = np.convolve(ty, np.ones(k) / k, "same")
        jitter = float(np.hypot(tx - smooth, ty - smooth_y).std() * fps)
    peak = float(np.abs(tx).max() * fps)
    detail = {"zoom_per_s": round(zoom, 3), "pan_per_s": round(pan, 3), "tilt_per_s": round(tilt, 3),
              "rot_deg_per_s": round(spin, 2), "jitter": round(jitter, 3), "energy": round(float(st.diff[a:b].mean()), 4)}
    labels = []
    if peak > 1.5:
        labels.append("whip")
    if zoom > 0.06:
        labels.append("push-in")
    elif zoom < -0.06:
        labels.append("pull-out")
    if abs(pan) > 0.08:
        labels.append("pan-left" if pan > 0 else "pan-right")
    if abs(tilt) > 0.08:
        labels.append("tilt-up" if tilt > 0 else "tilt-down")
    if abs(spin) > 6:
        labels.append("rotate")
    if jitter > 0.35:
        labels.append("shake")
    shot.motion = "+".join(labels) or ("busy" if detail["energy"] > 0.06 else "static")
    shot.motion_detail = detail


def grab(path: Path, indices: list[int], out: Path, long_side: int = 960) -> dict[int, Path]:
    out.mkdir(parents=True, exist_ok=True)
    want = sorted(set(indices))
    saved: dict[int, Path] = {}
    cap = cv2.VideoCapture(str(path))
    i = 0
    wi = 0
    while wi < len(want):
        if not cap.grab():
            break
        if i == want[wi]:
            ok, frame = cap.retrieve()
            if ok:
                h, w = frame.shape[:2]
                f = long_side / max(h, w)
                if f < 1:
                    frame = cv2.resize(frame, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA)
                p = out / f"f{i:06d}.jpg"
                cv2.imwrite(str(p), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                saved[i] = p
            wi += 1
        i += 1
    cap.release()
    return saved


def look(img_path: Path) -> dict:
    img = cv2.imread(str(img_path))
    small = cv2.resize(img, (64, int(64 * img.shape[0] / img.shape[1])), interpolation=cv2.INTER_AREA)
    px = small.reshape(-1, 3).astype(np.float32)
    k = 5
    _, labels, centers = cv2.kmeans(px, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0), 3, cv2.KMEANS_PP_CENTERS)
    share = np.bincount(labels.flatten(), minlength=k) / len(labels)
    order = np.argsort(-share)
    palette = [{"hex": "#%02x%02x%02x" % tuple(int(c) for c in centers[j][::-1]), "share": round(float(share[j]), 3)} for j in order]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    b, g, r = (img[..., c].mean() / 255 for c in range(3))
    luma = hsv[..., 2] / 255
    return {
        "palette": palette,
        "brightness": round(float(luma.mean()), 3),
        "contrast": round(float(luma.std()), 3),
        "saturation": round(float(hsv[..., 1].mean() / 255), 3),
        "warmth": round(float(r - b), 3),
        "crushed_blacks": round(float((luma < 0.05).mean()), 3),
        "clipped_whites": round(float((luma > 0.97).mean()), 3),
    }
