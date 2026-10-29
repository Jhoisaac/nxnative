"""NSP script: capture_glslc for a game that compiles no shader before its frame loop (Crash Team Racing Nitro-Fueled hands the precompiled GLSLC outputs in its archives to the driver and compiles two
only after its language select). A boot that reaches the frame loop and captures nothing, for a profile that names no wanted files, is not an error (a red line): the folder holds the marker and a later build reuses it; a host that stopped before the frame loop, or a
profile that names files, still fails. The host is not built or booted (build_mac_host and boot_mac are replaced); temporary files only."""
import contextlib
import importlib.util
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts/build_ipa_from_nsp.py'
spec = importlib.util.spec_from_file_location('build_ipa_from_nsp', SCRIPT)
assert spec and spec.loader
nsp = importlib.util.module_from_spec(spec); spec.loader.exec_module(nsp)


class Capture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp)
        self.d, self.work, self.logs = self.tmp / 'ext', self.tmp / 'work', self.tmp / 'logs'
        for p in (self.d, self.work, self.logs): p.mkdir()
        self.out = io.StringIO()
        self.prog = nsp.Progress('lines')
        for cm in (contextlib.redirect_stdout(self.out), mock.patch.object(nsp, 'PROG', self.prog), mock.patch.object(nsp, 'build_mac_host', return_value='host'),
                   mock.patch.object(nsp.rfs, 'source', side_effect=lambda p: p)):
            cm.__enter__(); self.addCleanup(cm.__exit__, None, None, None)

    def run_capture(self, log, want=None):
        def boot(host, patched, henv, rd, logp, secs, done): Path(logp).write_text(log); return None
        g = mock.Mock(); g.table.return_value = self.tmp / 'no_shader_map.tsv'
        with mock.patch.object(nsp, 'boot_mac', side_effect=boot), mock.patch.object(nsp, 'glslc_wanted', return_value=want):
            nsp.capture_glslc(self.tmp, {'v1': self.d}, 'v1', 'patched', self.work, {}, self.logs, g)

    def test_frames_without_compile(self):
        self.run_capture('[dm] [nvn] frame step: hold 1\n[dm] [nvn] frame 300: 5 functions 90 calls\n')   # the host's own prefix
        self.assertTrue(nsp.glslc_empty(self.d / 'glslc_capture'))
        self.assertEqual(nsp.glslc_done(self.d / 'glslc_capture'), set())
        self.assertFalse((self.d / 'glslc_capture.partial').exists())
        self.assertIn('[RED] the game reached its frame loop without compiling a shader', self.out.getvalue())
        self.out.truncate(0); self.out.seek(0)
        with mock.patch.object(nsp, 'boot_mac', side_effect=AssertionError('booted again')), mock.patch.object(nsp, 'glslc_wanted', return_value=None):
            nsp.capture_glslc(self.tmp, {'v1': self.d}, 'v1', 'patched', self.work, {}, self.logs, mock.Mock())   # reused
        self.assertIn('reusing', self.out.getvalue())

    def test_no_frames_fails(self):
        with self.assertRaises(nsp.BuildError): self.run_capture('[dm] [nvn] frame step: hold 1\nsegfault\n')
        self.assertFalse(nsp.glslc_empty(self.d / 'glslc_capture'))

    def test_wanted_files_fail(self):
        with self.assertRaises(nsp.BuildError): self.run_capture('[nvn] frame 300: 5 functions 90 calls\n', want={'0123456789abcdef.glslc'})


if __name__ == '__main__': unittest.main()
