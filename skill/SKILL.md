---
name: reelscope
description: Analyze and design video edits without watching or hearing them. Use whenever the user shares a video link or file (TikTok, YouTube, Reels, local mp4) as a reference, asks to make an edit/motion design/explainer/ad/meme video "like this", wants to know how an edit was made, or wants a rendered video checked against a reference. Covers TikTok/Reels edits, YouTube clips, brand/marketing spots, educational and comedic short animations.
---

# reelscope

`reelscope` is a CLI on PATH. It turns a video into things you can read: a report, contact sheets of freeze frames after every cut, a rhythm timeline image, frame-by-frame strips, and a Remotion cue map. It never plays audio or video. Keep it that way: never use afplay, say, ffplay, `open` on media, a browser preview or Remotion Studio to "check" a result. The user may be in a place where sound must not play.

## Commands

| Goal | Command |
|---|---|
| Full analysis of a URL or file | `reelscope analyze <url\|file> -o <scratchpad>/rs/<name>` (add `--earshot` for semantic sound tags, `--no-ocr` to skip text, `--sensitivity 1.5` for more cuts) |
| Study a transition frame by frame | `reelscope frames <run> --at <sec> --before 4 --after 8` |
| Remotion cue map (cuts, flashes, beats, downbeats, accents, drops, text) | `reelscope cues <run> --fps 30` |
| Reference vs. own render | `reelscope compare <ref-run> <own-run>` |
| Find similar videos or tutorials | `reelscope similar "<query>" -n 10`, `reelscope similar --from <run>`, `reelscope similar @user --platform tiktok-user` (add `--analyze 3` to analyze and compare the top hits) |

Outputs per run: `report.md` (read first), `sheet_XX.png` (frames after each cut, labeled with timecode, duration, transition, motion), `timeline.png` (luma, cut score, flashes, audio level, beats/downbeats, text lanes), `analysis.json`, `audio.wav`, `source.*`.

## Workflow for "make an edit like this"

1. `reelscope analyze` the reference. Read `report.md`, then look at `timeline.png` and the sheets.
2. For every flash, burst, high-activity region and interesting cut, run `reelscope frames` and look. That is where the technique is visible (2-frame white flash, chroma fade, masked subject over a panel, etc.). Cut detection is unreliable inside high-activity regions; trust the frame strips there.
3. Research: run WebSearch on the report's "Research leads" plus the technique names you saw. Optionally `reelscope similar "<style> tutorial"` for YouTube tutorials (titles and lengths tell you which are worth reading about). Prefer creator tutorials and official docs; say which claims are unverified.
4. Read `references/playbook.md` for the format the user wants (TikTok edit, YouTube, brand, education, comedy) and for the technique-to-Remotion recipes.
5. Build in Remotion. Use `reelscope cues` for timing instead of guessing; the audio file of the run (`audio.wav`) can be the soundtrack when the user supplies the sound.
6. Render, then `reelscope analyze` the render and `reelscope compare` it to the reference. Fix gaps (cuts/min, flashes/min, grade, LUFS, cut-on-beat ratio), re-render. Look at stills of your render before claiming it's done, and tell the user you checked frames and measurements, not playback.

## Reading the numbers

- `cuts on beat` / `cuts on onset`: share of cuts within ±2 frames of a beat/onset. Pro music edits usually sit above 0.5 on onsets.
- `median_offset_frames` negative means cuts land slightly before the musical event (common and intentional: the eye needs a frame).
- `shot_length_in_beats`: how shot lengths divide the beat (1/2, 1, 2, 4 ...). Copy this grid.
- Motion labels are apparent motion from feature tracking (camera move or big subject move): push-in, pull-out, pan, tilt, rotate, shake, whip, busy, static.
- Watermarks (creator handles that sit in place most of the video) are excluded from the text analysis.
- LUFS: social edits are often mastered very loud (-4 to -8 LUFS); platforms turn them down. Deliver around -14 LUFS, -1 dBTP unless matching a reference is the point.
