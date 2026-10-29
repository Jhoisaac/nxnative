"""Unreal Engine 4.21 to 4.25 paks (versions 7, 8 and 9, the last with a frozen memory-image index) built as synthetic files; no game files or keys."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'dm/gfx/tools'))
import uepak


def fstr(s):
    b = s.encode() + b'\0'
    return struct.pack('<i', len(b)) + b


BODY = b'legacy pak file body ' * 12


def data_of(files):
    """The pak data: each file behind a 53-byte FPakEntry (a zlib one also has 4 + 16 bytes of block table); (name, raw, stored, method, offset, head) per file"""
    data, out = bytearray(), []
    for name, raw, meth in files:
        stored = zlib.compress(raw) if meth else raw
        head = 53 + (4 + 16 if meth else 0)
        out.append((name, raw, stored, meth, len(data), head)); data += bytes(head) + stored
    return data, out


def legacy_index(rows):
    """Per file its name and FPakEntry (the blocks relative to the entry, as from version 5)"""
    index = fstr('../../../') + struct.pack('<i', len(rows))
    for name, raw, stored, meth, at, head in rows:
        index += fstr(name) + struct.pack('<qqqi', at, len(stored), len(raw), meth) + bytes(20)
        if meth: index += struct.pack('<i', 1) + struct.pack('<qq', head, head + len(stored))
        index += struct.pack('<BI', 0, len(raw))
    return index


def pak7(files):
    """Version 7: the 0x2d-byte legacy footer, with the key GUID (16) in front of the flag"""
    data, rows = data_of(files); index = legacy_index(rows)
    return bytes(data) + index + bytes(16) + b'\0' + struct.pack('<IIQQ', uepak.PAK_MAGIC, 7, len(data), len(index)) + bytes(20)


def named_footer(version, ioff, isz, names, frozen=None):
    """The footer of versions 8 and 9: GUID, encrypted flag, magic, version, index offset and size, SHA-1, (version 9: the frozen index flag,) five 32-byte method names"""
    foot = bytes(16) + b'\0' + struct.pack('<IIQQ', uepak.PAK_MAGIC, version, ioff, isz) + bytes(20)
    if frozen is not None: foot += bytes([frozen])
    return foot + b''.join(n.ljust(32, b'\0') for n in (list(names) + [b''] * 5)[:5])


def pak8(files, names=(b'Zlib',)):
    data, rows = data_of(files); index = legacy_index(rows)
    return bytes(data) + index + named_footer(8, len(data), len(index), names)


def rel(slot, target):
    """A frozen pointer: bit 0 set, the distance from its own place in the upper bits"""
    return struct.pack('<Q', (target - slot) << 1 | 1)


def pak9_frozen(files, names=(b'Zlib',), dirs=None):
    """Version 9 with a frozen index: root (mount FString, TArray of 80-byte entries at 0x10, the directory TSet at 0x20), the entries, their block tables, 80-byte directory elements, 32-byte file elements"""
    data, rows = data_of(files); b = bytearray(0x30)
    def put(blob):   # appended, 8-aligned; its place
        while len(b) % 8: b.append(0)
        at = len(b); b.extend(blob); return at
    def string(slot, s):   # an FString at slot: pointer, num, max
        w = (s + '\0').encode('utf-16-le'); at = put(w)
        b[slot:slot + 8] = rel(slot, at); struct.pack_into('<ii', b, slot + 8, len(s) + 1, len(s) + 1)
    string(0, '../../../')
    ep = put(bytes(80 * len(rows))); b[0x10:0x18] = rel(0x10, ep); struct.pack_into('<ii', b, 0x18, len(rows), len(rows))
    for k, (name, raw, stored, meth, at, head) in enumerate(rows):
        o = ep + 80 * k; struct.pack_into('<qqq', b, o, at, len(stored), len(raw))
        if meth:
            bp = put(struct.pack('<qq', head, head + len(stored))); b[o + 48:o + 56] = rel(o + 48, bp); struct.pack_into('<ii', b, o + 56, 1, 1)
        struct.pack_into('<IIB', b, o + 64, len(raw), meth, 0)
    dirs = dirs or {'Content/': list(range(len(rows)))}   # directory name -> entry indices
    dp = put(bytes(80 * len(dirs))); b[0x20:0x28] = rel(0x20, dp); struct.pack_into('<ii', b, 0x28, len(dirs), len(dirs))
    for d, (dn, idx) in enumerate(dirs.items()):
        o = dp + 80 * d; string(o, dn); fp = put(bytes(32 * len(idx))); b[o + 16:o + 24] = rel(o + 16, fp); struct.pack_into('<ii', b, o + 24, len(idx), len(idx))
        for i, j in enumerate(idx):
            string(fp + 32 * i, rows[j][0].rsplit('/', 1)[-1]); struct.pack_into('<i', b, fp + 32 * i + 16, j)
    return bytes(data) + bytes(b) + named_footer(9, len(data), len(b), names, frozen=1), len(data)   # the pak and where the index starts


class Legacy(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); self.root = Path(tmp.name)

    def pak(self, data):
        p = self.root / 'pakchunk0-Switch.pak'; p.write_bytes(data)
        pk = uepak.Pak(str(p)); self.addCleanup(pk.f.close); return pk

    def test_version_7(self):
        pk = self.pak(pak7([('Content/a.txt', BODY, 0), ('Content/z.bin', BODY * 3, 1)]))
        self.assertEqual(pk.version, 7)
        self.assertEqual(sorted(pk.files), ['Content/a.txt', 'Content/z.bin'])
        self.assertEqual((pk.files['Content/a.txt']['method'], pk.files['Content/z.bin']['method']), ('', 'Zlib'))
        self.assertEqual(pk.read('Content/a.txt'), BODY); self.assertEqual(pk.read('Content/z.bin'), BODY * 3)
        with open(pk.path, 'rb') as f: self.assertTrue(uepak.footer(f)[0] == 0 and not uepak.frozen_index(f))

    def test_version_8_names_the_methods(self):
        pk = self.pak(pak8([('Content/a.txt', BODY, 0), ('Content/z.bin', BODY * 3, 1)]))
        self.assertEqual(pk.version, 8); self.assertEqual(pk.methods[0], 'Zlib')
        self.assertEqual(pk.files['Content/z.bin']['method'], 'Zlib')
        self.assertEqual(pk.read('Content/z.bin'), BODY * 3); self.assertEqual(pk.read('Content/a.txt'), BODY)

    def test_version_8_method_the_footer_does_not_name(self):
        p = self.root / 'bad.pak'; p.write_bytes(pak8([('Content/z.bin', BODY, 2)]))   # method 2, names: Zlib only
        with self.assertRaisesRegex(ValueError, 'compression method 2, which the footer does not'): uepak.Pak(str(p))

    def test_version_9_frozen_index(self):
        data, _ = pak9_frozen([('Content/a.txt', BODY, 0), ('Content/z.bin', BODY * 3, 1), ('Engine/e.bin', BODY, 0)],
                              dirs={'Content/': [0, 1], 'Engine/': [2]})
        pk = self.pak(data)
        self.assertEqual((pk.version, pk.mount, pk.count), (9, '../../../', 3))
        self.assertEqual(sorted(pk.files), ['Content/a.txt', 'Content/z.bin', 'Engine/e.bin'])
        self.assertEqual(pk.files['Content/z.bin']['method'], 'Zlib')
        for name, raw in (('Content/a.txt', BODY), ('Content/z.bin', BODY * 3), ('Engine/e.bin', BODY)): self.assertEqual(pk.read(name), raw)
        with open(pk.path, 'rb') as f: self.assertTrue(uepak.frozen_index(f))

    def test_version_9_unfrozen_index_is_the_legacy_one(self):
        data, rows = data_of([('Content/a.txt', BODY, 0)]); index = legacy_index(rows)
        pk = self.pak(bytes(data) + index + named_footer(9, len(data), len(index), (b'Zlib',), frozen=0))
        self.assertEqual((pk.version, list(pk.files), pk.read('Content/a.txt')), (9, ['Content/a.txt'], BODY))

    def corrupt(self, edit):
        data, base = pak9_frozen([('Content/a.txt', BODY, 0)]); data = bytearray(data); edit(data, base)
        p = self.root / 'bad.pak'; p.write_bytes(bytes(data)); return p

    def test_version_9_pointer_without_bit_0(self):
        def edit(d, base): d[base + 0x10] &= 0xfe   # the entries pointer
        with self.assertRaisesRegex(ValueError, 'is not set'): uepak.Pak(str(self.corrupt(edit)))

    def test_version_9_pointer_out_of_bounds(self):
        def edit(d, base): d[base + 0x10:base + 0x18] = struct.pack('<Q', 1 << 40 | 1)
        with self.assertRaisesRegex(ValueError, 'do not fit'): uepak.Pak(str(self.corrupt(edit)))

    def test_version_9_entry_index_out_of_range(self):
        def edit(d, base):   # the one file element, found through the directory's pointers
            dp = base + 0x20 + (struct.unpack_from('<Q', d, base + 0x20)[0] >> 1); fp = dp + 16 + (struct.unpack_from('<Q', d, dp + 16)[0] >> 1)
            struct.pack_into('<i', d, fp + 16, 5)
        with self.assertRaisesRegex(ValueError, 'names entry 5 of 1'): uepak.Pak(str(self.corrupt(edit)))


if __name__ == '__main__': unittest.main()
