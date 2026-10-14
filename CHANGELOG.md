# Changelog

## 0.1.0 — final build 2026-10-14 (replaces the 2026-10-13 upload)

The v0.1.0 release asset was rebuilt from corrected source and re-uploaded.
New AppImage: 356,530,680 bytes, sha256 `b2e05a91…d3fa2b` (see TEST-REPORT.md).
The 2026-10-13 build (sha256 `49efd4c9…b89771`) contained the packaging fixes
below but shipped the author's original application code; application-level
defects found during GUI bring-up were fixed and are now included, each with
a regression test. All editor features are intact.

### Added
- Packaged AppImage (type 2) bundling Python 3.9.5, PySide6/Qt 6.8.3,
  FFmpeg n8.1.3 and FFprobe (libx264/H.264 + AAC), with AppDir license
  notices (`THIRD-PARTY-LICENSES.txt`, `LICENSE`).
- Built-in self-test mode (`CREATIVE_STUDIO_SMOKE=1`, offscreen-safe) that
  exercises import, preview render, undo/redo, inspector apply, 1080p
  H.264+AAC export and project save through the real UI/engine code, writing
  a `smoke-summary.json` report. Normal launches are unaffected.
- GUI acceptance test suite (`tests/test_gui.py`, 21 tests, offscreen-capable)
  covering import, duplicate append, drag reorder, delete, undo/redo,
  preview, split, inspector, project handling and export.
- `TEST-REPORT.md` with the recorded build/test matrix, checksums and the
  honest list of what a container cannot verify.
- `.gitignore` for build artifacts.

### Fixed (application)
- Timeline drag reordering did not update the project: `QListWidget`
  implements `InternalMove` drops as remove+insert and never emits
  `rowsMoved`, so drags looked right while exports/undo used the stale
  order. A `TimelineList.dropEvent` handler now rebuilds the clip list;
  foreign/rejected drops are ignored.
  (Regression: `tests/test_gui.py::test_drag_reorder_updates_model`.)
- Export progress never advanced with Ubuntu 20.04's system FFmpeg 4.2,
  which emits `out_time_ms` instead of `out_time_us`; both are accepted now.
  (Regression: `test_progress_parsing_supports_old_and_new_ffmpeg`.)
- Renders pass video and audio through one `-filter_complex` graph instead
  of separate `-vf`/`-af`, avoiding a spurious FFmpeg 4.x warning that
  polluted user-facing error text.
  (Regression: `test_filter_graph_uses_single_filter_complex`.)
- Malformed or missing `.csproj` files now fail with clear messages (file
  name, JSON line number, offending clip index, unknown fields) instead of
  raw `KeyError`/`TypeError`.
  (Regressions: `test_malformed_projects_give_useful_errors`,
  `test_missing_project_file_named_in_error`,
  `test_clip_field_set_matches_saved_format`.)

### Fixed (packaging)
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
- Verified inside Ubuntu 20.04.5 (this build): unit tests 30/30 (9 engine +
  21 GUI, offscreen), packaged self-test 11/11 steps, bundled FFmpeg/FFprobe
  audited (max GLIBC_2.28 ≤ 2.31). Not verifiable in a container: FUSE-mount
  launch, real X11/Wayland interaction, split-via-playback-position, audible
  playback with a sound device (see TEST-REPORT.md §5).
