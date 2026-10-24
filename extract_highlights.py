#!/usr/bin/env python3
"""Pick the clearest stills and short clips from a caller video, with no manual steps.

Produces, in <name>_highlights/ next to the input (or in --output):
  still_01_<mm>m<ss>s.jpg  the sharpest, steadiest frames, best first
  clip_01_<mm>m<ss>s.mp4   the clearest few-second stretches, best first

Classical image metrics only (no AI models): Laplacian variance for sharpness,
frame difference for motion, mean brightness for exposure and a Haar cascade
for "is a face in view". Every metric is ranked within the video itself, so it
adapts to each call's quality without thresholds to tune.
Requires ffmpeg/ffprobe plus OpenCV and NumPy (pip install "opencv-python-headless<5" numpy;
OpenCV 5 dropped the classical Haar face detector).
Accepts files or folders; a folder is searched for *_caller.mp4.
"""
import argparse
import subprocess
import sys
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:
    sys.exit("error: OpenCV and NumPy are required: pip install \"opencv-python-headless<5\" numpy")
if not hasattr(cv2, "CascadeClassifier"):
    sys.exit(f"error: OpenCV {cv2.__version__} has no Haar face detector: pip install \"opencv-python-headless<5\"")

from split_call import AUDIO_ENCODE, FFMPEG, VIDEO_ENCODE, probe, run_ffmpeg

# Frames are scored at this width; detail finer than this is mostly compression noise.
ANALYSIS_WIDTH = 480
# Mean absolute frame difference (0-255) below which the video counts as frozen.
FROZEN_DIFF = 0.3
# Mean brightness range (0-255) outside which a frame counts as badly exposed.
EXPOSURE_RANGE = (35, 220)
# Score multiplier for frames with no face when the video usually shows one.
NO_FACE_FACTOR = 0.4
# Faces are preferred once one is found in at least this share of frames; below it
# detection is likely just noise (or the caller is off camera the whole time).
FACE_MIN_SHARE = 0.05
# Picks scoring below this share of the best pick are dropped: fewer results beat weak ones.
MIN_RELATIVE_SCORE = 0.5

FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def read_frames(src, fps):
    """Yield (time, gray frame) at `fps`, downscaled to ANALYSIS_WIDTH, decoded by ffmpeg."""
    w, h = (int(v) for v in probe(src, "-select_streams", "v:0", "-show_entries", "stream=width,height").split(",")[:2])
    height = round(h * ANALYSIS_WIDTH / w / 2) * 2
    proc = subprocess.Popen([FFMPEG, "-hide_banner", "-v", "error", "-i", str(src), "-an",
                             "-vf", f"fps={fps},scale={ANALYSIS_WIDTH}:{height},format=gray",
                             "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    size = ANALYSIS_WIDTH * height
    i = 0
    while (buf := proc.stdout.read(size)) and len(buf) == size:
        yield i / fps, np.frombuffer(buf, np.uint8).reshape(height, ANALYSIS_WIDTH)
        i += 1
    proc.wait()


def measure(src, fps):
    """Per-sample metrics: time, sharpness, motion, brightness, face found."""
    rows, prev = [], None
    min_face = ANALYSIS_WIDTH // 8
    for t, gray in read_frames(src, fps):
        faces = FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=6, minSize=(min_face, min_face))
        # Judge sharpness on the face when there is one: a crisp background behind a blurred face is not clear.
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            region = gray[y:y + fh, x:x + fw]
        else:
            region = gray
        sharp = cv2.Laplacian(region, cv2.CV_64F).var()
        motion = float(cv2.absdiff(gray, prev).mean()) if prev is not None else 0.0
        rows.append((t, sharp, motion, float(region.mean()), len(faces) > 0))
        prev = gray
    if not rows:
        sys.exit(f"error: no video frames decoded from {src}")
    return np.array(rows, dtype=float)


def rank(values):
    """Percentile rank in [0, 1], so every metric is relative to this video."""
    return values.argsort().argsort() / max(len(values) - 1, 1)


def score(m):
    """Still and clip scores per sample, each in [0, 1]."""
    _, sharp, motion, bright, face = m.T
    sharp_r, calm_r = rank(sharp), 1 - rank(motion)
    quality = np.where((bright < EXPOSURE_RANGE[0]) | (bright > EXPOSURE_RANGE[1]), 0.2, 1.0)
    # Haar false positives rarely last; trust a face only if 2 of 3 neighbouring samples agree.
    face = np.convolve(face, np.ones(3), mode="same") >= 2
    face_mode = face.mean() >= FACE_MIN_SHARE
    if face_mode:
        quality *= np.where(face > 0, 1.0, NO_FACE_FACTOR)
    still = (0.65 * sharp_r + 0.35 * calm_r) * quality
    # A frozen picture can make a fine still but a bad clip.
    clip = sharp_r * quality * (motion >= FROZEN_DIFF)
    return still, clip, face_mode


def pick_stills(times, scores, count, gap):
    """Best samples, greedily, at least `gap` seconds apart."""
    order = np.argsort(-scores)
    floor = max(scores[order[0]] * MIN_RELATIVE_SCORE, 1e-9)
    chosen = []
    for i in order:
        if len(chosen) == count or scores[i] < floor:
            break
        if all(abs(times[i] - times[j]) >= gap for j in chosen):
            chosen.append(i)
    return [(times[i], scores[i]) for i in chosen]


def pick_clips(times, scores, fps, count, length, duration):
    """Best non-overlapping windows of `length` seconds by mean score."""
    n = int(round(length * fps))
    if n < 1 or len(scores) < n:
        return []
    means = np.convolve(scores, np.ones(n) / n, mode="valid")
    order = np.argsort(-means)
    floor = max(means[order[0]] * MIN_RELATIVE_SCORE, 1e-9)
    chosen = []
    for i in order:
        if len(chosen) == count or means[i] < floor:
            break
        start = times[i]
        if start + length > duration:
            continue
        if all(abs(start - s) >= length for s, _ in chosen):
            chosen.append((start, means[i]))
    return chosen


def stamp(t):
    return f"{int(t // 60):02d}m{int(t % 60):02d}s"


def process(src, out_root, args):
    out_dir = (out_root or src.parent) / f"{src.stem}_highlights"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in [*out_dir.glob("still_*.jpg"), *out_dir.glob("clip_*.mp4")]:
        old.unlink()
    duration = float(probe(src, "-show_entries", "format=duration"))
    has_audio = bool(probe(src, "-select_streams", "a", "-show_entries", "stream=index"))

    print(f"Input        : {src} ({duration:.2f}s)")
    m = measure(src, args.sample_fps)
    still_scores, clip_scores, face_mode = score(m)
    times = m[:, 0]
    print(f"Analysed     : {len(times)} frames at {args.sample_fps} fps, "
          f"face mode {'on' if face_mode else 'off'}")

    for n, (t, s) in enumerate(sorted(pick_stills(times, still_scores, args.stills, args.gap),
                                      key=lambda p: -p[1]), 1):
        path = out_dir / f"still_{n:02d}_{stamp(t)}.jpg"
        run_ffmpeg("-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1", "-q:v", "2", str(path))
        print(f"  {path.name}  score {s:.2f}")

    audio_args = AUDIO_ENCODE if has_audio else ["-an"]
    for n, (t, s) in enumerate(pick_clips(times, clip_scores, args.sample_fps, args.clips,
                                          args.clip_length, duration), 1):
        path = out_dir / f"clip_{n:02d}_{stamp(t)}.mp4"
        run_ffmpeg("-ss", f"{t:.3f}", "-i", str(src), "-t", f"{args.clip_length:.3f}",
                   *VIDEO_ENCODE, *audio_args, str(path))
        print(f"  {path.name}  score {s:.2f}")
    print(f"Output       : {out_dir}")


def positive(kind):
    def parse(value):
        try:
            v = kind(value)
        except ValueError:
            v = 0
        if v <= 0:
            raise argparse.ArgumentTypeError("expected a positive number")
        return v
    return parse


def main():
    ap = argparse.ArgumentParser(description="Extract the clearest stills and short clips from caller videos.")
    ap.add_argument("inputs", type=Path, nargs="+", help="video files, or folders to search for *_caller.mp4")
    ap.add_argument("-o", "--output", type=Path, help="output root (default: each input's folder)")
    ap.add_argument("--stills", type=int, default=10, help="number of stills (default 10, 0 for none)")
    ap.add_argument("--clips", type=int, default=5, help="number of clips (default 5, 0 for none)")
    ap.add_argument("--clip-length", type=positive(float), default=3.0, help="clip length in seconds (default 3)")
    ap.add_argument("--gap", type=positive(float), default=5.0, help="minimum seconds between stills (default 5)")
    ap.add_argument("--sample-fps", type=positive(float), default=4.0,
                    help="frames analysed per second (default 4)")
    args = ap.parse_args()
    if args.stills < 0 or args.clips < 0:
        ap.error("--stills and --clips must be 0 or more")

    sources = []
    for p in args.inputs:
        p = p.resolve()
        if p.is_dir():
            sources += sorted(p.glob("*_caller.mp4"))
        elif p.is_file():
            sources.append(p)
        else:
            sys.exit(f"error: input not found: {p}")
    if not sources:
        sys.exit("error: no *_caller.mp4 files found")
    out_root = args.output.resolve() if args.output else None
    for src in sources:
        process(src, out_root, args)


if __name__ == "__main__":
    main()
