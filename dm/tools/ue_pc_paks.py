#!/usr/bin/env python3
# Another platform's top texture mips for a game whose assets live in a legacy pak (no IoStore; UE 4.21 and the like): ue_pc_paks.py <game id> <RomFS root of the extracted game> <other platform's Paks dir> <out dir>
# ue_pc_assets.py hands its packages to a game that shares the other platform's IoStore layout. A pak game cannot take them: these Switch cooks store every streamed mip block-linear, the PC's are linear, and the packages
# differ. What can be shared is the texel data: checked on My Hero One's Justice 2 and DRAGON BALL Z: KAKAROT, each Switch level is the PC level of the same size, swizzled, byte for byte. So this tool keeps the Switch package and
# gives each texture the PC's whole chain: the levels the cook stripped on top (FirstMip 1 there, 0 on the PC; or a texture stored smaller, e.g. 512 against the PC's 2048) and the levels it never stored at the tail (one mip, no chain),
# all the PC's levels swizzled into the Switch's layout, with the PC's size, first mip and level count, the mip entries in the .uexp, the bulk offsets, SkipOffset, the export's SerialSize and the package's BulkDataStartOffset.
# A texture is extended only when every level the Switch stores, swizzled by the same rule, equals the Switch's own (so a wrong rule cannot reach the game), when those levels are consecutive levels of the PC's chain of the same
# sizes, when its pixel format is the same and it is a single 2D surface. When the first stored level equals the PC's but a later one does not (the same image encoded again), the PC's whole chain replaces the Switch's (every
# PC level, swizzled, with the PC's size, first mip and level count), so no texture mixes the builds' levels; it is counted apart in the report (`full chain`), as ue_pc_zen4.py does. When the first stored level differs, the
# Switch's texture stays (`level`). Every rebuilt texture is read back and each level compared with the swizzled PC level.
# Rows of the profile's ue_pc_assets.tsv: preset <TAB> textures <TAB> pattern (fnmatch on the package path without the extension, case-insensitive). The result joins ue_quality.py's pak, <out dir>/<preset>/<dir>/<stem>_99_P.pak,
# and is Zlib-compressed in 64 KB blocks. Materials, maps and meshes are not taken: materials hold D3D shaders. The PC pak's key is found in the PC build's executable (never printed or written).
import fnmatch, multiprocessing, os, re, shutil, struct, subprocess, sys, tempfile, zlib, ctypes
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '../gfx/tools')); sys.path.insert(0, os.path.join(HERE, '../games'))
import uepak

class Error(Exception): pass

# bytes per block, block width and height; other formats are not taken
FORMATS = {'PF_DXT1': (8, 4), 'PF_BC4': (8, 4), 'PF_DXT3': (16, 4), 'PF_DXT5': (16, 4), 'PF_BC5': (16, 4), 'PF_BC6H': (16, 4), 'PF_BC7': (16, 4), 'PF_B8G8R8A8': (4, 1), 'PF_R8G8B8A8': (4, 1), 'PF_G8': (1, 1), 'PF_G16': (2, 1), 'PF_FloatRGBA': (8, 1)}
TILE_H = {1: 5, 2: 4, 4: 4, 8: 3, 16: 3}   # block height (log2 GOBs) of a 64 KB tile by bytes per block (nvn_tex.c sparse_tile_h)
PF = re.compile(rb'(?<=[\x04-\x20]\x00\x00\x00)PF_[A-Za-z0-9_]+\x00')
BULK_END, BULK_FILE = 0x1, 0x100
BLOCK = 65536
SKIPS = ('missing', 'same', 'format', 'level', 'size')

_bl = None
def bl_lib(work=None):
    global _bl
    if _bl is None:
        d = work or tempfile.mkdtemp(prefix='ue_pc_paks'); so = os.path.join(d, 'block_linear.dylib')
        if not os.path.exists(so): subprocess.run(['cc', '-O2', '-shared', '-o', so, os.path.join(HERE, 'block_linear.c')], check=True)
        _bl = ctypes.CDLL(so)
    return _bl

def adj_tile(shift, dim):   # nvn_tex.c adj_tile, unit 8: the block height shrinks with the level's block rows
    if not shift: return 0
    x = 8 << (shift - 1)
    if x >= dim:
        while True:
            shift -= 1
            if not shift: break
            x >>= 1
            if x < dim: break
    return shift

def auto_tile(rows):   # nvn_tex.c: the automatic block height of a level 0 of that many block rows
    g = rows * 3 // 2 // 8
    return 4 if g >= 16 else 3 if g >= 8 else 2 if g >= 4 else 1 if g >= 2 else 0

def layout(w, h, bpb, bw, levels, sparse):
    """[(row bytes, block rows, GOB columns, log2 block height, size)] of the levels of a texture w x h, sparse (64 KB tiles) or not (nvn_tex.c level_walk, nvn_tex_layout)"""
    h0 = max((h + bw - 1) // bw, 1)
    tile = TILE_H[bpb] if sparse else auto_tile(h0)
    tw = 128 >> tile if sparse else 1
    tiled, out = sparse, []
    for i in range(levels):
        lw, lh = max(max(w >> i, 1) + bw - 1, 0) // bw, max(max(h >> i, 1) + bw - 1, 0) // bw
        row = lw * bpb; th = adj_tile(tile, lh); wg, hg = (row + 63) // 64, (lh + 7) // 8
        tiled = tiled and row >= tw * 64 and lh >= 8 << tile
        if tiled: wg = (wg + tw - 1) // tw * tw
        ht = (hg + (1 << th) - 1) >> th
        out.append((row, lh, wg, th, wg * ht << (9 + th)))
    return out

def swizzle(src, lev):
    row, rows, wg, th, size = lev
    if len(src) < row * rows: raise ValueError('short level')
    dst = ctypes.create_string_buffer(size)
    bl_lib().bl_swizzle(src, dst, row, rows, wg, th)
    return dst.raw

def blobs(b):
    """The cooked platform data of each texture in a .uexp: [{pf, skip (position of SkipOffset), w, h, packed, first (position of FirstMip), mips}], mips: {at, flags, n, disk, off, w, h, d, data, end}"""
    out = []
    for m in PF.finditer(b):
        i = m.start(); o = m.end()
        if i < 32: continue
        skip = i - 24; w, h, packed = struct.unpack_from('<iii', b, skip + 8)
        first, num = struct.unpack_from('<ii', b, o); fo = o; o += 8
        if not (0 <= first < num <= 16) or not (0 < w <= 16384 and 0 < h <= 16384): continue
        mips = []
        try:
            for k in range(num):
                at = o; cooked, fl, n, disk, off = struct.unpack_from('<iIiiq', b, o); o += 24
                data = None
                if not fl & BULK_FILE and not fl & BULK_END: data = o; o += disk
                mw, mh, md = struct.unpack_from('<iii', b, o); o += 12
                if cooked != 1 or disk < 0 or mw <= 0 or mh <= 0: raise ValueError
                mips.append(dict(at=at, flags=fl, n=n, disk=disk, off=off, w=mw, h=mh, d=md, data=data, end=o))
        except (struct.error, ValueError): continue
        if struct.unpack_from('<q', b, skip)[0] == 0: continue
        out.append(dict(pf=m.group()[:-1].decode(), skip=skip, w=w, h=h, packed=packed, fo=fo, first=first, num=num, mips=mips, end=o))
    return out

def exports(ua):
    """(the offset of the export table, its entry size, entry count) of a cooked .uasset (UE 4.21: no custom versions in a cooked summary, or skipped by their count)"""
    o = 20; ncv = struct.unpack_from('<i', ua, o)[0]; o += 4 + 20 * max(ncv, 0)
    o += 4                                   # TotalHeaderSize
    fl = struct.unpack_from('<i', ua, o)[0]; o += 4 + fl    # FolderName
    o += 4 + 8 + 8                           # PackageFlags, names, gatherable text
    n, eo, _, _, dep = struct.unpack_from('<iiiii', ua, o)
    if n <= 0 or (dep - eo) % n or dep <= eo: raise ValueError('no export table')
    return eo, (dep - eo) // n, n

def name_offset(ua):   # the summary's NameOffset, where the name table and so the end of the summary is (see exports for the walk)
    o = 20; ncv = struct.unpack_from('<i', ua, o)[0]; o += 4 + 20 * max(ncv, 0)
    o += 4
    fl = struct.unpack_from('<i', ua, o)[0]; o += 4 + fl
    return struct.unpack_from('<i', ua, o + 8)[0]   # after PackageFlags and NameCount

def chain(x, y):
    """(j, n) of a Switch texture x inside the other build's y: n stored levels, the first of them is y's level j and each following one y's next (same size); or None. The levels y has before j are added on top, those after j + n at the tail"""
    n = len(x['mips'])
    sz = [(m['w'], m['h']) for m in y['mips']]
    if not n or (x['mips'][0]['w'], x['mips'][0]['h']) not in sz: return None
    j = sz.index((x['mips'][0]['w'], x['mips'][0]['h']))
    if j + n > len(sz) or any(sz[j + i] != (m['w'], m['h']) for i, m in enumerate(x['mips'])): return None
    return j, n

def missing_mips(ue, pue):
    """[(Switch texture, other build's)] of the .uexp pairs whose textures lack levels of the other's chain (on top, as the cook stripped them or stored a smaller texture, or at the tail, no chain), and None; or None and the reason a package is not taken.
    The Switch's stored levels must be levels of the other's chain, the first one wherever it falls, each next one the next level of the same size"""
    a, p = blobs(ue), blobs(pue)
    if not a or len(a) != len(p): return None, 'format'
    out = []
    for x, y in zip(a, p):
        if x['pf'] != y['pf'] or x['pf'] not in FORMATS or x['packed'] & 0xffff != 1 or y['packed'] & 0xffff != 1 : return None, 'format'
        c = chain(x, y)
        if not c: return None, 'format'
        j, n = c
        if j == 0 and j + n == len(y['mips']) and (x['w'], x['h'], x['first']) == (y['w'], y['h'], y['first']): continue   # complete on both
        out.append((x, y))
    return (out, None) if out else (None, 'same')

def level_data(mip, uexp, ubulk, start):   # a mip's bytes: inline in the .uexp, or at its bulk offset plus the package's BulkDataStartOffset in the .ubulk
    if mip['data'] is not None: return uexp[mip['data']:mip['data'] + mip['disk']]
    d = ubulk[mip['off'] + start:mip['off'] + start + mip['disk']]
    return d if len(d) == mip['disk'] else None

def rebuild(ua, ue, ub, pue, pub, pstart, pairs, full=None):
    """The package's files with the pairs' missing levels added: ((uasset, uexp, ubulk), None), or (None, reason). A texture takes the other's size, first mip and level count; its stored levels stay as they are between the levels
    added on top and at the tail, all swizzled from the other's. A mip's bulk offset is its place in the .ubulk minus BulkDataStartOffset, which is where the package's data ends before its 4-byte tag; SkipOffset and an inline
    mip's offset are positions in the package (.uasset + .uexp), so everything after an added mip moves. A texture whose first stored level is the other's but a later one is not (another encode of the same image) takes the
    other's whole chain instead, none of its own levels; its index in the .uexp is appended to full when given. The result is read back and compared with the other's chain before it is returned"""
    lo, s0 = len(ua), len(ua) + len(ue) - 4
    top_of = {x['skip']: y for x, y in pairs}
    bs = blobs(ue); plan = {}   # plan: the texture's index -> (the other's texture, j, n, the bytes of each level of the other's chain)
    added = 0; isfull = set()
    for xi, x in enumerate(bs):
        y = top_of.get(x['skip'])
        if not y: continue
        j, n = chain(x, y); ny = len(y['mips']); bpb, bw = FORMATS[x['pf']]
        have = [level_data(m, ue, ub, s0) for m in x['mips']]; other = [level_data(m, pue, pub, pstart) for m in y['mips']]
        if None in have or None in other: return None, 'size'
        whole = None   # the layout of the first rule that makes the first stored level the other's while a later one differs
        for sparse in (True, False):   # one rule for the texture: the first that holds for every stored level
            lay = layout(y['w'], y['h'], bpb, bw, y['first'] + ny, sparse)
            try:
                f = lambda i, h: len(h) == lay[y['first'] + j + i][4] and swizzle(other[j + i], lay[y['first'] + j + i]) == h
                if all(f(i, h) for i, h in enumerate(have)): whole = None; break
                if whole is None and f(0, have[0]): whole = lay
            except ValueError: pass
        else:
            if whole is None: return None, 'level'
            try: lv = [swizzle(other[k], whole[y['first'] + k]) for k in range(ny)]
            except ValueError: return None, 'level'
            plan[xi] = (y, 0, 0, lv); isfull.add(xi)
            # the other's entries replace all of the texture's own
            added += sum(36 + (len(lv[k]) if y['mips'][k]['data'] is not None else 0) for k in range(ny)) - sum(m['end'] - m['at'] for m in x['mips'])
            continue
        lv = [have[k - j] if j <= k < j + n else swizzle(other[k], lay[y['first'] + k]) for k in range(ny)]
        plan[xi] = (y, j, n, lv)
        # an inline level's entry holds its data: the layout's size, whatever the other build's linear level took
        added += sum(36 + (len(lv[k]) if y['mips'][k]['data'] is not None else 0) for k in range(ny) if not j <= k < j + n)
    s1 = s0 + added
    ex, bulk, pos, marks = bytearray(), bytearray(), 0, []   # marks: (old .uexp position, how far what follows moved)
    def pc_entry(top, dat):   # a level of the other build's chain: its entry, in the .uexp (inline) or the .ubulk
        tail = struct.pack('<iii', top['w'], top['h'], top['d'])
        if top['data'] is not None:
            ex.extend(struct.pack('<iIiiq', 1, top['flags'], len(dat), len(dat), len(ex) + 24 + lo) + dat + tail)
        elif top['flags'] & BULK_FILE:
            ex.extend(struct.pack('<iIiiq', 1, top['flags'], len(dat), len(dat), len(bulk) - s1) + tail); bulk.extend(dat)
        else: return 'format'
    for xi, x in enumerate(bs):
        y, j, n, lv = plan.get(xi, (None,) * 4)
        ex += ue[pos:x['fo']]; skip_at = len(ex) - (x['fo'] - x['skip'])
        if y:
            ny = len(y['mips'])
            ex += struct.pack('<ii', y['first'], ny)
            struct.pack_into('<ii', ex, skip_at + 8, y['w'], y['h'])
            for k in range(j):
                if pc_entry(y['mips'][k], lv[k]): return None, 'format'
        else: ex += struct.pack('<ii', x['first'], x['num'])
        for m in ([] if xi in isfull else x['mips']):
            tail = ue[m['end'] - 12:m['end']]
            if m['data'] is not None:
                ex += struct.pack('<iIiiq', 1, m['flags'], m['n'], m['disk'], len(ex) + 24 + lo) + ue[m['data']:m['data'] + m['disk']] + tail
            elif m['flags'] & BULK_FILE:
                d = level_data(m, ue, ub, s0)
                if d is None: return None, 'size'
                ex += struct.pack('<iIiiq', 1, m['flags'], m['n'], m['disk'], len(bulk) - s1) + tail; bulk += d
            else: return None, 'format'   # a payload at the end of the .uexp is not rebuilt
        if y:
            for k in range(j + n, ny):
                if pc_entry(y['mips'][k], lv[k]): return None, 'format'
        pos = x['end']
        struct.pack_into('<q', ex, skip_at, len(ex) + lo)
        marks.append((x['end'], len(ex) - x['end']))
    ex += ue[pos:]
    if len(ex) != len(ue) + added: return None, 'size'
    nu = bytearray(ua)
    try: no = name_offset(ua)
    except struct.error: return None, 'format'
    if not 0 < no <= len(ua): return None, 'format'
    at = ua.find(struct.pack('<q', s0), 0, no)   # the summary holds the value once: the name table and what follows may hold the same 8 bytes
    if at < 0 or ua.find(struct.pack('<q', s0), at + 1, no) >= 0: return None, 'format'
    struct.pack_into('<q', nu, at, s1)
    eo, esz, n = exports(ua)
    def moved(at): return next((d for e, d in reversed(marks) if e <= at), 0)
    for i in range(n):
        o = eo + i * esz; size, off = struct.unpack_from('<qq', ua, o + 28)
        if off < lo or off + size > lo + len(ue): return None, 'format'
        d0, d1 = moved(off - lo), moved(off + size - lo)
        struct.pack_into('<qq', nu, o + 28, size + d1 - d0, off + d0)
    # read the new files back: every changed texture has the other's size and chain, every level its bytes at its place
    ex = bytes(ex); nb = blobs(ex)
    if len(nb) != len(bs): return None, 'size'
    for xi, (y, j, n, lv) in plan.items():
        z = nb[xi]
        if (z['first'], z['num'], z['w'], z['h']) != (y['first'], len(y['mips']), y['w'], y['h']) or len(z['mips']) != len(y['mips']): return None, 'size'
        for m, t, want in zip(z['mips'], y['mips'], lv):
            if (m['w'], m['h'], m['d']) != (t['w'], t['h'], t['d']): return None, 'size'
            if m['data'] is not None and m['off'] != m['at'] + 24 + lo: return None, 'size'
            if level_data(m, ex, bulk, s1) != want: return None, 'level'
    if full is not None: full.extend(sorted(isfull))
    return (bytes(nu), ex, bytes(bulk)), None

def compress(b):
    return [zlib.compress(b[i:i + BLOCK], 6) for i in range(0, len(b), BLOCK)] or [zlib.compress(b'')]

def pc_key(paks_dir, pak):
    """The PC pak's AES key from its executable (<game>/Binaries/Win64/*.exe): 32 bytes moved into place as eight immediates, the shape MSVC gives Unreal's key callback, or a data window. Kept in memory only"""
    root = os.path.normpath(os.path.join(paks_dir, '../../Binaries/Win64')); import glob
    with open(pak, 'rb') as f:
        ioff = uepak.footer(f)[1]; f.seek(ioff); blk = f.read(16)
    def good(w):
        d = uepak.aes_decrypt(w, blk); return 0 < struct.unpack_from('<i', d)[0] < 512 and d[4:7] == b'../'
    pat = re.compile(rb'\xC7\x01(....)\xC7\x41\x04(....)\xC7\x41\x08(....)\xC7\x41\x0C(....)\xC7\x41\x10(....)\xC7\x41\x14(....)\xC7\x41\x18(....)\xC7\x41\x1C(....)', re.S)
    for exe in glob.glob(root + '/*.exe'):
        img = open(exe, 'rb').read()
        for m in pat.finditer(img):
            w = b''.join(m.groups())
            if good(w): return w
    raise Error(f'no key for {pak} in {root}')

_w = {}
def _init(sw, pc, keys, lib):
    _w.update(sw=index(sw), pc=index(pc, keys)); bl_lib(lib)

def index(paths, keys=None):
    """{path from the root of the game: (Pak, its name in that pak)}: the later pak of a name wins (mount order)"""
    out = {}
    for i, p in enumerate(paths):
        k = uepak.Pak(p, keys[i] if keys else None); prefix = k.mount.replace('../../../', '')
        for n in k.files: out[prefix + n] = (k, n)
    return out

def job(base):
    """One package: (base, reason or None, [(path, chunks, raw size)...], bytes added, textures that took the other's whole chain)"""
    sw, pc = _w['sw'], _w['pc']
    def get(idx, name): k, n = idx[name]; return k.read(n)
    ua, ue = get(sw, base + '.uasset'), get(sw, base + '.uexp')
    ub = get(sw, base + '.ubulk') if base + '.ubulk' in sw else b''
    if base + '.uexp' not in pc or base + '.uasset' not in pc: return base, 'missing', [], 0, 0
    pua, pue = get(pc, base + '.uasset'), get(pc, base + '.uexp')
    pairs, why = missing_mips(ue, pue)
    if why: return base, why, [], 0, 0
    pub = get(pc, base + '.ubulk') if base + '.ubulk' in pc else b''
    full = []
    res, why = rebuild(ua, ue, ub, pue, pub, len(pua) + len(pue) - 4, pairs, full)
    if why: return base, why, [], 0, 0
    nua, nue, nub = res
    files = [(base + '.uasset', compress(nua), len(nua)), (base + '.uexp', compress(nue), len(nue))]
    if nub: files.append((base + '.ubulk', compress(nub), len(nub)))
    return base, None, files, len(nub) + len(nue) - len(ub) - len(ue), len(full)

def rows(path):
    out = []
    for n, line in enumerate(open(path, encoding='utf-8').read().splitlines(), 1):
        if not line.strip() or line.startswith('#'): continue
        c = line.split('\t')
        if len(c) != 3 or c[1] != 'textures': raise Error(f'{path}:{n}: a pak game takes rows: preset, textures, pattern')
        out.append(tuple(c))
    return out

def build(game_id, romfs, paks_dir, out):
    import game
    g = game.load(game_id); tsv = g.table('ue_pc_assets.tsv')
    if not tsv.is_file(): raise Error(f'game profile {game_id} has no ue_pc_assets.tsv')
    table = rows(tsv)
    sw_paks = uepak.paks(romfs)
    if not sw_paks: raise Error(f'no pak under {romfs}')
    rel = os.path.relpath(sw_paks[0], romfs); stem = os.path.basename(rel)[:-4]
    pcs = sorted(os.path.join(paks_dir, f) for f in os.listdir(paks_dir) if f.endswith('.pak'))
    if not pcs: raise Error(f'no pak in {paks_dir}')
    keys = []
    for p in pcs:
        with open(p, 'rb') as f: keys.append(pc_key(paks_dir, p) if uepak.footer(f)[0] else None)
    sw = index(sw_paks); version = uepak.Pak(sw_paks[0]).version; report = []
    lib = tempfile.mkdtemp(prefix='ue_pc_paks'); bl_lib(lib)
    pool = multiprocessing.Pool(int(os.environ.get('J') or 8), _init, (sw_paks, pcs, keys, lib))
    try:
        for preset in dict.fromkeys(r[0] for r in table):
            pats = [r[2].lower() for r in table if r[0] == preset]
            bases = sorted(n[:-5] for n in sw if n.endswith('.uexp') and n[:-5] + '.uasset' in sw and any(fnmatch.fnmatchcase(n[:-5].lower(), p) for p in pats))
            if not bases: raise Error(f'{preset}: no package matches {pats}')
            d = os.path.join(out, preset, os.path.dirname(rel)); os.makedirs(d, exist_ok=True)
            f = os.path.join(d, f'{stem}_99_P.pak'); tmp = f + '.tmp'
            old = uepak.Pak(f) if os.path.exists(f) else None; n = 0; added = 0; nfull = 0; skipped = dict.fromkeys(SKIPS, 0)
            with uepak.LegacyPakWriter(tmp, '../../../', version) as w:
                if old:
                    prefix = old.mount.replace('../../../', '')
                    for name in old.files: w.add(prefix + name, old.read(name))
                for base, why, files, grew, nf in pool.imap_unordered(job, bases, chunksize=8):
                    if why: skipped[why] += 1; continue
                    for path, chunks, raw in files: w.add_zlib(path, chunks, raw, BLOCK)
                    n += 1; added += grew; nfull += nf
            os.replace(tmp, f)
            report.append(f'{preset}: {n} textures taken (full chain {nfull}) of {len(bases)} packages, {added / 1e9:.2f} GB of raw texels added, pak {os.path.getsize(f) / 1e9:.2f} GB; skipped ' + ', '.join(f'{k} {v}' for k, v in skipped.items() if v))
    finally:
        pool.close(); pool.join(); shutil.rmtree(lib, ignore_errors=True)
    return report

def main(argv):
    if len(argv) != 4: sys.exit('usage: ue_pc_paks.py <game id> <RomFS root> <other platform\'s Paks dir> <out dir>')
    try:
        for line in build(*argv): print(line)
    except (Error, ValueError, OSError) as e:
        sys.exit(f'ue_pc_paks.py: {e}')

if __name__ == '__main__': main(sys.argv[1:])
