# whatsapp-call-split

Turn a screen recording of a **WhatsApp Desktop video call** into clean videos. It removes the app window around the video and enhances the voice.

A raw recording contains the title bar, call buttons, mouse cursor, OS watermarks and a small self-view in the corner. This tool finds the two video panels automatically and writes:

| Output | Content |
|---|---|
| `<name>_caller.mp4` | The remote caller's video only |
| `<name>_sidebyside.mp4` | Caller on the left, your self-view on the right (native size, vertically centred on black) |

Both get the same voice enhancement: rumble cut, clarity EQ, gentle compression and two-pass loudness normalisation.

```
+--------------------------------------------+        +----------+------+
| title bar                         [self]  |        |          |      |
|          +-----------+                     |        |          |      |
|          |  caller   |                     |  -->   |  caller  |[self]|
|          |  video    |                     |        |          |      |
|          +-----------+                     |        |          |      |
| [cam][mic]     (call controls)      [end] |        +----------+------+
+--------------------------------------------+
```

## Requirements

- **Python 3.8+**, standard library only, no `pip install` needed.
- **FFmpeg** with `ffmpeg` and `ffprobe` available:
  - Windows: `winget install --id Gyan.FFmpeg -e` (the script also finds it in the WinGet links folder before you restart the shell)
  - macOS: `brew install ffmpeg`
  - Debian/Ubuntu: `sudo apt install ffmpeg`

## Usage

```bash
# 1. Check the detected crops first (fast, writes preview frames to a temp folder)
python split_call.py "call.mp4" --preview-only

# 2. Render - outputs go next to call.mp4
python split_call.py "call.mp4"

# Write outputs somewhere else
python split_call.py "call.mp4" -o ./processed

# Quieter result
python split_call.py "call.mp4" --volume 0.7

# Detection wrong? Give the panel boxes yourself (w:h:x:y in source pixels)
python split_call.py "call.mp4" --main-crop 700:936:610:40 --self-crop 354:200:1548:48
```

Example output:

```
Input        : D:\calls\call.mp4 (1920x1038, 77.48s, audio=True)
Main crop    : 700:936:610:41
Self crop    : 354:200:1548:49
Side-by-side : 1054x936 (self-view at y=368)
D:\calls\call_caller.mp4  [700x936]  loudness -16.9 LUFS, peak -2.4 dBFS
D:\calls\call_sidebyside.mp4  [1054x936]  loudness -16.9 LUFS, peak -2.4 dBFS
Temp         : C:\Users\you\AppData\Local\Temp\whatsapp-call-split\call
```

### Options

| Option | Default | Description |
|---|---|---|
| `input` | - | The screen recording (.mp4) |
| `-o`, `--output DIR` | input's folder | Output folder, created if missing |
| `--volume N` | `0.9` | Level after normalising to -16 LUFS. `0.9` is about -16.9 LUFS, `0.7` about -19 LUFS |
| `--main-crop W:H:X:Y` | auto | Remote video panel box; skips detection |
| `--self-crop W:H:X:Y` | auto | Self-view box; skips detection |
| `--preview-only` | off | Detect panels, write preview frames, stop |

Only the two videos are written to the output folder. Preview frames (`preview_full.png`, `preview_main.png`, `preview_self.png`, `preview_sidebyside.png`) and the self-view clip (`selfview.mp4`) go to `<system temp>/whatsapp-call-split/<name>/`.

## How it works

### Panel detection

FFmpeg's `cropdetect` over the full frame finds nothing. WhatsApp's background is dark grey (#0b1014), not black, and the UI sits at the edges. Instead the script runs `cropdetect` (limit 40) inside two search regions, given as fractions of the frame:

| Panel | Region (x, y, w, h) |
|---|---|
| Caller video | 0.20, 0.03, 0.55, 0.93 - the centre, between title bar and call controls |
| Self-view | 0.75, 0.03, 0.25, 0.27 - the top-right corner |

`cropdetect` thresholds whole rows and columns, so the mouse cursor or small icons don't change the box. It runs with `reset=0`, so the box covers the whole video.

### Voice enhancement

| Step | Filter | Why |
|---|---|---|
| 1 | `highpass=f=80` | Remove rumble |
| 2 | `equalizer=f=250:g=-2` | Reduce muddiness |
| 3 | `equalizer=f=3000:g=3` | Presence / speech clarity |
| 4 | `acompressor` ratio 3, threshold -24 dB | Even out the level |
| 5 | `loudnorm` I=-16, TP=-1.5, two-pass, linear | Consistent loudness |
| 6 | `volume=0.9` | -16 LUFS was too loud in practice |

No noise reduction is applied. WhatsApp already suppresses noise (measured noise floor about -92 dB), so a denoiser would only add artefacts.

### Encoding

- **Video:** H.264 (`libx264 -crf 18 -preset slow`), yuv420p, `+faststart` for streaming.
- **Audio:** AAC 192 kbps.
- **Single pass:** the side-by-side video is built straight from the source in one filter graph, not from the caller output, so nothing is encoded twice.

Processing speed is about 0.6x real time; a 77 s recording takes about 46 s.

## Limitations

- **WhatsApp Desktop layout only:** detection expects the caller video in the centre and the self-view top-right. Other apps or layouts need `--main-crop` / `--self-crop`.
- **Rotation or resize mid-call:** if the phone rotates or the window is resized, the detected box is the union of all positions and comes out too large. Check `--preview-only` and split the recording by time first.
- **Bandwidth:** call audio stops at about 7.5 kHz. The EQ improves clarity but can't restore what the call codec removed.
- **Corners:** panel corners are slightly rounded, so the crops have faint dark corners.

## Privacy

Recordings are private call content. `.gitignore` excludes all video, audio and image files so test recordings and outputs are never committed.

## More

[docs/DESIGN.md](docs/DESIGN.md) records the decisions behind these defaults and the options that were considered.

## License

[MIT](LICENSE)
