"""Criterion's resource bundles (bnd2_shaders, Burnout Paradise Remastered's SHADERS.BNDL), without game data: each shader resource's block 1 is a zlib'd whole
GLSLC output, and a Shader resource imports its passes' vertex and pixel shaders, which give the pairs."""
from pathlib import Path
import os
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
_had = os.environ.get('DM_GAME'); os.environ['DM_GAME'] = '0100000000010000'   # shader_split loads a profile at import
import shader_split as split
if _had is None: del os.environ['DM_GAME']
else: os.environ['DM_GAME'] = _had


def glslc_output(stage, salt):
    """A whole GLSLC output of one stage that glslc_shaders accepts (the layout of test_unity_text_glslc's fixture); salt makes the code, and so the key, differ."""
    nctl, ncode, c = 0x850, 0x100, 0x100
    d = bytearray(c + nctl + ncode)
    d[:4] = bytes.fromhex('91688619')
    struct.pack_into('<I', d, 0x44, len(d))
    d[c:c + 4] = split.CTL_MAGIC
    struct.pack_into('<I', d, c + 0x20, nctl)
    struct.pack_into('<I', d, c + 0x704, ncode)
    k = c + nctl
    d[k:k + 4] = split.GFX_MAGIC
    struct.pack_into('<I', d, k + 0x30, (split.STAGES.index(stage) + 1) << 10 | 1)
    if stage == 'ps': struct.pack_into('<I', d, k + 0x48, 1)   # reads generic location 0
    d[k + 0x3c] = salt
    return bytes(d)


def bundle(resources, xml=True):
    """resources: [(id, type name, type id, block 0 bytes, block 1 bytes, imports)] → a bnd2 file: header, debug XML, entry table, then blocks 0 and 1 of every resource as zlib streams."""
    dbg = 0x30
    text = ''.join(f'<Resource id="{r[0]:08x}" type="{r[1]}" name="x"/>' for r in resources).encode() if xml else b''
    tab = dbg + len(text) + (-len(text) % 16)
    data0, data1, entries = bytearray(), bytearray(), []
    for rid, _, tid, b0, b1, imports in resources:
        imp = len(b0)
        b0 = b0 + b''.join(struct.pack('<QII', i, 8 * k, 0) for k, i in enumerate(imports))
        z0, z1 = zlib.compress(b0), (zlib.compress(b1) if b1 else b'')
        entries.append(struct.pack('<16I', rid, 0, 0, 0, 0x40000000 | len(b0), len(b1), 0, len(z0), len(z1), 0,
                                   len(data0), len(data1), 0, imp if imports else 0, tid, len(imports)))
        data0 += z0; data1 += z1
    start0 = tab + 0x40 * len(resources)
    head = struct.pack('<4s9I', b'bnd2', 2, 1, dbg, len(resources), tab, start0, start0 + len(data0), start0 + len(data0) + len(data1), 0xf)
    return (head + bytes(dbg - len(head)) + text).ljust(tab, b'\0') + b''.join(entries) + bytes(data0) + bytes(data1)


def key(out):
    _, _, ctl, code = split.glslc_shaders(out, 'k', need=False)[0]
    return split.skey(ctl, code)


class Bnd2Tests(unittest.TestCase):
    vs, ps, ps2 = glslc_output('vs', 1), glslc_output('ps', 2), glslc_output('ps', 3)
    res = [(0x10, 'VertexShader', 0x12, b'head', vs, []), (0x11, 'PixelShader', 0x12, b'head', ps, []), (0x12, 'PixelShader', 0x12, b'head', ps2, []),
           (0x20, 'Shader', 0x32, b'technique', b'', [0x10, 0x11, 0x10, 0x12]), (0x30, 'Texture', 0x1, b'tex', b'not a shader', [])]

    def test_shaders_and_technique_pairs(self):
        found, pairs = split.bnd2_shaders(bundle(self.res), '/SHADERS.BNDL')
        self.assertEqual([s for _, s, _, _ in found], ['vs', 'ps', 'ps'])
        self.assertTrue(all('#GLSLC@' in w for w, _, _, _ in found))   # single-stage programs (SINGLE_STAGE keeps covering them)
        self.assertEqual(pairs, {(key(self.vs), key(self.ps)), (key(self.vs), key(self.ps2))})

    def test_scan_file_reads_a_shader_bundle_and_skips_others(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 'SHADERS.BNDL'); Path(p).write_bytes(bundle(self.res))
            q = os.path.join(t, 'WORLD.BNDL'); Path(q).write_bytes(bundle([self.res[4]]))
            r = os.path.join(t, 'NODEBUG.BNDL'); Path(r).write_bytes(bundle(self.res, xml=False))
            rel, keys, pairs, _ = split.scan_file((p, 'SHADERS.BNDL'))
            self.assertEqual(set(keys), {key(self.vs), key(self.ps), key(self.ps2)})
            self.assertEqual(len(pairs), 2)
            self.assertEqual(split.scan_file((q, 'WORLD.BNDL'))[1:3], ({}, set()))
            self.assertEqual(split.scan_file((r, 'NODEBUG.BNDL'))[1:3], ({}, set()))

    def test_wrong_stage_is_red(self):
        bad = [(0x10, 'PixelShader', 0x12, b'head', self.vs, [])]
        with self.assertRaises(SystemExit): split.bnd2_shaders(bundle(bad), '/bad')


if __name__ == '__main__':
    unittest.main()
