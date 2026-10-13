# Validation performed — 2026-10-12

- PASS: all Python source files parse/compile with compileall.
- PASS: run.sh and build_appimage.sh pass bash -n.
- PASS: 4 unittest engine tests on the available system FFmpeg:
  - Project round trip with relative paths; split boundary/duration preserved.
  - Real MP4 export combining silent and audible sources, including speed,
    fades, colour and volume. H.264 output is 320×180, yuv420p; has audio;
    expected combined duration is within 0.15 seconds; progress reaches 100%.
  - Cancellation preserves an existing destination.
  - Export to a source path is rejected.

NOT RUN: GUI startup/playback, actual sound-device behavior, drag interaction,
AppImage build, clean Ubuntu desktop compatibility and packaging dependencies.
PySide6 is not installed in the authoring environment. Source and build recipe
are provided for Zai to finish and verify. No AppImage or executable is included.
Passing engine checks do not establish full GUI or distribution compatibility.
