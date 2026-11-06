from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .media import tc
from .text import region


def font(size: int) -> ImageFont.ImageFont:
    for p in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/SFNSMono.ttf", "DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


TRANSITION_COLOR = {"hard": (255, 255, 255), "flash": (255, 230, 80), "black": (120, 120, 120), "soft": (80, 200, 255), "start": (0, 255, 120)}


def sheets(shots: list[dict], frames: dict[int, Path], fps: float, portrait: bool, out: Path, per_sheet: int = 24) -> list[Path]:
    cols, tw = (8, 210) if portrait else (5, 340)
    th = int(tw * 16 / 9) if portrait else int(tw * 9 / 16)
    label_h = 46
    f = font(13)
    paths = []
    for page in range(0, len(shots), per_sheet):
        chunk = shots[page : page + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (tw + 6) + 6, rows * (th + label_h + 6) + 6), (12, 12, 14))
        d = ImageDraw.Draw(sheet)
        for k, s in enumerate(chunk):
            x = 6 + (k % cols) * (tw + 6)
            y = 6 + (k // cols) * (th + label_h + 6)
            src = frames.get(s["keyframes"].get("after_cut", -1))
            if src:
                im = Image.open(src).convert("RGB")
                im.thumbnail((tw, th))
                sheet.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
            col = TRANSITION_COLOR.get(s["transition_in"], (255, 255, 255))
            d.rectangle([x, y, x + tw - 1, y + th - 1], outline=col if s["transition_in"] != "hard" else (60, 60, 60), width=2)
            dur = (s["end"] - s["start"]) / fps
            d.text((x + 2, y + th + 3), f"#{s['index']:03d} {tc(s['start'] / fps)} {dur:.2f}s", fill=(235, 235, 235), font=f)
            tag = s["transition_in"] + (" BURST" if s["burst"] else "") + " · " + s["motion"]
            d.text((x + 2, y + th + 22), tag[:40], fill=col, font=f)
        p = out / f"sheet_{page // per_sheet + 1:02d}.png"
        sheet.save(p)
        paths.append(p)
    return paths


def timeline(stats: dict, fps: float, n: int, audio: dict | None, text_spans: list[dict], out: Path, width: int = 1800) -> Path:
    lanes = [("luma", 70), ("cut score", 90), ("audio rms", 70), ("beats/onsets", 40), ("text", 30)]
    pad_l = 120
    h = sum(l[1] for l in lanes) + 40
    im = Image.new("RGB", (width, h), (14, 14, 18))
    d = ImageDraw.Draw(im)
    f = font(12)
    dur = n / fps
    X = lambda t: pad_l + (width - pad_l - 10) * t / max(dur, 1e-6)
    y0 = 10
    tops = {}
    for name, lh in lanes:
        tops[name] = (y0, lh)
        d.text((8, y0 + lh // 2 - 6), name, fill=(170, 170, 180), font=f)
        d.line([(pad_l, y0 + lh), (width - 10, y0 + lh)], fill=(40, 40, 48))
        y0 += lh
    for s in range(int(dur) + 1):
        d.line([(X(s), 10), (X(s), y0)], fill=(30, 30, 36))
        d.text((X(s) + 2, y0 + 4), f"{s}s", fill=(120, 120, 130), font=f)

    def curve(lane: str, values: np.ndarray, color, vmax: float = 1.0):
        top, lh = tops[lane]
        pts = [(X(i / fps), top + lh - lh * min(1, v / vmax)) for i, v in enumerate(values)]
        if len(pts) > 1:
            d.line(pts, fill=color, width=1)

    curve("luma", np.asarray(stats["luma"]), (220, 220, 220))
    curve("cut score", np.asarray(stats["score"]), (120, 160, 255))
    top, lh = tops["cut score"]
    for s in stats["shots"]:
        c = TRANSITION_COLOR.get(s["transition_in"], (255, 255, 255))
        d.line([(X(s["start"] / fps), top), (X(s["start"] / fps), top + lh)], fill=c, width=1)
    top, lh = tops["luma"]
    for a, b in stats["flashes"]:
        d.rectangle([X(a / fps), top, max(X(a / fps) + 2, X(b / fps)), top + lh], fill=(255, 230, 80))
    if audio:
        rms = np.array(audio.get("rms_db_10hz") or audio["rms_db_per_s"], dtype=float)
        step = 0.1 if audio.get("rms_db_10hz") else 1.0
        top, lh = tops["audio rms"]
        if len(rms):
            lo, hi = np.nanmin(rms), np.nanmax(rms)
            pts = [(X((i + 0.5) * step), top + lh - lh * (v - lo) / max(hi - lo, 1e-6)) for i, v in enumerate(rms)]
            if len(pts) > 1:
                d.line(pts, fill=(255, 120, 160), width=2)
        top, lh = tops["beats/onsets"]
        for t in audio["onsets"]:
            d.line([(X(t), top + lh * 0.6), (X(t), top + lh)], fill=(110, 110, 120))
        for t in audio["beats"]:
            d.line([(X(t), top + lh * 0.25), (X(t), top + lh)], fill=(255, 120, 160), width=1)
        for t in audio["downbeats"]:
            d.line([(X(t), top), (X(t), top + lh)], fill=(255, 60, 120), width=2)
    top, lh = tops["text"]
    for sp in text_spans:
        d.rectangle([X(sp["start"]), top + 6, max(X(sp["start"]) + 2, X(sp["end"])), top + lh - 6], fill=(120, 255, 160))
    p = out / "timeline.png"
    im.save(p)
    return p


def text_spans(shots: list[dict], fps: float) -> list[dict]:
    spans: list[dict] = []
    for s in shots:
        for item in s["text"]:
            t0, t1 = s["start"] / fps, s["end"] / fps
            last = next((sp for sp in reversed(spans) if sp["text"].lower() == item["text"].lower()), None)
            if last and t0 - last["end"] < 0.5:
                last["end"] = t1
            else:
                spans.append({"text": item["text"], "start": round(t0, 2), "end": round(t1, 2), "region": region(item), "height": item["h"]})
    return spans


def split_watermarks(spans: list[dict], duration: float) -> tuple[list[dict], list[str]]:
    """Text that sits in one place for most of the video (logos, handles, OCR variants of them) is a watermark."""
    groups: list[list[dict]] = []
    for sp in spans:
        for g in groups:
            if g[0]["region"] == sp["region"] and SequenceMatcher(None, g[0]["text"].lower(), sp["text"].lower()).ratio() > 0.6:
                g.append(sp)
                break
        else:
            groups.append([sp])
    marks, keep = [], []
    for g in groups:
        if sum(s["end"] - s["start"] for s in g) > 0.35 * duration:
            marks.append(max(g, key=lambda s: len(s["text"]))["text"])
        else:
            keep += g
    return sorted(keep, key=lambda s: s["start"]), marks


def pacing(shots: list[dict], fps: float, n: int) -> dict:
    lens = np.array([(s["end"] - s["start"]) / fps for s in shots])
    dur = n / fps
    cuts = [s["start"] / fps for s in shots[1:]]
    windows = [sum(1 for c in cuts if w <= c < w + 2) / 2 for w in np.arange(0, dur, 2)]
    half = dur / 2
    first = sum(1 for c in cuts if c < half) / max(half, 1e-6)
    second = sum(1 for c in cuts if c >= half) / max(half, 1e-6)
    return {
        "shots": len(shots),
        "cuts_per_min": round(len(cuts) / dur * 60, 1) if dur else 0,
        "avg_shot_s": round(float(lens.mean()), 2),
        "median_shot_s": round(float(np.median(lens)), 2),
        "shortest_s": round(float(lens.min()), 3),
        "longest_s": round(float(lens.max()), 2),
        "first_cut_s": round(cuts[0], 2) if cuts else None,
        "cuts_per_s_2s_windows": [round(w, 1) for w in windows],
        "trend": "accelerates" if second > first * 1.3 else "decelerates" if first > second * 1.3 else "steady",
        "transitions": dict(Counter(s["transition_in"] for s in shots[1:])),
        "motion": dict(Counter(s["motion"] for s in shots).most_common(10)),
    }


def fingerprint(a: dict) -> dict:
    p, g, sy = a["pacing"], a["grade"], a.get("sync", {})
    tags = []
    cpm = p["cuts_per_min"]
    tags.append("hyper-fast cutting" if cpm > 60 else "fast cutting" if cpm > 30 else "moderate pacing" if cpm > 12 else "long takes")
    dur_min = a["probe"]["duration"] / 60 or 1
    if len(a["flashes"]) / dur_min > 6:
        tags.append("white flash transitions")
    if a["bursts"]:
        tags.append("strobe/glitch cut bursts")
    busy = sum(b - x + 1 for x, b in a.get("activity", [])) / max(1, a["probe"]["frames"])
    if busy > 0.4:
        tags.append("constant high visual activity (overlays/glitch/fast motion)")
    if p["transitions"].get("soft", 0) >= 2:
        tags.append("soft transitions (dissolve/morph)")
    motions = " ".join(s["motion"] for s in a["shots"])
    n = max(1, len(a["shots"]))
    for key, tag in (("push-in", "punch-in zooms"), ("shake", "camera shake"), ("whip", "whip pans"), ("rotate", "rotation moves")):
        if motions.count(key) / n > 0.15:
            tags.append(tag)
    if g["saturation"] > 0.5:
        tags.append("saturated grade")
    elif g["saturation"] < 0.18:
        tags.append("desaturated/monochrome")
    if g["contrast"] > 0.27:
        tags.append("high contrast")
    if g["warmth"] > 0.05:
        tags.append("warm tones")
    elif g["warmth"] < -0.05:
        tags.append("cool/teal tones")
    if g["crushed_blacks"] > 0.25:
        tags.append("crushed blacks")
    spans = a["text_spans"]
    if spans:
        big = [s for s in spans if s["height"] > 0.07]
        caps = [s for s in spans if s["region"].startswith("bottom") and s["height"] < 0.06]
        if big:
            tags.append("big title typography")
        if len(caps) >= 3 and len(caps) > len(spans) / 3:
            tags.append("captions/subtitles")
        if len(spans) / max(1, a["probe"]["duration"]) > 0.5:
            tags.append("text-driven / kinetic typography")
    if sy.get("beats", {}).get("hit_ratio", 0) >= 0.45 or sy.get("onsets", {}).get("hit_ratio", 0) >= 0.6:
        tags.append("cuts locked to the music")
    if a.get("audio") and a["audio"]["drops"]:
        tags.append("beat drop structure")
    title = (a["meta"].get("title") or "").split("#")[0].strip()
    track = a["meta"].get("track")
    queries = [f"{t} transition tutorial after effects" for t in tags[1:4]]
    queries += [f"{t} remotion" for t in tags[1:3]]
    if title:
        queries.insert(0, f"how to make {title} edit")
    if track and track.lower() != "original sound":
        queries.append(f"{track} edit template")
    return {"tags": tags, "search_queries": queries}


def grade(shots: list[dict], fps: float) -> dict:
    keys = ["brightness", "contrast", "saturation", "warmth", "crushed_blacks", "clipped_whites"]
    w = np.array([(s["end"] - s["start"]) for s in shots if s["look"]], dtype=float)
    looks = [s["look"] for s in shots if s["look"]]
    if not looks:
        return {k: 0 for k in keys} | {"palette": []}
    out = {k: round(float(np.average([l[k] for l in looks], weights=w)), 3) for k in keys}
    pal = Counter()
    for l, wt in zip(looks, w):
        for c in l["palette"]:
            r, g, b = (int(c["hex"][i : i + 2], 16) // 32 * 32 + 16 for i in (1, 3, 5))
            pal["#%02x%02x%02x" % (r, g, b)] += c["share"] * wt
    tot = sum(pal.values())
    out["palette"] = [{"hex": h, "share": round(v / tot, 3)} for h, v in pal.most_common(8)]
    return out


def markdown(a: dict) -> str:
    m, pr, p = a["meta"], a["probe"], a["pacing"]
    fps = pr["fps"]
    L = [f"# reelscope report: {m.get('title', 'video')}", ""]
    L.append(f"Source: {m.get('webpage_url') or m.get('source')}  ")
    for k in ("uploader", "track", "artist", "view_count", "like_count", "upload_date"):
        if m.get(k):
            L.append(f"{k}: {m[k]}  ")
    L += ["", "## Format", f"{pr['width']}x{pr['height']} ({a['aspect']}), {fps:.3g} fps, {pr['duration']:.2f} s, {pr['frames']} frames", ""]
    L += ["## Style fingerprint", ", ".join(a["fingerprint"]["tags"]), ""]
    L += ["## Pacing",
          f"{p['shots']} shots, {p['cuts_per_min']} cuts/min, avg {p['avg_shot_s']} s, median {p['median_shot_s']} s, shortest {p['shortest_s']} s, longest {p['longest_s']} s.",
          f"First cut at {p['first_cut_s']} s. Trend: {p['trend']}.",
          f"Transitions: {p['transitions']}",
          f"Cuts per second (2 s windows): {p['cuts_per_s_2s_windows']}", ""]
    if a["flashes"]:
        L.append("Flashes at: " + ", ".join(f"{tc(x / fps)} (f{x})" for x, _ in a["flashes"]))
    if a["bursts"]:
        L.append("Cut bursts: " + ", ".join(f"{tc(x / fps)}-{tc(y / fps)}" for x, y in a["bursts"]))
    if a.get("activity"):
        L.append("High-activity regions (glitch/overlay/fast motion, cuts there are unreliable, inspect with `reelscope frames`): " + ", ".join(f"{tc(x / fps)}-{tc(y / fps)}" for x, y in a["activity"]))
    if a.get("watermarks"):
        L.append("Watermarks (excluded from text analysis): " + ", ".join(a["watermarks"]))
    if a["blacks"]:
        L.append("Black frames: " + ", ".join(f"{tc(x / fps)}-{tc(y / fps)}" for x, y in a["blacks"]))
    L += ["", "## Motion", f"Shot motion labels (apparent motion from feature tracking): {p['motion']}", ""]
    g = a["grade"]
    L += ["## Look", f"brightness {g['brightness']}, contrast {g['contrast']}, saturation {g['saturation']}, warmth {g['warmth']}, crushed blacks {g['crushed_blacks']}, clipped whites {g['clipped_whites']}",
          "Palette (duration weighted): " + " ".join(f"{c['hex']} {int(c['share'] * 100)}%" for c in g["palette"]), ""]
    au = a.get("audio")
    if au:
        L += ["## Audio", f"{au['tempo_bpm']} BPM, {au['lufs']} LUFS integrated, true peak {au['true_peak_dbtp']} dBTP, {len(au['beats'])} beats, {len(au['onsets'])} onsets.",
              "Drops: " + (", ".join(f"{tc(x['t'])} (+{x['rise_db']} dB)" for x in au["drops"]) or "none"),
              "Gaps: " + (", ".join(f"{tc(x)}-{tc(y)}" for x, y in au["gaps"]) or "none"),
              f"Accents: {', '.join(tc(x) for x in au['accents'][:24])}", ""]
        sy = a.get("sync", {})
        if sy:
            L += ["## Cut/music sync (±2 frames)"] + [f"- {k}: {v}" for k, v in sy.items()] + [""]
    if a.get("earshot"):
        L += ["## earshot timeline", "```", a["earshot"], "```", ""]
    if a["text_spans"]:
        L += ["## On-screen text", "| time | region | size | text |", "|---|---|---|---|"]
        L += [f"| {tc(s['start'])}-{tc(s['end'])} | {s['region']} | {s['height']:.3f} | {s['text']} |" for s in a["text_spans"][:120]]
        L.append("")
    L += ["## Shots", "| # | start | frame | dur s | in | motion | bright | sat | colors | text |", "|---|---|---|---|---|---|---|---|---|---|"]
    for s in a["shots"]:
        lk = s["look"]
        cols = " ".join(c["hex"] for c in lk.get("palette", [])[:3])
        txt = " / ".join(t["text"] for t in s["text"])[:60]
        L.append(f"| {s['index']} | {tc(s['start'] / fps)} | {s['start']} | {(s['end'] - s['start']) / fps:.2f} | {s['transition_in']}{' B' if s['burst'] else ''} | {s['motion']} | {lk.get('brightness', '')} | {lk.get('saturation', '')} | {cols} | {txt} |")
    L += ["", "## Research leads", *[f"- {q}" for q in a["fingerprint"]["search_queries"]], "", "## Files"]
    L += [f"- {f}" for f in a["files"]]
    return "\n".join(L) + "\n"
