import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

META_KEYS = [
    "title", "uploader", "channel", "creator", "duration", "track", "artist", "album",
    "description", "tags", "view_count", "like_count", "comment_count", "upload_date", "webpage_url", "extractor",
]


@dataclass
class Probe:
    width: int
    height: int
    fps: float
    duration: float
    frames: int
    has_audio: bool

    @property
    def aspect(self) -> str:
        r = self.width / self.height
        for name, v in [("9:16", 9 / 16), ("4:5", 0.8), ("1:1", 1.0), ("16:9", 16 / 9), ("21:9", 21 / 9), ("4:3", 4 / 3)]:
            if abs(r - v) < 0.03:
                return name
        return f"{r:.2f}:1"


def tc(t: float) -> str:
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:05.2f}"


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def probe(path: Path) -> Probe:
    data = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]))
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    num, den = (int(x) for x in v.get("avg_frame_rate", "30/1").split("/"))
    fps = num / den if den else 30.0
    dur = float(data["format"].get("duration") or v.get("duration") or 0)
    frames = int(v.get("nb_frames") or round(dur * fps))
    w, h = int(v["width"]), int(v["height"])
    rot = int((v.get("tags") or {}).get("rotate", 0) or 0)
    for sd in v.get("side_data_list", []):
        rot = int(sd.get("rotation", rot) or rot)
    if abs(rot) in (90, 270):
        w, h = h, w
    return Probe(w, h, fps, dur, frames, any(s["codec_type"] == "audio" for s in data["streams"]))


def fetch(src: str, out: Path) -> tuple[Path, dict]:
    """Download a URL (or copy a local file) into `out`; returns the video path and trimmed metadata."""
    out.mkdir(parents=True, exist_ok=True)
    local = Path(src).expanduser()
    if local.exists():
        dst = out / f"source{local.suffix.lower()}"
        if not dst.exists():
            shutil.copy2(local, dst)
        return dst, {"source": str(local), "title": local.stem}
    existing = sorted(out.glob("source.*"))
    vids = [p for p in existing if p.suffix not in (".json", ".part")]
    if not vids:
        subprocess.run(
            ["yt-dlp", "--no-update", "-q", "--no-warnings", "--no-playlist", "--write-info-json",
             "-f", "bv*[height<=1920]+ba/b", "--merge-output-format", "mp4",
             "-o", str(out / "source.%(ext)s"), src],
            check=True,
        )
        vids = [p for p in sorted(out.glob("source.*")) if p.suffix not in (".json", ".part")]
    info_path = out / "source.info.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    meta = {k: info[k] for k in META_KEYS if info.get(k) not in (None, "", [])}
    meta["source"] = src
    return vids[0], meta


def extract_audio(video: Path, out: Path) -> Path:
    wav = out / "audio.wav"
    if not wav.exists():
        run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", str(wav)])
    return wav


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=lambda o: asdict(o) if hasattr(o, "__dataclass_fields__") else str(o)))
