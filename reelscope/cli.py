import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from . import audio as audio_mod
from . import report, text, video
from .media import extract_audio, fetch, probe, tc, write_json


def slug(src: str) -> str:
    m = re.search(r"/video/(\d+)|[?&]v=([\w-]{6,})|youtu\.be/([\w-]{6,})|/shorts/([\w-]{6,})|/reel/([\w-]{6,})", src)
    if m:
        return next(g for g in m.groups() if g)
    return re.sub(r"[^\w.-]+", "_", Path(src).stem if Path(src).exists() else src)[-60:]


def analyze(src: str, out: Path, ocr: bool = True, langs: list[str] | None = None, use_earshot: bool = False, sensitivity: float = 1.0, quiet: bool = False) -> dict:
    log = (lambda *a: None) if quiet else (lambda *a: print(*a, file=sys.stderr))
    out.mkdir(parents=True, exist_ok=True)
    log(f"[reelscope] fetch {src}")
    vid, meta = fetch(src, out)
    pr = probe(vid)
    log(f"[reelscope] scan {pr.frames} frames {pr.width}x{pr.height}@{pr.fps:.3g}")
    stats, fps = video.scan(vid)
    det = video.detect(stats, fps, sensitivity)
    shots: list[video.Shot] = det["shots"]
    n = len(stats.luma)

    want: list[int] = []
    for s in shots:
        settle = s.start
        for a0, b0 in det["flashes"]:
            if a0 - 1 <= s.start <= b0 + 1:
                settle = b0 + 1
        s.keyframes["after_cut"] = min(settle + 2, s.end - 1)
        s.keyframes["mid"] = (s.start + s.end - 1) // 2
        step = int(round(fps))
        s.keyframes["samples"] = list(range(s.start + step, s.end - 1, step))[:8] if s.end - s.start > 2 * step else []
        want += [s.keyframes["after_cut"], s.keyframes["mid"], *s.keyframes["samples"]]
    log(f"[reelscope] {len(shots)} shots, grabbing {len(set(want))} frames")
    frames = video.grab(vid, want, out / "frames")

    for s in shots:
        mid = frames.get(s.keyframes["mid"])
        if mid:
            s.look = video.look(mid)
    if ocr:
        log("[reelscope] on-screen text")
        cache: dict[int, list] = {}
        for s in shots:
            seen = set()
            for idx in [s.keyframes["mid"], *s.keyframes["samples"]]:
                if idx in frames and idx not in cache:
                    cache[idx] = text.ocr(frames[idx], langs or ["en-US", "de-DE"])
                for item in cache.get(idx, []):
                    if item["text"].lower() not in seen:
                        seen.add(item["text"].lower())
                        s.text.append(item)

    shot_dicts = [s.__dict__ for s in shots]
    a: dict = {
        "meta": meta,
        "probe": {"width": pr.width, "height": pr.height, "fps": fps, "duration": n / fps, "frames": n},
        "aspect": pr.aspect,
        "shots": shot_dicts,
        "flashes": det["flashes"],
        "blacks": det["blacks"],
        "bursts": det["bursts"],
        "activity": det["activity"],
    }
    if pr.has_audio:
        log("[reelscope] audio (offline measurement, nothing is played)")
        wav = extract_audio(vid, out)
        a["audio"] = audio_mod.analyze(wav)
        a["sync"] = audio_mod.sync([s.start / fps for s in shots[1:]], a["audio"], fps)
        if use_earshot:
            log("[reelscope] earshot timeline")
            a["earshot"] = audio_mod.earshot_timeline(wav)
    a["pacing"] = report.pacing(shot_dicts, fps, n)
    a["grade"] = report.grade(shot_dicts, fps)
    a["text_spans"], a["watermarks"] = report.split_watermarks(report.text_spans(shot_dicts, fps), n / fps)
    a["fingerprint"] = report.fingerprint(a)

    portrait = pr.height > pr.width
    files = [str(p) for p in report.sheets(shot_dicts, frames, fps, portrait, out)]
    files.append(str(report.timeline({"luma": stats.luma, "score": det["score"], "shots": shot_dicts, "flashes": det["flashes"]}, fps, n, a.get("audio"), a["text_spans"], out)))
    files += [str(vid)] + ([str(out / "audio.wav")] if pr.has_audio else [])
    a["files"] = files
    a["frame_stats"] = {"luma": [round(float(x), 3) for x in stats.luma], "cut_score": [round(float(x), 3) for x in det["score"]]}
    write_json(out / "analysis.json", a)
    (out / "report.md").write_text(report.markdown(a))
    log(f"[reelscope] done: {out / 'report.md'}")
    return a


def load(run: Path) -> dict:
    return json.loads((run / "analysis.json").read_text())


def cues(run: Path, fps: float) -> dict:
    a = load(run)
    src = a["probe"]["fps"]
    fr = lambda t: int(round(t * fps))
    cv = lambda f: int(round(f / src * fps))
    au = a.get("audio") or {}
    return {
        "fps": fps,
        "duration_frames": fr(a["probe"]["duration"]),
        "cuts": [cv(s["start"]) for s in a["shots"][1:]],
        "shots": [{"from": cv(s["start"]), "frames": max(1, cv(s["end"]) - cv(s["start"])), "transition": s["transition_in"], "motion": s["motion"], "text": [t["text"] for t in s["text"]]} for s in a["shots"]],
        "flashes": [cv(x) for x, _ in a["flashes"]],
        "bursts": [[cv(x), cv(y)] for x, y in a["bursts"]],
        "beats": [fr(t) for t in au.get("beats", [])],
        "downbeats": [fr(t) for t in au.get("downbeats", [])],
        "accents": [fr(t) for t in au.get("accents", [])],
        "onsets": [fr(t) for t in au.get("onsets", [])],
        "drops": [fr(d["t"]) for d in au.get("drops", [])],
        "text": [{"from": fr(s["start"]), "to": fr(s["end"]), "text": s["text"], "region": s["region"]} for s in a["text_spans"]],
    }


def compare(runs: list[Path]) -> str:
    rows = [
        ("duration s", lambda a: round(a["probe"]["duration"], 2)),
        ("aspect", lambda a: a["aspect"]),
        ("cuts/min", lambda a: a["pacing"]["cuts_per_min"]),
        ("avg shot s", lambda a: a["pacing"]["avg_shot_s"]),
        ("first cut s", lambda a: a["pacing"]["first_cut_s"]),
        ("trend", lambda a: a["pacing"]["trend"]),
        ("flashes/min", lambda a: round(len(a["flashes"]) / max(a["probe"]["duration"], 1e-6) * 60, 1)),
        ("bursts", lambda a: len(a["bursts"])),
        ("brightness", lambda a: a["grade"]["brightness"]),
        ("contrast", lambda a: a["grade"]["contrast"]),
        ("saturation", lambda a: a["grade"]["saturation"]),
        ("warmth", lambda a: a["grade"]["warmth"]),
        ("text spans/s", lambda a: round(len(a["text_spans"]) / max(a["probe"]["duration"], 1e-6), 2)),
        ("tempo bpm", lambda a: (a.get("audio") or {}).get("tempo_bpm")),
        ("LUFS", lambda a: (a.get("audio") or {}).get("lufs")),
        ("true peak", lambda a: (a.get("audio") or {}).get("true_peak_dbtp")),
        ("cuts on beat", lambda a: (a.get("sync") or {}).get("beats", {}).get("hit_ratio")),
        ("cuts on onset", lambda a: (a.get("sync") or {}).get("onsets", {}).get("hit_ratio")),
        ("fingerprint", lambda a: ", ".join(a["fingerprint"]["tags"])),
    ]
    data = [load(r) for r in runs]
    head = "| metric | " + " | ".join(r.name for r in runs) + " |"
    lines = [head, "|---" * (len(runs) + 1) + "|"]
    for name, fn in rows:
        lines.append(f"| {name} | " + " | ".join(str(fn(a)) for a in data) + " |")
    return "\n".join(lines)


def frames_strip(run: Path, at: float, before: int, after: int, step: int, out: Path | None) -> Path:
    a = load(run)
    vid = Path(next(f for f in a["files"] if Path(f).name.startswith("source")))
    fps = a["probe"]["fps"]
    center = int(round(at * fps))
    idx = [max(0, center + k * step) for k in range(-before, after + 1)]
    tmp = run / "frames_detail"
    got = video.grab(vid, idx, tmp, long_side=720)
    ims = [Image.open(got[i]) for i in idx if i in got]
    if not ims:
        raise SystemExit("no frames in range")
    w, h = ims[0].size
    cols = min(len(ims), 6 if h > w else 4)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + 4) + 4, rows * (h + 26) + 4), (12, 12, 14))
    d = ImageDraw.Draw(sheet)
    f = report.font(16)
    for k, (i, im) in enumerate(zip([i for i in idx if i in got], ims)):
        x, y = 4 + (k % cols) * (w + 4), 4 + (k // cols) * (h + 26)
        sheet.paste(im, (x, y))
        d.text((x + 4, y + h + 4), f"f{i} {tc(i / fps)}" + ("  <- at" if i == center else ""), fill=(255, 230, 80) if i == center else (230, 230, 230), font=f)
    path = out or run / f"detail_{center:06d}.png"
    sheet.save(path)
    return path


def similar(query: str, n: int, platform: str) -> list[dict]:
    if platform == "tiktok-user":
        url = query if query.startswith("http") else f"https://www.tiktok.com/@{query.lstrip('@')}"
        target = url
    else:
        target = f"ytsearch{n}:{query}"
    res = subprocess.run(["yt-dlp", "--no-update", "--no-warnings", "--flat-playlist", "-J", "--playlist-end", str(n), target], capture_output=True, text=True)
    if res.returncode != 0:
        return [{"error": res.stderr.strip()[-400:]}]
    data = json.loads(res.stdout)
    out = []
    for e in data.get("entries", [])[:n]:
        url = e.get("url") or e.get("webpage_url")
        if url and not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={url}"
        out.append({"title": e.get("title"), "url": url, "duration": e.get("duration"), "views": e.get("view_count"), "channel": e.get("channel") or e.get("uploader")})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(prog="reelscope", description="Video analysis for agents. Never plays audio or video.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("analyze", help="fetch + full analysis -> report.md, analysis.json, sheets, timeline")
    p.add_argument("source", help="URL (TikTok, YouTube, Instagram, ... via yt-dlp) or local file")
    p.add_argument("-o", "--out", type=Path)
    p.add_argument("--no-ocr", action="store_true")
    p.add_argument("--lang", nargs="+", default=["en-US", "de-DE"])
    p.add_argument("--earshot", action="store_true", help="add earshot semantic sound timeline")
    p.add_argument("--sensitivity", type=float, default=1.0, help=">1 finds more cuts, <1 fewer")

    p = sub.add_parser("frames", help="frame-by-frame strip around a time, e.g. to study a transition")
    p.add_argument("run", type=Path)
    p.add_argument("--at", type=float, required=True, help="seconds")
    p.add_argument("--before", type=int, default=4)
    p.add_argument("--after", type=int, default=7)
    p.add_argument("--step", type=int, default=1)
    p.add_argument("-o", "--out", type=Path)

    p = sub.add_parser("cues", help="export a cue map in frames for Remotion")
    p.add_argument("run", type=Path)
    p.add_argument("--fps", type=float, default=30)
    p.add_argument("-o", "--out", type=Path)

    p = sub.add_parser("compare", help="side-by-side metrics of runs, e.g. reference vs. own render")
    p.add_argument("runs", type=Path, nargs="+")

    p = sub.add_parser("similar", help="find similar videos (YouTube search or a TikTok creator feed)")
    p.add_argument("query", nargs="?", help="search text, @user for tiktok-user; omit with --from")
    p.add_argument("--from", dest="from_run", type=Path, help="derive the query from a run")
    p.add_argument("-n", type=int, default=10)
    p.add_argument("--platform", choices=["youtube", "tiktok-user"], default="youtube")
    p.add_argument("--analyze", type=int, default=0, help="also analyze the top K results")
    p.add_argument("-o", "--out", type=Path, default=Path("reelscope_runs/similar"))

    args = ap.parse_args()
    if args.cmd == "analyze":
        out = args.out or Path("reelscope_runs") / slug(args.source)
        analyze(args.source, out, not args.no_ocr, args.lang, args.earshot, args.sensitivity)
        print(out / "report.md")
    elif args.cmd == "frames":
        print(frames_strip(args.run, args.at, args.before, args.after, args.step, args.out))
    elif args.cmd == "cues":
        c = cues(args.run, args.fps)
        dst = args.out or args.run / f"cues_{int(args.fps)}fps.json"
        dst.write_text(json.dumps(c, indent=1))
        print(dst)
    elif args.cmd == "compare":
        print(compare(args.runs))
    elif args.cmd == "similar":
        query = args.query
        if args.from_run:
            a = load(args.from_run)
            m = a["meta"]
            if args.platform == "tiktok-user":
                query = m.get("uploader") or m.get("channel")
            else:
                title = re.sub(r"#\w+", "", m.get("title") or "").replace("||", " ").strip()
                query = query or title or " ".join(a["fingerprint"]["tags"][:2])
        if not query:
            raise SystemExit("give a query or --from")
        hits = similar(query, args.n, args.platform)
        print(f"# similar: {query}\n")
        for h in hits:
            print(f"- {h.get('title')} | {h.get('channel')} | {h.get('duration')} s | {h.get('views')} views | {h.get('url')}" if "error" not in h else f"error: {h['error']}")
        if args.analyze:
            runs = []
            for h in [h for h in hits if h.get("url")][: args.analyze]:
                d = args.out / slug(h["url"])
                try:
                    analyze(h["url"], d, quiet=True)
                    runs.append(d)
                except Exception as e:  # one broken download should not stop the batch
                    print(f"skip {h['url']}: {e}", file=sys.stderr)
            if args.from_run:
                runs.insert(0, args.from_run)
            if runs:
                print("\n" + compare(runs))


if __name__ == "__main__":
    main()
