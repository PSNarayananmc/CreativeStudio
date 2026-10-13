import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from creative_studio.model import Clip, save_project, load_project
from creative_studio.render import binary, probe, render, Cancelled

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.silent = self.root / "silent ' clip.mp4"
        self.audio = self.root / 'audio clip.mp4'
        common = [binary('ffmpeg'), '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30']
        subprocess.run(common + ['-t', '1', '-c:v', 'libx264', '-threads', '1', str(self.silent)], check=True)
        subprocess.run(common + ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
            '-t', '1', '-c:v', 'libx264', '-threads', '1', '-c:a', 'aac', str(self.audio)], check=True)
    def tearDown(self): self.temp.cleanup()
    def test_project_and_split(self):
        clip = Clip(str(self.audio), 0, 1, speed=2, fade_in=0.1, fade_out=0.1)
        a, b = clip.split(0.25)
        self.assertAlmostEqual(a.duration+b.duration, clip.duration)
        self.assertAlmostEqual(a.end, b.start)
        a.validate(); b.validate()
        path = self.root / 'test.csproj'; save_project(path, [a,b])
        self.assertEqual(load_project(path), [a,b])
        self.assertFalse(Path(json.loads(path.read_text())['clips'][0]['path']).is_absolute())
    def test_render_audio_silent_speed_colour_fades(self):
        output = self.root / 'output.mp4'; progress = []
        render([Clip(str(self.silent),0,1,speed=2,fade_in=0.1,fade_out=0.1,
                     brightness=0.05,contrast=1.1,saturation=0.8),
                Clip(str(self.audio),0,1,speed=0.5,volume=0.5)],
               output,320,180,30,progress.append)
        duration, audio = probe(output)
        self.assertTrue(audio); self.assertAlmostEqual(duration,2.5,delta=0.15)
        self.assertEqual(progress[-1],1.0)
        streams = json.loads(subprocess.check_output([binary('ffprobe'),'-v','error',
            '-show_streams','-of','json',str(output)],text=True))['streams']
        video = next(s for s in streams if s['codec_type']=='video')
        self.assertEqual((video['width'],video['height']),(320,180))
        self.assertEqual(video['pix_fmt'],'yuv420p')
    def test_cancel_preserves_destination(self):
        output = self.root / 'existing.mp4'; output.write_bytes(b'existing')
        cancel = threading.Event(); cancel.set()
        with self.assertRaises(Cancelled):
            render([Clip(str(self.audio),0,1)],output,cancel=cancel)
        self.assertEqual(output.read_bytes(),b'existing')
    def test_source_overwrite_rejected(self):
        with self.assertRaises(ValueError): render([Clip(str(self.audio),0,1)],self.audio)

if __name__ == '__main__': unittest.main()
