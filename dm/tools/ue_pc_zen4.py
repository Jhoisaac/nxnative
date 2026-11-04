#!/usr/bin/env python3
# The Unreal Engine 4.25 path of ue_pc_assets.py (a game whose Switch build keeps its packages in IoStore TOC version 2 and whose PC build keeps them in legacy paks): not run by itself, ue_pc_assets.py calls build(...).
# Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles. The two builds are the same cook except for the settings: the Switch's device profile (LODBias=1) stripped the top mips of about 8,000 textures. A PC package cannot go
# into the Switch's container as it is (a legacy .uasset / .uexp / .ubulk against the loader's zen package: a header with its name, import and export maps, then the export data, and the bulk data in a chunk of its own), and its
# other data differs (D3D shader maps, PhysXPC names). What can be shared is the texel data: measured on this game, the levels both builds hold are almost always byte for byte the same (the Switch's stored linear, so the copy is
# the whole rule; the tool also tries the block-linear swizzles of ue_pc_paks.py and applies whichever makes the first level the Switch holds equal). So the tool keeps the Switch's zen package and rebuilds its texture platform data:
#   - every stored Switch level is the PC level of its size (swizzled by the rule found on the first): the PC's top levels are added in front of the Switch's (FirstMipToSerialize, the mip count, SizeX and SizeY, the inline mips'
#     offsets, the platform data's SkipOffset, the export's SerialSize and the later exports' offsets); a mip the PC keeps in its .ubulk goes into the package's bulk chunk (type 3, appended, the flags the Switch's bulk mips have), an
#     inline one stays inline;
#   - the first stored level matches and a later one does not (the same image encoded again): the PC's whole chain replaces the Switch's, all its levels, its size and mip count, so no texture mixes the builds' levels (report: `full chain`);
#   - the first stored level differs, or anything else does not fit: the Switch's package stays.
# The container header (type 10) gets the store entry of each taken package with the Switch's own imports, export counts and load order and the new chunk length (the entry's export bundles size is the length of the package chunk,
# checked on all 775 packages of pakchunk1-Switch). A texture is paired with the PC's by the name of its export, so a map's lightmap package with several textures works.
# Skip reasons (counted in the report): missing (no such package on the PC), culture (a package of the container header's culture map or redirects), notex (no texture platform data in the Switch's package or the PC's), same (the PC
# holds nothing more), format (another pixel format, a size no power of two apart, a texture with no partner, a layout this tool does not rebuild), level (the first stored level is not the PC's), size (a level's data is cut short or
# the rebuilt package does not read back as intended: verify).
# Output as ue_pc_assets.py: <out dir>/<preset>/<directory of the Switch container>/<stem>_99_P.utoc/.ucas (TOC version 2, Zlib blocks of 64 KB, write_toc2), a pak beside it empty when ue_quality.py wrote none. The rule `textures`
# takes the packages whose path matches the pattern (fnmatch on the path without "../../../" and the extension, case-insensitive); other rules are refused with a message. How the game takes the container over its own: see "Writing a
# version 2 container" in uepak.py (read from main; not run in the game yet). J=1 runs in this process.
import fnmatch, hashlib, multiprocessing, os, struct, sys, tempfile, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '../gfx/tools')); sys.path.insert(0, HERE)
import uepak, ue_pc_paks as pk

class Error(Exception): pass

MOUNT = '../../../'
REASONS = ('missing', 'culture', 'notex', 'same', 'format', 'level', 'size')
EXPORT_ENTRY = 72   # bytes of an export map entry (u64 offset, u64 size, then names and object indices)
BULK_FLAGS, INLINE_FLAGS = 0x10501, 0x48   # the Switch's mip flags (66817 and 72 on every texture sampled): payload at the end and in a separate file, not inline; force inline and single use

def summary(d):
    """(CookedHeaderSize, header size, export map offset, export bundles offset) of a 4.25 package chunk (a zen header: u64 name, u64 source name, u32 package flags, u32 cooked header size, then the offsets and sizes of the
    name map, the name hashes, the import map, the export map, the export bundles and the graph data), or None"""
    if len(d) < 0x40: return None
    cooked, = struct.unpack_from('<I', d, 0x14); eo, bo, go, gs = struct.unpack_from('<4I', d, 0x2c)
    hsz = go + gs
    if not 0x40 <= eo <= bo <= go or (bo - eo) % EXPORT_ENTRY or hsz > len(d) or not cooked: return None
    return cooked, hsz, eo, bo

def transform(have, other, w0, h0, x, d):
    """The way to turn the other platform's level d into the Switch's first level (the rule found by the check): 'copy', or the layout of a swizzle (ue_pc_paks.layout, tried sparse first), or None when no rule makes them equal"""
    if other == have: return 'copy'
    bpb, bw = pk.FORMATS[x['pf']]
    for sparse in (True, False):
        lay = pk.layout(w0, h0, bpb, bw, x['num'] + d, sparse)
        if lay[d][4] == len(have) and pk.swizzle(other, lay[d]) == have: return sparse
    return None

def zen_exports(chunk):
    """[(position in the export data, size, (object name, number))] of a 4.25 package chunk's exports: the export map entries (u64 offset in the cooked file, u64 size, FMappedName of the object name: u32 index into this
    package's name map, u32 number) and the name map (the bytes after the summary: each name a big-endian u16 length, bit 15 for UTF-16, and its characters); None when a name is not in the package's own name map"""
    s = summary(chunk)
    if not s: return None
    lo, hsz, eo, bo = s; no, ns = struct.unpack_from('<2I', chunk, 0x18); d = chunk[no:no + ns]; names, o = [], 0
    while o + 2 <= len(d):
        ln, = struct.unpack_from('>H', d, o); o += 2; w = ln & 0x8000; ln &= 0x7fff; k = 2 * ln if w else ln
        names.append(d[o:o + k].decode('utf-16-le' if w else 'latin-1')); o += k
    out = []
    for i in range((bo - eo) // EXPORT_ENTRY):
        off, size, nm, num = struct.unpack_from('<qqII', chunk, eo + i * EXPORT_ENTRY)
        if nm >> 30 or (nm & 0x3fffffff) >= len(names): return None
        out.append((off - lo, size, (names[nm & 0x3fffffff], num)))
    return out

def legacy_exports(ua):
    """The same for a legacy .uasset (UE 4.25 cooked summary; offsets are in the .uasset + .uexp, so the position in the .uexp is the offset minus the length of the .uasset)"""
    try:
        o = 20; ncv, = struct.unpack_from('<i', ua, o); o += 4 + 20 * max(ncv, 0) + 4
        fl, = struct.unpack_from('<i', ua, o); o += 4 + fl + 4
        nn, no, _, _, n, eo = struct.unpack_from('<6i', ua, o); names = []
        for _ in range(nn):
            ln, = struct.unpack_from('<i', ua, no); no += 4
            if ln < 0: names.append(ua[no:no - 2 * ln - 2].decode('utf-16-le')); no += -2 * ln
            else: names.append(ua[no:no + ln - 1].decode('latin-1')); no += ln
            no += 4
        _, _, dep = struct.unpack_from('<iii', ua, o + 24); esz = (dep - eo) // n
        out = []
        for i in range(n):
            nm, num, _, size, off = struct.unpack_from('<iiiqq', ua, eo + i * esz + 16)
            out.append((off - len(ua), size, (names[nm], num)))
        return out
    except (struct.error, IndexError, ZeroDivisionError, ValueError): return None

def owner(exports, at):
    """The name of the export whose data holds position at, or None"""
    return next((e[2] for e in exports or () if e[0] <= at < e[0] + e[1]), None)

def shift(x, y):
    """How many levels the PC's texture y is larger than the Switch's x (its SizeX and SizeY are x's times 2^k: the cook capped the size, not only the stored mips), or None for sizes no power of two apart"""
    if (x['w'], x['h']) == (y['w'], y['h']): return 0
    k = y['w'] // x['w'] if y['w'] % x['w'] == 0 else 0
    if k < 2 or k & (k - 1) or y['w'] != x['w'] * k or y['h'] != x['h'] * k: return None
    return k.bit_length() - 1

def rebuild(chunk, bulk, pue, pub, pairs):
    """The package chunk and bulk chunk with the pairs' (Switch blob, PC blob) top mips added: (new package chunk, new bulk chunk or None), or (None, reason)"""
    s = summary(chunk)
    if not s: return None, 'notex'
    lo, hsz, eo, bo = s; body = chunk[hsz:]; bulk = bulk or b''
    swizzled, chains = False, set()
    top_of = {x['skip']: (x, y) for x, y in pairs}
    ex, nb, pos, marks = bytearray(), bytearray(bulk), 0, []   # marks: (old body position, how far what follows moved)
    for x in pk.blobs(body):
        xy = top_of.get(x['skip'])
        ex += body[pos:x['fo']]; skip_at = len(ex) - (x['fo'] - x['skip'])
        y = xy[1] if xy else None
        d = xy[0]['first'] + shift(xy[0], y) - y['first'] if xy else 0   # the mips this cook stripped, and the levels it cut off
        ex += struct.pack('<ii', y['first'] if y else x['first'], y['num'] if y else x['num'])   # the PC's chain either way: first mip and count
        if y:
            struct.pack_into('<ii', ex, skip_at + 8, y['w'], y['h'])
            have = pk.level_data(x['mips'][0], body, bulk, 0); other = pk.level_data(y['mips'][d], pue, pub, 0)
            if have is None or other is None: return None, 'size'
            w0, h0 = y['mips'][0]['w'], y['mips'][0]['h']
            rule_ = transform(have, other, w0, h0, x, d)
            if rule_ is None: return None, 'level'
            swizzled |= rule_ != 'copy'
            if rule_ != 'copy':
                bpb, bw = pk.FORMATS[x['pf']]; lay = pk.layout(w0, h0, bpb, bw, x['num'] + d, rule_)
            # every stored Switch level must be the PC level of its size (swizzled by the rule found on the first); when the first matches and a later one does not (the same image encoded again), the PC's whole chain
            # replaces the Switch's, so that no texture mixes the two builds' levels
            chain = False
            for j, m in enumerate(x['mips']):
                a_ = pk.level_data(m, body, bulk, 0); b_ = pk.level_data(y['mips'][d + j], pue, pub, 0)
                if a_ is None or b_ is None: return None, 'size'
                if (pk.swizzle(b_, lay[d + j]) if rule_ != 'copy' else b_) != a_: chain = True
            if chain: chains.add(x['skip']); d = 0
            for i in range(len(y['mips']) if chain else d):
                top = y['mips'][i]; dat = pk.level_data(top, pue, pub, 0)
                if dat is None: return None, 'size'
                if rule_ != 'copy': dat = pk.swizzle(dat, lay[i])
                tail = struct.pack('<iii', top['w'], top['h'], top['d'])
                if top['data'] is not None:
                    ex += struct.pack('<iIiiq', 1, INLINE_FLAGS, len(dat), len(dat), len(ex) + 24 + lo) + dat + tail
                else:
                    ex += struct.pack('<iIiiq', 1, BULK_FLAGS, len(dat), len(dat), len(nb)) + tail; nb += dat
        for m in (() if y and x['skip'] in chains else x['mips']):
            tail = body[m['end'] - 12:m['end']]
            if m['data'] is not None:
                ex += struct.pack('<iIiiq', 1, m['flags'], m['n'], m['disk'], len(ex) + 24 + lo) + body[m['data']:m['data'] + m['disk']] + tail
            elif m['flags'] & pk.BULK_FILE: ex += body[m['at']:m['end']]   # its place in the bulk chunk is unchanged: the new mips are appended
            else: return None, 'format'   # a payload at the end of the export data is not rebuilt
        pos = x['end']
        old = struct.unpack_from('<q', body, x['skip'])[0]
        struct.pack_into('<q', ex, skip_at, old + len(ex) - x['end'])
        marks.append((x['end'], len(ex) - x['end']))
    ex += body[pos:]
    nh = bytearray(chunk[:hsz])
    def moved(at): return next((dd for e, dd in reversed(marks) if e <= at), 0)
    n = (bo - eo) // EXPORT_ENTRY
    for i in range(n):
        o = eo + i * EXPORT_ENTRY; off, size = struct.unpack_from('<qq', nh, o)
        if off < lo or off + size > lo + len(body): return None, 'format'
        d0, d1 = moved(off - lo), moved(off + size - lo)
        struct.pack_into('<qq', nh, o, off + d0, size + d1 - d0)
    return (bytes(nh) + bytes(ex), bytes(nb) if len(nb) != len(bulk) else None, swizzled, chains), None

def verify(chunk, bulk, old, old_bulk, a, pairs, pue, pub, swizzled, chains):
    """Whether the rebuilt package reads back as intended: the header sums, every texture's platform data (size, first mip, mip count, the added levels equal to the PC's or, swizzled, of the layout's size, the old ones unchanged),
    and the export map inside the export data"""
    s = summary(chunk); lo, hsz, eo, bo = s; body = chunk[hsz:]; new = pk.blobs(body); of = {x['skip']: y for x, y in pairs}
    if len(new) != len(a): return False
    for n, x in zip(new, a):
        y = of.get(x['skip'])
        if not y:
            if [pk.level_data(m, body, bulk, 0) for m in n['mips']] != [pk.level_data(m, summary_body(old), old_bulk, 0) for m in x['mips']]: return False
            continue
        chain = x['skip'] in chains; d = 0 if chain else len(n['mips']) - len(x['mips'])
        if (n['w'], n['h'], n['first'], n['num']) != (y['w'], y['h'], y['first'], y['num']) or len(n['mips']) != y['num'] or (d != x['first'] + shift(x, y) - y['first'] or d < 1) and not chain: return False
        if chain:   # every level is the PC's (or its swizzle, of the same size)
            for i, m in enumerate(n['mips']):
                have = pk.level_data(m, body, bulk, 0); want = pk.level_data(y['mips'][i], pue, pub, 0)
                if have is None or want is None or len(have) < len(want) or not swizzled and have != want or (m['w'], m['h'], m['d']) != (y['mips'][i]['w'], y['mips'][i]['h'], y['mips'][i]['d']): return False
            continue
        for i, m in enumerate(n['mips']):
            have = pk.level_data(m, body, bulk, 0)
            want = pk.level_data(y['mips'][i], pue, pub, 0) if i < d else pk.level_data(x['mips'][i - d], summary_body(old), old_bulk, 0)
            if have is None or want is None or len(have) != len(want) or have != want and (i >= d or not swizzled): return False   # the added levels equal the PC's unless swizzled
            if (m['w'], m['h'], m['d']) != ((y['mips'][i]['w'], y['mips'][i]['h'], y['mips'][i]['d']) if i < d else (x['mips'][i - d]['w'], x['mips'][i - d]['h'], x['mips'][i - d]['d'])): return False
        if struct.unpack_from('<q', body, n['skip'])[0] - n['end'] != struct.unpack_from('<q', summary_body(old), x['skip'])[0] - x['end']: return False   # SkipOffset still ends the platform data
    for i in range((bo - eo) // EXPORT_ENTRY):
        off, size = struct.unpack_from('<qq', chunk, eo + i * EXPORT_ENTRY)
        if off < lo or off + size > lo + len(body): return False
    return True

def summary_body(chunk): return chunk[summary(chunk)[1]:]

def compress(b):
    """The blocks of a chunk, Zlib-compressed in 64 KB pieces (a piece that does not shrink stays stored): [(bytes, raw size, method)]"""
    out = []
    for i in range(0, len(b), uepak.IO_BLOCK):
        r = b[i:i + uepak.IO_BLOCK]; z = zlib.compress(r, 6)
        out.append((z, len(r), 'Zlib') if len(z) < len(r) else (r, len(r), ''))
    return out

def meta(raw, blocks):
    """The 33-byte chunk meta: SHA-1 of the chunk's bytes in 32, flags 1 when a block is compressed"""
    return hashlib.sha1(raw).digest() + bytes(12) + bytes([1 if any(m for _, _, m in blocks) else 0])

_w = {}
def _init(romfs, pc_paths):
    _w['tocs'] = {t.path: t for t in uepak.io_tocs(romfs) if t.version < 4}
    _w['pc'] = pc_index(pc_paths); pk.bl_lib(tempfile.mkdtemp(prefix='ue_pc_zen4'))

def pc_index(paths):
    """{lower-case path from the game's root (Content/... as the legacy pak names it): (Pak, name)}: a later pak of a name wins"""
    out = {}
    for p in paths:
        k = uepak.Pak(p); prefix = k.mount.replace(MOUNT, '')
        for n in k.files: out[(prefix + n).lower()] = (k, n)
    return out

def job(item):
    """One package: (package ID, reason or None, (Switch top size, PC top size, new package chunk blocks, new bulk chunk blocks or None, chunk length, bulk length, SHA-1 of the chunk, SHA-1 of the bulk or None) or None)"""
    pid, base, toc_path, i2, i3 = item
    t = _w['tocs'][toc_path]; pc = _w['pc']
    chunk = t.read(i2)
    s = summary(chunk)
    if not s: return pid, 'notex', None
    body = chunk[s[1]:]; a = pk.blobs(body)
    if not a: return pid, 'notex', None
    ua, ue, ub = (pc.get((base + e).lower()) for e in ('.uasset', '.uexp', '.ubulk'))
    if not ua or not ue: return pid, 'missing', None
    pua = ua[0].read(ua[1]); pue = ue[0].read(ue[1]); pub = ub[0].read(ub[1]) if ub else b''
    p = pk.blobs(pue)
    if not p: return pid, 'notex', None
    pairs, why = [], None   # a texture is paired by the name of its export (a map's lightmaps are several, and the PC build has some more); a package with one texture on each side by position
    ex, pex = zen_exports(chunk), legacy_exports(pua)
    by = {}
    for y in p: by.setdefault(owner(pex, y['skip']), y)
    for j, x in enumerate(a):
        nm = owner(ex, x['skip'])
        y = by.get(nm) if nm and ex and pex else (p[j] if len(a) == len(p) == 1 else None)
        if not y: why = why or 'format'; continue
        if x['pf'] != y['pf'] or x['pf'] not in pk.FORMATS or x['packed'] & 0xffff != 1 or y['packed'] & 0xffff != 1: why = why or 'format'; continue
        k = shift(x, y)   # the levels the cook cut off the size itself (MaxLODSize), before the stripped ones
        if k is None: why = why or 'format'; continue
        if x['first'] == y['first'] and x['num'] == y['num'] and not k: why = why or 'same'; continue
        if x['first'] + k <= y['first'] or y['num'] + y['first'] != x['num'] + x['first'] + k: why = why or 'format'; continue
        pairs.append((x, y))
    if not pairs: return pid, why or 'same', None
    bulk = t.read(i3) if i3 is not None else None
    new, why = rebuild(chunk, bulk, pue, pub, pairs)
    if why: return pid, why, None
    c2, c3, swz, chains = new
    if not verify(c2, c3 or bulk or b'', chunk, bulk or b'', a, pairs, pue, pub, swz, chains): return pid, 'size', None
    return pid, None, (f"{a[0]['mips'][0]['w']}x{a[0]['mips'][0]['h']}", f"{p[0]['mips'][0]['w']}x{p[0]['mips'][0]['h']}", compress(c2), compress(c3) if c3 else None, len(c2), len(c3) if c3 else 0, hashlib.sha1(c2).digest(), hashlib.sha1(c3).digest() if c3 else None, len(chains))

def index(tocs):
    """The packages of the containers in mount order (a later one wins): ({package ID: (path without mount and extension, toc path, package chunk index, bulk chunk index or None)}, {package ID: container header entry},
    the package IDs the culture maps and redirects name, the first container header's raw tail check). Containers without a container header chunk (global) are skipped"""
    pk_, store, local = {}, {}, set()
    for t in tocs:
        h = [i for i, c in enumerate(t.ids) if c[11] == 10]
        if not h: continue
        raw = t.read(h[0]); head = uepak.read_container_header2(raw)
        for e in head['entries']: store[e[0]] = e
        local |= culture_ids(raw, head)
        paths = t.paths()
        for i, c in enumerate(t.ids):
            if c[11] != 2: continue
            p = paths.get(i, '')
            if not p.endswith(('.uasset', '.umap')): continue
            pid = int.from_bytes(c[:8], 'little'); j = t.index.get(uepak.io_chunk_id(pid, 0, 3))
            pk_[pid] = (os.path.splitext(p[len(MOUNT):] if p.startswith(MOUNT) else p)[0], t.path, i, j)
    return pk_, store, local

def culture_ids(raw, head):
    """The package IDs of the container header's culture map (after the store entries: i32 count, then per culture an FString, an i32 count and pairs of package IDs) and package redirects (i32 count of pairs)"""
    r = uepak.R(raw, what='container header'); r.take('<Q'); r.take('<I'); r.raw(r.take('<i')); r.raw(r.take('<i')); r.raw(8 * r.take('<i')); r.raw(r.take('<i'))
    out = set()
    try:
        for _ in range(r.take('<i')):
            r.fstr()
            for _ in range(r.take('<i')): out.update(r.take('<QQ'))
        for _ in range(r.take('<i')): out.update(r.take('<QQ'))
    except ValueError: pass
    return out

def build(rules, romfs, paks, out):
    """rules = [(preset, rule, pattern)] → report lines; writes the containers under out and the TSVs beside it"""
    if any(r[1] != 'textures' for r in rules): raise Error('this engine\'s path takes `textures` rows only: ' + ', '.join(sorted({r[1] for r in rules if r[1] != 'textures'})))
    tocs = [t for t in uepak.io_tocs(romfs) if t.version < 4 and any(c[11] == 10 for c in t.ids)]
    if not tocs: raise Error(f'no IoStore container with a container header under {romfs}')
    if any(t.encrypted for t in tocs): raise Error('a container is encrypted')
    pc_paths = sorted(os.path.join(paks, f) for f in os.listdir(paks) if f.endswith('.pak'))
    if not pc_paths: raise Error(f'no pak in {paks}')
    sw, store, local = index(tocs)
    main = max(tocs, key=lambda t: len(t.export_bundles()))
    stem = os.path.basename(main.path)[:-5]; name = f'{stem}_99_P'
    dest_rel = os.path.dirname(os.path.relpath(main.path, romfs))
    report = []
    jobs = int(os.environ.get('J') or 6)   # J=1 runs in this process (the tests, a debugger)
    pool = multiprocessing.Pool(jobs, _init, (romfs, pc_paths)) if jobs > 1 else None
    if not pool: _init(romfs, pc_paths)
    try:
        for preset in dict.fromkeys(r[0] for r in rules):
            skipped = dict.fromkeys(REASONS, 0); items = []
            for _, rule, pattern in (r for r in rules if r[0] == preset):
                pat = pattern.lower(); hits = [pid for pid, v in sw.items() if fnmatch.fnmatchcase(v[0].lower(), pat)]
                if not hits: raise Error(f'{preset}: {rule} {pattern}: no package matches')
                for pid in hits:
                    if pid in local: skipped['culture'] += 1; continue
                    items.append((pid, sw[pid][0], sw[pid][1], sw[pid][2], sw[pid][3]))
            seen = set(); items = [i for i in items if not (i[0] in seen or seen.add(i[0]))]
            d = os.path.join(out, preset, dest_rel); stem_path = os.path.join(d, name); os.makedirs(d, exist_ok=True)
            for ext in ('.utoc', '.ucas'):
                if os.path.exists(stem_path + ext): os.remove(stem_path + ext)
            spool = tempfile.TemporaryFile(); recs = []; tsv = []; nbytes = 0
            for pid, why, res in (pool.imap_unordered(job, items, chunksize=16) if pool else map(job, items)):
                if why: skipped[why] += 1; continue
                swx, pcx, b2, b3, n2, n3, h2, h3, nch = res
                def put(blocks):
                    out_ = []
                    for data, raw, meth in blocks:
                        out_.append((spool.tell(), len(data), raw, meth)); spool.write(data)
                    return out_
                recs.append((pid, put(b2), n2, h2, put(b3) if b3 else None, n3, h3, swx, pcx, nch))
            recs.sort(key=lambda r: r[0])
            def lazy(at, n): return lambda: (spool.seek(at), spool.read(n))[1]
            chunks, entries = [], []
            for pid, b2, n2, h2, b3, n3, h3, swx, pcx, nch in recs:
                e = store[pid]
                entries.append((pid, n2, e[2], e[3], e[4], e[5]))
                for cid, blocks, n, h in ((uepak.io_chunk_id(pid, 0, 2), b2, n2, h2), (uepak.io_chunk_id(pid, 0, 3), b3, n3, h3)):
                    if blocks is None: continue
                    bl = [(lazy(at, sz), raw, meth) for at, sz, raw, meth in blocks]
                    chunks.append(dict(id=cid, size=n, blocks=bl, meta=h.ljust(32, b'\0') + bytes([1 if any(m for _, _, _, m in blocks) else 0])))
                tsv.append('\t'.join((sw[pid][0], 'full chain' if nch else 'textures', swx, pcx, str(1 + (b3 is not None)), str(n2 + n3))))
            if chunks:
                cid = uepak.io_container_id(name); data = uepak.container_header2(cid, entries); blocks = compress(data)
                chunks.append(dict(id=uepak.io_chunk_id(cid, 0, 10), size=len(data), blocks=blocks, meta=meta(data, blocks)))
                uepak.write_toc2(stem_path, name, chunks); nbytes = os.path.getsize(stem_path + '.ucas')
            spool.close()
            report_tsv = os.path.join(os.path.dirname(os.path.abspath(out)), f'ue_pc_assets_{preset}.tsv')
            Path_write(report_tsv, ''.join(l + '\n' for l in sorted(tsv)))
            if not os.path.exists(stem_path + '.pak'): uepak.write_pak(stem_path + '.pak', MOUNT, [])
            report.append(f'{preset}: {len(recs)} package(s) (textures; full chain {sum(1 for r in recs if r[9])}), {len(chunks)} chunks, {nbytes:,} bytes; skipped: ' + ', '.join(f'{k} {skipped[k]}' for k in REASONS))
    finally:
        if pool: pool.close(); pool.join()
    return report

def Path_write(path, text):
    with open(path, 'w', encoding='utf-8') as f: f.write(text)
