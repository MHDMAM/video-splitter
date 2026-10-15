#!/usr/bin/env python3
"""Split a WhatsApp Desktop video-call screen recording into clean videos.

Produces, next to the input (or in --output):
  <name>_caller.mp4      the remote video panel only, with enhanced voice
  <name>_sidebyside.mp4  remote video left, self-view right, with enhanced voice

Preview frames and the self-view temp file go to <tmp>/whatsapp-call-split/<name>/.
Requires ffmpeg and ffprobe (on PATH, or in the WinGet links folder on Windows).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Search regions as fractions of the frame (x, y, w, h). They match the WhatsApp Desktop
# call layout: remote video centred between title bar and call controls, self-view top-right.
MAIN_REGION = (0.20, 0.03, 0.55, 0.93)
SELF_REGION = (0.75, 0.03, 0.25, 0.27)

# Rumble cut, de-mud, presence boost, gentle compression; loudnorm is appended per file.
VOICE_CHAIN = (
    "highpass=f=80,"
    "equalizer=f=250:t=q:w=1:g=-2,"
    "equalizer=f=3000:t=q:w=1:g=3,"
    "acompressor=threshold=-24dB:ratio=3:attack=5:release=100:makeup=2"
)
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
VIDEO_ENCODE = ["-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
AUDIO_ENCODE = ["-c:a", "aac", "-b:a", "192k"]


def find_tool(name):
    path = shutil.which(name)
    if path:
        return path
    if os.name == "nt":
        winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / f"{name}.exe"
        if winget.exists():
            return str(winget)
    sys.exit(f"error: {name} not found. Install FFmpeg (Windows: winget install --id Gyan.FFmpeg -e).")


FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")


def run_ffmpeg(*args):
    """Run ffmpeg quietly, failing loudly on error."""
    result = subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-y", *args],
                            capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        sys.exit(f"error: ffmpeg failed:\n{result.stderr.strip()}")


def ffmpeg_log(*args):
    """Run ffmpeg for analysis and return its log (stderr)."""
    return subprocess.run([FFMPEG, "-hide_banner", *args], capture_output=True, text=True, errors="replace").stderr


def probe(path, *args):
    return subprocess.run([FFPROBE, "-v", "error", *args, "-of", "csv=p=0", str(path)],
                          capture_output=True, text=True).stdout.strip()


def parse_crop(value):
    parts = value.split(":")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        raise argparse.ArgumentTypeError("expected w:h:x:y, e.g. 700:936:610:40")
    return tuple(int(p) for p in parts)


def find_box(src, width, height, region):
    """Bounding box of non-dark content inside a search region of the frame.

    WhatsApp's background is dark grey, not black, so cropdetect over the full frame
    finds nothing; searching one region at a time isolates each video panel.
    reset=0 makes the box the union over the whole video.
    """
    fx, fy, fw, fh = region
    rx, ry, rw, rh = int(width * fx), int(height * fy), int(width * fw), int(height * fh)
    log = ffmpeg_log("-i", str(src), "-an", "-vf",
                     f"crop={rw}:{rh}:{rx}:{ry},cropdetect=limit=40:round=2:reset=0", "-f", "null", "-")
    matches = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", log)
    if not matches:
        sys.exit(f"error: no panel found in region {rw}x{rh} at {rx},{ry}; pass --main-crop/--self-crop")
    w, h, x, y = (int(v) for v in matches[-1])
    if w >= rw - 4 or h >= rh - 4:
        print("warning: detected box fills the whole search region - check the previews", file=sys.stderr)
    return w, h, x + rx, y + ry


def crop_filter(box):
    return "crop={}:{}:{}:{}".format(*box)


def voice_filter(src, volume):
    """Voice chain with a two-pass (measured, linear) loudness normalisation."""
    log = ffmpeg_log("-i", str(src), "-vn", "-af", f"{VOICE_CHAIN},{LOUDNORM}:print_format=json", "-f", "null", "-")
    m = json.loads(log[log.rindex("{"):log.rindex("}") + 1])
    return (f"{VOICE_CHAIN},{LOUDNORM}:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
            f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
            f":offset={m['target_offset']}:linear=true,aresample=48000,volume={volume}")


def loudness(path):
    log = ffmpeg_log("-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-")
    summary = log[log.rfind("Summary:"):]
    m = re.search(r"I:\s+(-?[\d.]+) LUFS[\s\S]*?Peak:\s+(-?[\d.]+)", summary)
    return f"loudness {m.group(1)} LUFS, peak {m.group(2)} dBFS" if m else "loudness n/a"


def main():
    ap = argparse.ArgumentParser(description="Split a WhatsApp Desktop call recording into a caller video "
                                             "and a side-by-side video, with enhanced voice.")
    ap.add_argument("input", type=Path, help="screen recording (.mp4)")
    ap.add_argument("-o", "--output", type=Path, help="output folder (default: the input file's folder)")
    ap.add_argument("--volume", type=float, default=0.9,
                    help="level after normalising to -16 LUFS (default 0.9, about -16.9 LUFS)")
    ap.add_argument("--main-crop", type=parse_crop, metavar="W:H:X:Y", help="remote video panel box (skip detection)")
    ap.add_argument("--self-crop", type=parse_crop, metavar="W:H:X:Y", help="self-view box (skip detection)")
    ap.add_argument("--preview-only", action="store_true", help="detect panels and write preview frames, then stop")
    args = ap.parse_args()

    src = args.input.resolve()
    if not src.is_file():
        sys.exit(f"error: input not found: {src}")
    out_dir = (args.output or src.parent).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    name = src.stem
    tmp_dir = Path(tempfile.gettempdir()) / "whatsapp-call-split" / name
    tmp_dir.mkdir(parents=True, exist_ok=True)

    width, height = (int(v) for v in probe(src, "-select_streams", "v:0", "-show_entries", "stream=width,height").split(",")[:2])
    duration = float(probe(src, "-show_entries", "format=duration"))
    has_audio = bool(probe(src, "-select_streams", "a", "-show_entries", "stream=index"))

    main_box = args.main_crop or find_box(src, width, height, MAIN_REGION)
    self_box = args.self_crop or find_box(src, width, height, SELF_REGION)
    mw, mh = main_box[:2]
    sw, sh = self_box[:2]
    if sh > mh:
        sys.exit(f"error: self-view ({sh}px) is taller than the main panel ({mh}px)")
    pad_y = (mh - sh) // 4 * 2  # vertically centred, kept even for yuv420p

    print(f"Input        : {src} ({width}x{height}, {duration:.2f}s, audio={has_audio})")
    print(f"Main crop    : {':'.join(map(str, main_box))}")
    print(f"Self crop    : {':'.join(map(str, self_box))}")
    print(f"Side-by-side : {mw + sw}x{mh} (self-view at y={pad_y})")

    t = f"{duration / 2:.2f}"
    run_ffmpeg("-ss", t, "-i", str(src), "-frames:v", "1", str(tmp_dir / "preview_full.png"))
    run_ffmpeg("-ss", t, "-i", str(src), "-vf", crop_filter(main_box), "-frames:v", "1", str(tmp_dir / "preview_main.png"))
    run_ffmpeg("-ss", t, "-i", str(src), "-vf", crop_filter(self_box), "-frames:v", "1", str(tmp_dir / "preview_self.png"))
    if args.preview_only:
        print(f"Previews     : {tmp_dir}")
        return

    audio_graph, maps, audio_args = "", ["-map", "[v]"], ["-an"]
    if has_audio:
        audio_graph = f";[0:a]{voice_filter(src, args.volume)}[a]"
        maps += ["-map", "[a]"]
        audio_args = AUDIO_ENCODE

    caller = out_dir / f"{name}_caller.mp4"
    run_ffmpeg("-i", str(src), "-filter_complex", f"[0:v]{crop_filter(main_box)}[v]{audio_graph}",
               *maps, *VIDEO_ENCODE, *audio_args, str(caller))

    run_ffmpeg("-i", str(src), "-vf", crop_filter(self_box), "-an", "-c:v", "libx264", "-crf", "18",
               "-preset", "slow", str(tmp_dir / "selfview.mp4"))

    # Built straight from the source in one pass to avoid re-encoding the caller video.
    sidebyside = out_dir / f"{name}_sidebyside.mp4"
    graph = (f"[0:v]{crop_filter(main_box)}[main];"
             f"[0:v]{crop_filter(self_box)},pad={sw}:{mh}:0:{pad_y}:black[self];"
             f"[main][self]hstack=inputs=2[v]{audio_graph}")
    run_ffmpeg("-i", str(src), "-filter_complex", graph, *maps, *VIDEO_ENCODE, *audio_args, str(sidebyside))
    run_ffmpeg("-ss", t, "-i", str(sidebyside), "-frames:v", "1", str(tmp_dir / "preview_sidebyside.png"))

    for path in (caller, sidebyside):
        size = probe(path, "-select_streams", "v:0", "-show_entries", "stream=width,height").replace(",", "x")
        print(f"{path}  [{size}]" + (f"  {loudness(path)}" if has_audio else ""))
    print(f"Temp         : {tmp_dir}")


if __name__ == "__main__":
    main()
