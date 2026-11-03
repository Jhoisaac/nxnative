"""IoStore writer: the perfect hash, write_toc's round trip and the container header, on synthetic data; DM_TEST_IOWRITE_TOC names a real .utoc to check the lookup against (optional)."""
import os
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'dm/gfx/tools'))
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


@unittest.skipUnless(os.environ.get('DM_TEST_IOWRITE_TOC'), 'DM_TEST_IOWRITE_TOC names a real .utoc')
class RealToc(unittest.TestCase):
    def test_lookup_with_its_own_seeds(self):
        t = uepak.Toc(os.environ['DM_TEST_IOWRITE_TOC'])
        for i, c in enumerate(t.ids[:2000]): self.assertEqual(uepak.io_lookup(t.ids, t.seeds, c), i)


if __name__ == '__main__': unittest.main()
