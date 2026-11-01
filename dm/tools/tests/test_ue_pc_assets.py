"""ue_pc_assets.py on two synthetic platforms (IoStore containers written with uepak.write_toc, no game files, no host); Toc.paths() on a directory index; DM_TEST_PC_ASSETS_TOC names a real .utoc whose
directory index is read (optional)."""
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'dm/gfx/tools')); sys.path.insert(0, str(REPO / 'dm/tools'))
import uepak
import ue_pc_assets as T

MOUNT = '../../../'
PKG = 'APK2/Content/APK2/Art/'


def package(w, h, first, nmips=5, pf=b'PF_DXT1'):
    """A minimal zen package: version 0, header size, then a body with SizeX, SizeY, packed, the pixel format FString, first mip and mip count"""
    hdr = struct.pack('<II', 0, 64) + bytes(56)
    return hdr + struct.pack('<iii', w, h, 0) + struct.pack('<i', len(pf) + 1) + pf + b'\0' + struct.pack('<ii', first, nmips) + bytes(100)


def platform(root, stem, pkgs, extra=None):
    """pkgs = [(path, data, imports)]; extra = {path: bulk bytes} → the container's stem path. Package IDs are the path's hash (any 64 bits)"""
    chunks, paths, entries = [], {}, []
    for path, data, imps in pkgs:
        pid = uepak.city64(path.lower().encode('utf-16-le'))
        c = uepak.io_chunk_id(pid, 0, 1)
        chunks.append(dict(id=c, size=len(data), blocks=uepak.stored_blocks(data), meta=None)); paths[c] = MOUNT + path + '.uasset'
        entries.append((pid, tuple(imps), ()))
        if path in (extra or {}):
            b = extra[path]; chunks.append(dict(id=uepak.io_chunk_id(pid, 0, 2), size=len(b), blocks=uepak.stored_blocks(b), meta=None))
    cid = uepak.io_container_id(stem); d = uepak.container_header(cid, sorted(entries))
    chunks.append(dict(id=uepak.io_chunk_id(cid, 0, 6), size=len(d), blocks=uepak.stored_blocks(d), meta=None))
    os.makedirs(root, exist_ok=True)
    uepak.write_toc(os.path.join(root, stem), stem, chunks, paths)
    return os.path.join(root, stem)


def pid_of(path): return uepak.city64(path.lower().encode('utf-16-le'))


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); self.root = Path(tmp.name)
        self.romfs, self.paks, self.out = str(self.root / 'RomFS'), str(self.root / 'pc'), str(self.root / 'quality')
        a, b, c, e = PKG + 'Env/T_A', PKG + 'Env/T_B', PKG + 'Env/M_C', PKG + 'Env/T_E'
        self.a, self.b, self.c, self.e = a, b, c, e
        self.bulk = bytes(range(256)) * 700   # three blocks
        platform(self.romfs + '/APK2/Content/Paks', 'pakchunk0-Switch', [(a, package(64, 64, 1), [7]), (b, package(64, 64, 0), []), (c, bytes(80), []), (e, package(64, 64, 1), [1])])
        platform(self.paks, 'pakchunk0-Windows', [(a, package(64, 64, 0), [8]), (b, package(64, 64, 0), []), (c, bytes(80) + b'x', []), (PKG + 'Env/T_D', package(64, 64, 0), []), (e, package(64, 64, 0), [2])],
                 {a: self.bulk, b: b'bb' * 10, c: b'cc' * 10})   # a bulk chunk each: a container of two chunks may have no perfect hash (io_perfect_hash)
        self.stem = f'{self.romfs}/APK2/Content/Paks/pakchunk0-Switch'

    def run_rules(self, rules):
        return T.build_rules(rules, self.romfs, self.paks, self.out, lambda d, n: self.fail('Oodle'))

    def container(self, preset='low'):
        return uepak.Toc(f'{self.out}/{preset}/APK2/Content/Paks/pakchunk0-Switch_99_P.utoc')


class Build(Base):
    def test_textures_rule_picks_only_the_larger_one(self):
        # A differs in its imports (7 vs 8): skipped; make the Switch's equal first
        platform(self.romfs + '/APK2/Content/Paks', 'pakchunk0-Switch', [(self.a, package(64, 64, 1), [8]), (self.b, package(64, 64, 0), []), (self.c, bytes(80), []), (self.e, package(64, 64, 1), [1])])
        rep = self.run_rules([('low', 'textures', PKG.lower() + 'env/*')])
        self.assertEqual(rep, ['low: 1 package(s) (1 textures, 0 packages), 3 chunks, %s bytes; skipped: missing 0, imports 1, same 1, notex 1, format 0' % f"{os.path.getsize(self.container().path[:-5] + '.ucas'):,}"])
        t = self.container(); src = uepak.Toc(self.paks + '/pakchunk0-Windows.utoc'); pid = pid_of(self.a)
        for typ in (1, 2):
            c = uepak.io_chunk_id(pid, 0, typ); i = uepak.io_lookup(t.ids, t.seeds, c)
            self.assertIsNotNone(i); self.assertEqual(t.raw_blocks(i), src.raw_blocks(src.index[c]))
        for k, c in enumerate(t.ids): self.assertEqual(uepak.io_lookup(t.ids, t.seeds, c), k)
        h = uepak.read_container_header(t.read(t.of_type(6)[0]))
        self.assertEqual(h['cid'], uepak.io_container_id('pakchunk0-Switch_99_P'))
        self.assertEqual(h['entries'], [(pid, (8,), ())])
        self.assertEqual(t.read(uepak.io_lookup(t.ids, t.seeds, uepak.io_chunk_id(pid, 0, 2))), self.bulk)
        self.assertEqual(t.paths(), {})
        tsv = (self.root / 'ue_pc_assets_low.tsv').read_text().splitlines()
        self.assertEqual(len(tsv), 1); self.assertEqual(tsv[0].split('\t')[:5], [self.a, 'textures', '32x32', '64x64', '2'])

    def test_package_rule_picks_the_package(self):
        rep = self.run_rules([('low', 'package', PKG.lower() + 'env/m_c')])
        self.assertIn('1 package(s) (0 textures, 1 packages), 3 chunks', rep[0])
        t = self.container(); pid = pid_of(self.c)
        self.assertEqual(uepak.read_container_header(t.read(t.of_type(6)[0]))['entries'], [(pid, (), ())])
        self.assertEqual(t.read(uepak.io_lookup(t.ids, t.seeds, uepak.io_chunk_id(pid, 0, 1))), bytes(80) + b'x')

    def test_imports_mismatch_is_skipped(self):
        rep = self.run_rules([('low', 'package', PKG + 'Env/T_E')])
        self.assertIn('0 package(s)', rep[0]); self.assertIn('imports 1', rep[0])
        self.assertFalse(os.path.exists(self.stem.replace(self.romfs, f'{self.out}/low') + '_99_P.utoc'))

    def test_pak_created_when_absent_and_left_alone_when_present(self):
        pak = f'{self.out}/low/APK2/Content/Paks/pakchunk0-Switch_99_P.pak'
        self.run_rules([('low', 'package', PKG + 'Env/M_C')])
        p = uepak.Pak(pak); self.assertEqual(list(p.files), [])
        Path(pak).write_bytes(b'mine'); os.utime(pak, (1, 1))
        self.run_rules([('low', 'package', PKG + 'Env/M_C')])
        self.assertEqual(Path(pak).read_bytes(), b'mine'); self.assertEqual(os.stat(pak).st_mtime, 1)

    def test_rule_matching_nothing_is_an_error(self):
        with self.assertRaises(T.Error): self.run_rules([('low', 'textures', 'nothing/*')])

    def test_missing_on_the_other_platform(self):
        platform(self.romfs + '/APK2/Content/Paks', 'pakchunk0-Switch', [(PKG + 'Env/T_Z', package(64, 64, 1), []), (self.a, package(64, 64, 1), [8]), (self.b, package(64, 64, 0), [])])
        rep = self.run_rules([('low', 'textures', '*T_Z')])
        self.assertIn('missing 1', rep[0])

    def test_two_presets(self):
        rep = self.run_rules([('low', 'package', PKG + 'Env/M_C'), ('high', 'package', PKG + 'Env/T_B')])
        self.assertEqual([r.split(':')[0] for r in rep], ['low', 'high'])
        self.assertTrue((self.root / 'ue_pc_assets_high.tsv').exists())


class Paths(unittest.TestCase):
    def test_no_directory_index(self):
        with tempfile.TemporaryDirectory() as d:
            c = uepak.io_chunk_id(1, 0, 1)
            uepak.write_toc(d + '/x', 'x', [dict(id=c, size=3, blocks=uepak.stored_blocks(b'abc'), meta=None)])
            self.assertEqual(uepak.Toc(d + '/x.utoc').paths(), {})

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            names = [MOUNT + 'A/B/x.uasset', MOUNT + 'A/B/y.uasset', MOUNT + 'A/C/z.umap', MOUNT + 'top.uasset', MOUNT + 'A/B/D/wé.uasset']
            ids = [uepak.io_chunk_id(10 + k, 0, 1) for k in range(len(names))]
            uepak.write_toc(d + '/x', 'x', [dict(id=c, size=1, blocks=uepak.stored_blocks(b'q'), meta=None) for c in ids], dict(zip(ids, names)))
            t = uepak.Toc(d + '/x.utoc')
            self.assertEqual({t.ids[i]: p for i, p in t.paths().items()}, dict(zip(ids, names)))

    def test_encrypted_refused(self):
        with tempfile.TemporaryDirectory() as d:
            c = uepak.io_chunk_id(1, 0, 1)
            uepak.write_toc(d + '/x', 'x', [dict(id=c, size=1, blocks=uepak.stored_blocks(b'q'), meta=None)], {c: MOUNT + 'a.uasset'})
            t = uepak.Toc(d + '/x.utoc'); t.flags |= 2; t._paths = None
            with self.assertRaises(ValueError): t.paths()

    def test_lazy_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            c = uepak.io_chunk_id(1, 0, 1); calls = []
            def get(): calls.append(1); return b'abc'
            uepak.write_toc(d + '/x', 'x', [dict(id=c, size=3, blocks=[(get, 3, '')], meta=None)])
            self.assertEqual(calls, [1]); self.assertEqual(uepak.Toc(d + '/x.utoc').read(0), b'abc')
            with self.assertRaises(ValueError): uepak.write_toc(d + '/y', 'y', [dict(id=c, size=4, blocks=[(get, 4, '')], meta=None)])


class TextureTop(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(T.texture_top(package(256, 128, 2)), ('PF_DXT1', 64, 32))
        self.assertEqual(T.texture_top(package(4, 4, 5)), ('PF_DXT1', 1, 1))
        self.assertIsNone(T.texture_top(bytes(80))); self.assertIsNone(T.texture_top(b''))


@unittest.skipUnless(os.environ.get('DM_TEST_PC_ASSETS_TOC'), 'DM_TEST_PC_ASSETS_TOC names a real .utoc')
class RealToc(unittest.TestCase):
    def test_paths(self):
        t = uepak.Toc(os.environ['DM_TEST_PC_ASSETS_TOC']); p = t.paths()
        self.assertTrue(p); self.assertTrue(all(v.startswith(MOUNT) for v in p.values()))


if __name__ == '__main__': unittest.main()
