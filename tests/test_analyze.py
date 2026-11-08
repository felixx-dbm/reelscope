import subprocess
from pathlib import Path

from reelscope.cli import analyze, cues


def _three_shot_clip(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=320x240:d=2:r=30",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2:r=30",
            "-f", "lavfi", "-i", "color=c=green:s=320x240:d=2:r=30",
            "-f", "lavfi", "-i", "sine=f=440:d=6",
            "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0[v]",
            "-map", "[v]", "-map", "3", "-shortest", str(path),
        ],
        check=True,
    )


def test_detects_hard_cuts(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    _three_shot_clip(clip)
    run = tmp_path / "run"

    a = analyze(str(clip), run, ocr=False, quiet=True)

    assert [s["start"] for s in a["shots"]] == [0, 60, 120]
    assert (run / "report.md").exists()
    assert (run / "timeline.png").exists()
    assert cues(run, fps=60)["cuts"] == [120, 240]
