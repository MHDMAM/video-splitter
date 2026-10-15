# video-splitter

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

## Getting started (step by step)

New to the command line? Follow these steps in order. You only need to do steps 1-4 once.

### What you need

| Tool | Why | Download |
|---|---|---|
| **Python** 3.8 or newer (tested on 3.13) | Runs the script | https://www.python.org/downloads/ |
| **FFmpeg** (includes `ffprobe`) | Does the video and audio work | https://ffmpeg.org/download.html (Windows builds: https://www.gyan.dev/ffmpeg/builds/) |
| **Git** (optional) | Downloads the code | https://git-scm.com/downloads, or use **Code -> Download ZIP** on the GitHub page instead |

No other packages are needed (no `pip install`).

### Step 1 - Open a terminal

- **Windows:** press **Start**, type `PowerShell`, press **Enter**.
- **macOS:** press **Cmd+Space**, type `Terminal`, press **Enter**.
- **Linux:** press **Ctrl+Alt+T**.

### Step 2 - Install Python

**Windows**, either of these:
- **Option A, one command** (Windows 10/11):
  ```powershell
  winget install --id Python.Python.3.13 -e
  ```
- **Option B, installer:** download from https://www.python.org/downloads/ and run it. On the first screen, **tick "Add python.exe to PATH"**, then click **Install Now**.

**macOS:** install Homebrew from https://brew.sh, then:
```bash
brew install python
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt update && sudo apt install python3
```

### Step 3 - Install FFmpeg

**Windows**, either of these:
- **Option A, one command:**
  ```powershell
  winget install --id Gyan.FFmpeg -e
  ```
- **Option B, manual:** download `ffmpeg-release-full.7z` from https://www.gyan.dev/ffmpeg/builds/ and extract it (for example to `C:\ffmpeg`). Then add `C:\ffmpeg\bin` to your PATH: **Start** -> "Edit the system environment variables" -> **Environment Variables** -> select **Path** -> **Edit** -> **New**.

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt install ffmpeg
```

### Step 4 - Check the installs

**Close the terminal and open a new one** so it picks up the new programs. Then run:

```bash
python --version
ffmpeg -version
```

- **Expected:** something like `Python 3.13.x`, then a block of text starting with `ffmpeg version ...`.
- **macOS/Linux:** use `python3` instead of `python`, here and in every command below.
- **Not working?** See [Troubleshooting](#troubleshooting).

### Step 5 - Download this project

- **With Git:**
  ```bash
  git clone https://github.com/MHDMAM/video-splitter.git
  cd video-splitter
  ```
- **Without Git:** on the [GitHub page](https://github.com/MHDMAM/video-splitter) click **Code -> Download ZIP** and extract it. Then in the terminal, go to the extracted folder, for example:
  ```powershell
  cd "$HOME\Downloads\video-splitter-main"
  ```

All commands below are run from inside this folder.

### Step 6 - Record a call (if you don't have a recording yet)

Record the **WhatsApp Desktop call window** while the call is in progress, then save the video as `.mp4`:
- **Windows 11:** Snipping Tool -> **Record**.
- **macOS:** Cmd+Shift+5.
- Or any screen recorder.

Keep the default WhatsApp layout: the caller in the middle, your camera small in the top-right corner.

### Step 7 - Check the detection (preview)

Tip: type the start of the command, then **drag the video file onto the terminal window** to paste its full path. Keep the quotes if the path has spaces.

```bash
python split_call.py "C:\Users\me\Videos\call.mp4" --preview-only
```

This takes a few seconds and prints the detected boxes plus a `Previews` folder path:
- **Windows:** open that folder with `explorer "<path it printed>"`.
- **macOS:** use `open "<path it printed>"`.

Check the images:
- `preview_main.png` should show **only the caller's video**: no black or grey border, no buttons.
- `preview_self.png` should show **only your self-view**.

If they look wrong, see [Detection is wrong](#detection-is-wrong).

### Step 8 - Make the videos

```bash
python split_call.py "C:\Users\me\Videos\call.mp4"
```

- **Time:** a 1-minute recording takes about 40 seconds.
- **Output:** when it finishes, two new files sit **next to your recording**:
  - `call_caller.mp4` - the caller only
  - `call_sidebyside.mp4` - the caller plus your self-view

To put them somewhere else, add `-o` and a folder (it's created if it doesn't exist):
```bash
python split_call.py "C:\Users\me\Videos\call.mp4" -o "C:\Users\me\Videos\processed"
```

### Troubleshooting

| Problem | Fix |
|---|---|
| `'python' is not recognized` or the Microsoft Store opens | Open a **new** terminal after installing. Still failing: reinstall Python with "Add python.exe to PATH" ticked, or turn off the alias in **Settings -> Apps -> Advanced app settings -> App execution aliases** (python.exe / python3.exe). |
| `error: ffmpeg not found` | Open a **new** terminal after installing FFmpeg. With the manual install, check that the `bin` folder is in PATH (Step 3). |
| `can't open file 'split_call.py'` | You're not in the project folder - `cd` into it (Step 5). |
| `error: input not found` | The path is wrong or missing its quotes. Drag the file onto the terminal to paste the exact path. |
| The voice is too loud or too quiet | Add `--volume 0.7` (quieter) or `--volume 1.0` (louder). Default is `0.9`. |

#### Detection is wrong

Open `preview_full.png` from the preview folder in an image editor (Paint works) and find the caller's video rectangle:
- **x, y:** the top-left corner, in pixels.
- **w, h:** the width and height. Use even numbers.

Do the same for your self-view, then pass both boxes:

```bash
python split_call.py "call.mp4" --main-crop 700:936:610:40 --self-crop 354:200:1548:48
```

## Usage reference

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

Only the two videos are written to the output folder, and a full run leaves no temporary files behind. `--preview-only` writes its preview frames (`preview_full.png`, `preview_main.png`, `preview_self.png`) to `<system temp>/video-splitter/<name>/` so you can inspect them.

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

## License

[MIT](LICENSE)
