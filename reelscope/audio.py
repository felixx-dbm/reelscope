import os
import shutil
import subprocess
from pathlib import Path

import librosa
import numpy as np
import pyloudnorm
import soundfile as sf
from scipy.signal import resample_poly

SR = 22050
HOP = 512


def analyze(wav: Path) -> dict:
    """Offline measurement only. Nothing here plays sound."""
    full, fsr = sf.read(wav, always_2d=True)
    lufs = float(pyloudnorm.Meter(fsr).integrated_loudness(full)) if len(full) > fsr * 0.5 else float("nan")
    true_peak = 20 * np.log10(np.abs(resample_poly(full, 4, 1, axis=0)).max() + 1e-12)

    y = librosa.to_mono(full.T.astype(np.float32))
    y = librosa.resample(y, orig_sr=fsr, target_sr=SR)
    dur = len(y) / SR
    env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    tempo, beats = librosa.beat.beat_track(onset_envelope=env, sr=SR, hop_length=HOP)
    beat_t = librosa.frames_to_time(beats, sr=SR, hop_length=HOP)
    onset_t = librosa.onset.onset_detect(onset_envelope=env, sr=SR, hop_length=HOP, units="time", backtrack=False)

    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    rms_db = 20 * np.log10(rms + 1e-9)
    t = librosa.frames_to_time(np.arange(len(rms)), sr=SR, hop_length=HOP)

    strength = np.interp(onset_t, librosa.frames_to_time(np.arange(len(env)), sr=SR, hop_length=HOP), env)
    accents = [float(x) for x in onset_t[strength > np.percentile(strength, 90)]] if len(onset_t) else []

    # Downbeat guess: the beat phase (0..3) whose beats carry the most onset energy.
    downbeats: list[float] = []
    if len(beats) >= 8:
        phase = int(np.argmax([env[beats[p::4]].sum() for p in range(4)]))
        downbeats = [float(x) for x in beat_t[phase::4]]

    drops = []
    win = int(1.0 * SR / HOP)
    for i in range(win, len(rms_db) - win):
        before = rms_db[i - win : i].mean()
        after = rms_db[i : i + win].mean()
        if after - before > 6:
            if not drops or t[i] - drops[-1]["t"] > 2:
                drops.append({"t": round(float(t[i]), 3), "rise_db": round(float(after - before), 1)})

    gaps = []
    quiet = rms_db < (np.median(rms_db) - 25)
    i = 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j + 1 < len(quiet) and quiet[j + 1]:
                j += 1
            if t[j] - t[i] >= 0.25:
                gaps.append([round(float(t[i]), 3), round(float(t[j]), 3)])
            i = j + 1
        else:
            i += 1

    return {
        "duration": round(dur, 3),
        "lufs": round(lufs, 1),
        "true_peak_dbtp": round(float(true_peak), 1),
        "tempo_bpm": round(float(np.atleast_1d(tempo)[0]), 1),
        "beats": [round(float(x), 3) for x in beat_t],
        "downbeats": [round(x, 3) for x in downbeats],
        "onsets": [round(float(x), 3) for x in onset_t],
        "accents": [round(x, 3) for x in accents],
        "drops": drops,
        "gaps": gaps,
        "rms_db_10hz": [round(float(rms_db[(t >= s / 10) & (t < (s + 1) / 10)].mean()), 1) for s in range(int(dur * 10))],
        "rms_db_per_s": [round(float(rms_db[(t >= s) & (t < s + 1)].mean()), 1) for s in range(int(np.ceil(dur)))],
    }


def sync(cut_times: list[float], audio: dict, fps: float) -> dict:
    """How tightly cuts sit on the music."""
    tol = 2 / fps
    out = {}
    for name in ("beats", "downbeats", "onsets", "accents"):
        ref = np.array(audio.get(name) or [])
        if not len(ref) or not cut_times:
            continue
        d = np.array([ref[np.argmin(np.abs(ref - c))] - c for c in cut_times])
        out[name] = {"hit_ratio": round(float((np.abs(d) <= tol).mean()), 2), "median_offset_frames": round(float(np.median(d) * fps), 1)}
    beats = audio.get("beats") or []
    if len(beats) > 2 and len(cut_times) > 2:
        period = float(np.median(np.diff(beats)))
        lens = np.diff(cut_times) / period
        ratios = {}
        for v in lens:
            for name, r in (("1/4", 0.25), ("1/2", 0.5), ("1", 1), ("2", 2), ("4", 4), ("8", 8)):
                if abs(v - r) / r < 0.12:
                    ratios[name] = ratios.get(name, 0) + 1
                    break
        out["shot_length_in_beats"] = ratios
        out["beat_period_s"] = round(period, 3)
    return out


def earshot_timeline(wav: Path) -> str | None:
    """Optional semantic sound tagging via earshot, if installed (EARSHOT_DIR or ~/Developer/Tools/earshot)."""
    root = Path(os.environ.get("EARSHOT_DIR", "~/Developer/Tools/earshot")).expanduser()
    if shutil.which("earshot"):
        cmd = ["earshot", "timeline", str(wav)]
    elif (root / "pyproject.toml").exists() and shutil.which("uv"):
        cmd = ["uv", "run", "-q", "--project", str(root), "earshot", "timeline", str(wav)]
    else:
        return None
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return None
    lines = [l for l in res.stdout.splitlines() if "torch/distributed" not in l]
    return "\n".join(lines).strip() or None
