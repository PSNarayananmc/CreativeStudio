# Creative Studio 0.1.0

Original Python / Qt / FFmpeg video editor for Ubuntu. This is newly written
source, not a converted EXE, Adobe product, or Premiere clone. It includes no
Adobe code, installers, accounts, activation or branding.

## Run from source

Target: Ubuntu 22.04 / 24.04 x86_64, Python 3.10 or newer.

```bash
sudo apt install python3-venv ffmpeg libxcb-cursor0 libxkbcommon-x11-0 libegl1 libopengl0
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
CREATIVE_STUDIO_PYTHON="$PWD/.venv/bin/python" ./run.sh
```

Qt uses system display/audio services. No audio output is created when no
device is reported; preview can operate silently. This guard does not guarantee
against every driver or multimedia failure.

## Workflow

1. Import videos (Ctrl+I); they append to the timeline. Double-click a project
   media item to append another copy. Video imports only in this version.
2. Drag timeline items to reorder. Select one, change inspector controls, then
   click Apply. Fades are to/from black and silence, not cross transitions.
3. Render preview after edits. Seek the rendered preview, then press S to split
   at that timeline position. Delete removes the selected clip.
4. Ctrl+Z undo; Ctrl+Shift+Z redo. Ctrl+S saves `.csproj`; Ctrl+O opens it.
   Media paths are relative to the project; source files are not copied into it.
5. Export MP4 (Ctrl+E) at landscape 1080p, landscape 720p or portrait 1080p.
   Output: H.264 / AAC, 30 fps. Aspect ratio is preserved with black padding.
   Speed preserves pitch using FFmpeg's atempo filter.

Rendering uses a worker thread with cancellation. Existing outputs are replaced
only after a successful render; source overwrite is rejected. Project save is
atomic. Closing during a render cancels and waits, then checks unsaved edits.

Preview is a 640x360 render of the whole timeline, not a live GPU compositor.
Re-render after edits. Export needs disk space for temporary clips and final output.

## Scope

Single sequential video/audio track; cuts; reorder; trim; split; speed
0.125–8×; volume; colour; fades; undo/redo; projects; preview; MP4 export.

Not implemented: stacked multi-track composition, audio-only imports, waveforms,
titles/subtitles, keyframes, masks, chroma key, cross dissolves, proxies, plugins,
RAW editing, hardware encoding or Premiere project interchange. The dark NLE
workspace is an original layout. Full Premiere feature parity is not provided.

## Verification

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q main.py creative_studio tests
bash -n run.sh build_appimage.sh
```

Engine tests generate media locally and check export, silent/audio inputs,
punctuation in paths, splitting, projects and safe cancellation.
See VALIDATION.md for checks actually performed. ZAI_PROMPT.md covers GUI checks.

## AppImage build recipe

Build on Ubuntu 22.04 x86_64 to keep the glibc baseline compatible with 24.04.
Supply trusted static ffmpeg/ffprobe (libx264 and AAC support), plus appimagetool.
Verify provider checksums and licenses. Dynamic binaries are rejected because
copying them alone does not bundle their shared libraries.

```bash
FFMPEG_STATIC=/absolute/path/ffmpeg \
FFPROBE_STATIC=/absolute/path/ffprobe \
APPIMAGETOOL=/absolute/path/appimagetool \
./build_appimage.sh
```

The script builds a PyInstaller one-folder bundle with PySide6 plugins, adds
media tools and invokes appimagetool. It does not download opaque executables
or install system packages. FUSE-free launch:

```bash
./CreativeStudio-x86_64.AppImage --appimage-extract-and-run
```

Build recipe supplied; AppImage build and desktop testing not performed here.
Verify on target machines before distributing. Include third-party notices and
source offers required by the actual Qt/FFmpeg binaries you distribute.

References: https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/QAudioOutput.html
and https://pyinstaller.org/en/stable/usage.html .
