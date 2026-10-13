#!/usr/bin/env bash
# Run on Ubuntu 22.04 x86_64 for a glibc baseline compatible with 24.04.
# Supply audited static FFmpeg tools and an appimagetool; no opaque auto-downloads.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ $(uname -m) == x86_64 ]] || { echo 'Build requires x86_64'; exit 1; }
: "${FFMPEG_STATIC:?Set FFMPEG_STATIC to an absolute static ffmpeg executable}"
: "${FFPROBE_STATIC:?Set FFPROBE_STATIC to an absolute static ffprobe executable}"
: "${APPIMAGETOOL:?Set APPIMAGETOOL to an absolute appimagetool executable}"
for task_binary in "$FFMPEG_STATIC" "$FFPROBE_STATIC" "$APPIMAGETOOL"; do
  [[ "$task_binary" == /* && -x "$task_binary" ]] || { echo "Invalid executable: $task_binary"; exit 1; }
done
for task_binary in "$FFMPEG_STATIC" "$FFPROBE_STATIC"; do
  if ldd "$task_binary" 2>/dev/null | grep -q '=>'; then
    echo "Supply a static binary, or extend packaging to bundle all dependencies: $task_binary"
    exit 1
  fi
done
"$FFMPEG_STATIC" -hide_banner -encoders 2>/dev/null | grep -q libx264 || { echo 'FFmpeg needs libx264'; exit 1; }
python3 -m venv .build-venv
.build-venv/bin/python -m pip install -r requirements.txt 'pyinstaller==6.12.0'
.build-venv/bin/python -m PyInstaller --noconfirm --clean --onedir \
  --name creative-studio --collect-all PySide6 --add-data 'packaging:packaging' main.py
# Only this generated build directory is removed.
rm -rf -- build/CreativeStudio.AppDir
appdir="$PWD/build/CreativeStudio.AppDir"
mkdir -p "$appdir/usr/bin"
cp -a dist/creative-studio "$appdir/usr/creative-studio"
mkdir -p "$appdir/usr/creative-studio/bin"
cp "$FFMPEG_STATIC" "$appdir/usr/creative-studio/bin/ffmpeg"
cp "$FFPROBE_STATIC" "$appdir/usr/creative-studio/bin/ffprobe"
cp packaging/creative-studio.desktop packaging/creative-studio.svg "$appdir/"
cp packaging/creative-studio.svg "$appdir/.DirIcon"
cat > "$appdir/AppRun" <<'APPRUN'
#!/bin/sh
set -eu
APPDIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export PATH="$APPDIR/usr/creative-studio/bin:$PATH"
exec "$APPDIR/usr/creative-studio/creative-studio" "$@"
APPRUN
chmod +x "$appdir/AppRun" "$appdir/usr/creative-studio/bin/ffmpeg" "$appdir/usr/creative-studio/bin/ffprobe"
ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run "$appdir" "$PWD/CreativeStudio-x86_64.AppImage"
echo "Created $PWD/CreativeStudio-x86_64.AppImage — run acceptance tests before distribution."
