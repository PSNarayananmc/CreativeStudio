#!/usr/bin/env bash
# Build CreativeStudio-x86_64.AppImage.
#
# Run on Ubuntu 20.04 x86_64 (glibc 2.31) so the bundled Python/Qt binaries
# stay compatible with the 20.04 baseline. A faithful 20.04 userland can be
# obtained with ubuntu-base-20.04.5 + proot (see TEST-REPORT.md); run this
# script inside it with PYTHON=python3.9.
#
# Supply audited FFmpeg tools and an appimagetool; no opaque auto-downloads.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ $(uname -m) == x86_64 ]] || { echo 'Build requires x86_64'; exit 1; }
: "${FFMPEG_STATIC:?Set FFMPEG_STATIC to an absolute ffmpeg executable}"
: "${FFPROBE_STATIC:?Set FFPROBE_STATIC to an absolute ffprobe executable}"
: "${APPIMAGETOOL:?Set APPIMAGETOOL to an absolute appimagetool executable}"
: "${PYTHON:=python3}"
for task_binary in "$FFMPEG_STATIC" "$FFPROBE_STATIC" "$APPIMAGETOOL"; do
  [[ "$task_binary" == /* && -x "$task_binary" ]] || { echo "Invalid executable: $task_binary"; exit 1; }
done

# Runtime compatibility audit for the Ubuntu 20.04 (glibc 2.31, GCC 9) baseline:
# the tools may link the core glibc runtime only, and may not require glibc
# symbols newer than 2.31 or GLIBCXX newer than 3.4.28.
verify_2004_compat() {
  local tool="$1" name dep max_symbol
  name="$(basename -- "$tool")"
  local allowed='^(linux-vdso|ld-linux-x86-64\.so\.2|libc\.so\.6|libm\.so\.6|libmvec\.so\.1|libdl\.so\.2|libpthread\.so\.0|librt\.so\.1|libgcc_s\.so\.1|libstdc\+\+\.so\.6|libz\.so\.1)$'
  while IFS= read -r dep; do
    [[ -z "$dep" ]] && continue
    grep -Eq "$allowed" <<<"$dep" || { echo "$name: non-baseline library '$dep'"; exit 1; }
  done < <(ldd -- "$tool" 2>/dev/null | awk '/=> \//{print $1} /^\//{print $1}')
  max_symbol="$(objdump -T -- "$tool" 2>/dev/null | grep -oE 'GLIBC_[0-9.]+' | sort -uV | tail -1 | cut -d_ -f2 || true)"
  if [[ -n "$max_symbol" ]]; then
    [[ "$(printf '%s\n2.31\n' "$max_symbol" | sort -V | head -1)" == "$max_symbol" ]] \
      || { echo "$name: requires GLIBC $max_symbol > 2.31 (Ubuntu 20.04)"; exit 1; }
  fi
  max_symbol="$(objdump -T -- "$tool" 2>/dev/null | grep -oE 'GLIBCXX_[0-9.]+' | sort -uV | tail -1 | cut -d_ -f2 || true)"
  if [[ -n "$max_symbol" ]]; then
    [[ "$(printf '%s\n3.4.28\n' "$max_symbol" | sort -V | head -1)" == "$max_symbol" ]] \
      || { echo "$name: requires GLIBCXX $max_symbol > 3.4.28 (Ubuntu 20.04)"; exit 1; }
  fi
  echo "$name: Ubuntu 20.04 baseline OK (glibc<=2.31, core libs only)"
}
verify_2004_compat "$FFMPEG_STATIC"
verify_2004_compat "$FFPROBE_STATIC"
# Capture encoder output before grepping: 'grep -q' exiting early sends
# SIGPIPE to ffmpeg and 'set -o pipefail' would turn that into a false
# negative (a latent bug in the previous revision of this script).
ffmpeg_encoders="$("$FFMPEG_STATIC" -hide_banner -encoders 2>/dev/null || true)"
echo "$ffmpeg_encoders" | grep -q libx264 || { echo 'FFmpeg needs libx264'; exit 1; }
echo "$ffmpeg_encoders" | grep -qE '[[:space:]]aac[[:space:]]' || { echo 'FFmpeg needs the AAC encoder'; exit 1; }
"$FFPROBE_STATIC" -hide_banner -version >/dev/null 2>&1 || { echo 'ffprobe not runnable'; exit 1; }

"$PYTHON" -m venv .build-venv
.build-venv/bin/python -m pip install -q -U pip
.build-venv/bin/python -m pip install -q -r requirements.txt 'pyinstaller==6.12.0'
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
cp packaging/THIRD-PARTY-LICENSES.txt "$appdir/THIRD-PARTY-LICENSES.txt"
cp LICENSE "$appdir/LICENSE"
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
