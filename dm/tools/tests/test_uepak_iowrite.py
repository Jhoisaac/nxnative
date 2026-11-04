"""IoStore writer: the perfect hash, write_toc's round trip and the container header, on synthetic data; DM_TEST_IOWRITE_TOC names a real .utoc to check the lookup against (optional);
the version 2 writer (Unreal Engine 4.25) and its container header, and DM_TEST_IOWRITE_TOC2 names a real version 2 .utoc (a game's pakchunk1-Switch.utoc) whose tables write_toc2 must reproduce byte for byte (optional)."""
import os
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
import zlib

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'dm/gfx/tools')); sys.path.insert(0, str(REPO / 'dm/tools'))
import romfs
import uepak


def rand_ids(rng, n):
    out = set()
    while len(out) < n: out.add(uepak.io_chunk_id(rng.getrandbits(64), rng.randrange(4), rng.choice((1, 2, 3, 6, 9))))
    return sorted(out)


class PerfectHash(unittest.TestCase):
    def test_every_id_found_and_absent_ones_not(self):
        rng = random.Random(7)
        for n in (1, 2, 3, 50, 1000):
            ids = rand_ids(rng, n)
            slots, seeds = uepak.io_perfect_hash(ids)
            self.assertEqual(sorted(slots), list(range(n)))
            self.assertEqual(len(seeds), max(1, (n + 1) // 2))
            stored = [ids[i] for i in slots]
            for k, c in enumerate(stored): self.assertEqual(uepak.io_lookup(stored, seeds, c), k)
            have = set(ids)
            for c in rand_ids(rng, 200):
                if c not in have: self.assertIsNone(uepak.io_lookup(stored, seeds, c))

    def test_hash_of_known_values(self):
        h = 0xcbf29ce484222325
        for c in bytes(12): h = ((h * 0x100000001B3) & (2**64 - 1)) ^ c
        self.assertEqual(uepak.io_hash(bytes(12), 0), h)
        self.assertNotEqual(uepak.io_hash(bytes(12), 1), h)

    def test_duplicates_refused(self):
        c = uepak.io_chunk_id(1, 0, 1)
        with self.assertRaises(ValueError): uepak.io_perfect_hash([c, c])


class WriteToc(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); self.root = Path(tmp.name)
        rng = random.Random(3)
        self.big, self.small = rng.randbytes(150000), rng.randbytes(10)
        self.o1, self.o2 = rng.randbytes(30000), rng.randbytes(500)
        self.meta = bytes(range(32)) + b'\x01'
        self.ids = [uepak.io_chunk_id(n, 0, 1) for n in (11, 22, 33)]
        self.chunks = [dict(id=self.ids[0], size=len(self.big), blocks=uepak.stored_blocks(self.big), meta=None),
                       dict(id=self.ids[1], size=len(self.small), blocks=uepak.stored_blocks(self.small), meta=None),
                       dict(id=self.ids[2], size=65536 + 1000, blocks=[(self.o1, 65536, 'Oodle'), (self.o2, 1000, 'Oodle')], meta=self.meta)]

    def test_round_trip(self):
        stem = str(self.root / 'pakchunk99-Switch')
        cid = uepak.write_toc(stem, 'pakchunk99-Switch', self.chunks)
        self.assertEqual(cid, uepak.io_container_id('pakchunk99-Switch'))
        t = uepak.Toc(stem + '.utoc')
        self.assertEqual((t.version, t.block_size, t.flags), (5, 65536, 1))
        self.assertEqual(t.methods, ['Oodle'])
        self.assertEqual(struct.unpack_from('<Q', Path(stem + '.utoc').read_bytes(), 56)[0], cid)
        for k, c in enumerate(self.chunks):
            i = t.index[c['id']]
            self.assertEqual(uepak.io_lookup(t.ids, t.seeds, c['id']), i)
            self.assertEqual(t.ranges[i][0] % 65536, 0)
            self.assertEqual(t.ranges[i][1], c['size'])
        self.assertEqual(t.read(t.index[self.ids[0]]), self.big)
        self.assertEqual(t.read(t.index[self.ids[1]]), self.small)
        i = t.index[self.ids[2]]
        self.assertEqual(t.raw_blocks(i), [(self.o1, 65536, 'Oodle'), (self.o2, 1000, 'Oodle')])
        self.assertEqual(t.meta(i), self.meta)
        self.assertEqual(t.meta(t.index[self.ids[1]]), bytes(33))
        self.assertTrue(all(at % 16 == 0 for at, _, _, _ in t.blocks))
        n, nb, ns = len(self.chunks), len(t.blocks), len(t.seeds)
        want = 144 + 12 * n + 10 * n + 4 * ns + 12 * nb + 32 + 33 * n
        self.assertEqual(os.path.getsize(stem + '.utoc'), want)
        last = max(t.blocks)
        self.assertEqual(os.path.getsize(stem + '.ucas'), last[0] + last[1])

    def test_uncompressed_container_has_no_methods(self):
        stem = str(self.root / 'plain')
        uepak.write_toc(stem, 'plain', self.chunks[:2])
        t = uepak.Toc(stem + '.utoc')
        self.assertEqual((t.flags, t.methods), (0, []))

    def test_validation(self):
        stem = str(self.root / 'bad')
        a = self.chunks[0]
        with self.assertRaises(ValueError): uepak.write_toc(stem, 'bad', [a, dict(a)])
        with self.assertRaises(ValueError): uepak.write_toc(stem, 'bad', [dict(a, blocks=[(b'x' * 100, 100, '')] * 3)])
        with self.assertRaises(ValueError): uepak.write_toc(stem, 'bad', [dict(a, size=10, blocks=[(b'x' * 10, 10, 'Zlib')])])
        with self.assertRaises(ValueError): uepak.write_toc(stem, 'bad', [dict(a, size=10, blocks=[(b'x' * 9, 10, '')])])


class ContainerHeader(unittest.TestCase):
    def test_round_trip_and_layout(self):
        h1, h2 = bytes(range(20)), bytes(range(20, 40))
        entries = [(0x1111, (5, 6, 7), (h1,)), (0x2222, (), ()), (0x3333, (9,), (h1, h2))]
        d = uepak.container_header(0xdd448b1f247da50e, entries)
        self.assertEqual(d[:4], b'nCoI')
        self.assertEqual(struct.unpack_from('<I', d, 4)[0], 3)
        self.assertEqual(d[-12:], bytes(12))
        self.assertEqual(d[-20:-12], bytes(8))   # the two optional counts
        r = uepak.read_container_header(d)
        self.assertEqual((r['cid'], r['version']), (0xdd448b1f247da50e, 3))
        self.assertEqual(r['entries'], entries)
        self.assertEqual(uepak.read_container_header(uepak.container_header(1, []))['entries'], [])

    def test_wrong_signature_or_version(self):
        d = uepak.container_header(1, [(2, (), ())])
        with self.assertRaises(ValueError): uepak.read_container_header(b'xxxx' + d[4:])
        with self.assertRaises(ValueError): uepak.read_container_header(d[:4] + struct.pack('<I', 2) + d[8:])


class WriteToc2(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); self.root = Path(tmp.name)
        rng = random.Random(5)
        self.a, self.b, self.c = rng.randbytes(150000), rng.randbytes(40), rng.randbytes(65536 + 7)
        z = lambda x: zlib.compress(x, 6)
        self.ids = [uepak.io_chunk_id(n, 0, t) for n, t in ((5, 2), (3, 3), (9, 2))]
        self.chunks = [dict(id=self.ids[0], size=len(self.a), blocks=[(z(self.a[o:o + 65536]), len(self.a[o:o + 65536]), 'Zlib') for o in range(0, len(self.a), 65536)], meta=None),
                       dict(id=self.ids[1], size=len(self.b), blocks=uepak.stored_blocks(self.b), meta=bytes(range(32)) + b'\x00'),
                       dict(id=self.ids[2], size=len(self.c), blocks=[(z(self.c[:65536]), 65536, 'Zlib'), (self.c[65536:], 7, '')], meta=None)]

    def test_round_trip(self):
        stem = str(self.root / 'pakchunk0-Switch_99_P')
        cid = uepak.write_toc2(stem, 'pakchunk0-Switch_99_P', self.chunks)
        raw = Path(stem + '.utoc').read_bytes()
        self.assertEqual((raw[16], struct.unpack_from('<I', raw, 20)[0], struct.unpack_from('<I', raw, 36)[0], struct.unpack_from('<I', raw, 40)[0], struct.unpack_from('<I', raw, 52)[0], raw[80]), (2, 144, 1, 32, 0, 1))
        self.assertEqual(struct.unpack_from('<Q', raw, 56)[0], cid)
        t = uepak.Toc(stem + '.utoc')
        self.assertEqual((t.version, t.block_size, t.flags, t.methods, t.seeds, t.ids), (2, 65536, 1, ['Zlib'], [], self.ids))   # the order given
        self.assertEqual([t.read(i) for i in range(3)], [self.a, self.b, self.c])
        self.assertEqual(t.meta(1), bytes(range(32)) + b'\x00')
        self.assertEqual(t.meta(0), bytes(32) + b'\x01')
        self.assertTrue(all(at % 16 == 0 for at, _, _, _ in t.blocks))
        self.assertEqual(os.path.getsize(stem + '.ucas') % 16, 0)
        self.assertEqual(t.raw_blocks(2)[1], (self.c[65536:], 7, ''))
        self.assertEqual(len(raw), 144 + 12 * 3 + 10 * 3 + 12 * len(t.blocks) + 32 + 33 * 3)

    def test_directory_index(self):
        stem = str(self.root / 'withdir')
        paths = {self.ids[0]: '../../../APK/Content/A/x.uasset', self.ids[1]: '../../../APK/Content/A/x.ubulk'}
        uepak.write_toc2(stem, 'withdir', self.chunks, paths)
        t = uepak.Toc(stem + '.utoc')
        self.assertEqual(t.flags, 9)
        self.assertEqual(t.paths(), {0: paths[self.ids[0]], 1: paths[self.ids[1]]})

    def test_methods_of_each_version(self):
        with self.assertRaises(ValueError): uepak.write_toc2(str(self.root / 'o'), 'o', [dict(self.chunks[1], size=10, blocks=[(b'x' * 5, 10, 'Oodle')])])
        with self.assertRaises(ValueError): uepak.write_toc(str(self.root / 'z'), 'z', self.chunks[:1])
        with self.assertRaises(ValueError): uepak.write_toc(str(self.root / 'v'), 'v', self.chunks[:2], None, 3)

    def test_container_header2(self):
        entries = [(0x1111, 3846, 1, 1, 9903, (5, 6, 7)), (0x2222, 100, 9, 1, 3, ()), (0x3333, 70000, 2, 1, 4, (9,))]
        d = uepak.container_header2(0xb9f66c62c549f00c, entries)
        self.assertEqual(len(d) % 65536, 0)
        self.assertEqual(struct.unpack_from('<QIi', d, 0), (0xb9f66c62c549f00c, 3, 0))
        self.assertEqual(d[16:28], struct.pack('<iQ', 8, 0xC1640000))   # the algorithm ID where the game's headers have it
        r = uepak.read_container_header2(d)
        self.assertEqual((r['cid'], r['entries']), (0xb9f66c62c549f00c, entries))
        self.assertEqual(uepak.read_container_header2(uepak.container_header2(1, []))['entries'], [])
        with self.assertRaises(ValueError): uepak.read_container_header2(d[:60])


@unittest.skipUnless(os.environ.get('DM_TEST_IOWRITE_TOC2'), 'DM_TEST_IOWRITE_TOC2 names a real version 2 .utoc')
class RealToc2(unittest.TestCase):
    def test_tables_reproduced(self):
        path = os.environ['DM_TEST_IOWRITE_TOC2']; src = uepak.Toc(path)
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); stem = str(Path(tmp.name) / 'copy')
        chunks = [dict(id=src.ids[i], size=src.ranges[i][1], blocks=src.raw_blocks(i, lazy=True), meta=src.meta(i)) for i in range(len(src.ids))]
        uepak.write_toc2(stem, 'copy', chunks)
        a, b = romfs.Path(path).read_bytes(), Path(stem + '.utoc').read_bytes(); n = len(src.ids); nb = len(src.blocks)
        end = 144 + 22 * n + 12 * nb + 32 * len(src.methods)
        self.assertEqual((a[16:48], a[52:56]), (b[16:48], b[52:56]))   # version, sizes, block size, partitions
        self.assertEqual(a[144:end], b[144:end])   # IDs, offsets and lengths, blocks, method names
        self.assertEqual(a[-33 * n:], b[-33 * n:])   # metas
        t = uepak.Toc(stem + '.utoc')
        for i in range(0, n, max(1, n // 50)): self.assertEqual(t.read(i), src.read(i))
        for i in range(0, n, max(1, n // 50)): self.assertEqual(t.raw_blocks(i), src.raw_blocks(i))   # the blocks verbatim (the padding between them is random in the game's .ucas, zero here)


@unittest.skipUnless(os.environ.get('DM_TEST_IOWRITE_TOC'), 'DM_TEST_IOWRITE_TOC names a real .utoc')
class RealToc(unittest.TestCase):
    def test_lookup_with_its_own_seeds(self):
        t = uepak.Toc(os.environ['DM_TEST_IOWRITE_TOC'])
        for i, c in enumerate(t.ids[:2000]): self.assertEqual(uepak.io_lookup(t.ids, t.seeds, c), i)


if __name__ == '__main__': unittest.main()
