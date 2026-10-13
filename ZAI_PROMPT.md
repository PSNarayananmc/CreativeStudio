You are an experienced Linux/Python desktop engineer. Use the attached
creative-studio folder as the source. Deliver a tested
CreativeStudio-x86_64.AppImage for Ubuntu 22.04/24.04, the corrected complete
source ZIP and build/test logs.

Creative Studio is an original single-track Python, PySide6 and FFmpeg video
editor. No Windows EXE is needed. Preserve its features and original dark UI.
Do not claim Premiere parity, reuse Adobe assets, remove third-party licensing,
or replace this app with a launcher/downloader.

1. Inspect all source files, README.md and VALIDATION.md. Use a clean Ubuntu
   22.04 x86_64 build environment. Pins: PySide6 6.8.3, PyInstaller 6.12.0;
   retain unless a documented issue needs a tested upgrade.
2. Run engine tests, syntax checks and real GUI tests. Fix actual app and
   packaging defects without removing features. Record changes. Preserve
   argument-array subprocesses, safe source handling and atomic outputs.
3. Obtain trusted static ffmpeg/ffprobe with libx264 and AAC, and appimagetool.
   Verify published checksums; record exact versions. Set FFMPEG_STATIC,
   FFPROBE_STATIC and APPIMAGETOOL, then run ./build_appimage.sh. Do not copy
   dynamic ffmpeg without dependencies. Audit Qt multimedia/xcb/platform
   plugins and shared libraries in the final bundle.
4. Test the AppImage on clean Ubuntu 22.04/24.04 desktops without installed
   Python or ffmpeg. Test normal and --appimage-extract-and-run launch.
   Confirm bundled media tools are used and Qt codecs/plugins load.
5. GUI acceptance:
   - Window name Creative Studio. Import, append duplicate media, drag reorder,
     delete, undo and redo.
   - Render preview, seek and split at timeline playhead; duration is preserved.
     Edits invalidate preview; re-render uses updated edits.
   - Trim; speeds 0.125/0.5/2/8; colour, volume and fades; same edits in export.
   - Silent/audio files, varying sizes/rates, short clips and spaces/apostrophes/
     Unicode in paths. Save/reopen .csproj; missing/malformed media handling.
   - Export all resolutions; check codecs, dimensions, duration, A/V sync,
     nonblank frames and audible output. Reject overwriting a source.
   - Cancel long render; close while rendering; permission errors, invalid
     paths and full disk. Preserve prior output when rendering fails.
   - No sound device: audio remains optional and video preview can work.
     Also test working sound devices and visible playback errors.
6. The author's environment lacked PySide6. GUI and AppImage tests were not
   performed. Perform them yourself, add regressions for real fixes, and do
   not invent passing checks or promise that no errors are possible.
7. Include third-party notices and fulfill applicable Qt/FFmpeg/GPL/LGPL
   distribution obligations for actual binaries. Original source uses MIT.

Return AppImage, corrected source ZIP, CHANGELOG.md, exact validation report
and dependency version/checksum manifest. Report unresolved limitations.
If unable to build/test, say precisely what is blocked instead of claiming
success. Multi-track editing and other new features are outside this task.
