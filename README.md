# Creative Studio 0.1.0

Original Python / Qt / FFmpeg video editor for Ubuntu. This is newly written
source, not a converted EXE, Adobe product, or Premiere clone. It includes no
Adobe code, installers, accounts, activation or branding.

## Install (AppImage, Ubuntu 20.04+)

`CreativeStudio-x86_64.AppImage` is built and tested on an Ubuntu 20.04.5
x86_64 userland (glibc 2.31) and bundles its own Python 3.9, PySide6/Qt 6.8.3,
FFmpeg and FFprobe (H.264/libx264 + AAC). It does not use your system Python,
FFmpeg, or build directory, and can run from any location.

```bash
chmod +x CreativeStudio-x86_64.AppImage
./CreativeStudio-x86_64.AppImage            # requires FUSE (libfuse2)
./CreativeStudio-x86_64.AppImage --appimage-extract-and-run   # FUSE-free
```

Standard Ubuntu 20.04 desktop libraries (X11, ALSA, fontconfig, NSS) are used
from the system. With no audio device the app starts in silent-preview mode.
A self-test is built in:

```bash
QT_QPA_PLATFORM=offscreen CREATIVE_STUDIO_SMOKE=1 CREATIVE_STUDIO_SMOKE_OUT=/tmp \
  ./CreativeStudio-x86_64.AppImage --appimage-extract-and-run
```

It exits 0 and writes `smoke-summary.json` after verifying import, preview
render, undo/redo, inspector apply, 1080p H.264+AAC export and project save.
See TEST-REPORT.md for the full recorded test matrix.

## Run from source

Target: Ubuntu 20.04+ x86_64. On 20.04 use Python 3.9 (PySide6 6.8 supports
it); on 22.04+ use the default python3.

```bash
sudo apt install python3.9-venv ffmpeg libxcb-cursor0 libxkbcommon-x11-0 libegl1 libopengl0
python3.9 -m venv .venv   # python3 -m venv .venv on 22.04+
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

Build on Ubuntu 20.04 x86_64 (glibc 2.31) so the bundled binaries stay
compatible with the 20.04 baseline; newer hosts produce binaries that 20.04
cannot load. A faithful 20.04 build environment on any Linux host:

```bash
# 1. Ubuntu 20.04.5 base userland (no root needed via proot)
curl -LO https://cdimage.ubuntu.com/ubuntu-base/releases/20.04/release/ubuntu-base-20.04.5-base-amd64.tar.gz
mkdir rootfs && tar -xzf ubuntu-base-20.04.5-base-amd64.tar.gz -C rootfs
curl -LO https://github.com/proot-me/proot/releases/download/v5.5.0/proot  # verify SHA256SUMS
chmod +x proot
# 2. Toolchain inside the 20.04 rootfs
./proot -0 -r rootfs -b /dev -b /proc -b /sys -w / /bin/sh -c '
  apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3.9 python3.9-venv python3-pip libgl1 libegl1 libxkbcommon0 \
  libfontconfig1 libdbus-1-3 libglib2.0-0 libpulse0 fonts-dejavu-core \
  libasound2 libxrandr2 libxi6 libxrender1 libxtst6 libxcomposite1 \
  libxdamage1 libnss3 libnspr4 file desktop-file-utils ca-certificates \
  libgssapi-krb5-2 libpython3.9'
# 3. Build (from the source checkout inside the rootfs)
./proot -0 -r rootfs -b /dev -b /proc -b /sys -w /opt/creative-studio-src /bin/sh -c '
  PATH=/opt/ffmpeg-static/bin:$PATH FFMPEG_STATIC=/opt/ffmpeg-static/bin/ffmpeg \
  FFPROBE_STATIC=/opt/ffmpeg-static/bin/ffprobe APPIMAGETOOL=/opt/appimagetool-x86_64.AppImage \
  PYTHON=python3.9 ./build_appimage.sh'
```

Supply trusted FFmpeg/FFprobe (libx264 and AAC; the script audits that they
only link core glibc runtime libraries and require no glibc symbols newer
than 2.31 / GLIBCXX newer than 3.4.28) plus appimagetool. Verify provider
checksums and record the digests (see TEST-REPORT.md).

The script builds a PyInstaller one-folder bundle with PySide6 plugins, adds
media tools and third-party license notices, and invokes appimagetool. It does
not download opaque executables or install system packages. FUSE-free launch:

```bash
./CreativeStudio-x86_64.AppImage --appimage-extract-and-run
```

The 0.1.0 AppImage was built and validated on an Ubuntu 20.04.5 userland; see
TEST-REPORT.md for results and the honest list of what could not be tested in
a container (FUSE mount launch, real X11 interaction, audible playback).
Verify on target machines before distributing.

References: https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/QAudioOutput.html
and https://pyinstaller.org/en/stable/usage.html .
