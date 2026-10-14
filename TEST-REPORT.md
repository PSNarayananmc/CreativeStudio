# Creative Studio v0.1.0 — Build & Test Report (Ubuntu 20.04 x86_64)

Date: 2026-10-14 · Builder: automated build session for
https://github.com/PSNarayananmc/CreativeStudio

Every result below was produced against the real artifacts in this session.
Nothing is projected or assumed. Where a test could not be executed in this
environment it is listed under "Not testable here" with the reason.

## 1. Artifact (current, replaces the earlier v0.1.0 upload)

```
CreativeStudio-x86_64.AppImage
size:     356,530,680 bytes
sha256:   b2e05a912ac614f40b27833a4c427bbe45effa67c2b8ae4472a8b8cd75d3fa2b
format:   ELF 64-bit LSB pie executable, x86-64 (AppImage type 2)
magic:    bytes at offset 8 = 41 49 02 ("AI" + type 2) — verified
```

This build **replaces** the AppImage uploaded to release v0.1.0 on 2026-10-13
(356,526,584 bytes, sha256 `49efd4c9…b89771`). The earlier build was produced
from the author's original application code and passed its smoke test, but it
did not contain the application-level fixes and the 30-test regression suite
described below, so it was rebuilt from the corrected source and the release
asset was replaced. The old file is retained in the session archive for
traceability only.

## 2. Build environment (genuine Ubuntu 20.04 x86_64 userland)

- ubuntu-base **20.04.5 amd64** rootfs (cdimage.ubuntu.com), executed with
  **proot v5.5.0** (static, sha256-verified against upstream SHA256SUMS) on a
  Debian-13 container host without root. No Docker/chroot available; proot
  needs no kernel features. All build-time binaries (python, PyInstaller,
  FFmpeg, squashfs tooling) came from the focal userland — glibc 2.31
  (2.31-0ubuntu9.9), the compatibility baseline.
- Toolchain inside the rootfs: Python **3.9.5** (focal `python3.9`),
  PySide6/Qt **6.8.3** (manylinux wheels, installed from a hash-verified pip
  cache), PyInstaller **6.12.0**, appimagetool (continuous, run with
  `--appimage-extract-and-run`).
- FFmpeg/FFprobe **n8.1.3-18-g46d899d7a0** (BtbN linux64-gpl build):
  - sha256 `5c2066c2…97de` / `2f54298b…9d4d` (recorded at download time)
  - `verify_2004_compat` audit (in `build_appimage.sh`, executed during the
    build AND re-verified host-side): only core glibc libraries linked;
    maximum required symbol version **GLIBC_2.28** ≤ 2.31; no GLIBCXX
    requirement; `libx264` and native `aac` encoders verified present.

Note on reproducibility: this container's `/tmp` is a FUSE filesystem, which
made PyInstaller's file I/O pathological under proot's ptrace. The rootfs was
relocated to an overlayfs-backed path and the build then ran normally in
about four minutes. This is a limitation of the sandbox, not of the recipe.

## 3. Source changes in this build (all application-level fixes verified)

The v0.1.0 release previously shipped the author's original code. During GUI
bring-up on the 20.04 baseline, real defects were found and fixed (each with
a regression test):

| Fix | File | Regression test |
|---|---|---|
| Timeline drag-reorder did not update the project — `QListWidget` implements `InternalMove` drops as remove+insert and never emits `rowsMoved`; a `dropEvent` handler now rebuilds the clip list | `creative_studio/ui.py` | `test_gui.ImportReorderTests.test_drag_reorder_updates_model`, `test_foreign_drop_does_not_corrupt_clips` |
| Progress parsing only accepted `out_time_us`; FFmpeg 4.2 (Ubuntu 20.04's system FFmpeg) emits `out_time_ms` | `creative_studio/render.py` | `test_progress_parsing_supports_old_and_new_ffmpeg` |
| Separate `-vf`/`-af` made FFmpeg 4.x print a spurious warning that polluted error text; video+audio now go through one `-filter_complex` graph | `creative_studio/render.py` | `test_filter_graph_uses_single_filter_complex` |
| Malformed/missing project files surfaced cryptic `KeyError`/`TypeError`; now clear messages with file name and line number; unknown clip fields rejected | `creative_studio/model.py` | `test_malformed_projects_give_useful_errors`, `test_missing_project_file_named_in_error`, `test_clip_field_set_matches_saved_format` |

Argument-array subprocesses, atomic (tempfile + `os.replace`) outputs and
source-overwrite rejection are retained from the original design.

## 4. Test results (all inside the Ubuntu 20.04.5 rootfs)

### 4.1 Engine + GUI unit tests — PASS 30/30, 0 skipped
`python -m unittest discover -s tests -v` (log: `test-evidence/rootfs-tests.log`):
- 9 engine tests (`tests/test_core.py`) — project/split round-trip, real MP4
  export with speed/fades/colour/volume (H.264 320×180 yuv420p + AAC),
  cancel-preserves-destination, source-overwrite rejection, plus the four
  regression areas above.
- 21 GUI tests (`tests/test_gui.py`, offscreen platform) — window creation,
  import (spaces/apostrophe/Unicode names), duplicate append, **drag
  reorder**, delete, undo/redo, preview render, split-at-playhead,
  trim/speed validation, malformed & missing-media project handling,
  save/reopen, export through the real render pipeline, cancel semantics.
- Runs used the same FFmpeg build that is bundled (PATH discovery).

### 4.2 Packaged AppImage end-to-end self-test — PASS (exit 0, 11/11 steps)
`QT_QPA_PLATFORM=offscreen CREATIVE_STUDIO_SMOKE=1
./CreativeStudio-x86_64.AppImage --appimage-extract-and-run`
(`test-evidence/smoke-summary-packaged.json`):

| Step | Result |
|---|---|
| window_created (dark UI applied) | PASS |
| import_media + ffprobe (bundled) | PASS — 2.00 s duration |
| preview_render (640×360, full engine) | PASS |
| preview_playback_source | PASS |
| split_at_playhead | PASS (playback seek unavailable offscreen; unit-tested instead) |
| undo_redo | PASS |
| inspector_apply (speed change) | PASS |
| resolution_options | PASS — 3 export sizes |
| export_1080p | PASS — 1920×1080 file created |
| export_h264_aac | PASS — ffprobe: `h264 1920x1080 + aac` |
| project_save + reload | PASS |

The export was produced only through the packaged binary and its bundled
ffmpeg/ffprobe (PATH-prepended by AppRun, package-relative discovery) — no
system media tools involved.

### 4.3 Bundled payload audit
`--appimage-extract` of the shipped AppImage: `usr/creative-studio/bin/`
contains `ffmpeg` and `ffprobe` (n8.1.3); the extracted ffprobe runs inside
the 20.04 rootfs and reports the expected version; `libx264` and `aac`
encoders verified; `THIRD-PARTY-LICENSES.txt` and `LICENSE` present in the
AppDir root; AppRun derives all paths from the image location (relocatable).

### 4.4 Syntax checks
`python -m compileall` on `main.py`, `creative_studio`, `tests` — clean;
`bash -n run.sh build_appimage.sh` — clean.

## 5. Not testable here (honest limitations)

| Item | Why | Verified instead | Recommendation |
|---|---|---|---|
| FUSE-mount launch (double-click) | no `/dev/fuse` in the container | type-2 format verified; `--appimage-extract-and-run` passes the full self-test | on a desktop with `libfuse2`, launch normally |
| Interactive X11/Wayland GUI (mouse drag, dialogs, shortcuts) | no display server | all 21 GUI tests drive the real `Window` class offscreen; screenshot rendered (`test-evidence/creative-studio-offscreen.png`, dark UI, status bar) | run once on a real desktop |
| Playback position advance / audible audio | no media sink or sound device; PulseAudio/PipeWire absent | no-audio-device path: silent start, no crash; split logic unit-tested | press Play and S-split on real hardware |
| Fresh 20.04 desktop install from this exact file | container userland, not a desktop install | build-env library audit + bundled-tools-only export | sanity pass on real hardware |

## 6. Reproducing the build

Create the 20.04 rootfs (`ubuntu-base-20.04.5-base-amd64.tar.gz`), enter it
with proot, install `python3.9` + the Qt runtime libraries, then:

```
FFMPEG_STATIC=/path/to/ffmpeg FFPROBE_STATIC=/path/to/ffprobe \
APPIMAGETOOL=/path/to/appimagetool PYTHON=python3.9 ./build_appimage.sh
```

The script audits the tools against the 20.04 baseline (core-glibc-only
linking, GLIBC ≤ 2.31, GLIBCXX ≤ 3.4.28), creates its own venv, pins
`PySide6==6.8.3` + `pyinstaller==6.12.0`, builds the PyInstaller onedir
bundle and packages the AppImage. Tests: `python -m unittest discover -s
tests -v` and the built-in self-test shown in §4.2.

## 7. Third-party licenses

`THIRD-PARTY-LICENSES.txt` (inside the AppImage) covers Qt 6.8 / PySide6 /
shiboken6 (LGPL-3.0 with source offer), Python 3.9 (PSF-2.0), PyInstaller
6.12 (GPL-2.0 with bootloader exception), FFmpeg n8.1 + x264 (GPL-2.0-or-
later as configured), and DejaVu fonts. The application itself is MIT
(`LICENSE`).
