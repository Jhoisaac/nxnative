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


def package(w, h, first, nmips=5, pf=b'PF_DXT1', names=(b'Texture2D',)):
    """A minimal zen package: version 0, header size, the name map at 0x34, then a body with SizeX, SizeY, packed, the pixel format FString, first mip and mip count"""
    nm = struct.pack('<IIQ', len(names), sum(map(len, names)), 0) + bytes(8 * len(names)) + struct.pack(f'>{len(names)}H', *map(len, names)) + b''.join(names)
    hsz = 0x34 + len(nm); hdr = struct.pack('<II', 0, hsz) + bytes(0x34 - 8) + nm
    return hdr + struct.pack('<iii', w, h, 0) + struct.pack('<i', len(pf) + 1) + pf + b'\0' + struct.pack('<ii', first, nmips) + bytes(100 + 16 * (nmips - first))   # one bulk-map entry per stored mip, as a real package: a stripped mip shortens it


def mesh(names, body, span=72):
    """A minimal zen package that is no texture: the name map, the summary's sizes and offsets (the export map holds span bytes), then the body"""
    nm = struct.pack('<IIQ', len(names), sum(map(len, names)), 0) + b''.join(struct.pack('<Q', uepak.city64(n.lower())) for n in names) + struct.pack(f'>{len(names)}H', *map(len, names)) + b''.join(names)
    hsz = 0x34 + len(nm); offs = (hsz, hsz + 8, hsz + 16, hsz + 16 + span, hsz + 16 + span + 8, hsz + 16 + span + 16, hsz + 16 + span + 24)
    return struct.pack('<IIQII', 0, hsz, 0, 0, hsz) + struct.pack('<7i', *offs) + nm + body


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
        self.assertEqual(rep, ['low: 1 package(s) (1 textures, 0 packages, 0 meshes), 3 chunks, %s bytes; skipped: missing 0, imports 1, same 1, notex 1, names 0, format 0, texture 0, exports 0, bulk 0, notmesh 0' % f"{os.path.getsize(self.container().path[:-5] + '.ucas'):,}"])
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
        self.assertIn('1 package(s) (0 textures, 1 packages, 0 meshes), 3 chunks', rep[0])
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

    def test_other_name_map_is_skipped(self):
        # a larger texture whose package also names another platform's data (a map or blueprint with a texture beside its physics or shaders): not taken
        z = PKG + 'Env/T_Y'
        platform(self.romfs + '/APK2/Content/Paks', 'pakchunk0-Switch', [(z, package(64, 64, 1, names=(b'Texture2D', b'PhysXGeneric')), []), (self.a, package(64, 64, 1), [8])])
        platform(self.paks, 'pakchunk0-Windows', [(z, package(64, 64, 0, names=(b'Texture2D', b'PhysXPC')), []), (self.a, package(64, 64, 0), [8])], {z: b'zz' * 10, self.a: self.bulk})
        rep = self.run_rules([('low', 'textures', '*T_Y')])
        self.assertIn('0 package(s)', rep[0]); self.assertIn('names 1', rep[0])

    def test_two_presets(self):
        rep = self.run_rules([('low', 'package', PKG + 'Env/M_C'), ('high', 'package', PKG + 'Env/T_B')])
        self.assertEqual([r.split(':')[0] for r in rep], ['low', 'high'])
        self.assertTrue((self.root / 'ue_pc_assets_high.tsv').exists())


class Meshes(Base):
    def setUp(self):
        super().setUp()
        sn, pn = (b'Texture2D', b'BodySetup', b'PhysXGeneric'), (b'Texture2D', b'BodySetup', b'PhysXPC'); nb = (b'Texture2D', b'PhysXGeneric')
        self.m = [PKG + 'Mesh/SM_' + c for c in 'ABCDEFGH']; m = self.m; self.lod = bytes(range(50))
        platform(self.romfs + '/APK2/Content/Paks', 'pakchunk0-Switch', [(m[0], mesh(sn, b'body0'), [1]), (m[1], mesh(sn, b'body1'), []), (m[2], mesh(sn, b'body2'), []), (m[3], mesh(sn, b'body3'), []),
                                                                         (m[4], mesh(sn, b'body4'), []), (m[5], package(64, 64, 1), []), (m[6], mesh(sn, b'body6'), []), (m[7], mesh(nb, b'body7'), [])], {m[1]: b'filler'})   # chunk counts that have a perfect hash (io_perfect_hash)
        platform(self.paks, 'pakchunk0-Windows', [(m[0], mesh(pn, b'body0' + self.lod), [1]), (m[1], mesh(pn, b'body1'), []), (m[2], mesh(pn + (b'Extra',), b'body2' + self.lod), []),
                                                  (m[3], mesh(pn, b'body3' + self.lod, span=144), []), (m[4], mesh(pn, b'body4' + self.lod), []), (m[5], package(64, 64, 0), []), (m[6], mesh(pn, b'body6' + self.lod), []), (m[7], mesh((b'Texture2D', b'PhysXPC'), b'body7' + self.lod), [])], {m[4]: b'bulk' * 10})
        self.rules = [('low', 'rename', 'PhysXPC=PhysXGeneric'), ('low', 'meshes', PKG.lower() + 'mesh/*')]

    def test_rename_names(self):
        d = mesh((b'Texture2D', b'PhysXPC'), b'body'); r = T.rename_names(d, {'PhysXPC': 'PhysXGeneric'})
        self.assertEqual(T.names(r), (b'Texture2D', b'PhysXGeneric')); self.assertEqual(r[-4:], b'body')
        self.assertEqual(struct.unpack_from('<I', r, 4)[0], struct.unpack_from('<I', d, 4)[0] + 5)
        self.assertEqual(struct.unpack_from('<I', r, 0x14)[0], struct.unpack_from('<I', d, 0x14)[0] + 5)
        self.assertEqual(struct.unpack_from('<7i', r, 0x18), tuple(v + 5 for v in struct.unpack_from('<7i', d, 0x18)))
        self.assertEqual(struct.unpack_from('<I', r, 0x38)[0], struct.unpack_from('<I', d, 0x38)[0] + 5)
        self.assertEqual(struct.unpack_from('<2Q', r, 0x44)[1], uepak.city64(b'physxgeneric')); self.assertEqual(struct.unpack_from('<Q', r, 0x44)[0], uepak.city64(b'texture2d'))
        self.assertEqual(r, mesh((b'Texture2D', b'PhysXGeneric'), b'body'))   # as if built so
        self.assertIsNone(T.rename_names(b'junk', {}))

    def test_meshes_rule(self):
        rep = self.run_rules(self.rules)
        self.assertEqual(len(rep), 1); self.assertIn('2 package(s) (0 textures, 0 packages, 2 meshes), 3 chunks', rep[0])
        self.assertIn('same 1', rep[0]); self.assertIn('names 1', rep[0]); self.assertIn('exports 1', rep[0]); self.assertIn('bulk 1', rep[0]); self.assertIn('notmesh 1', rep[0]); self.assertIn('texture 1', rep[0]); self.assertIn('name-only checked 1', rep[0])
        t = self.container(); pid = pid_of(self.m[0])
        self.assertEqual(t.read(uepak.io_lookup(t.ids, t.seeds, uepak.io_chunk_id(pid, 0, 1))), mesh((b'Texture2D', b'BodySetup', b'PhysXGeneric'), b'body0' + self.lod))
        self.assertEqual(uepak.read_container_header(t.read(t.of_type(6)[0]))['entries'], sorted([(pid, (1,), ()), (pid_of(self.m[6]), (), ())]))

    def test_not_taken_without_a_rename_row(self):
        rep = self.run_rules(self.rules[1:])
        self.assertIn('0 package(s)', rep[0]); self.assertIn('names 5', rep[0])

    def test_wrong_rename_raises(self):
        good = T.rename_names   # a rename that leaves a same-length package unlike ours (a broken hash or offset shift)
        T.rename_names = lambda d, t: (lambda r: r[:0x40] + b'!' + r[0x41:])(good(d, t))
        try:
            with self.assertRaises(T.Error): self.run_rules(self.rules)
        finally: T.rename_names = good

    def test_rows(self):
        f = self.root / 't.tsv'; f.write_text('low\trename\tA=B\nlow\tmeshes\t*\n'); self.assertEqual(T.rows(f), [('low', 'rename', 'A=B'), ('low', 'meshes', '*')])
        f.write_text('low\trename\tAB\n')
        with self.assertRaises(T.Error): T.rows(f)


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
