"""ue_pc_paks.py on a synthetic texture: the Switch package gets the other build's top mip, swizzled, with every offset moved. No game files"""
import os, struct, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, '..'), os.path.join(HERE, '../../gfx/tools'), os.path.join(HERE, '../../games')]
import ue_pc_paks as U

UA_LEN = 200
EXPORT = 104   # the export entry's place in the fake summary

def fstr(t): b = t.encode() + b'\0'; return struct.pack('<i', len(b)) + b

def mip_entry(size, off, w, inline=None):
    fl = 0x48 if inline is not None else 0x501
    return struct.pack('<iIiiq', 1, fl, size, size, off) + (inline or b'') + struct.pack('<iii', w, w, 1)

def package(w, levels, first, bulk_levels, data, uasset_len=UA_LEN):
    """.uasset, .uexp, .ubulk of a texture: levels [(width, bytes)] from its stored top; bulk_levels of them streamed. A fake summary with the fields the tool reads"""
    head = b'\xAA' * 40
    def uexp(start):
        ex, bulk = bytearray(), bytearray()
        ex += head + struct.pack('<q', 0) + struct.pack('<iii', w, w, 1) + fstr('PF_DXT5') + struct.pack('<ii', first, len(levels))
        for i, (mw, d) in enumerate(levels):
            if i < bulk_levels: ex += mip_entry(len(d), len(bulk) - start, mw); bulk += d
            else: ex += mip_entry(len(d), len(ex) + 24 + uasset_len, mw, d)
        struct.pack_into('<q', ex, len(head), len(ex) + uasset_len)
        ex += b'\xBB' * 8 + b'\xC1\x83\x2A\x9E'
        return bytes(ex), bytes(bulk)
    ex, _ = uexp(0)
    start = uasset_len + len(ex) - 4
    ex, bulk = uexp(start)
    ua = bytearray(uasset_len)
    o = 20
    struct.pack_into('<i', ua, o, 0); o += 4                       # custom versions
    o += 4                                                         # TotalHeaderSize
    struct.pack_into('<i', ua, o, 0); o += 4                       # FolderName
    o += 4 + 8 + 8
    struct.pack_into('<iiiii', ua, o, 1, EXPORT, 0, 0, EXPORT + 80)   # exports: count, offset; imports; DependsOffset
    struct.pack_into('<q', ua, 88, start)                          # BulkDataStartOffset
    struct.pack_into('<qq', ua, EXPORT + 28, len(ex) - 4, uasset_len) # SerialSize, SerialOffset
    return bytes(ua), ex, bulk

def levels_pc(w):
    out, n = [], w
    while n >= 4:
        out.append((n, os.urandom((n // 4) ** 2 * 16))); n //= 2
    return out

class Rebuild(unittest.TestCase):
    def setUp(self):
        self.pc = levels_pc(512)                                  # 512 .. 4: 8 levels
        bpb, bw = U.FORMATS['PF_DXT5']
        lay = U.layout(512, 512, bpb, bw, len(self.pc), True)
        self.lay = lay
        self.sw = [(self.pc[i][0], U.swizzle(self.pc[i][1], lay[i]) if i < 3 else self.pc[i][1]) for i in range(1, len(self.pc))]
        self.sua, self.sue, self.sub = package(512, self.sw, 1, 2, b'')
        self.pua, self.pue, self.pub = package(512, self.pc, 0, 3, b'')

    def test_top_mip_added(self):
        pairs, why = U.missing_mips(self.sue, self.pue); self.assertIsNone(why)
        res, why = U.rebuild(self.sua, self.sue, self.sub, self.pue, self.pub, len(self.pua) + len(self.pue) - 4, pairs)
        self.assertIsNone(why)
        ua, ue, ub = res
        b = U.blobs(ue)[0]
        self.assertEqual((b['first'], b['num'], b['mips'][0]['w']), (0, 8, 512))
        start = len(ua) + len(ue) - 4
        self.assertEqual(ua.count(struct.pack('<q', start)), 1)
        self.assertEqual(struct.unpack_from('<qq', ua, EXPORT + 28), (len(ue) - 4, UA_LEN))
        self.assertEqual(struct.unpack_from('<q', ue, b['skip'])[0], b['end'] + UA_LEN)
        # the new top is the PC's top, swizzled; the old level keeps its bytes at its new offset
        top = b['mips'][0]; self.assertEqual(ub[top['off'] + start:top['off'] + start + top['disk']], U.swizzle(self.pc[0][1], self.lay[0]))
        m = b['mips'][1]; self.assertEqual(ub[m['off'] + start:m['off'] + start + m['disk']], self.sw[0][1])
        inl = b['mips'][3]; self.assertEqual(ue[inl['off'] - UA_LEN:inl['off'] - UA_LEN + inl['disk']], self.sw[2][1])

    def test_two_stripped_mips(self):
        bpb, bw = U.FORMATS['PF_DXT5']; lay = self.lay
        sw = [(self.pc[i][0], U.swizzle(self.pc[i][1], lay[i]) if i < 3 else self.pc[i][1]) for i in range(2, len(self.pc))]
        sua, sue, sub = package(512, sw, 2, 1, b'')
        pairs, why = U.missing_mips(sue, self.pue); self.assertIsNone(why)
        res, why = U.rebuild(sua, sue, sub, self.pue, self.pub, len(self.pua) + len(self.pue) - 4, pairs)
        self.assertIsNone(why)
        ua, ue, ub = res; b = U.blobs(ue)[0]; start = len(ua) + len(ue) - 4
        self.assertEqual((b['first'], b['num'], [m['w'] for m in b['mips'][:3]]), (0, 8, [512, 256, 128]))
        for i in range(2):
            m = b['mips'][i]; self.assertEqual(ub[m['off'] + start:m['off'] + start + m['disk']], U.swizzle(self.pc[i][1], lay[i]))

    def test_other_encode_refused(self):
        pairs, _ = U.missing_mips(self.sue, self.pue)
        other = bytearray(self.pub); other[len(self.pc[0][1])] ^= 1    # one byte of the PC's second level
        self.assertEqual(U.rebuild(self.sua, self.sue, self.sub, self.pue, bytes(other), len(self.pua) + len(self.pue) - 4, pairs), (None, 'level'))

    def test_complete_texture_not_taken(self):
        self.assertEqual(U.missing_mips(self.pue, self.pue), (None, 'same'))

    def test_layout_matches_the_checked_shapes(self):
        # checked on My Hero One's Justice 2's 4096 BC7 textures: 8 GOBs down to 64 block rows, 4 at 32
        lay = U.layout(4096, 4096, 16, 4, 6, True)
        self.assertEqual([l[3] for l in lay], [3, 3, 3, 3, 3, 2])
        self.assertEqual(lay[0][4], 16777216); self.assertEqual(lay[1][4], 4194304)

if __name__ == '__main__': unittest.main()
