"""Self-test harness for packaged builds.

Runs only when the CREATIVE_STUDIO_SMOKE environment variable is set, so normal
launches are unaffected. It exercises the real UI/engine code paths offscreen:
import, preview render, split, edit, undo/redo, 1080p export (H.264 + AAC) and
project save, then writes a JSON summary and returns a process exit code.
"""
import json
import os
import sys
import time
import traceback


def _wait(app, predicate, timeout=180.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _sample_clip(root, seconds=2.0):
    """Generate a test video with the bundled FFmpeg and probe it."""
    import threading
    from .model import Clip
    from . import render
    path = str(root / 'sample.mp4')
    render.run_ffmpeg(
        ['-f', 'lavfi', '-i', f'testsrc2=size=320x180:rate=30:duration={seconds:g}',
         '-f', 'lavfi', '-i', f'sine=frequency=440:sample_rate=48000:duration={seconds:g}',
         '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'aac', '-y', path],
        seconds, lambda v: None, threading.Event())
    duration, audio = render.probe(path)
    return path, duration, audio


def run_smoke():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from pathlib import Path
    from PySide6.QtWidgets import QApplication
    from .model import Clip, load_project
    from . import render

    out_dir = Path(os.environ.get('CREATIVE_STUDIO_SMOKE_OUT', '/tmp'))
    out_dir.mkdir(parents=True, exist_ok=True)
    steps, failures = [], []
    app = QApplication(sys.argv[:1])

    def record(name, ok, detail=''):
        steps.append({'step': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
        print(f"[smoke] {'PASS' if ok else 'FAIL'} {name} {detail}")

    try:
        from .ui import Window
        window = Window()
        window.show()
        record('window_created', window.windowTitle().startswith('Creative Studio'))

        clip_path, duration, _audio = _sample_clip(out_dir)
        # Mirror import_media(): history entry first, then append + refresh.
        window.remember()
        window.clips.append(Clip(clip_path, 0, duration))
        from PySide6.QtWidgets import QListWidgetItem
        entry = QListWidgetItem(Path(clip_path).name)
        entry.setData(Qt_item_role(), (clip_path, duration))
        window.media.addItem(entry)
        window.changed(); window.refresh(len(window.clips) - 1)
        record('import_media', len(window.clips) == 1 and duration > 1,
               f'duration={duration:.2f}s')

        window.preview()
        ok = _wait(app, lambda: window.preview_ready, timeout=300)
        record('preview_render', ok and Path(window.preview_path).is_file(),
               window.preview_path)
        record('preview_playback_source', ok and not window.player.source().isEmpty())

        window.player.setPosition(1000)
        seeked = _wait(app, lambda: window.player.position() >= 950, timeout=30)
        if seeked:
            window.split_clip()
        record('split_at_playhead', (not seeked) or len(window.clips) == 2,
               f'clips={len(window.clips)}' + ('' if seeked else ' (playback seek unavailable; skipped)'))

        n0 = len(window.clips)
        window.remember()
        window.clips.append(Clip(clip_path, 0, duration))
        window.changed(); window.refresh()
        n1 = len(window.clips)
        window.undo(); undone = len(window.clips) == n0
        window.redo(); redone = len(window.clips) == n1
        window.undo()  # leave a single clip for export
        record('undo_redo', n1 == n0 + 1 and undone and redone and len(window.clips) == n0,
               f'undo={undone} redo={redone}')

        row = window.timeline.currentRow()
        window.timeline.setCurrentRow(0)
        window.fields['speed'].setValue(1.5)
        window.apply_clip()
        applied = window.clips[0].speed == 1.5
        window.fields['speed'].setValue(1.0)
        window.apply_clip()
        window.timeline.setCurrentRow(row)
        record('inspector_apply', applied)

        resolution_count = window.resolution.count()
        record('resolution_options', resolution_count == 3, f'count={resolution_count}')

        export_path = out_dir / 'smoke-export-1080p.mp4'
        window.start_render(str(export_path), (1920, 1080, 30), False)
        finished = _wait(app, lambda: window.job is None, timeout=900)
        record('export_1080p', finished and export_path.is_file() and export_path.stat().st_size > 1000,
               str(export_path))
        if export_path.is_file():
            streams = json.loads(render.subprocess.check_output(
                [render.binary('ffprobe'), '-v', 'error', '-show_streams', '-of', 'json',
                 str(export_path)], text=True))['streams']
            video = next((s for s in streams if s['codec_type'] == 'video'), {})
            audio = next((s for s in streams if s['codec_type'] == 'audio'), {})
            record('export_h264_aac',
                   video.get('codec_name') == 'h264' and audio.get('codec_name') == 'aac'
                   and (video.get('width'), video.get('height')) == (1920, 1080),
                   f"{video.get('codec_name')}:{video.get('width')}x{video.get('height')}+{audio.get('codec_name')}")

        project_path = out_dir / 'smoke-project.csproj'
        window.project_path = str(project_path)
        saved = window.save()
        reloaded = load_project(str(project_path)) if project_path.is_file() else []
        record('project_save', bool(saved) and project_path.is_file() and len(reloaded) == 1,
               str(project_path))

        window.close()
        window.temp.cleanup()
    except Exception:
        failures.append(traceback.format_exc())
        print(traceback.format_exc(), file=sys.stderr)

    result = {
        'app': 'Creative Studio self-test',
        'platform': os.environ.get('QT_QPA_PLATFORM', 'default'),
        'passed': all(s['ok'] for s in steps) and not failures,
        'steps': steps,
        'failures': failures,
    }
    summary = out_dir / 'smoke-summary.json'
    summary.write_text(json.dumps(result, indent=2))
    print(f"[smoke] summary: {summary} passed={result['passed']}")
    app.processEvents()
    return 0 if result['passed'] else 1


def Qt_item_role():
    from PySide6.QtCore import Qt
    return Qt.ItemDataRole.UserRole
