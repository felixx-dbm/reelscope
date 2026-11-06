# Motion and edit playbook

Defaults to start from, not laws. Numbers marked (vendor) come from third-party guides, not platform documentation; re-check them when it matters.

## Delivery specs

| Format | Size | fps | Safe area | Loudness |
|---|---|---|---|---|
| TikTok / Reels / Shorts | 1080x1920 (9:16) | 30 (60 for sports/gaming) | Keep text and faces out of the bottom ~650 px, top ~250 px, right ~150 px. Safe band roughly y 250-1270 (vendor; platforms change UI, design to the strictest) | -14 LUFS, -1 dBTP as a safe target (TikTok/IG targets are not published) |
| YouTube long-form | 1920x1080 or 3840x2160 | 24/25/30/60 | Title-safe ~5% inset | -14 LUFS (YouTube turns louder content down) |
| Feed ads (IG/FB/LinkedIn) | 1080x1350 (4:5) or 1080x1080 | 30 | Logo in the first 2 s, captions on (most feeds start muted) | -14 LUFS |
| Landscape edits (TikTok fan edits) | 1920x1080 | 30 | none | references are often mastered at -4 to -8 LUFS |

Sources: socialync.io/tools/safe-zones/tiktok, bundle.social/tools/safe-zone-checker, socialync.io/tools/safe-zones/youtube-shorts, forasoft.com LUFS targets per platform 2026, openclip.app/learn/audio-normalization.

## Format grammar

**TikTok / Reels edits (fan edits, aura edits, polyester, velocity):** The song decides everything. Build on a beat grid measured with `reelscope cues`. The intro is quiet with slow motion or a held image (2-5 s), then the drop gets a flash and a hard change, and every downbeat after it gets an accent (flash, zoom punch, shake). Use 1-4 beat shots in the build and 1/2 to 1 beat in the climax. End on the strongest image, then cut to black on the song's tail. There is one hero subject. The grade is high contrast and saturated with crushed blacks, often a teal/blue push with a red or orange subject. The text is one big title word, chrome or outlined, plus a small watermark.

**Short educational animation (30-90 s):** Hook in the first 2 s by stating the payoff or the problem ("this is why X"). Show one idea per beat: build a diagram step by step with progressive reveal instead of cutting between static slides. Keep the on-screen text at 3-7 words, synced to the voice, and change visual state every 2-3 s (vendor: retention drops when a shot holds past ~3 s). Use one color for "the thing we track" and keep it consistent. End with a recap frame that can be screenshotted.

**Comedic shorts:** The timing is the joke. Hold the setup slightly too long, then hard-cut on the punchline with no transition. Use a zoom punch (100% to 130% in 2 frames) on the reaction, with an SFX hit on the same frame. Silence before the punchline is louder than a sound. Captions can be the punchline (reveal the last word late). Keep it to 7-20 s, and make a loop point where the last frame flows into the first.

**Brand / marketing:** Show the brand mark or product in the first 2 s, because many viewers never get further. Lead with the benefit, not the feature. Keep one message per 6-15 s cutdown, motion slower and smoother than fan edits (ease-in-out, 12-20 frame moves), and the brand palette only. Always add captions. End with a 2-3 s end card holding the logo and CTA. Deliver 9:16, 4:5 and 16:9 versions from one composition with responsive layout.

**YouTube clips / video essays:** The first 30 s promise and preview. Pattern interrupts come every 20-40 s (b-roll, zoom, graphic, sound change). Lower thirds and motion graphics explain; they don't decorate. Chapters go on topic boundaries.

## Hook checklist (first 3 s)

- Motion or change in frame 1, never a static title card.
- Text hook on screen within 0.5 s (vendor data: text hooks and 2-3 caption changes in the first 3 s correlate with better hold).
- The sound starts immediately, or the drop is teased.
- Open loop: show the result, then "how".

## Technique recipes (Remotion)

| Technique | What reelscope shows | Remotion recipe |
|---|---|---|
| White flash transition | 1-3 white frames on a downbeat; `flash` transition | Full-frame white `AbsoluteFill`, opacity `exp(-(f-hit)/2.5)`; cut the content under it on the hit frame |
| Chromatic fade after flash | Color fringes on the frames after the flash | `drop-shadow(±Npx 0 0 red/cyan)` or text-shadow offsets that decay with the same envelope |
| Strip / slice glitch | High-activity region, horizontal bands offset in `frames` | Render the scene again inside bands with `clipPath: inset()` + `translateX`, seeded by `random(frame)` |
| Masked subject over panel | Subject sharp in front of a tilted strip of other footage | Layer order: background, panel (`clipPath: polygon`) with other footage, cut-out subject (PNG with alpha, or Remotion `<OffthreadVideo>` with an alpha-channel ProRes/WebM) |
| Zoom punch | `push-in` shots of 1-2 beats | `scale` 1 → 1.15 over 3 frames on the hit, ease out over 8 |
| Shake | `shake` label, jitter value | Translate by `(random(frame)-0.5)*amp`, amp from a hit envelope |
| Whip pan | `whip` label, large horizontal motion over 2-4 frames | `translateX` plus horizontal motion blur (stack 4-6 offset copies at low opacity) across the cut |
| Speed ramp | Motion energy rising then freezing near a hit | `<OffthreadVideo playbackRate>` cannot ramp; pre-render ramps with ffmpeg `setpts` or use `Sequence` + `startFrom` per segment |
| Kinetic typography | Many text spans, big title sizes | Word-level `Sequence`s on onsets; slam scale 1.6 → 1 over 4-5 frames; letter-spacing ease |
| Chrome / metal title | Big title, gradient fill | `background: linear-gradient(...)` + `background-clip: text` + white stroke + `drop-shadow` glow |
| Speed lines / radial blur | Busy frames radiating from the center | SVG lines from the center with random lengths per frame, `mix-blend-mode: screen` |
| Grade | Look: brightness, contrast, saturation, warmth, palette | Wrapper `filter: contrast() saturate()`, colored radial vignette, `mix-blend-mode` color layers; match the reference with `reelscope compare` |
| Film grain | Fine noise | `feTurbulence` SVG with seed = frame, opacity 0.06-0.1, `screen` blend |

## Motion principles that separate pro from amateur

- Ease everything: fast-out-slow-in for entrances, slow-in-fast-out for exits. Linear motion only for continuous things (scrolling tapes, rotation).
- Use one dominant motion per moment; when everything moves, nothing reads.
- Anticipation: a 2-4 frame counter-move before a big move.
- Overshoot and settle on slams, e.g. scale 1.6 → 0.97 → 1.
- Hit the frame *before* the beat for cuts and on the beat for flashes (reelscope often shows a median offset of about -1 frame on pro edits).
- Contrast in pacing: a still beat before the drop makes the drop hit harder.
- Typography: at most two families, one display (condensed/heavy) and one mono or grotesk for labels; tracking wider on small caps labels.
- Color: one accent color per section. A palette change signals a new act.
