"""Alchemy IGA archives (Crash Team Racing Nitro-Fueled's .pak files): shader_split.iga_members and iga_shaders on a synthetic archive, without game data. The members are raw LZMA1 chunks
(lzma.compress with FORMAT_RAW) of 0x8000 bytes behind a u32 length, each at a multiple of 0x800; a member holding a GLSLC output and a name ending in '.asl' is read, a member of another
kind is skipped, a member whose chunk is damaged is red when it is read."""
import lzma
import os
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
_had = os.environ.get('DM_GAME'); os.environ['DM_GAME'] = '01007BB017812000'   # shader_split loads a profile at import; other tests expect no default game
import shader_split as ss
if _had is None: del os.environ['DM_GAME']
else: os.environ['DM_GAME'] = _had

GLSLC_MAGIC = bytes.fromhex('91688619')


def glslc_output():
    """A synthetic whole-GLSLC output that glslc_shaders accepts (the same as test_unity_text_glslc's): the magic, the length at +0x44, one control section and a 0x100-byte code area, a vertex shader."""
    nctl, ncode, c = 0x850, 0x100, 0x100
    d = bytearray(c + nctl + ncode)
    d[:4] = GLSLC_MAGIC
    struct.pack_into('<I', d, 0x44, len(d))
    d[c:c + 4] = ss.CTL_MAGIC
    struct.pack_into('<I', d, c + 0x20, nctl)
    struct.pack_into('<I', d, c + 0x704, ncode)
    k = c + nctl
    d[k:k + 4] = ss.GFX_MAGIC
    struct.pack_into('<I', d, k + 0x30, 0x400)
    return bytes(d)


def igz(body, asl=True):   # an effect file: the IGZ magic, then the source name the game's effects name
    return ss.IGZ + b'\0' * 12 + (b'data/shared/shaders/Test.asl\0' if asl else b'textures/Test.png\0') + b'\0' * 16 + body


def chunk(raw, bad=False):   # u32 length, props 0x5d, dictionary 0x8000, the stream; bad: bytes of the stream replaced
    z = lzma.compress(raw, lzma.FORMAT_RAW, filters=[{'id': lzma.FILTER_LZMA1, 'dict_size': 0x8000, 'lc': 3, 'lp': 0, 'pb': 2}])
    if bad: z = z[:4] + b'\xff' * (len(z) - 4)
    return struct.pack('<I', len(z) + 5) + b'\x5d' + struct.pack('<I', 0x8000) + z


def archive(members, bad=(), stored=(), gap=()):
    """members: [bytes]; each is cut into 0x8000-byte chunks laid out one after the other at multiples of 0x800. Header: magic, version 0xd, a header length that is not used, the count, 0x800, a checksum,
    zeros up to +0x38, hashes, 16-byte records {offset, 0, length, tag}, a u16 table, then the data from 0x1000. stored: members kept as they are (tag 0xffffffff). gap: members whose chunks have a
    gap of 0x800 bytes between them, found only through the table run their tag names (starts in 0x800 units, bit 15 on a compressed chunk, an end entry after them)"""
    n = len(members)
    head = bytearray(0x1000)
    head[:4] = ss.IGA
    struct.pack_into('<4I', head, 4, 0xd, 0x10, n, 0x800)
    tab = 0x38 + 20 * n
    data, t = bytearray(), [0]   # the table starts with an entry no run uses, so that a run is not taken for the one before
    for i, m in enumerate(members):
        off, tag, first = 0x1000 + len(data), 0x20000000 | len(t), len(data)
        if i in stored: tag = 0xffffffff; data += m + bytes(-len(m) % 0x800)
        else:
            for c in range(0, len(m), 0x8000):
                t.append(0x8000 | (len(data) - first) // 0x800)
                b = chunk(m[c:c + 0x8000], bad=i in bad)
                data += b + bytes(-len(b) % 0x800) + (bytes(0x800) if i in gap else b'')
            t.append((len(data) - first) // 0x800)
        struct.pack_into('<4I', head, 0x38 + 4 * n + 16 * i, off, 0, len(m), tag)
    for q, x in enumerate(t): struct.pack_into('<H', head, tab + 2 * q, x)
    return bytes(head) + bytes(data)


class Iga(unittest.TestCase):
    def test_members(self):
        a = [igz(b'x' * 0x9000), b'\x01ZGI' + bytes(100)]
        got = dict(ss.iga_members(archive(a), 'p'))
        self.assertEqual(got, dict(enumerate(a)))   # a member of two chunks and one of one

    def test_shader_found_and_other_skipped(self):
        out = glslc_output()
        a = [igz(bytes(0x400) + out), igz(b'\0' * 64, asl=False) + out, ss.IGZ + bytes(40)]
        found = ss.iga_shaders(archive(a), '/a.pak')
        self.assertEqual([w for w, *_ in found], [f'/a.pak#0#GLSLC@{len(a[0]) - len(out):#x}'])   # the member with a source name only; the output of the other is not looked for

    def test_member_of_several_chunks(self):
        out = glslc_output()
        m = igz(bytes(0x9000) + out)
        found = ss.iga_shaders(archive([m]), 'p')
        self.assertEqual(len(found), 1)

    def test_corrupt_chunk_is_red(self):
        a = [igz(bytes(0x400) + glslc_output())]
        with self.assertRaises(SystemExit) as e: ss.iga_shaders(archive(a, bad={0}), 'p')
        self.assertIn('[RED] p#0:', str(e.exception))

    def test_stored_file(self):
        out = glslc_output()
        m = igz(bytes(0x100) + out)
        found = ss.iga_shaders(archive([m, b'\x01ZGI' + bytes(10)], stored={0}), 'p')
        self.assertEqual(len(found), 1)

    def test_gap_found_through_the_table(self):
        m = igz(bytes(0x9000) + glslc_output())
        self.assertEqual(dict(ss.iga_members(archive([m], gap={0}), 'p')), {0: m})   # the second chunk is not where the first one ended
        self.assertEqual(dict(ss.iga_members(archive([m]), 'p')), {0: m})

    def test_not_version(self):
        a = bytearray(archive([igz(b'')])); struct.pack_into('<I', a, 4, 7)
        with self.assertRaises(SystemExit): list(ss.iga_members(bytes(a), 'p'))


if __name__ == '__main__': unittest.main()
