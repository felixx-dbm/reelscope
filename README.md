# reelscope

Eyes for coding agents on video. `reelscope` turns a TikTok, Reel, YouTube clip or local file into things an LLM can read: a Markdown report, contact sheets of frames after every cut, a rhythm timeline, frame-by-frame strips and a cue map for [Remotion](https://www.remotion.dev).

It never plays audio or video. Everything is measured offline.

## The problem

Coding agents can build videos in Remotion, but they cannot watch a reference. "Make an edit like this TikTok" fails because the agent does not know where the cuts are, how fast the pacing is, whether cuts land on the beat, or what the white flash at 0:03 actually is. `reelscope` extracts that structure so the agent can copy the technique and then check its own render against the reference.

## What it measures

- **Cuts and transitions**: shot detection with flash, black-frame and high-activity (burst) handling
- **Pacing**: cuts per minute, average shot length, first cut, speed-up/slow-down trend
- **Look**: brightness, contrast, saturation, warmth per shot
- **On-screen text**: OCR per shot with screen region (Apple Vision on macOS, Tesseract elsewhere), watermark separation
- **Audio**: tempo, beats, downbeats, onsets, drops, LUFS, true peak, and how many cuts land on a beat
- **Style fingerprint**: tags that summarize the edit for search and comparison

## Commands

| Goal | Command |
|---|---|
| Full analysis of a URL or file | `reelscope analyze <url\|file> -o runs/<name>` |
| Study a transition frame by frame | `reelscope frames <run> --at 3.2 --before 4 --after 8` |
| Remotion cue map in frames | `reelscope cues <run> --fps 30` |
| Reference vs. own render | `reelscope compare <ref-run> <own-run>` |
| Find similar videos or tutorials | `reelscope similar "<query>" -n 10 --analyze 3` |

Each run writes `report.md` (read this first), `sheet_XX.png`, `timeline.png`, `analysis.json`, `audio.wav` and the source video.

## Agent workflow

The [`skill/`](skill/SKILL.md) folder is a Claude Code skill that teaches an agent the loop:

1. Analyze the reference, read the report, look at the sheets and timeline.
2. Zoom into flashes and bursts with `frames` to see the actual technique.
3. Build in Remotion using `cues` for timing instead of guessing.
4. Render, analyze the render, `compare` it to the reference, fix the gaps.

Install it by copying `skill/` to `~/.claude/skills/reelscope/`.

## Install

Requirements: Python 3.11-3.13, `ffmpeg` on PATH. Optional: `tesseract` for OCR outside macOS.

```bash
uv tool install git+https://github.com/felixx-dbm/reelscope
reelscope analyze "https://www.tiktok.com/@user/video/123" -o runs/ref
```

Downloads go through `yt-dlp`, so anything it supports works.

## Stack

Python, OpenCV, librosa, pyloudnorm, NumPy/SciPy, Pillow, yt-dlp, Apple Vision (via `ocrmac`).

## License

MIT
