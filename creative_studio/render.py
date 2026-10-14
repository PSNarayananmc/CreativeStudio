"""FFmpeg renderer. No shell interpolation; all outputs are atomic."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading


def binary(name):
    roots = [Path(sys.executable).parent / 'bin', Path(__file__).resolve().parent.parent / 'bin']
    for root in roots:
        candidate = root / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    result = shutil.which(name)
    if not result:
        raise RuntimeError(f'{name} is missing. Install FFmpeg or use the packaged AppImage.')
    return result


def probe(path):
    p = subprocess.run([binary('ffprobe'), '-v', 'error', '-show_streams',
                        '-show_format', '-of', 'json', str(path)],
                       capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise ValueError(p.stderr[-2000:] or 'Cannot read media.')
    data = json.loads(p.stdout)
    video = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
    if video is None:
        raise ValueError('This version imports video files only.')
    duration = float(data.get('format', {}).get('duration') or video.get('duration') or 0)
    if duration <= 0:
        raise ValueError('Media has no valid duration.')
    return duration, any(s['codec_type'] == 'audio' for s in data['streams'])


def tempo(speed):
    filters = []
    while speed > 2:
        filters.append('atempo=2'); speed /= 2
    while speed < 0.5:
        filters.append('atempo=0.5'); speed *= 2
    filters.append(f'atempo={speed:.9g}')
    return ','.join(filters)


def progress_seconds(line):
    """Out time in seconds from one 'ffmpeg -progress' line, or None.

    ffmpeg 4.4+ emits out_time_us (microseconds). Older releases such as
    Ubuntu 20.04's 4.2 only emit out_time_ms, which historically also carries
    microseconds despite its name. Accepting both keeps progress bars working
    across the FFmpeg versions this editor may be packaged with.
    """
    key, _, value = line.strip().partition('=')
    if key not in ('out_time_us', 'out_time_ms'):
        return None
    try:
        return float(value) / 1e6
    except ValueError:
        return None


class Cancelled(Exception):
    pass


def run_ffmpeg(args, duration, callback, cancel):
    with tempfile.TemporaryFile(mode='w+') as log:
        process = subprocess.Popen([binary('ffmpeg'), '-hide_banner', '-nostdin', '-y',
                                    '-loglevel', 'error', *args, '-progress', 'pipe:1'],
                                   stdout=subprocess.PIPE, stderr=log, text=True)
        done = threading.Event()
        def monitor():
            while not done.wait(0.1):
                if cancel.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return
        watcher = threading.Thread(target=monitor, daemon=True)
        watcher.start()
        try:
            for line in process.stdout:
                seconds = progress_seconds(line)
                if seconds is not None:
                    try:
                        callback(min(0.99, max(0, seconds / duration)))
                    except ValueError:
                        pass
            result = process.wait()
        finally:
            done.set(); watcher.join(timeout=4)
            process.stdout.close()
            if process.poll() is None:
                process.kill(); process.wait()
        if cancel.is_set():
            raise Cancelled('Render cancelled.')
        if result:
            log.seek(0)
            raise RuntimeError(log.read()[-4000:] or 'FFmpeg failed.')


def clip_args(clip, part, width, height, fps, has_audio):
    """FFmpeg argument array that renders one clip to a part file.

    Video and audio chains go through a single -filter_complex graph. Passing
    -vf and -af separately makes FFmpeg 4.x print a spurious 'ignoring
    remaining -vf options' warning, which would pollute the error text shown
    to users when a render fails for an unrelated reason. Argument arrays are
    used throughout; media paths are never shell-interpolated.
    """
    vf = (f'setpts=(PTS-STARTPTS)/{clip.speed:.9g},'
          f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
          f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},'
          f'eq=brightness={clip.brightness}:contrast={clip.contrast}:saturation={clip.saturation},'
          'format=yuv420p')
    af = f'asetpts=PTS-STARTPTS,{tempo(clip.speed)},volume={clip.volume}'
    for kind, length, start in [('in', clip.fade_in, 0),
                                ('out', clip.fade_out, clip.duration-clip.fade_out)]:
        if length > 0:
            vf += f',fade=t={kind}:st={start:.9g}:d={length:.9g}'
            af += f',afade=t={kind}:st={start:.9g}:d={length:.9g}'
    af += f',apad,atrim=duration={clip.duration:.9g}'
    args = ['-ss', str(clip.start), '-t', str(clip.end-clip.start), '-i', clip.path]
    if not has_audio:
        args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
    audio_in = '0:a' if has_audio else '1:a'
    graph = f'[0:v]{vf}[vout];[{audio_in}]{af}[aout]'
    args += ['-filter_complex', graph,
             '-map', '[vout]', '-map', '[aout]', '-t', str(clip.duration),
             '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
             '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-threads', '2', str(part)]
    return args


def render(clips, output, width=1920, height=1080, fps=30, progress=lambda v: None, cancel=None):
    cancel = cancel or threading.Event()
    if not clips:
        raise ValueError('The timeline is empty.')
    if width % 2 or height % 2 or min(width, height, fps) <= 0:
        raise ValueError('Export dimensions must be positive even numbers.')
    for clip in clips:
        clip.validate()
    destination = Path(output).resolve()
    if destination in [Path(c.path).resolve() for c in clips]:
        raise ValueError('Export cannot overwrite source media.')
    total = sum(c.duration for c in clips)
    completed = 0.0
    # Same-filesystem temporary output protects any existing destination.
    with tempfile.TemporaryDirectory(prefix='creative-studio-', dir=destination.parent) as temp:
        parts = []
        for i, c in enumerate(clips):
            if cancel.is_set():
                raise Cancelled('Render cancelled.')
            duration, audio = probe(c.path)
            if c.end > duration + 0.05:
                raise ValueError(f'Trim exceeds source duration: {c.path}')
            part = Path(temp) / f'part-{i:06d}.mp4'
            args = clip_args(c, part, width, height, fps, audio)
            base = completed
            run_ffmpeg(args, c.duration,
                       lambda value: progress(0.95*(base+value*c.duration)/total), cancel)
            completed += c.duration
            parts.append(part)
        manifest = Path(temp) / 'concat.txt'
        manifest.write_text(''.join(f"file '{p.name}'\n" for p in parts))
        final = Path(temp) / 'final.mp4'
        run_ffmpeg(['-f', 'concat', '-safe', '1', '-i', str(manifest), '-c', 'copy',
                    '-movflags', '+faststart', str(final)], total,
                   lambda value: progress(0.95+value*0.05), cancel)
        if cancel.is_set():
            raise Cancelled('Render cancelled.')
        os.replace(final, destination)
    progress(1.0)
