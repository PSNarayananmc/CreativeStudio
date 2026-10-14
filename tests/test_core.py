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

    # --- Regressions for defects fixed for the 0.1.1 build -----------------
    def test_malformed_projects_give_useful_errors(self):
        """Fixed: malformed .csproj used to surface cryptic KeyError/TypeError/
        JSONDecodeError text. load_project must always raise ValueError with a
        message naming the problem and the clip number where relevant."""
        cases = {
            'not_json': b'{broken',
            'not_an_object': b'[]',
            'no_clips_key': b'{"format": "creative-studio", "version": 1}',
            'clips_not_a_list': b'{"format": "creative-studio", "version": 1, "clips": {}}',
            'clip_not_an_object': b'{"format": "creative-studio", "version": 1, "clips": [5]}',
            'unknown_field': b'{"format": "creative-studio", "version": 1, "clips": ['
                             b'{"path": "audio clip.mp4", "start": 0, "end": 1, "oops": 1}]}',
            'clip_without_path': b'{"format": "creative-studio", "version": 1, "clips": ['
                                 b'{"start": 0, "end": 1}]}',
            'unsupported_format': b'{"format": "other-app", "version": 1, "clips": []}',
        }
        for name, payload in cases.items():
            path = self.root / f'bad-{name}.csproj'
            path.write_bytes(payload)
            with self.subTest(case=name):
                with self.assertRaises(ValueError) as ctx:
                    load_project(path)
                self.assertTrue(str(ctx.exception).strip(), 'error message must not be empty')
                self.assertNotIsInstance(ctx.exception, KeyError)

    def test_missing_project_file_named_in_error(self):
        missing = self.root / 'nope.csproj'
        with self.assertRaises(ValueError) as ctx:
            load_project(missing)
        self.assertIn('nope.csproj', str(ctx.exception))

    def test_clip_field_set_matches_saved_format(self):
        # Guards CLIP_FIELDS staying in sync with Clip so unknown-field
        # rejection cannot reject legitimate round-tripped projects.
        from creative_studio.model import CLIP_FIELDS
        import dataclasses
        self.assertEqual(CLIP_FIELDS, tuple(f.name for f in dataclasses.fields(Clip)))

    def test_progress_parsing_supports_old_and_new_ffmpeg(self):
        """Fixed: only out_time_us was parsed, so with Ubuntu 20.04's FFmpeg 4.2
        (which emits out_time_ms carrying microseconds) export progress stayed
        at zero until completion."""
        from creative_studio.render import progress_seconds
        self.assertAlmostEqual(progress_seconds('out_time_us=1500000\n'), 1.5)
        self.assertAlmostEqual(progress_seconds('out_time_ms=1500000\n'), 1.5)
        self.assertAlmostEqual(progress_seconds('out_time_us=0\n'), 0.0)
        self.assertIsNone(progress_seconds('frame=12\n'))
        self.assertIsNone(progress_seconds('progress=continue\n'))
        self.assertIsNone(progress_seconds('out_time_us=N/A\n'))
        self.assertIsNone(progress_seconds('out_time_us=\n'))
        self.assertIsNone(progress_seconds('\n'))

    def test_filter_graph_uses_single_filter_complex(self):
        """Fixed: separate -vf and -af options made FFmpeg 4.x print a spurious
        'ignoring remaining -vf options' warning that polluted user-visible
        error logs. The chains now travel in one -filter_complex graph."""
        from creative_studio.render import clip_args
        clip = Clip(str(self.audio), 0, 1, speed=2, fade_in=0.1, fade_out=0.1,
                    brightness=0.05, contrast=1.1, saturation=0.8, volume=0.5)
        args = clip_args(clip, 'part.mp4', 640, 360, 30, has_audio=True)
        self.assertEqual(args.count('-filter_complex'), 1)
        self.assertNotIn('-vf', args)
        self.assertNotIn('-af', args)
        graph = args[args.index('-filter_complex') + 1]
        self.assertIn('[0:v]', graph)
        self.assertIn('[0:a]', graph)
        self.assertIn('[vout]', graph)
        self.assertIn('[aout]', graph)
        self.assertIn('atempo=2', graph)
        self.assertIn('fade=t=in', graph)
        self.assertIn('fade=t=out', graph)
        self.assertIn('volume=0.5', graph)
        # Argument arrays only; no shell involvement anywhere in the command.
        self.assertNotIn('sh', args[:4])
        silent_args = clip_args(Clip(str(self.silent), 0, 1), 'part.mp4', 640, 360, 30, has_audio=False)
        graph_s = silent_args[silent_args.index('-filter_complex') + 1]
        self.assertIn('[1:a]', graph_s)
        self.assertIn('anullsrc=r=48000:cl=stereo', silent_args)



if __name__ == '__main__': unittest.main()
