from dataclasses import dataclass, asdict, replace
from pathlib import Path
import json
import math
import os
import tempfile

@dataclass
class Clip:
    path: str
    start: float
    end: float
    speed: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    volume: float = 1.0

    @property
    def duration(self):
        return (self.end - self.start) / self.speed

    def validate(self):
        values = (self.start, self.end, self.speed, self.fade_in, self.fade_out,
                  self.brightness, self.contrast, self.saturation, self.volume)
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            raise ValueError('Clip values must be finite numbers.')
        if self.start < 0 or self.end <= self.start or not 0.125 <= self.speed <= 8:
            raise ValueError('Invalid trim or speed; end must be after start.')
        if not 0 <= self.fade_in <= self.duration or not 0 <= self.fade_out <= self.duration:
            raise ValueError('Fade must fit inside the clip.')
        if not -1 <= self.brightness <= 1 or not 0 <= self.contrast <= 3:
            raise ValueError('Invalid brightness or contrast.')
        if not 0 <= self.saturation <= 3 or not 0 <= self.volume <= 4:
            raise ValueError('Invalid saturation or volume.')
        if not isinstance(self.path, str) or not Path(self.path).is_file():
            raise ValueError(f'Missing media: {self.path}')

    def split(self, seconds):
        if not 0.02 < seconds < self.duration - 0.02:
            raise ValueError('Place the playhead inside the clip to split.')
        boundary = self.start + seconds * self.speed
        a = replace(self, end=boundary, fade_out=0,
                    fade_in=min(self.fade_in, seconds))
        b = replace(self, start=boundary, fade_in=0,
                    fade_out=min(self.fade_out, self.duration-seconds))
        return a, b


def save_project(path, clips):
    target = Path(path).resolve()
    data = []
    for clip in clips:
        clip.validate()
        item = asdict(clip)
        item['path'] = os.path.relpath(Path(clip.path).resolve(), target.parent)
        data.append(item)
    fd, temporary = tempfile.mkstemp(dir=target.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump({'format': 'creative-studio', 'version': 1, 'clips': data}, f, indent=2)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_project(path):
    target = Path(path).resolve()
    data = json.loads(target.read_text())
    if data.get('format') != 'creative-studio' or data.get('version') != 1:
        raise ValueError('Unsupported project format.')
    clips = []
    for item in data['clips']:
        item = dict(item)
        item['path'] = str((target.parent / item['path']).resolve())
        clip = Clip(**item)
        clip.validate()
        clips.append(clip)
    return clips
