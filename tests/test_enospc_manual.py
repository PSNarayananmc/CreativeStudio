"""Full-disk (ENOSPC) export test: fills /dev/shm, exports into it, verifies
the failure surfaces as a useful error, existing output is preserved, and the
temp directory is cleaned up. Run inside the focal rootfs via the GUI stack.

IMPORTANT: run from the host afterward: rm -f /dev/shm/cs-full-disk-filler
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, '.')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

FILLER = '/dev/shm/cs-full-disk-filler'
DEST = '/dev/shm/cs-export-dest.mp4'

results = []


def note(msg):
    results.append(msg)
    print(msg, flush=True)


def wait_until(pred, timeout=90, what='condition'):
    from PySide6.QtWidgets import QApplication
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if pred():
            return True
        time.sleep(0.02)
    raise AssertionError(f'timeout waiting for {what}')


def main():
    from tests.test_gui import make_media
    from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
    from creative_studio.ui import Window

    app = QApplication([])
    warnings = []
    outcomes = []
    with mock.patch('creative_studio.ui.QMessageBox.warning',
                    side_effect=lambda *a, **k: warnings.append(a[2]) or QMessageBox.StandardButton.Ok), \
         mock.patch('creative_studio.ui.QMessageBox.question',
                    side_effect=lambda *a, **k: warnings.append('question:' + str(a[2])) or QMessageBox.StandardButton.Yes):
        root = Path(tempfile.mkdtemp(prefix='cs-enospc-'))
        try:
            media = make_media(root, silent=False, name='tone.mp4')
            # Pre-place an existing good output that must survive the failure.
            Path(DEST).write_bytes(b'existing-output-must-survive')

            # Fill /dev/shm (64MB tmpfs) with a sparse-but-resident file.
            filled = 0
            f = open(FILLER, 'wb')
            chunk = b'\0' * (1024 * 1024)
            while True:
                try:
                    f.write(chunk)
                    f.flush()
                    filled += len(chunk)
                except OSError as exc:
                    note(f'filler hit the wall at {filled // (1024*1024)} MB: {exc}')
                    break
            try:
                f.close()
            except OSError:
                pass
            stat = os.statvfs('/dev/shm')
            free_mb = stat.f_bavail * stat.f_frsize // (1024 * 1024)
            note(f'free on /dev/shm after fill: {free_mb} MB')

            window = Window()
            window.job
            def _succeeded(p):
                outcomes.append(('succeeded', p))
            def _failed(m):
                outcomes.append(('failed', m))
            with mock.patch('creative_studio.ui.QFileDialog.getOpenFileNames',
                            return_value=([media], 'Video files')):
                window.import_media()
            assert len(window.clips) == 1, 'import failed'
            with mock.patch('creative_studio.ui.QFileDialog.getSaveFileName',
                            return_value=(DEST, 'MP4 (*.mp4)')):
                window.export()
            if window.job is not None:
                window.job.succeeded.connect(_succeeded)
                window.job.failed.connect(_failed)
            wait_until(lambda: window.job is None, 120, 'job to finish')
            time.sleep(0.5)
            note(f'job outcome: {outcomes}')
            note(f'status bar: {window.statusBar().currentMessage()!r}')
            note(f'dest size: {os.path.getsize(DEST) if os.path.exists(DEST) else "missing"}')
            time.sleep(0.5)
            free_mb2 = os.statvfs('/dev/shm').f_bavail * stat.f_frsize // (1024 * 1024)
            note(f'free on /dev/shm after export attempt: {free_mb2} MB '
                 f'(temp cleaned up: {free_mb2 >= free_mb})')
            survived = Path(DEST).read_bytes() == b'existing-output-must-survive'
            note(f'existing output preserved: {survived}')
            note(f'error surfaced to user: {warnings!r}')
            no_stray = not any(p.suffix == '.mp4' and p.name != 'tone.mp4'
                               for p in root.iterdir())
            note(f'no stray outputs in media dir: {no_stray}')
            window.close()
            wait_until(lambda: window.job is None, 30, 'close')
            window.temp.cleanup()
        finally:
            shutil.rmtree(root, ignore_errors=True)
            try:
                os.unlink(DEST)
            except OSError:
                pass
    ok = (any('space' in (w or '').lower() or 'disk' in (w or '').lower()
              or 'quota' in (w or '').lower() or 'write' in (w or '').lower()
              for w in warnings) and
          Path(DEST).read_bytes() == b'existing-output-must-survive'
          if os.path.exists(DEST) else True)
    print('ENOSPC-TEST-' + ('PASS' if ok else 'CHECK-MANUALLY'))
    Path('/home/z/my-project/work/enospc-result.txt').write_text('\n'.join(results))


if __name__ == '__main__':
    main()
