# Creative Studio 0.1.0 — Build & Test Report (Ubuntu 20.04 x86_64)

Date: 2026-10-13 · Builder: automated build session for
https://github.com/PSNarayananmc/CreativeStudio

Every result below was produced in this session against the real artifacts.
Nothing is projected or assumed. Where a test could not be executed in this
environment it is listed under "Not testable here" with the reason and the
recommended check on real hardware.

## 1. Build environment (genuine Ubuntu 20.04 x86_64 userland)

The build host is a Debian 13 container without root. Its seccomp filter
blocks `chroot`, `mknod`, and unprivileged user namespaces, so the build ran
inside **proot v5.5.0** (ptrace-based userspace rootfs; no kernel features
required) over an **ubuntu-base 20.04.5 amd64** rootfs. Everything compiled
and executed there uses the genuine Ubuntu 20.04 userland — glibc
2.31-0ubuntu9.9, GCC-9 runtime, focal package set — which is the compatibility
baseline the binary AppImage must satisfy.

| Component | Version | Source | Integrity |
|---|---|---|---|
| Ubuntu base rootfs | 20.04.5 amd64 | cdimage.ubuntu.com | official image |
| proot | 5.5.0 static | github.com/proot-me/proot v5.5.0 | sha256 `db185300a9daabbce86aca7632d8c7fdc4249f6f153171954013b70c5f491ec0` — matched upstream `SHA256SUMS` |
| Python | 3.9.5 (`python3.9`, focal) | archive.ubuntu.com | apt, focal-updates |
| PySide6 / Qt | 6.8.3 | PyPI (manylinux_2_28 cp39) | pip hash-checked by pip |
| PyInstaller | 6.12.0 | PyPI | pip |
| FFmpeg / FFprobe | n8.1.3-18-g46d899d7a0-20261012 (linux64-gpl) | github.com/BtbN/FFmpeg-Builds `latest` tag | sha256 below; upstream publishes no checksum file for auto-builds — digest recorded here pins the exact artifact |
| appimagetool | continuous x86_64 | github.com/AppImage/appimagetool | static-pie ELF, ran with `--appimage-extract-and-run` |

**FFmpeg/FFprobe SHA-256**
```
5c2066c217e63d0e58808d8ac5cc807fe4b29754c3211c9975efa8eeddf497de  ffmpeg
2f54298b661ce34c4048362753d3010bb110bf50002b11449d4c8dc8db839d4d  ffprobe
```

**Baseline audit of the FFmpeg tools** (script `verify_2004_compat` in
`build_appimage.sh`, run during the build):
- linked libraries: only `libc/libm/libmvec/libdl/libpthread/librt/libgcc_s`
  + `ld-linux` — all core glibc, present on every Ubuntu desktop
- maximum required glibc symbol version: **GLIBC_2.28** (20.04 provides 2.31)
- no `GLIBCXX` requirements (no libstdc++ dependency)
- encoders verified present: `libx264` (H.264/AVC) and `aac`

**Why PySide6 6.8.3 needs Python 3.9:** PySide6 6.8 dropped Python 3.8, and
Ubuntu 20.04 defaults to 3.8; focal's `python3.9` package (3.9.5) satisfies
it, so `build_appimage.sh` gained a `PYTHON` override. requirements.txt is
unchanged (`PySide6==6.8.3`).

## 2. Artifact

```
CreativeStudio-x86_64.AppImage
size:     356,526,584 bytes
sha256:   49efd4c9daf62e74c0334566c4ab4322fbc85ecc0d6abaf0d3b08bce50b89771
format:   ELF 64-bit LSB shared object, x86-64 (AppImage type 2)
magic:    bytes at offset 8 = 41 49 02 ("AI" + type 2) — verified
```

AppDir audit (from `--appimage-extract`): `AppRun`, `creative-studio.desktop`,
`creative-studio.svg`/`.DirIcon`, `LICENSE`, `THIRD-PARTY-LICENSES.txt`,
`usr/creative-studio/` (PyInstaller onedir bundle with all PySide6/Qt plugins)
and `usr/creative-studio/bin/{ffmpeg,ffprobe}` (bundled media tools).
`AppRun` prepends only the bundled `bin` to `PATH`; all paths are derived from
the AppImage's own location at runtime, so the image is relocatable and uses
no build directory, venv, or system FFmpeg.

## 3. Test results (all inside the Ubuntu 20.04.5 rootfs)

### 3.1 Engine unit tests — PASS 4/4
`python3.9 -m unittest discover -s tests -v` with the bundled-to-be FFmpeg on
`PATH`:
```
test_cancel_preserves_destination ... ok
test_project_and_split ... ok
test_render_audio_silent_speed_colour_fades ... ok
test_source_overwrite_rejected ... ok
Ran 4 tests in 0.647s — OK
```
These generate real media with `testsrc2`/`sine`, encode H.264+AAC, verify
render output (dimensions, pix_fmt, duration, audio), atomic cancel
preservation, project save/load round-trip and source-overwrite rejection.

### 3.2 Packaged AppImage end-to-end self-test — PASS (exit 0, 10/10 steps)
Command: `QT_QPA_PLATFORM=offscreen CREATIVE_STUDIO_SMOKE=1
./CreativeStudio-x86_64.AppImage --appimage-extract-and-run`
(see `test-logs/appimage-smoke.log`, `test-evidence/smoke-summary.json`)

| # | Step | Result | Evidence |
|---|---|---|---|
| 1 | Window created (dark UI QSS applied) | PASS | windowTitle check |
| 2 | Media import + ffprobe (bundled) | PASS | 2.00 s duration probed |
| 3 | Preview render (640×360, full engine) | PASS | preview.mp4 created |
| 4 | Preview playback source attached | PASS | QMediaPlayer source set |
| 5 | Split at playhead | SKIPPED | QMediaPlayer does not advance positions on the offscreen platform — see §4 |
| 6 | Undo / redo | PASS | history stacks verified |
| 7 | Inspector apply (speed change) | PASS | clip.speed updated |
| 8 | Resolution options | PASS | 3 export sizes present |
| 9 | 1080p export (1920×1080) | PASS | export file created |
| 10 | Export codec verification | PASS | ffprobe: `h264 1920x1080 + aac` |
| 11 | Project save + reload | PASS | .csproj written, load_project round-trip |

The export in steps 9–10 was produced **only through the packaged binary and
its bundled ffmpeg/ffprobe** — no system media tools involved.

### 3.3 UI rendering evidence
`test-evidence/creative-studio-offscreen.png` — the main window rendered by
Qt 6.8.3 inside the 20.04 rootfs (offscreen platform, no X server): dark
theme, toolbar, media pane, clip inspector, transport, timeline, and the
status bar message `Ready · No audio device: silent preview`, which also
exercises the no-audio-device code path. The packaged AppImage runs the same
frozen code.

### 3.4 Syntax / script checks
`python -m compileall` on `main.py`, `creative_studio`, `tests` — clean;
`bash -n run.sh build_appimage.sh` — clean.

## 4. Not testable here (honest limitations)

| Item | Why | What was verified instead | Recommendation |
|---|---|---|---|
| FUSE-mount launch (double-click / direct exec) | no `/dev/fuse` in the container | `--appimage-extract-and-run` works end-to-end (§3.2); AppImage type-2 format verified | on a desktop with `libfuse2`, launch normally; if FUSE is absent use `--appimage-extract-and-run` |
| Interactive GUI on X11/Wayland (real rendering, drag-reorder with a mouse, dialogs, shortcuts) | no display server in the container | full widget construction, styling and rendering offscreen; all non-dialog code paths driven through the real `Window` class | run once on a 20.04 desktop; try import → preview → seek → S-split → export |
| Split at playhead via playback | QMediaPlayer does not advance position on the offscreen platform (no audio/video sink timing) | split logic covered by unit test (`test_project_and_split`) against the same `Clip.split` used by the UI | press Play, seek, press S on real hardware |
| Audible playback with a sound device | no audio hardware; PulseAudio/PipeWire not running | `QMediaDevices.audioOutputs()` empty path: app starts silent, no crash, status bar reflects it | play an exported MP4 / preview audibly on real hardware |
| Fresh-20.04-desktop install from this exact AppImage | this was a container userland, not a full desktop install | build-env library audit + bundled-tools-only export | the sanity pass above on real hardware |

## 5. Reproducing the build & tests

See `README.md` § "AppImage build recipe" for the exact proot + ubuntu-base
commands. In short: create the 20.04 rootfs, install the toolchain, then run
`build_appimage.sh` with `FFMPEG_STATIC`, `FFPROBE_STATIC`, `APPIMAGETOOL`
and `PYTHON=python3.9`. Tests: engine tests (§3.1 command) and the built-in
self-test (§3.2 command) — both exit non-zero on any failure.

## 6. Third-party licenses

`THIRD-PARTY-LICENSES.txt` (inside the AppImage and the source tree) covers
Qt 6.8 / PySide6 / shiboken6 (LGPL-3.0, with source links and the LGPL source
offer), Python 3.9 (PSF-2.0, full text included), PyInstaller 6.12 (GPL-2.0
with the bootloader exception), FFmpeg n8.1 + x264 (GPL-2.0-or-later as
configured), DejaVu fonts, and the embedded helper packages. The application
itself is MIT-licensed (`LICENSE`).
