"""ue_pc_zen4.py (the Unreal Engine 4.25 path of ue_pc_assets.py) on synthetic packages: a Switch container of TOC version 2 with zen packages, a PC folder with a legacy pak. No game files"""
import os, struct, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, '..'), os.path.join(HERE, '../../gfx/tools'), os.path.join(HERE, '../../games')]
import ue_pc_assets, ue_pc_zen4 as Z, ue_pc_paks as pk, uepak

COOKED = 300   # the legacy header's length (CookedHeaderSize): the first export starts there in both builds
MOUNT = '../../../'

def fstr(t): b = t.encode() + b'\0'; return struct.pack('<i', len(b)) + b

def mip(size, off, w, h, inline=None, flags=None):
    fl = flags if flags is not None else 0x48 if inline is not None else 0x10501
    return struct.pack('<iIiiq', 1, fl, size, size, off) + (inline or b'') + struct.pack('<iii', w, h, 1)

def texture(w, h, levels, first, bulk_levels, pf='PF_DXT5', lo=COOKED):
    """The export data of one texture (platform data as the game's cook writes it) and its bulk bytes: levels = [(w, h, bytes)] from the stored top; bulk_levels of them in the bulk chunk"""
    ex, bulk = bytearray(b'\xAA' * 40), bytearray()
    ex += struct.pack('<q', 0) + struct.pack('<iii', w, h, 1) + fstr(pf) + struct.pack('<ii', first, len(levels))
    for i, (mw, mh, d) in enumerate(levels):
        if i < bulk_levels: ex += mip(len(d), len(bulk), mw, mh); bulk += d
        else: ex += mip(len(d), len(ex) + 24 + lo, mw, mh, d)
    struct.pack_into('<q', ex, 40, len(ex) + lo + 4)   # SkipOffset: past the platform data and the 4-byte virtual flag
    ex += bytes(4) + b'\xBB' * 8
    return bytes(ex), bytes(bulk)

def zen(name, body, lo=COOKED):
    """A zen package chunk: summary (0x40 bytes), name map, hashes, no imports, one export, bundles, graph data"""
    names = [f'/Game/{name}', '/Script/Engine', name, 'Texture2D']
    nm = b''.join(struct.pack('>H', len(n)) + n.encode() for n in names); hs = bytes(8 * (len(names) + 1))
    no = 0x40; ho = (no + len(nm) + 7) & ~7; io = ho + len(hs); eo = io; bo = eo + 72; go = bo + 24
    h = bytearray(go + 4)
    struct.pack_into('<IIIIIIIIIIII', h, 0x10, 0x80000000, lo, no, len(nm), ho, len(hs), io, eo, bo, go, 4, 0)
    h[no:no + len(nm)] = nm; h[ho:ho + len(hs)] = hs
    struct.pack_into('<qqIIqqqqqII', h, eo, lo, len(body), 2, 0, -1, -1, -1, -1, -1, 0, 0)   # the object name is name 2 of the package's own map
    struct.pack_into('<IIIIII', h, bo, 0, 2, 0, 0, 0, 1)
    return bytes(h) + body

def legacy(name, body, lo=COOKED):
    """.uasset (a 4.25 cooked summary with the fields the tool reads: names, exports) and .uexp of a texture; the .uexp ends with the 4-byte package tag"""
    names = [f'/Game/{name}', name, 'Texture2D']; nt = b''.join(fstr(n) + bytes(4) for n in names)
    ua = bytearray(lo); o = 20
    struct.pack_into('<i', ua, o, 0); o += 4 + 4                       # custom versions, TotalHeaderSize
    struct.pack_into('<i', ua, o, 1); ua[o + 4] = 0; o += 4 + 1 + 4     # FolderName "", PackageFlags
    no = 120; eo = no + len(nt)
    struct.pack_into('<6i', ua, o, len(names), no, 0, 0, 1, eo)
    struct.pack_into('<3i', ua, o + 24, 0, 0, eo + 104)
    ua[no:no + len(nt)] = nt
    struct.pack_into('<iiiqq', ua, eo + 16, 1, 0, 0, len(body), lo)
    assert eo + 104 <= lo
    return bytes(ua), body + b'\xC1\x83\x2A\x9E'

def levels(w, h, n, seed, pf_bytes=16):
    out = []
    for i in range(n):
        lw, lh = max(w >> i, 1), max(h >> i, 1); k = max(1, (lw + 3) // 4) * max(1, (lh + 3) // 4) * pf_bytes
        out.append((lw, lh, bytes((seed * 7 + i * 13 + j) & 255 for j in range(k))))
    return out

def build_switch(root, pkgs):
    """pkgs = [(path, chunk, bulk or None)] → the container pakchunk0-Switch (TOC version 2, Zlib blocks)"""
    import zlib
    z = lambda b: [(zlib.compress(b[o:o + 65536]), len(b[o:o + 65536]), 'Zlib') for o in range(0, len(b), 65536)]
    chunks, paths, entries = [], {}, []
    for k, (path, ch, bulk) in enumerate(pkgs):
        pid = uepak.city64(('/Game/' + path.split('Content/')[1]).lower().encode('utf-16-le')); c = uepak.io_chunk_id(pid, 0, 2)
        chunks.append(dict(id=c, size=len(ch), blocks=z(ch), meta=None)); paths[c] = MOUNT + path + '.uasset'
        entries.append((pid, len(ch), 1, 1, 100 + k, (pid + 1,) if k == 0 else ()))
        if bulk:
            b = uepak.io_chunk_id(pid, 0, 3); chunks.append(dict(id=b, size=len(bulk), blocks=z(bulk), meta=None)); paths[b] = MOUNT + path + '.ubulk'
    cid = uepak.io_container_id('pakchunk0-Switch'); d = uepak.container_header2(cid, entries)
    chunks.insert(0, dict(id=uepak.io_chunk_id(cid, 0, 10), size=len(d), blocks=z(d), meta=None))
    d_ = os.path.join(root, 'APK/Content/Paks'); os.makedirs(d_)
    uepak.write_toc2(os.path.join(d_, 'pakchunk0-Switch'), 'pakchunk0-Switch', chunks, paths)
    uepak.write_toc2(os.path.join(d_, 'global'), 'global', [dict(id=uepak.io_chunk_id(0, 0, 7), size=4, blocks=uepak.stored_blocks(b'abcd'), meta=None)])
    return entries

def build_pc(root, files):
    os.makedirs(root)
    with uepak.LegacyPakWriter(os.path.join(root, 'pakchunk0-WindowsNoEditor.pak'), MOUNT, 9) as w:
        for n, b in files.items(): w.add(n, b)

class Zen4(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); self.root = tmp.name
        self.sw_root, self.pc_root, self.out = (os.path.join(self.root, n) for n in ('sw', 'pc', 'out'))
        os.makedirs(self.sw_root); os.makedirs(self.out)
        sw, files = [], {}
        def add(name, sw_tex, pc_tex, pf='PF_DXT5'):
            """a texture on both builds: sw_tex, pc_tex = (export data, bulk bytes) or None for a package the build lacks"""
            path = f'APK/Content/Art/Textures/{name}'
            if sw_tex: sw.append((path, zen(name, sw_tex[0]), sw_tex[1] or None))
            if pc_tex:
                ua, ue = legacy(name, pc_tex[0]); files[path + '.uasset'] = ua; files[path + '.uexp'] = ue
                if pc_tex[1]: files[path + '.ubulk'] = pc_tex[1]
        full = levels(256, 128, 8, 1); self.full = full
        self.sa = texture(256, 128, full[1:], 1, 1)                       # the Switch: the top level stripped, its first stored level in the bulk chunk
        add('T_Add', self.sa, texture(256, 128, full, 0, 2))              # every Switch level is the PC level of its size: the top one is added
        # the same with the Switch's levels block-linear (the PC's linear)
        pcs = levels(128, 128, 5, 5); lay = pk.layout(128, 128, 16, 4, 5, True); self.pcs, self.lay = pcs, lay
        add('T_Swizzled', texture(128, 128, [(w, h, pk.swizzle(d, lay[i])) for i, (w, h, d) in enumerate(pcs) if i], 1, 1), texture(128, 128, pcs, 0, 2))
        # the first stored level is the PC's, a later one another encode of the same image: the PC's whole chain
        re = levels(256, 128, 8, 1); re[4] = (re[4][0], re[4][1], bytes(len(re[4][2])))
        add('T_Chain', texture(256, 128, [full[1]] + re[2:], 1, 1), texture(256, 128, full, 0, 2))
        add('T_Same', texture(64, 64, levels(64, 64, 5, 2), 0, 0), texture(64, 64, levels(64, 64, 5, 2), 0, 0))
        other = levels(64, 64, 6, 3)
        add('T_Other', texture(64, 64, other[1:], 1, 0), texture(64, 64, [(w, h, bytes(len(d))) for w, h, d in other], 0, 0))   # not even the first level agrees: the Switch's stays
        add('T_Fmt', texture(64, 64, other[1:], 1, 0), texture(64, 64, other, 0, 0, pf='PF_BC7'))
        add('T_Missing', texture(64, 64, other[1:], 1, 0), None)
        sw.append(('APK/Content/Maps/NoTexture', zen('NoTexture', b'\x01' * 200), None))
        files['APK/Content/Maps/NoTexture.uasset'], files['APK/Content/Maps/NoTexture.uexp'] = legacy('NoTexture', b'\x01' * 200)
        self.entries = build_switch(self.sw_root, sw)
        build_pc(self.pc_root, files)
        self.rules = [('max', 'textures', '*')]
        os.environ['J'] = '1'; self.addCleanup(os.environ.pop, 'J', None)

    def package_of(self, t, name):
        pid = uepak.city64(('/Game/Art/Textures/' + name).lower().encode('utf-16-le'))
        i2 = t.index[uepak.io_chunk_id(pid, 0, 2)]; i3 = t.index.get(uepak.io_chunk_id(pid, 0, 3))
        chunk = t.read(i2); lo, hsz, eo, bo = Z.summary(chunk); body = chunk[hsz:]
        return chunk, body, t.read(i3) if i3 is not None else b'', pid

    def run_build(self, rules=None):
        return Z.build(rules or self.rules, self.sw_root, self.pc_root, self.out)

    def container(self):
        return uepak.Toc(os.path.join(self.out, 'max/APK/Content/Paks/pakchunk0-Switch_99_P.utoc'))

    def test_taken_and_skipped(self):
        rep = self.run_build()
        self.assertEqual(len(rep), 1)
        self.assertIn('3 package(s) (textures; full chain 1)', rep[0])
        for k, n in (('missing', 1), ('same', 1), ('format', 1), ('level', 1), ('notex', 1)): self.assertIn(f'{k} {n}', rep[0])
        t = self.container()
        self.assertEqual((t.version, t.methods), (2, ['Zlib']))
        self.assertTrue(os.path.exists(os.path.join(self.out, 'max/APK/Content/Paks/pakchunk0-Switch_99_P.pak')))
        h = [i for i, c in enumerate(t.ids) if c[11] == 10]; head = uepak.read_container_header2(t.read(h[0]))
        self.assertEqual(sorted(e[0] for e in head['entries']), sorted(self.package_of(t, n)[3] for n in ('T_Add', 'T_Swizzled', 'T_Chain')))
        self.assertEqual(head['cid'], uepak.io_container_id('pakchunk0-Switch_99_P'))
        for pid, size, nex, nbun, order, imps in head['entries']:   # the Switch's own export counts, load order and imports, the new chunk length
            self.assertEqual((nex, nbun), (1, 1))
            self.assertEqual(size, t.ranges[t.index[uepak.io_chunk_id(pid, 0, 2)]][1])
            self.assertEqual(imps, (pid + 1,) if order == 100 else ())

    def test_levels_added(self):
        self.run_build(); t = self.container()
        chunk, body, bulk, _ = self.package_of(t, 'T_Add'); lo, hsz, eo, bo = Z.summary(chunk)
        b = pk.blobs(body); self.assertEqual(len(b), 1); b = b[0]
        self.assertEqual((b['first'], b['num'], b['w'], b['h']), (0, 8, 256, 128))
        self.assertEqual([pk.level_data(m, body, bulk, 0) for m in b['mips']], [d for _, _, d in self.full])
        self.assertEqual(b['mips'][0]['flags'], Z.BULK_FLAGS)
        self.assertEqual(b['mips'][0]['off'], len(self.sa[1]))   # appended after the Switch's bulk level, which stays where it was
        self.assertEqual(bulk[:len(self.sa[1])], self.sa[1])
        self.assertEqual(struct.unpack_from('<q', body, b['skip'])[0], b['end'] + lo + 4)   # SkipOffset still ends the platform data
        self.assertEqual(struct.unpack_from('<qq', chunk, eo), (lo, len(body)))
        for m in b['mips']:
            if m['data'] is not None: self.assertEqual(m['off'], m['data'] + COOKED)   # an inline mip's offset is its place in the package

    def test_swizzled_levels_added(self):
        self.run_build(); t = self.container()
        chunk, body, bulk, _ = self.package_of(t, 'T_Swizzled'); b = pk.blobs(body)[0]
        self.assertEqual((b['first'], b['num']), (0, 5))
        self.assertEqual([pk.level_data(m, body, bulk, 0) for m in b['mips']], [pk.swizzle(d, self.lay[i]) for i, (_, _, d) in enumerate(self.pcs)])

    def test_full_chain_when_a_later_level_differs(self):
        self.run_build(); t = self.container()
        chunk, body, bulk, _ = self.package_of(t, 'T_Chain'); b = pk.blobs(body)[0]
        self.assertEqual((b['first'], b['num'], b['w'], b['h']), (0, 8, 256, 128))
        self.assertEqual([pk.level_data(m, body, bulk, 0) for m in b['mips']], [d for _, _, d in self.full])   # no level of the Switch's re-encode is left
        rows = open(os.path.join(os.path.dirname(self.out), 'ue_pc_assets_max.tsv')).read().splitlines()
        self.assertEqual(sorted(r.split('\t')[1] for r in rows), ['full chain', 'textures', 'textures'])

    def test_report_and_only_textures_rows(self):
        self.run_build()
        tsv = open(os.path.join(os.path.dirname(self.out), 'ue_pc_assets_max.tsv')).read().splitlines()
        self.assertEqual(len(tsv), 3)
        add = [r.split('\t') for r in tsv if r.startswith('APK/Content/Art/Textures/T_Add')][0]
        self.assertEqual(add[:5], ['APK/Content/Art/Textures/T_Add', 'textures', '128x64', '256x128', '2'])
        with self.assertRaises(Z.Error): self.run_build([('max', 'package', '*')])
        with self.assertRaises(Z.Error): self.run_build([('max', 'textures', 'Nothing/*')])

    def test_dispatch_from_ue_pc_assets(self):
        import game
        self.assertTrue(game.load('0100309016E7A000').table('ue_pc_assets.tsv').is_file())
        self.assertTrue(any(t.version < 4 for t in uepak.io_tocs(self.sw_root)))
        rep = ue_pc_assets.build('0100309016E7A000', self.sw_root, self.pc_root, self.out, None, None)
        self.assertIn('3 package(s) (textures; full chain 1)', rep[0])


class Names(unittest.TestCase):
    def test_exports_by_name(self):
        body, _ = texture(64, 64, levels(64, 64, 4, 1), 0, 0)
        z = zen('T_X', body); ua, ue = legacy('T_X', body)
        self.assertEqual(Z.zen_exports(z), [(0, len(body), ('T_X', 0))])
        self.assertEqual(Z.legacy_exports(ua), [(COOKED - len(ua), len(body), ('T_X', 0))][:0] or [(0, len(body), ('T_X', 0))])
        self.assertEqual(Z.owner(Z.zen_exports(z), 100), ('T_X', 0))
        self.assertIsNone(Z.owner(Z.zen_exports(z), len(body)))

    def test_shift(self):
        a, b = dict(w=64, h=64), dict(w=256, h=256)
        self.assertEqual(Z.shift(a, a), 0)
        self.assertEqual(Z.shift(a, b), 2)
        self.assertIsNone(Z.shift(a, dict(w=192, h=192)))
        self.assertIsNone(Z.shift(a, dict(w=256, h=128)))


if __name__ == '__main__': unittest.main()
