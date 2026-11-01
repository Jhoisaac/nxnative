"""dm/tools/nso_fnmap.py: offsets carried across two builds through FDE functions, through prologue-cut segments where no FDE covers the text, and through the longest identical masked run.
Synthetic images (an eh_frame_hdr with FDEs for the first functions only); the real-image case runs when DM_TEST_FNMAP_IMAGES names two memory images."""
import contextlib
import io
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import unittest.mock

try:
    import numpy as np
except ImportError:
    np = None

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'dm/tools'))
if np: import nso_fnmap

SUB_SP, STP, RET, ADRP_X8, ADD_X8 = 0xd10103ff, 0xa9bf7bfd, 0xd65f03c0, 0x90000008, 0x91000108


def body(seed, n):
    """n filler words (ldr x0, [x1, #imm]) that no prologue, return or branch pattern matches, distinct per seed"""
    return [0xf9400020 | (((seed * 37 + k * 11) % 4000) << 10) for k in range(n)]


def function(seed, n, bl=0, prologue=SUB_SP):
    """a function: prologue, filler with a bl (target bits differ between builds) and an adrp + add pair that image() points at its target, ret"""
    w = [prologue] + body(seed, n)
    w[3] = 0x94000000 | bl
    w[5], w[6] = ADRP_X8, ADD_X8
    return w + [RET, 0]


def image(funcs, nfde, skew, target):
    """memory image: MOD0 header at 8, the functions from 0x40, a PLT stub (br x17), a page of zeros, then eh_frame_hdr + FDEs for the first nfde functions"""
    words = [0, 8, 0x30444f4d, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]   # MOD0 at 8: its eh_frame_hdr offset is patched below
    starts, sizes = [], []
    for i, f in enumerate(funcs):
        words += [0] * skew[i]; starts.append(len(words) * 4); sizes.append(len(f) * 4); words += f
        pc = starts[-1] + 5 * 4; pages = (target >> 12) - (pc >> 12)   # adrp x8, target; add x8, x8, #(target & 0xfff)
        words[len(words) - len(f) + 5] = ADRP_X8 | ((pages & 3) << 29) | (((pages >> 2) & 0x7ffff) << 5)
        words[len(words) - len(f) + 6] = ADD_X8 | ((target & 0xfff) << 10)
    words += [0xd61f0220]; text = len(words) * 4
    words += [0] * ((0x1000 - text % 0x1000) // 4)
    ehs = len(words) * 4
    hdr = struct.pack('<BBBBiI', 1, 0x1b, 0x03, 0x3b, 0, nfde)
    fde_at = ehs + 12 + 8 * nfde
    table = b''.join(struct.pack('<ii', starts[i] - ehs, fde_at + 16 * i - ehs) for i in range(nfde))
    fdes = b''.join(struct.pack('<IIiI', 12, 0, starts[i] - (fde_at + 16 * i + 8), sizes[i]) for i in range(nfde))
    raw = bytearray(struct.pack('<%dI' % len(words), *words)) + hdr + table + fdes
    struct.pack_into('<i', raw, 8 + 16, ehs - 8)
    return bytes(raw), starts


class Fnmap(unittest.TestCase):
    OLD_DATA, NEW_DATA = 0x300040, 0x380058   # the data moved by a page and an in-page offset

    @classmethod
    def setUpClass(cls):
        if np is None: raise unittest.SkipTest('numpy is not installed')

    def run_tool(self, old, new, *offs):
        with tempfile.TemporaryDirectory() as d:
            po, pn = Path(d, 'old.bin'), Path(d, 'new.bin'); po.write_bytes(old); pn.write_bytes(new)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), unittest.mock.patch.object(sys, 'argv', ['nso_fnmap', str(po), str(pn)] + [hex(o) for o in offs]):
                nso_fnmap.main()
        return out.getvalue().splitlines()[2:]   # after the two summary lines

    def builds(self):
        sizes = [20 + 3 * i for i in range(12)]
        old = [function(i, sizes[i], bl=i + 1) for i in range(12)]
        new = [function(i, sizes[i], bl=i + 5) for i in range(12)]
        (po, so), (pn, sn) = image(old, 3, [0] * 12, self.OLD_DATA), image(new, 3, [0, 4, 0, 4, 0, 4, 0, 4, 0, 4, 0, 4], self.NEW_DATA)
        return po, so, pn, sn

    def test_fde_function_unchanged(self):
        po, so, pn, sn = self.builds()
        line, = self.run_tool(po, pn, so[1] + 0x10)
        self.assertEqual(line.split('  ')[:3], [f'{so[1] + 0x10:#x} → {sn[1] + 0x10:#x}', 'code', 'exact'])

    def test_segment_exact_outside_fde(self):
        po, so, pn, sn = self.builds()
        for i in (5, 9):
            line, = self.run_tool(po, pn, so[i] + 0x20)
            self.assertTrue(line.startswith(f'{so[i] + 0x20:#x} → {sn[i] + 0x20:#x}  code  segment-exact'), line)

    def test_run_when_the_function_changed(self):
        po, so, pn, sn = self.builds()
        # one filler word of function 7 differs, so its segment has no identical hash; a run around the offset still finds it
        raw = bytearray(pn); struct.pack_into('<I', raw, sn[7] + 4 * 30, 0xf9400000)
        line, = self.run_tool(po, bytes(raw), so[7] + 4 * 8)
        self.assertTrue(line.startswith(f'{so[7] + 4 * 8:#x} → {sn[7] + 4 * 8:#x}  code  run '), line)
        self.assertNotIn('[RED]', line)

    def test_data_by_references_in_fallback_functions(self):
        po, so, pn, sn = self.builds()
        line, = self.run_tool(po, pn, self.OLD_DATA)
        self.assertIn(f'{self.OLD_DATA:#x} → {self.NEW_DATA:#x}  data  12/12 references agree', line)

    @unittest.skipUnless(os.environ.get('DM_TEST_FNMAP_IMAGES'), 'DM_TEST_FNMAP_IMAGES names no images')
    def test_real_images(self):
        old, new = os.environ['DM_TEST_FNMAP_IMAGES'].split(':')
        want = {0xcd22ff0: 0xcda6fe0, 0xcbfb958: 0xcc7f958, 0xcd23388: 0xcda7378, 0xcd22ce0: 0xcda6cd0, 0x1cfb220: 0x1cfb1f0,
                0x1e57f64: 0x1e57f34, 0xc2a9d0: 0xc2a9c0, 0xcbfb4a0: 0xcc7f4a0, 0x23f5ef0: 0x23f5ec0}
        out = self.run_tool(Path(old).read_bytes(), Path(new).read_bytes(), *want)
        self.assertEqual(len(out), len(want), out)
        for (o, n), line in zip(want.items(), out):
            self.assertTrue(line.startswith(f'{o:#x} → {n:#x}  '), line)


if __name__ == '__main__':
    unittest.main()
