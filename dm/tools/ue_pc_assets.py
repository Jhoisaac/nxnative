#!/usr/bin/env python3
# Another platform's higher-resolution packages as a patch container: ue_pc_assets.py <game id> <RomFS root of the extracted game> <other platform's Paks dir> <out dir> <host> <modules dir>
# The Switch cook stripped the top mips of the textures (the device profile's LODBias); another platform's build of the same game (the same engine, the same IoStore/zen layout, the same chunk IDs: a
# package's ID is its name's hash) has them. For each preset in the profile's ue_pc_assets.tsv (dm/games/README.md) it writes <out dir>/<preset>/<directory of the Switch container>/<stem>_99_P.utoc/.ucas,
# holding every chunk of each chosen package as the other platform stores it (blocks copied verbatim, nothing recompressed) and a container header with that platform's store entries (imports, shader map
# hashes). The host serves the container from the preset's folder (hle_fs.c, DM_UE_QUALITY=<preset>) and the game mounts <stem>_99_P with its pak with priority, so the packages' chunks resolve to the other
# platform's. The inputs are the player's own folders (nothing is copied into the repository); the output goes to <out dir>; a pak beside the container is written empty when ue_quality.py wrote none.
# A game on Unreal Engine 4.25 (the Switch's containers are TOC version 2 and the PC build keeps legacy paks: Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles) goes to ue_pc_zen4.py: the PC's chunks cannot be copied there, so the Switch's package
# gets the PC's top mip levels added (rule `textures` only). Table rows: preset <TAB> rule <TAB> pattern (fnmatch on the package path without "../../../" and the extension, case-insensitive; # starts a comment). Rule `textures`: the packages that are textures whose
# top mip there has more pixels than here (same pixel format); rule `package`: every match (a map's *_BuiltData lightmaps). A pattern that matches no Switch package stops with a message and a non-zero exit.
# A package is skipped, and counted in the report, when it is missing there, its imports or shader map hashes differ (its chunks would not fit the Switch's other packages), or (textures) is not
# larger, has another pixel format, shows no texture data in the first 64 KB, or (textures) has another name map than the Switch's (a platform name such as PhysXPC or PCD3D_SM5, a map or
# blueprint holding a texture beside shader maps: this game's store entries carry no shader map hashes, so the imports check alone does not catch them); and any package whose export chunk has the same length on both (a stripped mip changes it: the mip count and the
# bulk data map are in it), which also spares decoding its head. Rule `meshes` (with the preset's `rename` rows, pattern <from>=<to>: the platform names the cooked collision format differently, PhysXPC for PhysXGeneric): the packages that are not textures, have only an export
# chunk, whose name map is ours after the rename, with as many exports and a longer chunk (the top LODs this cook stripped); the other platform's chunk is written with its names renamed (hashes, lengths, header sizes
# shifted; the package must name BodySetup, so no material is taken; skips `texture`, `notmesh`, `names`, `exports`, `bulk`, and `same` for a rename-only difference; the heads of the first renamed packages of our length must equal ours or the tool stops). Beside <out dir> it writes ue_pc_assets_<preset>.tsv: package, rule, Switch WxH, other WxH, chunks, bytes.
import fnmatch, os, re, struct, sys
from pathlib import Path
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '../gfx/tools')); sys.path.insert(0, os.path.join(HERE, '../games'))
import uepak

class Error(Exception): pass

MOUNT = '../../../'
PFRE = re.compile(rb'[\x04-\x20]\x00\x00\x00(PF_[A-Za-z0-9_]+)\x00')   # an FString "PF_...": the pixel format that follows a texture's SizeX, SizeY and packed data
REASONS = ('missing', 'imports', 'same', 'notex', 'names', 'format', 'texture', 'exports', 'bulk', 'notmesh')
CHECKED = 20   # the name-only meshes whose renamed bytes must equal the Switch's before any other is trusted

def rows(path):   # [(preset, rule, pattern)] in file order
    out = []
    for n, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip() or line.startswith('#'): continue
        c = line.split('\t')
        if len(c) != 3 or not all(c) or c[1] not in ('textures', 'package', 'meshes', 'rename'): raise Error(f'{path}:{n}: expected preset, rule (textures, package, meshes or rename), pattern (3 tab-separated fields)')
        if c[1] == 'rename' and c[2].count('=') != 1: raise Error(f'{path}:{n}: a rename pattern is <from>=<to>')
        out.append(tuple(c))
    return out

def texture_top(d):
    """(pixel format, width, height) of the top mip of the first texture platform data in a package chunk's head (FZenPackageSummary without versioning info: version 0, header size at +4; the body
    after the header holds i32 SizeX, SizeY, packed, the FString "PF_...", 8 more bytes when packed has bit 30, then i32 first mip and i32 mip count), or None"""
    if len(d) < 8 or struct.unpack_from('<I', d, 0)[0] != 0: return None
    hsz = struct.unpack_from('<I', d, 4)[0]; body = d[hsz:]; m = PFRE.search(body)
    if not m or m.start() < 12: return None
    sx, sy, pk = struct.unpack_from('<iii', body, m.start() - 12); o = m.end() + (8 if pk & 1 << 30 else 0)
    if o + 8 > len(body): return None
    fm = struct.unpack_from('<i', body, o)[0]
    if sx <= 0 or sy <= 0 or not 0 <= fm < 32: return None
    return m.group(1).decode(), max(1, sx >> fm), max(1, sy >> fm)

def names(d):
    """The name map of a package chunk's head (FZenPackageSummary without versioning info, 0x34 bytes; then u32 name count, u32 string bytes, u64 hash version, the u64 hashes, each name's
    big-endian u16 length (bit 15: UTF-16) and the strings), or None when the head is not one or ends inside the map"""
    if len(d) < 0x44 or struct.unpack_from('<I', d, 0)[0] != 0: return None
    n = struct.unpack_from('<I', d, 0x34)[0]; o = 0x44 + 8 * n
    if o + 2 * n > len(d): return None
    lens = struct.unpack_from(f'>{n}H', d, o); o += 2 * n; out = []
    for ln in lens:
        k = 2 * (ln & 0x7fff) if ln & 0x8000 else ln
        if o + k > len(d): return None
        out.append(d[o:o + k]); o += k
    return tuple(out)

def rename_names(d, table):
    """A package chunk with every name of its name map found in table ({from: to}, str) renamed: the name's hash (CityHash64 of the lower-case name, as latin-1 bytes or UTF-16 when the name is wide),
    its length and its string, and the head's sizes shifted by the change in string bytes (HeaderSize, CookedHeaderSize, the seven table offsets and the name map's string byte count; the body
    is not touched); None when the head is not a package's or ends inside the name map"""
    if names(d) is None: return None
    n = struct.unpack_from('<I', d, 0x34)[0]; ho = 0x44; lo = ho + 8 * n; so = lo + 2 * n
    lens = struct.unpack_from(f'>{n}H', d, lo); hashes = list(struct.unpack_from(f'<{n}Q', d, ho)); out = []; o = so
    for k, ln in enumerate(lens):
        wide = ln & 0x8000; nb = 2 * (ln & 0x7fff) if wide else ln; raw = d[o:o + nb]; o += nb
        text = raw.decode('utf-16-le' if wide else 'latin-1')
        if text in table:
            text = table[text]; wide = 0x8000 if not text.isascii() and not all(ord(c) < 256 for c in text) else 0
            raw = text.encode('utf-16-le' if wide else 'latin-1'); hashes[k] = uepak.city64(text.lower().encode('utf-16-le' if wide else 'latin-1'))
            lens = lens[:k] + (wide | (len(raw) // 2 if wide else len(raw)),) + lens[k + 1:]
        out.append(raw)
    delta = sum(map(len, out)) - (o - so)
    h = bytearray(d[:ho]); struct.pack_into('<I', h, 4, struct.unpack_from('<I', d, 4)[0] + delta)
    for p in (0x14, 0x18, 0x1c, 0x20, 0x24, 0x28, 0x2c, 0x30): struct.pack_into('<i', h, p, struct.unpack_from('<i', d, p)[0] + delta)
    struct.pack_into('<I', h, 0x38, struct.unpack_from('<I', d, 0x38)[0] + delta)
    return bytes(h) + struct.pack(f'<{n}Q', *hashes) + struct.pack(f'>{n}H', *lens) + b''.join(out) + d[o:]

def export_span(d):
    """The bytes of a package head's export map (its offset to the export bundle entries minus its own): the export count times the entry size, unchanged by a rename"""
    return struct.unpack_from('<i', d, 0x24)[0] - struct.unpack_from('<i', d, 0x20)[0]

def head(toc, i, dec):
    """The first block of chunk i, decoded (Oodle through dec(bytes, raw size)): enough for the head of a package"""
    if toc.encrypted: raise Error(f'{toc.path}: the container is encrypted')
    off, ln = toc.ranges[i]; first = off // toc.block_size
    if not ln: return b''
    at, size, raw, m = toc.blocks[first]; f = toc.ucas(at // toc.part_size); f.seek(at % toc.part_size); d = f.read(size)
    if len(d) != size: raise Error(f'{toc.path}: chunk {i} is cut short')
    meth = toc.methods[m - 1] if m else ''
    if meth == 'Oodle': d = dec(d, raw)
    elif meth: raise Error(f'{toc.path}: compression method {meth} is not read')
    else: d = d[:raw]
    s = off - first * toc.block_size
    return d[s:s + ln]

def index(tocs, dec, bulk=False):
    """The packages of containers in mount order (a later one wins, as in the engine): ({package ID: (path without mount and extension, toc, chunk index)}, {package ID: (imports, shader map hashes)},
    {package ID: {chunk ID: (toc, chunk index)}} of the package's chunks of types 1 to 4 when bulk). Containers without a container header (global) are skipped"""
    pk, store, chunks = {}, {}, {}
    for t in tocs:
        h = t.of_type(uepak.IO_CONTAINER_HEADER)
        if not h: continue
        for pid, imps, hashes in uepak.read_container_header(t.read(h[0], dec))['entries']: store[pid] = (tuple(imps), tuple(hashes))
        paths = t.paths()
        for i, c in enumerate(t.ids):
            pid = int.from_bytes(c[:8], 'little')
            p = paths.get(i, '')
            if c[11] == uepak.IO_EXPORT_BUNDLE and p.endswith(('.uasset', '.umap')): pk[pid] = (os.path.splitext(p[len(MOUNT):] if p.startswith(MOUNT) else p)[0], t, i)
            if bulk and c[11] in (1, 2, 3, 4): chunks.setdefault(pid, {})[c] = (t, i)
    return pk, store, chunks

def containers(paks):
    out = []
    for f in uepak.os.listdir(paks):
        if f.endswith('.utoc'):
            try: out.append(uepak.Toc(os.path.join(paks, f)))
            except (OSError, ValueError, struct.error): pass
    return sorted(out, key=lambda t: uepak.mount_order(t.path))

def mesh_check(a, b, chunks, rename, dec, check):
    """One package for the meshes rule: a, b = (path, toc, chunk index) here and there, chunks = the other platform's chunks of the package → ('take', the other's chunk with its names renamed to
    this platform's) when its name map equals ours after the rename, it has as many exports and is longer (the top LODs the cook stripped); else (the reason, 0), or ('same', 1) for a package that is ours
    byte for byte after the rename (a platform name only; with check, a rename that leaves the head of a same-length chunk different raises Error: it would be wrong)"""
    if any(c[11] != uepak.IO_EXPORT_BUNDLE for c in chunks): return 'bulk', 0
    ds = a[1].read(a[2], dec); dp = b[1].read(b[2], dec)
    if texture_top(dp): return 'texture', 0
    if b'BodySetup' not in (names(dp) or ()): return 'notmesh', 0   # not a mesh: its name map lacks the collision (the materials, lighting and blueprints of this game also differ and grow on the other platform)
    r = rename_names(dp, rename)
    if r is None or names(ds) is None or names(r) != names(ds): return 'names', 0
    if export_span(r) != export_span(ds): return 'exports', 0
    if r == ds: return 'same', 1
    if len(r) <= len(ds):   # not longer: another value in an export (this game's meshes differ in a float or two of the StaticMesh export), nothing stripped
        hs = struct.unpack_from('<I', ds, 4)[0]
        if check and len(r) == len(ds) and r[:hs] != ds[:hs]: raise Error(f'{b[0]}: the renamed head differs from ours at our length: the rename is wrong')
        return 'exports', 0
    return 'take', r

def build_rules(rules, romfs, paks, out, dec):
    """rules = [(preset, rule, pattern)] → report lines; writes the containers under out and the TSVs beside it. dec(bytes, raw size) decodes Oodle"""
    sw_tocs = uepak.io_tocs(romfs); sw_tocs = [t for t in sw_tocs if t.of_type(uepak.IO_CONTAINER_HEADER)]
    if not sw_tocs: raise Error(f'no IoStore container with a container header under {romfs}')
    ot_tocs = containers(paks)
    if not any(t.of_type(uepak.IO_CONTAINER_HEADER) for t in ot_tocs): raise Error(f'no IoStore container with a container header in {paks}')
    sw, sw_store, _ = index(sw_tocs, dec); ot, ot_store, ot_chunks = index(ot_tocs, dec, True)
    main = max(sw_tocs, key=lambda t: len(t.of_type(uepak.IO_EXPORT_BUNDLE)))
    stem = os.path.basename(main.path)[:-5]; name = f'{stem}_99_P'
    dest_rel = os.path.dirname(os.path.relpath(main.path, romfs))
    report = []
    for preset in dict.fromkeys(r[0] for r in rules):
        chosen, skipped = {}, dict.fromkeys(REASONS, 0)   # chosen: package ID → (rule, switch size, other size)
        rename = dict(r[2].split('=') for r in rules if r[0] == preset and r[1] == 'rename'); mesh_data = {}; checked = 0   # mesh_data: package ID → the renamed chunk
        for _, rule, pattern in (r for r in rules if r[0] == preset and r[1] != 'rename'):
            pat = pattern.lower(); hits = [pid for pid, v in sw.items() if fnmatch.fnmatchcase(v[0].lower(), pat)]
            if not hits: raise Error(f'{preset}: {rule} {pattern}: no package matches')
            for pid in hits:
                if pid in chosen: continue
                if pid not in ot: skipped['missing'] += 1; continue
                if sw_store.get(pid) != ot_store.get(pid): skipped['imports'] += 1; continue
                if rule == 'meshes':
                    r = mesh_check(sw[pid], ot[pid], ot_chunks[pid], rename, dec, checked < CHECKED)
                    if r[0] == 'take': chosen[pid] = (rule, None, None); mesh_data[pid] = r[1]
                    else: skipped[r[0]] += 1
                    checked += r[0] == 'same' and r[1]
                    continue
                if sw[pid][1].ranges[sw[pid][2]][1] == ot[pid][1].ranges[ot[pid][2]][1]: skipped['same'] += 1; continue   # the same package length: no mip (or lightmap) was stripped, nothing to gain
                if rule == 'package': chosen[pid] = (rule, None, None); continue
                ha, hb = head(sw[pid][1], sw[pid][2], dec), head(ot[pid][1], ot[pid][2], dec); a, b = texture_top(ha), texture_top(hb)
                if not a or not b: skipped['notex'] += 1
                elif names(ha) is None or names(ha) != names(hb): skipped['names'] += 1   # another name map: platform data besides the texture (PhysXPC, PCD3D_SM5 shader maps) or more exports
                elif a[0] != b[0]: skipped['format'] += 1
                elif b[1] * b[2] <= a[1] * a[2]: skipped['same'] += 1
                else: chosen[pid] = (rule, a, b)
        d = os.path.join(out, preset, dest_rel); stem_path = os.path.join(d, name)
        chunks, tsv = {}, []
        for pid in sorted(chosen):
            rule, a, b = chosen[pid]; n = size = 0
            if rule == 'meshes':
                cid = uepak.io_chunk_id(pid, 0, uepak.IO_EXPORT_BUNDLE); data = mesh_data[pid]
                chunks[cid] = dict(id=cid, size=len(data), blocks=uepak.stored_blocks(data), meta=None); n = 1; size = len(data)
            for cid, (t, i) in (() if rule == 'meshes' else ot_chunks[pid].items()):
                chunks[cid] = dict(id=cid, size=t.ranges[i][1], blocks=t.raw_blocks(i, lazy=True), meta=t.meta(i)); n += 1; size += t.ranges[i][1]
            tsv.append('\t'.join((ot[pid][0], rule, f'{a[1]}x{a[2]}' if a else '-', f'{b[1]}x{b[2]}' if b else '-', str(n), str(size))))
        report_tsv = os.path.join(os.path.dirname(os.path.abspath(out)), f'ue_pc_assets_{preset}.tsv')
        Path(report_tsv).write_text(''.join(l + '\n' for l in tsv), encoding='utf-8')
        os.makedirs(d, exist_ok=True)
        for ext in ('.utoc', '.ucas'):
            if os.path.exists(stem_path + ext): os.remove(stem_path + ext)
        nbytes = 0
        if chosen:
            cid = uepak.io_container_id(name); data = uepak.container_header(cid, [(pid, *ot_store[pid]) for pid in sorted(chosen)])
            chunks[uepak.io_chunk_id(cid, 0, uepak.IO_CONTAINER_HEADER)] = dict(id=uepak.io_chunk_id(cid, 0, uepak.IO_CONTAINER_HEADER), size=len(data), blocks=uepak.stored_blocks(data), meta=None)
            uepak.write_toc(stem_path, name, list(chunks.values())); nbytes = os.path.getsize(stem_path + '.ucas')
        if not os.path.exists(stem_path + '.pak'): uepak.write_pak(stem_path + '.pak', MOUNT, [])
        nt, nm = (sum(1 for v in chosen.values() if v[0] == k) for k in ('textures', 'meshes'))
        report.append(f'{preset}: {len(chosen)} package(s) ({nt} textures, {len(chosen) - nt - nm} packages, {nm} meshes), {len(chunks)} chunks, {nbytes:,} bytes; skipped: '
                      + ', '.join(f'{k} {skipped[k]}' for k in REASONS) + (f'; name-only checked {checked}' if any(r[0] == preset and r[1] == 'meshes' for r in rules) else ''))
    return report

def build(game_id, romfs, paks, out, host, modules):
    import game
    g = game.load(game_id); tsv = g.table('ue_pc_assets.tsv')
    if not tsv.is_file(): raise Error(f'game profile {game_id} has no ue_pc_assets.tsv')
    tocs = uepak.io_tocs(romfs)
    if not tocs:   # a game with no IoStore container: a pak game's packages cannot move between platforms, its texels can (ue_pc_paks.py)
        import ue_pc_paks
        return ue_pc_paks.build(game_id, romfs, paks, out)
    table = rows(tsv)
    if not table: raise Error(f'{tsv} has no rows')
    if any(t.version < 4 for t in tocs):   # Unreal Engine 4.25 (TOC version 2, zen packages against a legacy pak on the PC): the texel data moves, not the packages (ue_pc_zen4.py)
        import ue_pc_zen4
        try: return ue_pc_zen4.build(table, romfs, paks, out)
        except ue_pc_zen4.Error as e: raise Error(str(e))
    dec = uepak.Lazy(lambda: uepak.OodleHost(host, modules, os.environ))
    try: return build_rules(table, romfs, paks, out, dec)
    finally: dec.close()

def main(argv):
    if len(argv) != 6: sys.exit(__doc__ or 'usage: ue_pc_assets.py <game id> <RomFS root> <other platform\'s Paks dir> <out dir> <host> <modules dir>')
    try:
        for line in build(*argv): print(line)
    except (Error, ValueError, OSError) as e:
        sys.exit(f'ue_pc_assets.py: {e}')

if __name__ == '__main__': main(sys.argv[1:])
