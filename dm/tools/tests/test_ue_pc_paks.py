"""ue_pc_paks.py on a synthetic texture: the Switch package gets the other build's top mip, swizzled, with every offset moved. No game files"""
import os, struct, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, '..'), os.path.join(HERE, '../../gfx/tools'), os.path.join(HERE, '../../games')]
import ue_pc_paks as U

UA_LEN = 200
NAMES = 150    # the fake name table's place, after the summary
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
    struct.pack_into('<i', ua, 40, NAMES)                          # NameOffset: the summary ends there
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
        self.sw = [(self.pc[i][0], U.swizzle(self.pc[i][1], lay[i])) for i in range(1, len(self.pc))]
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
        sw = [(self.pc[i][0], U.swizzle(self.pc[i][1], lay[i])) for i in range(2, len(self.pc))]
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

    def rb(self, sua, sue, sub):
        pairs, why = U.missing_mips(sue, self.pue); self.assertIsNone(why)
        return pairs, U.rebuild(sua, sue, sub, self.pue, self.pub, len(self.pua) + len(self.pue) - 4, pairs)

    def test_size_differs_top_added(self):
        sw = [(self.pc[i][0], U.swizzle(self.pc[i][1], self.lay[i])) for i in range(2, 8)]
        sua, sue, sub = package(128, sw, 0, 2, b'')
        _, (res, why) = self.rb(sua, sue, sub); self.assertIsNone(why)
        ua, ue, ub = res; b = U.blobs(ue)[0]; start = len(ua) + len(ue) - 4
        self.assertEqual((b['w'], b['h'], b['first'], b['num'], b['mips'][0]['w']), (512, 512, 0, 8, 512))
        for i, m in enumerate(b['mips']):
            d = ub[m['off'] + start:m['off'] + start + m['disk']] if m['data'] is None else ue[m['data']:m['data'] + m['disk']]
            self.assertEqual(d, sw[i - 2][1] if i >= 2 else U.swizzle(self.pc[i][1], self.lay[i]))
        self.assertEqual(struct.unpack_from('<q', ue, b['skip'])[0], b['end'] + UA_LEN)

    def test_tail_added(self):
        sw = [(self.pc[i][0], U.swizzle(self.pc[i][1], self.lay[i])) for i in range(4)]
        sua, sue, sub = package(512, sw, 0, 2, b'')
        pairs, (res, why) = self.rb(sua, sue, sub); self.assertIsNone(why)
        ua, ue, ub = res; b = U.blobs(ue)[0]; start = len(ua) + len(ue) - 4
        self.assertEqual((b['first'], b['num'], len(b['mips'])), (0, 8, 8))
        self.assertEqual(len(ue), len(sue) + sum(36 + (self.lay[k][4] if m['data'] is not None else 0) for k, m in enumerate(pairs[0][1]['mips']) if k >= 4))
        for i, m in enumerate(b['mips']):
            d = ub[m['off'] + start:m['off'] + start + m['disk']] if m['data'] is None else ue[m['data']:m['data'] + m['disk']]
            self.assertEqual(d, sw[i][1] if i < 4 else U.swizzle(self.pc[i][1], self.lay[i]))
            if m['data'] is not None: self.assertEqual(m['off'], m['at'] + 24 + UA_LEN)
        self.assertEqual(struct.unpack_from('<qq', ua, EXPORT + 28), (len(ue) - 4, UA_LEN))

    def test_chain_mismatch_refused(self):
        sw = [(300, os.urandom(1000)), (150, os.urandom(100))]      # a top width the PC does not have
        self.assertEqual(U.missing_mips(*package(300, sw, 0, 1, b'')[1:2], self.pue), (None, 'format'))
        sw = [(self.pc[2][0], self.pc[2][1]), (self.pc[4][0], self.pc[4][1])]   # the second level is off the chain
        self.assertEqual(U.missing_mips(package(128, sw, 0, 1, b'')[1], self.pue), (None, 'format'))

    def test_every_level_checked(self):
        # the first stored level is the PC's, a later inline one is not: nothing of the Switch's is kept, the PC's whole chain is taken
        sw = [(self.pc[i][0], U.swizzle(self.pc[i][1], self.lay[i])) for i in range(2, 8)]
        bad = bytearray(sw[4][1]); bad[3] ^= 1; sw[4] = (sw[4][0], bytes(bad))
        sua, sue, sub = package(128, sw, 0, 2, b'')
        pairs, why = U.missing_mips(sue, self.pue); self.assertIsNone(why)
        full = []
        res, why = U.rebuild(sua, sue, sub, self.pue, self.pub, len(self.pua) + len(self.pue) - 4, pairs, full)
        self.assertIsNone(why); self.assertEqual(full, [0])
        ua, ue, ub = res; b = U.blobs(ue)[0]; start = len(ua) + len(ue) - 4
        self.assertEqual((b['w'], b['h'], b['first'], b['num'], len(b['mips'])), (512, 512, 0, 8, 8))
        for i, m in enumerate(b['mips']):
            self.assertEqual(m['w'], self.pc[i][0])
            d = ub[m['off'] + start:m['off'] + start + m['disk']] if m['data'] is None else ue[m['data']:m['data'] + m['disk']]
            self.assertEqual(d, U.swizzle(self.pc[i][1], self.lay[i]))
            if m['data'] is not None: self.assertEqual(m['off'], m['at'] + 24 + UA_LEN)
        self.assertEqual(struct.unpack_from('<qq', ua, EXPORT + 28), (len(ue) - 4, UA_LEN))
        self.assertEqual(struct.unpack_from('<q', ue, b['skip'])[0], b['end'] + UA_LEN)
        self.assertEqual(ua.count(struct.pack('<q', start)), 1)
        self.assertEqual(U.missing_mips(ue, self.pue), (None, 'same'))

    def test_first_level_differs_stays(self):
        sw = [(self.pc[i][0], U.swizzle(self.pc[i][1], self.lay[i])) for i in range(2, 8)]
        bad = bytearray(sw[0][1]); bad[3] ^= 1; sw[0] = (sw[0][0], bytes(bad))   # the first stored level (a streamed one)
        sua, sue, sub = package(128, sw, 0, 2, b'')
        _, res = self.rb(sua, sue, sub); self.assertEqual(res, (None, 'level'))

    def test_bulk_start_offset_collision(self):
        start = len(self.sua) + len(self.sue) - 4
        sua = bytearray(self.sua); sua[NAMES + 10:NAMES + 18] = struct.pack('<q', start)   # the same 8 bytes in the name table
        _, (res, why) = self.rb(bytes(sua), self.sue, self.sub); self.assertIsNone(why)
        ua, ue, ub = res; s1 = len(ua) + len(ue) - 4
        self.assertEqual(struct.unpack_from('<q', ua, 88)[0], s1)
        self.assertEqual(ua[NAMES + 10:NAMES + 18], struct.pack('<q', start))
        sua[100:108] = struct.pack('<q', start)    # twice in the summary: not taken
        self.assertEqual(self.rb(bytes(sua), self.sue, self.sub)[1], (None, 'format'))

    def test_idempotent(self):
        _, (res, why) = self.rb(self.sua, self.sue, self.sub); self.assertIsNone(why)
        self.assertEqual(U.missing_mips(res[1], self.pue), (None, 'same'))

    def test_complete_texture_not_taken(self):
        self.assertEqual(U.missing_mips(self.pue, self.pue), (None, 'same'))

    def test_layout_matches_the_checked_shapes(self):
        # checked on My Hero One's Justice 2's 4096 BC7 textures: 8 GOBs down to 64 block rows, 4 at 32
        lay = U.layout(4096, 4096, 16, 4, 6, True)
        self.assertEqual([l[3] for l in lay], [3, 3, 3, 3, 3, 2])
        self.assertEqual(lay[0][4], 16777216); self.assertEqual(lay[1][4], 4194304)

if __name__ == '__main__': unittest.main()
