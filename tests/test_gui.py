"""GUI acceptance tests for Creative Studio.

Requires PySide6 and a working Qt platform (Xvfb or offscreen). Skips cleanly
when PySide6 is unavailable. Rendering tests use the same FFmpeg discovery as
the app (set CREATIVE_STUDIO_FFMPEG_DIR or PATH, or place ffmpeg/ffprobe in a
'bin' directory next to the creative_studio package).
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from creative_studio.render import binary, probe

try:
    from PySide6.QtCore import Qt, QPointF, QUrl, QTimer, QMimeData
    from PySide6.QtGui import QDropEvent
    from PySide6.QtWidgets import (QApplication, QMessageBox, QFileDialog,
                                   QListWidget)
    from PySide6.QtMultimedia import QMediaDevices
    from creative_studio.ui import Window
    HAVE_PYSIDE = True
except Exception as _exc:  # PySide6 missing or platform unusable
    HAVE_PYSIDE = False
    _IMPORT_ERROR = _exc

APP = None


def setUpModule():
    global APP
    if not HAVE_PYSIDE:
        raise unittest.SkipTest(f'PySide6 unavailable: {_IMPORT_ERROR}')
    os.environ.setdefault('QT_LOGGING_RULES', 'qt.multimedia.*=false')
    APP = QApplication.instance() or QApplication(['creative-studio-tests'])


def wait_until(predicate, timeout=30.0, what='condition'):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        APP.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f'Timed out after {timeout}s waiting for {what}')


def make_media(root, silent=True, name='clip.mp4', size='160x90', rate=30, seconds=1.0):
    path = root / name
    cmd = [binary('ffmpeg'), '-v', 'error', '-y', '-f', 'lavfi',
           '-i', f'testsrc2=size={size}:rate={rate}']
    if not silent:
        cmd += ['-f', 'lavfi', '-i', f'sine=frequency=440:sample_rate=48000']
    cmd += ['-t', str(seconds), '-c:v', 'libx264', '-threads', '1']
    if not silent:
        cmd += ['-c:a', 'aac', '-shortest']
    cmd += [str(path)]
    subprocess.run(cmd, check=True)
    return str(path)


def mean_luma(path, when=0.1):
    out = subprocess.run([binary('ffmpeg'), '-hide_banner', '-nostdin',
                          '-ss', str(when), '-i', str(path), '-frames:v', '1',
                          '-vf', 'signalstats,metadata=print:file=-',
                          '-f', 'null', '-'], capture_output=True, text=True)
    values = [line.split('=')[1] for line in out.stdout.splitlines()
              if 'YAVG' in line]
    if not values:
        raise AssertionError(f'No YAVG from signalstats: {out.stderr[-500:]}')
    return float(values[-1])


def mean_volume(path):
    out = subprocess.run([binary('ffmpeg'), '-hide_banner', '-nostdin', '-i', str(path),
                          '-map', '0:a', '-af', 'volumedetect', '-f', 'null', '-'],
                         capture_output=True, text=True)
    for line in out.stderr.splitlines():
        if 'mean_volume' in line:
            return float(line.split(':')[1].replace(' dB', '').strip())
    raise AssertionError(f'volumedetect produced no mean_volume: {out.stderr[-500:]}')


class WindowCase(unittest.TestCase):
    """Base class owning one Window per test and a temp directory."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cs-gui-')
        self.root = Path(self.temp.name)
        self.silent = make_media(self.root, silent=True, name="silent ' clip.mp4")
        self.audio = make_media(self.root, silent=False, name='audio clip.mp4')
        self.dialogs = {'warning': [], 'question': []}
        warn_patcher = mock.patch('creative_studio.ui.QMessageBox.warning',
                                  side_effect=lambda *a, **k: self.dialogs['warning'].append(a) or QMessageBox.StandardButton.Ok)
        question_patcher = mock.patch('creative_studio.ui.QMessageBox.question',
                                      side_effect=lambda *a, **k: self.dialogs['question'].append(a) or QMessageBox.StandardButton.Yes)
        warn_patcher.start(); question_patcher.start()
        self.patchers = [warn_patcher, question_patcher]
        self.window = Window()
        APP.processEvents()

    def tearDown(self):
        # Closing may prompt for unsaved edits; keep the dialog patches active
        # until the window is closed, resolving any save dialog into the temp
        # directory, so tearDown can never block on a modal dialog.
        save_patcher = mock.patch('creative_studio.ui.QFileDialog.getSaveFileName',
                                  return_value=(str(self.root / 'teardown-save.csproj'), 'Project (*.csproj)'))
        save_patcher.start()
        try:
            self.window.close()
            wait_until(lambda: self.window.job is None, 60, 'job to finish on close')
        finally:
            for p in self.patchers + [save_patcher]:
                p.stop()
            self.temp.cleanup()

    # ---- helpers -------------------------------------------------------
    def import_paths(self, paths):
        with mock.patch('creative_studio.ui.QFileDialog.getOpenFileNames',
                        return_value=(paths, 'Video files')):
            self.window.import_media()
        APP.processEvents()

    def run_render(self, timeout=240):
        wait_until(lambda: self.window.job is None, timeout, 'render job to finish')

    def export_to(self, path, resolution=0):
        with mock.patch('creative_studio.ui.QFileDialog.getSaveFileName',
                        return_value=(str(path), 'MP4 (*.mp4)')):
            self.window.resolution.setCurrentIndex(resolution)
            self.window.export()
        APP.processEvents()

    def probe_streams(self, path):
        data = json.loads(subprocess.check_output(
            [binary('ffprobe'), '-v', 'error', '-show_streams', '-show_format',
             '-of', 'json', str(path)], text=True))
        streams = data['streams']
        video = next(s for s in streams if s['codec_type'] == 'video')
        audio = next((s for s in streams if s['codec_type'] == 'audio'), None)
        return video, audio, data['format']


class AppWindowTests(WindowCase):
    def test_window_title_dark_theme_and_actions(self):
        self.assertEqual(self.window.windowTitle(), 'Creative Studio')
        self.assertIn('#202329', self.window.styleSheet())
        names = {a.text() for a in self.window.actions}
        self.assertLessEqual({'New', 'Open', 'Save', 'Import media', 'Undo',
                              'Redo', 'Export'}, names)
        self.assertEqual(self.window.timeline.dragDropMode(),
                         __import__('PySide6.QtWidgets', fromlist=['QAbstractItemView'])
                         .QAbstractItemView.DragDropMode.InternalMove)

    def test_status_reports_audio_availability(self):
        has_devices = bool(QMediaDevices.audioOutputs())
        if has_devices:
            self.assertIsNotNone(self.window.audio)
            self.assertTrue(self.window.statusBar().currentMessage().startswith('Ready'))
        else:
            self.assertIsNone(self.window.audio)
            self.assertIn('No audio device', self.window.statusBar().currentMessage())


class ImportReorderTests(WindowCase):
    def test_import_and_duplicate_append(self):
        self.import_paths([self.silent, self.audio])
        self.assertEqual(len(self.window.clips), 2)
        self.assertEqual(self.window.media.count(), 2)
        # Filenames with apostrophes and spaces survive import.
        self.assertEqual(Path(self.window.clips[0].path).name, "silent ' clip.mp4")
        # Double-click appends another copy of the same media.
        item = self.window.media.item(0)
        self.window.media.itemDoubleClicked.emit(item)
        APP.processEvents()
        self.assertEqual(len(self.window.clips), 3)
        self.assertEqual(self.window.clips[-1].path, self.window.clips[0].path)

    def test_import_rejects_bad_media_but_keeps_good(self):
        bad = str(self.root / 'not-a-video.mp4')
        Path(bad).write_bytes(b'garbage')
        self.import_paths([self.audio, bad])
        self.assertEqual(len(self.window.clips), 1)
        self.assertEqual(len(self.dialogs['warning']), 1)
        self.assertIn('not-a-video.mp4', self.dialogs['warning'][0][2])

    def test_drag_reorder_updates_model(self):
        """Regression: the old code listened to rowsMoved, which QListWidget
        never emits for InternalMove, so drags changed the view but not
        self.clips. The fix handles dropEvent directly."""
        self.import_paths([self.silent, self.audio, self.silent])
        clips_before = [c.path for c in self.window.clips]
        self.assertEqual(len(clips_before), 3)
        self.window.show()
        APP.processEvents()
        timeline = self.window.timeline
        timeline.setCurrentRow(2)
        APP.processEvents()
        model = timeline.model()
        mime = model.mimeData([model.index(2, 0)])
        rect = timeline.visualItemRect(timeline.item(0))
        event = QDropEvent(QPointF(rect.left() + 2, rect.center().y()),
                           Qt.DropAction.MoveAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        # A synthetic QDropEvent cannot carry source()==self, so Qt's view
        # rejects it before our handler runs (verified empirically). Emulate
        # exactly what an accepted internal move does to the item list, then
        # let TimelineList.dropEvent drive the app-side integration.
        with mock.patch.object(QListWidget, 'dropEvent',
                               side_effect=lambda *a, **k: self._qt_internal_move(a[-1])):
            timeline.dropEvent(event)
        APP.processEvents()
        clips_after = [c.path for c in self.window.clips]
        self.assertEqual(clips_after, [clips_before[2], clips_before[0], clips_before[1]])
        self.assertTrue(self.window.dirty)
        self.assertEqual(len(self.window.history), 2)  # import + reorder
        self.assertFalse(self.window.preview_ready)
        # Undo restores the original order.
        self.window.undo()
        APP.processEvents()
        self.assertEqual([c.path for c in self.window.clips], clips_before)

    def _qt_internal_move(self, event):
        timeline = self.window.timeline
        item = timeline.takeItem(timeline.currentRow())
        timeline.insertItem(0, item)
        timeline.setCurrentRow(0)
        event.accept()

    def test_foreign_drop_does_not_corrupt_clips(self):
        """A drop Qt rejects (wrong action / not accepted) must not rebuild
        the clip list or grow undo history."""
        self.import_paths([self.audio])
        self.window.show()
        APP.processEvents()
        before = [c.path for c in self.window.clips]
        timeline = self.window.timeline
        rect = timeline.visualItemRect(timeline.item(0))
        event = QDropEvent(QPointF(rect.center()), Qt.DropAction.CopyAction,
                           QMimeData(),
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        timeline.dropEvent(event)  # Qt rejects: not an internal move source
        APP.processEvents()
        self.assertEqual([c.path for c in self.window.clips], before)
        # Only the import itself is in history; the rejected drop added nothing.
        self.assertEqual(len(self.window.history), 1)

    def test_apply_and_trim_validation(self):
        self.import_paths([self.audio])
        self.window.timeline.setCurrentRow(0)
        self.window.fields['speed'].setValue(2.0)
        self.window.fields['fade_in'].setValue(0.2)
        self.window.apply_clip()
        APP.processEvents()
        clip = self.window.clips[0]
        self.assertEqual(clip.speed, 2.0)
        self.assertAlmostEqual(clip.fade_in, 0.2)
        self.assertAlmostEqual(clip.duration, 0.5, delta=0.06)
        self.assertTrue(self.window.timeline.item(0).text().splitlines()[1].endswith('· 2×'))
        # Out point beyond source duration must be rejected without change.
        self.window.fields['end'].setValue(999.0)
        before = self.window.clips[0]
        self.window.apply_clip()
        APP.processEvents()
        self.assertEqual(len(self.dialogs['warning']), 1)
        self.assertIs(self.window.clips[0], before)

    def test_delete_undo_redo(self):
        self.import_paths([self.silent, self.audio])
        self.window.timeline.setCurrentRow(1)
        self.window.delete_clip()
        APP.processEvents()
        self.assertEqual(len(self.window.clips), 1)
        self.window.undo(); APP.processEvents()
        self.assertEqual(len(self.window.clips), 2)
        self.window.redo(); APP.processEvents()
        self.assertEqual(len(self.window.clips), 1)
        self.assertEqual(self.window.windowTitle(), 'Creative Studio *')


class PreviewSplitTests(WindowCase):
    def render_preview(self):
        self.import_paths([self.audio])
        self.window.preview()
        self.run_render()
        self.assertTrue(self.window.preview_ready)
        wait_until(lambda: self.window.player.duration() > 0, 30, 'player to load preview')

    def test_split_at_playhead_preserves_duration(self):
        self.render_preview()
        self.window.player.setPosition(500)
        wait_until(lambda: self.window.player.position() >= 440, 15, 'seek to 0.5s')
        self.window.split_clip()
        APP.processEvents()
        self.assertEqual(len(self.window.clips), 2)
        total = sum(c.duration for c in self.window.clips)
        self.assertAlmostEqual(total, 1.0, delta=0.03)
        self.assertAlmostEqual(self.window.clips[0].end + self.window.clips[1].start, 1.0, delta=0.03)
        # Preview invalidated by the edit; re-render reflects the split.
        self.assertFalse(self.window.preview_ready)
        self.assertIn('out of date', self.window.preview_label.text())
        self.window.preview(); self.run_render()
        self.assertTrue(self.window.preview_ready)
        video, _, fmt = self.probe_streams(self.window.preview_path)
        wait_until(lambda: self.window.player.duration() > 0, 30, 'player reload')
        self.assertAlmostEqual(float(fmt['duration']), total, delta=0.2)

    def test_split_without_preview_is_refused(self):
        self.import_paths([self.audio])
        self.window.split_clip()
        APP.processEvents()
        self.assertEqual(len(self.window.clips), 1)
        self.assertEqual(len(self.dialogs['warning']), 1)
        self.assertIn('Render preview first', self.dialogs['warning'][0][2])


class ExportTests(WindowCase):
    def assert_export_ok(self, path, width, height, expect_audio, duration):
        video, audio, fmt = self.probe_streams(path)
        self.assertEqual(video['codec_name'], 'h264')
        self.assertEqual((video['width'], video['height']), (width, height))
        self.assertEqual(video['pix_fmt'], 'yuv420p')
        self.assertAlmostEqual(float(fmt['duration']), duration, delta=0.2)
        if expect_audio:
            self.assertIsNotNone(audio)
            self.assertEqual(audio['codec_name'], 'aac')
            self.assertAlmostEqual(float(audio['duration']), float(fmt['duration']), delta=0.3)
        return video, audio

    def test_export_all_resolutions(self):
        self.import_paths([self.audio, self.silent])
        total = sum(c.duration for c in self.window.clips)
        for index, (w, h) in enumerate([(1920, 1080), (1280, 720), (1080, 1920)]):
            with self.subTest(resolution=f'{w}x{h}'):
                out = self.root / f'out{index}.mp4'
                self.export_to(out, index)
                self.run_render()
                self.assertTrue(out.is_file())
                self.assert_export_ok(out, w, h, True, total)
                self.assertAlmostEqual(self.window.progress.value(), 100)
                self.assertTrue(Path(out).stat().st_size > 10000)

    def test_speed_colour_volume_fades_in_export(self):
        self.import_paths([self.audio])
        out = self.root / 'adjusted.mp4'
        plain = self.root / 'plain.mp4'
        # Plain export first, from the untouched clip.
        self.export_to(plain, 1)
        self.run_render()
        self.assert_export_ok(plain, 1280, 720, True, 1.0)
        # Then adjust the clip and export again.
        self.window.timeline.setCurrentRow(0)
        for key, value in [('speed', 2.0), ('fade_in', 0.1), ('fade_out', 0.1),
                           ('brightness', 0.3), ('contrast', 1.2), ('saturation', 0.5),
                           ('volume', 0.5)]:
            self.window.fields[key].setValue(value)
        self.window.apply_clip()
        APP.processEvents()
        self.export_to(out, 1)  # 1280x720
        self.run_render()
        # speed=2 on a 1s clip halves the export duration
        self.assert_export_ok(out, 1280, 720, True, 0.5)
        # testsrc2 is animated but steady in luma; brightness=0.3 must lift
        # the same timestamp far above the plain export (past the scaled fade).
        bright = mean_luma(out, 0.3)
        base = mean_luma(plain, 0.3)
        self.assertGreater(bright - base, 15)
        # Volume 0.5 ≈ -6 dB vs the plain export (fades pull slightly below).
        self.assertAlmostEqual(mean_volume(plain), mean_volume(out), delta=8)

    def test_cancel_preserves_existing_output(self):
        self.import_paths([self.audio, self.audio])
        out = self.root / 'existing.mp4'
        out.write_bytes(b'previous-good-output')
        self.export_to(out, 0)
        self.assertIsNotNone(self.window.job)
        self.window.cancel_button.click()
        APP.processEvents()
        self.run_render()
        self.assertEqual(out.read_bytes(), b'previous-good-output')
        self.assertEqual(self.window.statusBar().currentMessage(), 'Render cancelled.')

    def test_export_rejects_source_overwrite(self):
        self.import_paths([self.audio])
        source = Path(self.window.clips[0].path)
        before = source.read_bytes()
        self.export_to(source, 1)
        self.run_render()
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(len(self.dialogs['warning']), 1)
        self.assertIn('cannot overwrite source', self.dialogs['warning'][0][2])

    def test_export_invalid_path_reports_error(self):
        self.import_paths([self.audio])
        out = self.root / 'no-such-dir' / 'out.mp4'
        self.export_to(out, 1)
        self.run_render()
        self.assertFalse(out.exists())
        self.assertEqual(len(self.dialogs['warning']), 1)

    def test_export_unwritable_directory_reports_error(self):
        self.import_paths([self.audio])
        # /proc/self cannot contain a temporary directory for any user,
        # including root, so this exercises the unwritable-destination path.
        out = Path('/proc/self/out.mp4')
        self.export_to(out, 1)
        self.run_render()
        self.assertFalse(out.exists())
        self.assertEqual(len(self.dialogs['warning']), 1)

    @unittest.skipIf(os.geteuid() == 0, 'permission bits do not apply to root')
    def test_export_readonly_directory_reports_error(self):
        self.import_paths([self.audio])
        ro = self.root / 'readonly'
        ro.mkdir()
        os.chmod(ro, 0o500)
        try:
            self.export_to(ro / 'out.mp4', 1)
            self.run_render()
            self.assertFalse((ro / 'out.mp4').exists())
            self.assertEqual(len(self.dialogs['warning']), 1)
        finally:
            os.chmod(ro, 0o700)

    def test_close_while_rendering_cancels_then_closes(self):
        self.import_paths([self.audio, self.audio])
        out = self.root / 'slow.mp4'
        self.export_to(out, 0)
        self.assertFalse(self.window.closing)
        # The project has unsaved edits; after the cancelled render the window
        # re-closes and the save prompt resolves via the patched save().
        with mock.patch.object(self.window, 'save', return_value=True):
            self.window.close()
            APP.processEvents()
            self.assertTrue(self.window.closing)
            wait_until(lambda: self.window.job is None, 120, 'cancel to finish')
            wait_until(lambda: self.window.isHidden(), 30, 'window to close after render ends')


class ProjectTests(WindowCase):
    def test_save_and_reopen(self):
        self.import_paths([self.silent, self.audio])
        path = self.root / 'my project.csproj'
        with mock.patch('creative_studio.ui.QFileDialog.getSaveFileName',
                        return_value=(str(path), 'Project (*.csproj)')):
            self.assertTrue(self.window.save())
        self.assertEqual(self.window.windowTitle(), 'Creative Studio · my project.csproj')
        self.assertFalse(self.window.dirty)
        self.assertFalse(json.loads(path.read_text())['clips'][0]['path'].startswith('/'))
        other = Window()
        try:
            with mock.patch('creative_studio.ui.QFileDialog.getOpenFileName',
                            return_value=(str(path), 'Project (*.csproj)')):
                other.open_project()
            APP.processEvents()
            self.assertEqual(len(other.clips), 2)
            self.assertEqual(other.clips[1].path, self.window.clips[1].path)
            self.assertFalse(other.dirty)
        finally:
            other.close(); other.temp.cleanup()

    def test_open_project_with_missing_media_fails_clearly(self):
        self.import_paths([self.audio])
        path = self.root / 'gone.csproj'
        with mock.patch('creative_studio.ui.QFileDialog.getSaveFileName',
                        return_value=(str(path), 'Project (*.csproj)')):
            self.window.save()
        data = json.loads(path.read_text())
        data['clips'][0]['path'] = 'deleted-media.mp4'
        path.write_text(json.dumps(data))
        with mock.patch('creative_studio.ui.QFileDialog.getOpenFileName',
                        return_value=(str(path), 'Project (*.csproj)')):
            self.window.open_project()
        APP.processEvents()
        self.assertEqual(len(self.dialogs['warning']), 1)
        self.assertIn('Missing media', self.dialogs['warning'][0][2])

    def test_malformed_project_shows_dialog_not_crash(self):
        bad = self.root / 'bad.csproj'
        bad.write_bytes(b'{not json at all')
        with mock.patch('creative_studio.ui.QFileDialog.getOpenFileName',
                        return_value=(str(bad), 'Project (*.csproj)')):
            self.window.open_project()
        APP.processEvents()
        self.assertEqual(len(self.dialogs['warning']), 1)
        self.assertIn('Not a valid project file', self.dialogs['warning'][0][2])


if __name__ == '__main__':
    unittest.main()
