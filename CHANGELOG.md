# Changelog

## 0.1.0 — 2026-10-13

First packaged release: `CreativeStudio-x86_64.AppImage`, built and validated
on an Ubuntu 20.04.5 x86_64 userland (glibc 2.31). Application source is
unchanged from the initial authoring except where noted below; all editor
features are intact.

### Added
- Packaged AppImage (type 2) bundling Python 3.9.5, PySide6/Qt 6.8.3,
  FFmpeg n8.1.3 and FFprobe (libx264/H.264 + AAC), with AppDir license
  notices (`THIRD-PARTY-LICENSES.txt`, `LICENSE`).
- Built-in self-test mode (`CREATIVE_STUDIO_SMOKE=1`, offscreen-safe) that
  exercises import, preview render, undo/redo, inspector apply, 1080p
  H.264+AAC export and project save through the real UI/engine code, writing
  a `smoke-summary.json` report. Normal launches are unaffected.
- `TEST-REPORT.md` with the recorded build/test matrix, checksums and the
  honest list of what a container cannot verify.
- `.gitignore` for build artifacts.

### Fixed
- `build_appimage.sh`: latent false failure in the encoder checks —
  `ffmpeg -encoders | grep -q` exits early, ffmpeg receives SIGPIPE and
  `set -o pipefail` turned that into a spurious "FFmpeg needs libx264" abort.
  Encoder output is now captured before grepping.
- `build_appimage.sh`: retargeted from an Ubuntu 22.04 baseline to the
  Ubuntu 20.04 (glibc 2.31 / GLIBCXX 3.4.28) baseline, replacing the
  "must be fully static" FFmpeg requirement with a precise runtime audit:
  core glibc libraries only, max GLIBC_ symbol ≤ 2.31, max GLIBCXX ≤ 3.4.28.
  A `PYTHON` variable override supports focal's `python3.9` (required for
  PySide6 6.8.x, which needs Python ≥ 3.9 while 20.04 defaults to 3.8).

### Compatibility
- Verified inside Ubuntu 20.04.5: engine tests 4/4, packaged self-test 10/10
  steps (see TEST-REPORT.md). Not verifiable in a container: FUSE-mount
  launch, real X11/Wayland interaction, audible playback with a sound device.
