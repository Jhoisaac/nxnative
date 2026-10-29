"""Unreal Engine 5 shader maps (uepak.ue5_shader_maps / ue5_global_maps) and the pair rules of shader_split.py, on synthetic packages; no game files or keys.
DM_TEST_KIMETSU2_CHUNKS=<folder of ExportBundleData chunk files> adds the scale guard against Demon Slayer 2's counts (skipped without it)."""
import contextlib
import io
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'dm/gfx/tools'))
sys.path.insert(0, str(REPO / 'dm/tools'))
sys.path.insert(0, str(REPO / 'dm/games'))
os.environ.setdefault('DM_GAME', '0100AD80208A8000')
import uepak
import shader_split as ss

L = uepak.UE5_MAP_LAYOUTS
ROOT_KEY = next(iter(L))
LAY = L[ROOT_KEY]
GLOBAL_KEY = next(iter(uepak.UE5_GLOBAL_LAYOUTS))
SHADER_SIZE = 0xf6
SHADER_TYPES = ['TBasePassVSFNoLightMapPolicy', 'TBasePassPSFNoLightMapPolicy', 'TBasePassPSFNoLightMapPolicySkylight', 'TShadowDepthVSVertexShadowDepth_OutputDepth',
                'TShadowDepthPSPixelShadowDepth_NonPerspectiveCorrect', 'TShadowDepthPSPixelShadowDepth_PerspectiveCorrect', 'FVelocityVS', 'FVelocityPS']
FREQ = [0, 3, 3, 0, 3, 3, 0, 3]   # vertex 0, pixel 3
TYPE_HASH = [0x1000 + 7 * i for i in range(len(SHADER_TYPES))]
SHA = {n: bytes.fromhex(s) for n, (_, s) in LAY.deps.items()}


def ptr(at, target):   # a frozen pointer: the signed 40-bit distance from the pointer to its target, 1 in the low 24 bits
    return struct.pack('<Q', (((target - at) & (1 << 40) - 1) << 24) | 1)


def elem_ptr(at, target):   # a TMemoryImagePtr element: the same distance, a type in the low bits (nonzero, bit 0 set)
    return ptr(at, target)[:1].replace(b'\x01', b'\x09') + ptr(at, target)[1:]


def lslg_record(tag, n):
    code = struct.pack('<I', n) * 4
    ctl = bytearray(0x880); ctl[:4] = bytes.fromhex('34127698'); struct.pack_into('<I', ctl, 0x704, len(code))
    return b'LSLG' + tag + b'\0\0' + struct.pack('<I', len(code)) + code + struct.pack('<I', len(ctl)) + bytes(ctl)


def stream(rec, stored=False):   # the stand-in for Oodle: an 8C 0A header and zlib
    return rec if stored else b'\x8c\x0a' + zlib.compress(rec)


def decode(s, raw):
    out = zlib.decompress(s[2:])
    if len(out) != raw: raise ValueError('size')
    return out


class Img:
    """A frozen image under construction: alloc() returns offsets, put() writes bytes"""
    def __init__(self): self.b = bytearray()
    def alloc(self, n): o = len(self.b); self.b += bytes(n + (-n % 8)); return o
    def put(self, o, data): self.b[o:o + len(data)] = data
    def array(self, at, first, n): self.put(at, ptr(at, first) + struct.pack('<ii', n, n)) if n else None


def shader_obj(img, freq, entry):
    o = img.alloc(SHADER_SIZE)
    img.put(o + LAY.target, struct.pack('<II', freq | 0x26 << 4, entry))
    return o


def sub_map(img, base, vf, shaders, pipes):
    """shaders [(type index, permutation, object offset)], pipes [(type hash, {slot: object offset})] written at the frozen object `base`"""
    if shaders:
        st, pm, sh = img.alloc(8 * len(shaders)), img.alloc(4 * len(shaders)), img.alloc(8 * len(shaders))
        for j, (ti, perm, o) in enumerate(shaders):
            img.put(st + 8 * j, struct.pack('<Q', TYPE_HASH[ti])); img.put(pm + 4 * j, struct.pack('<i', perm)); img.put(sh + 8 * j, elem_ptr(sh + 8 * j, o))
        img.array(base + LAY.types, st, len(shaders)); img.array(base + LAY.perms, pm, len(shaders)); img.array(base + LAY.shaders, sh, len(shaders))
    if pipes:
        pa = img.alloc(8 * len(pipes))
        for j, (th, slots) in enumerate(pipes):
            po = img.alloc(68); img.put(po, struct.pack('<Q', th)); img.put(pa + 8 * j, elem_ptr(pa + 8 * j, po))
            for slot, o in slots.items(): img.put(po + slot, elem_ptr(po + slot, o))
        img.array(base + LAY.pipes, pa, len(pipes))
    if vf is not None: img.put(base + LAY.vf, struct.pack('<Q', vf))


def build_image():
    """The test material's frozen image: a root with two mesh shader maps. Entries: sub-map 1 holds shaders 0-5 (entries 0-5), sub-map 2 the same types (entries 6-11); a pipeline 0x777 in sub-map 1 with
    FVelocityVS / FVelocityPS (entries 12, 13) and a vertex-only pipeline 0x888 (entry 14). → (image bytes, entries' frequencies)"""
    img = Img(); root = img.alloc(0x68 + 8); m1, m2 = img.alloc(0x68), img.alloc(0x68); arr = img.alloc(16)
    img.put(root, ptr(root, m1))   # the hash table pointer the image starts with
    img.put(arr, elem_ptr(arr, m1)); img.put(arr + 8, elem_ptr(arr + 8, m2))
    img.array(root + LAY.meshes, arr, 2)
    objs = [shader_obj(img, FREQ[ti], 6 * s + ti) for s in range(2) for ti in range(6)]
    vv, vp, vo = shader_obj(img, 0, 12), shader_obj(img, 3, 13), shader_obj(img, 0, 14)
    sub_map(img, m1, 0xAA, [(ti, 0, objs[ti]) for ti in range(6)], [(0x777, {8: vv, 0x20: vp}), (0x888, {8: vo})])
    sub_map(img, m2, 0xBB, [(ti, 0, objs[6 + ti]) for ti in range(6)], [])
    return bytes(img.b)


def entries(n=15, stored=()):
    """n code entries: the LSLG record of entry i has code of its own; frequency from the test layout"""
    freqs = [FREQ[ti] for ti in range(6)] * 2 + [0, 3, 0]
    out, tags = [], {0: b'SV', 3: b'SP'}
    for i in range(n):
        rec = lslg_record(tags[freqs[i]], i + 1)
        out.append((stream(rec, i in stored), len(rec), freqs[i], bytes([i + 1]) * 20))
    return out


def package(layout_sha=None, entries_=None, corrupt=None, tables=1, image=None):
    """A Zen-less chunk with `tables` shader map images, the first with a name table: name table, filler, FrozenSize, image, layout table, pointer table, patches, resource code"""
    ents = entries_ or entries()
    names = ['FMaterialShaderMapContent', 'FHashedName', 'FMeshMaterialShaderMap', 'FShaderPipeline'] + SHADER_TYPES + ['MyParameter', 'SP_GLSL_SWITCH']
    rows = [('FMaterialShaderMapContent', 572, ROOT_KEY[2]), ('FHashedName', *LAY.deps['FHashedName']), ('FMeshMaterialShaderMap', *LAY.deps['FMeshMaterialShaderMap']),
            ('FShaderPipeline', *LAY.deps['FShaderPipeline'])] + [(n, SHADER_SIZE, '%040x' % (i + 1)) for i, n in enumerate(SHADER_TYPES)]
    if layout_sha: rows[0] = ('FMaterialShaderMapContent', 572, layout_sha)
    img = image or build_image()
    out = bytearray(b'prefix-of-the-package' + bytes(7))
    for t in range(tables):
        if t == 0:
            out += struct.pack('<I', len(names))
            for n in names: out += struct.pack('<I', len(n) + 1) + n.encode() + b'\0' + struct.pack('<I', 0x1234)
            out += bytes(63)
        out += struct.pack('<I', len(img)) + img
        out += struct.pack('<I', len(rows))
        for i, (_, size, sha) in enumerate(rows): out += struct.pack('<QI', i, size) + bytes.fromhex(sha)
        out += struct.pack('<II', len(SHADER_TYPES), 2) + b''.join(struct.pack('<Q', h) for h in TYPE_HASH) + struct.pack('<QQ', 0xAA, 0xBB)
        out += struct.pack('<II', 0, 3) + bytes(48)   # the FMemoryImageName patches
        n = len(ents); cnt2 = n if corrupt != 'count' else n + 1
        out += struct.pack('<I', n) + b''.join(h for _, _, _, h in ents) + struct.pack('<I', cnt2)
        for s, raw, fr, _ in ents: out += struct.pack('<I', len(s)) + s + struct.pack('<iB', raw, fr)
        out += bytes(16)   # between maps / after the last
    return bytes(out)


def fake_key(mp, i): return f'k{i:02d}'


class Maps(unittest.TestCase):
    def read(self, d, **kw):
        reds, seen, st = [], {}, __import__('collections').Counter()
        ms = uepak.ue5_shader_maps(d, 'test', reds.append, stats=st, seen=seen, **kw)
        return ms, reds, seen, st

    def test_chunk_without_a_map_gives_nothing(self):
        ms, reds, seen, st = self.read(b'\0' * 1000 + b'no shader map here')
        self.assertEqual((ms, reds, seen, dict(st)), ([], [], {}, {}))

    def test_map_structure(self):
        ms, reds, seen, st = self.read(package())
        self.assertEqual((reds, seen), ([], {}))
        self.assertEqual(len(ms), 1)
        m = ms[0]
        self.assertEqual((m['root'], m['layout']), ('FMaterialShaderMapContent', ROOT_KEY[2]))
        self.assertEqual(m['types'], dict(zip(TYPE_HASH, SHADER_TYPES)))   # the shader types are the rows of the shader size
        root, s1, s2 = m['submaps']
        self.assertEqual((root['vf'], root['shaders'], root['pipes']), (0, [], []))
        self.assertEqual(s1['vf'], 0xAA)
        self.assertEqual(s1['shaders'], [(TYPE_HASH[ti], 0, FREQ[ti], ti) for ti in range(6)])
        self.assertEqual(s1['pipes'], [(0x777, {0: 12, 3: 13}), (0x888, {0: 14})])
        self.assertEqual((s2['vf'], s2['shaders'][0], s2['pipes']), (0xBB, (TYPE_HASH[0], 0, 0, 6), []))
        self.assertEqual([e[2:] for e in m['entries']][:2], [(len(lslg_record(b'SV', 1)), 0), (len(lslg_record(b'SP', 2)), 3)])
        self.assertEqual(m['hashes'][3], bytes([4]) * 20)

    def test_entries_decode_and_stored_entries(self):
        ms, *_ = self.read(package(entries_=entries(stored={1})))
        m = ms[0]
        rec = uepak.ue5_entry(m, 0, decode)
        self.assertEqual(rec, lslg_record(b'SV', 1))
        self.assertEqual(uepak.ue5_entry(m, 1, decode), lslg_record(b'SP', 2))   # the record itself, no decoder
        self.assertEqual((uepak.lslg(rec) or ('',))[0], 'SV')

    def test_double_count_mismatch_drops_the_map(self):
        d = package(corrupt='count') + package()
        ms, reds, seen, st = self.read(d)
        self.assertEqual(len(ms), 1)   # the damaged run is no resource code, the second chunk's map is read
        self.assertTrue(st['no resource code'] or st['pointer table'])

    def test_unknown_layout_is_reported_not_walked(self):
        ms, reds, seen, st = self.read(package(layout_sha='ab' * 20))
        self.assertEqual((ms, reds), ([], []))
        self.assertEqual(list(seen), [('FMaterialShaderMapContent', 572, 'ab' * 20)])
        line = uepak.unknown_layout(*next(iter(seen.items())), L)
        self.assertTrue(line.startswith('[RED] test: FMaterialShaderMapContent layout ' + 'ab' * 20))
        self.assertIn(ROOT_KEY[2][:12], line)

    def test_frequency_mismatch_drops_the_whole_map(self):
        img = bytearray(build_image())
        at = img.find(struct.pack('<II', 3 | 0x260, 1))   # shader 1 (a pixel shader)
        img[at:at + 4] = struct.pack('<I', 0 | 0x260)
        ms, reds, seen, st = self.read(package(image=bytes(img)))
        self.assertEqual(ms, [])
        self.assertEqual(len(reds), 1)
        self.assertIn('frequency 0 but its code entry says 3', reds[0])
        self.assertIn('give no pairs', reds[0])

    def test_pointer_checks(self):
        img = bytearray(build_image())
        # the mesh shader map array's data pointer: low bits other than 1 are not a pointer of this layout
        v = struct.unpack_from('<Q', img, LAY.meshes)[0]; struct.pack_into('<Q', img, LAY.meshes, (v & ~0xffffff) | 0x5)
        ms, reds, seen, st = self.read(package(image=bytes(img)))
        self.assertEqual((ms, len(reds)), ([], 1)); self.assertIn('low bits 0x5', reds[0])
        # bit 0 clear is null: an array with elements and a null pointer is refused
        struct.pack_into('<Q', img, LAY.meshes, 0)
        ms, reds, *_ = self.read(package(image=bytes(img)))
        self.assertEqual((ms, len(reds)), ([], 1)); self.assertIn('is null', reds[0])

    def test_negative_pointer_deltas(self):
        # the shader objects lie after the pointers that name them, so the second sub-map's arrays point forward and the pipelines' slots point back to nothing: check a backward one directly
        img = Img(); a = img.alloc(16); b = img.alloc(16)
        img.put(b, ptr(b, a))   # b points back to a
        f = uepak._Frozen(bytes(img.b), 0, len(img.b))
        self.assertEqual(f.ptr(b), a)
        self.assertIsNone(f.ptr(a))   # bit 0 clear: null

    def test_second_image_without_a_name_table(self):
        ms, reds, seen, st = self.read(package(tables=2))
        self.assertEqual((len(ms), reds), (2, []))
        self.assertEqual(ms[1]['types'], ms[0]['types'])

    def test_second_image_with_another_layout_is_reported(self):
        d = bytearray(package(tables=2))
        k = d.rfind(bytes.fromhex(LAY.deps['FHashedName'][1]))   # the second image's FHashedName row
        d[k] ^= 0xff
        ms, reds, seen, st = self.read(bytes(d))
        self.assertEqual(len(ms), 1)
        self.assertEqual(len(reds), 1); self.assertIn('without a name table', reds[0])
        self.assertEqual(st['unnamed image, other layout'], 1)

    def test_dependent_type_layout_is_gated(self):
        d = bytearray(package())
        k = d.find(bytes.fromhex(LAY.deps['FMeshMaterialShaderMap'][1])); d[k] ^= 0xff
        ms, reds, seen, st = self.read(bytes(d))
        self.assertEqual(ms, []); self.assertEqual(len(reds), 1); self.assertIn('FMeshMaterialShaderMap layout', reds[0])


def zen(path, exports=((b'\0' * 40),)):
    names = ['/Script/Engine', path]
    out = bytearray()
    out += struct.pack('<I', len(names)) + struct.pack('<I', sum(map(len, names))) + struct.pack('<Q', 0xC164000000000000)
    out += b''.join(struct.pack('<Q', i) for i in range(len(names))) + b''.join(struct.pack('>H', len(n)) for n in names) + b''.join(n.encode() for n in names)
    names_end = 0x34 + len(out)
    ex = names_end; exe = ex + 72 * len(exports)
    hsz = exe + 16
    s = struct.pack('<13I', 0, hsz, 1, 0, 0x80002200, 0x100, 0x80, 0x80, ex, exe, exe, exe, exe)
    body = bytearray(); table = bytearray()
    off = 0
    for e in exports:
        table += struct.pack('<QQIIQQQQQIB3x', off, len(e), 1, 0, 0, 0, 0, 0, 0, 0, 0); body += e; off += len(e)
    return bytes(s + out + table + bytes(16) + body), hsz


class Zen(unittest.TestCase):
    def test_header(self):
        d, hsz = zen('/Game/Art/MI_Test', exports=(b'A' * 40, b'B' * 24))
        h = uepak.zen_header(d) or {'names': [], 'exports': []}
        self.assertEqual(h['names'][-1:], ['/Game/Art/MI_Test'])
        self.assertEqual(h['exports'], [(hsz, 40, 1), (hsz + 40, 24, 1)])
        self.assertEqual(d[h['exports'][1][0]:h['exports'][1][0] + 24], b'B' * 24)

    def test_truncated_or_foreign_data_is_none(self):
        d, _ = zen('/Game/X')
        self.assertIsNone(uepak.zen_header(d[:60]))
        self.assertIsNone(uepak.zen_header(d[:-30]))   # an export range beyond the chunk
        self.assertIsNone(uepak.zen_header(b'\1' * 200))


class Pairs(unittest.TestCase):
    def maps(self):
        return uepak.ue5_shader_maps(package(), 'test', lambda m: None)

    def test_pass_families(self):
        f = ss.ue_pass_family
        self.assertEqual(f('TBasePassVSFNoLightMapPolicy'), f('TBasePassPSFNoLightMapPolicySkylight'))
        self.assertNotEqual(f('TBasePassVSFNoLightMapPolicy'), f('TBasePassPSTLightMapPolicyHQ'))
        self.assertEqual(f('TShadowDepthVSVertexShadowDepth_OutputDepth'), f('TShadowDepthPSPixelShadowDepth_NonPerspectiveCorrect'))
        self.assertNotEqual(f('TShadowDepthVSVertexShadowDepth_OutputDepth'), f('TShadowDepthPSPixelShadowDepth_PerspectiveCorrect'))
        self.assertEqual(f('TDepthOnlyVS<true>'), f('FDepthOnlyPS'))
        self.assertEqual(f('FPostProcessMaterialVS'), f('FPostProcessMaterialPS'))
        self.assertEqual(f('FCloudRenderViewPS010'), ('f', 'CloudRenderView'))
        self.assertEqual(f('TVoxelizeVolumeVS<A_B>'), f('TVoxelizeVolumePS<A_B>'))
        self.assertIsNone(f('SomethingElse'))

    def test_map_pairs(self):
        m = self.maps()[0]
        un, orph, pp = set(), set(), __import__('collections').defaultdict(set)
        a, pl = ss.ue_map_pairs(m, lambda i: fake_key(m, i), (), un, orph, pp)
        # sub-map 1: VS 0 (basepass) with PS 1 and 2; VS 3 (shadow OutputDepth) with PS 4, not PS 5; sub-map 2 the same with entries 6..11: no pair across sub-maps
        self.assertEqual(a, {('k00', 'k01'), ('k00', 'k02'), ('k03', 'k04'), ('k06', 'k07'), ('k06', 'k08'), ('k09', 'k10')})
        self.assertEqual(pl, {('k12', 'k13')})   # the VS+PS pipeline; the vertex-only one gives none
        self.assertEqual((un, dict(pp)), (set(), {0x777: {('k12', 'k13')}}))
        # the pixel shaders PerspectiveCorrect (entries 5, 11) have no vertex shader of their family: candidates for a global one
        self.assertEqual(orph, {(ss.ue_pass_family('TShadowDepthPSPixelShadowDepth_PerspectiveCorrect'), 'k05'), (ss.ue_pass_family('TShadowDepthPSPixelShadowDepth_PerspectiveCorrect'), 'k11')})

    def test_skip_pipelines_and_unmatched(self):
        m = self.maps()[0]
        a, pl = ss.ue_map_pairs(m, lambda i: fake_key(m, i), {0x777})
        self.assertEqual(pl, set())
        m['types'][TYPE_HASH[0]] = 'WeirdName'
        un = set()
        a, _ = ss.ue_map_pairs(m, lambda i: fake_key(m, i), (), un)
        self.assertEqual(un, {'WeirdName'}); self.assertNotIn(('k00', 'k01'), a)

    def test_determinism(self):
        m = self.maps()[0]
        a1, p1 = ss.ue_map_pairs(m, lambda i: fake_key(m, i))
        m['submaps'][1]['shaders'].reverse(); m['submaps'].reverse()
        a2, p2 = ss.ue_map_pairs(m, lambda i: fake_key(m, i))
        self.assertEqual((sorted(a1), sorted(p1)), (sorted(a2), sorted(p2)))

    def test_global_stems(self):
        def sm(types):
            return dict(types={i: n for i, n in enumerate(types)}, submaps=[dict(vf=0, shaders=[(i, 0, 0 if n.endswith('VS') else 3, i) for i, n in enumerate(types)], pipes=[])])
        mp = sm(['FFilterVS', 'FFilterPS', 'FScreenPassVS', 'FUpscalePS', 'FDeferredDecalVS'])
        key = lambda m, i: f'g{i}'
        pairs, by_fam, fs = ss.ue_global_pairs([mp], key)
        self.assertEqual(fs, {'g2'})
        self.assertEqual(pairs, {('g0', 'g1'), ('g2', 'g1'), ('g2', 'g3')})   # FUpscalePS has no FUpscaleVS: only the full-screen one
        self.assertEqual(by_fam[ss.ue_pass_family('FDeferredDecalVS')], {'g4'})
        self.assertEqual(ss.ue_orphan_pairs({(ss.ue_pass_family('FDeferredDecalPS'), 'm1'), (('f', 'Nothing'), 'm2')}, by_fam, fs), {('g4', 'm1'), ('g2', 'm2')})


def global_cache(rows, entries_, sections=1, shaders=()):
    """GlobalShaderCache bytes: u32 count, then per section ff ff ff ff, u32 1, FrozenSize, the image, the named layout table, the pointer table and the resource code"""
    out = bytearray(struct.pack('<I', sections))
    for _ in range(sections):
        img = Img(); root = img.alloc(104)
        objs = [shader_obj(img, fr, i) for i, fr in enumerate(shaders)]
        sub_map(img, root, None, [(i, 0, o) for i, o in enumerate(objs)], [])
        out += b'\xff\xff\xff\xff' + struct.pack('<II', 1, len(img.b)) + bytes(img.b)
        out += struct.pack('<I', len(rows))
        for n, size, sha in rows: out += struct.pack('<I', len(n) + 1) + n.encode() + b'\0' + struct.pack('<I', size) + bytes.fromhex(sha)
        out += struct.pack('<II', len(shaders), 0) + b''.join(struct.pack('<Q', TYPE_HASH[i]) for i in range(len(shaders)))
        out += struct.pack('<II', 0, 0)
        out += struct.pack('<I', len(entries_)) + b''.join(h for _, _, _, h in entries_) + struct.pack('<I', len(entries_))
        for s, raw, fr, _ in entries_: out += struct.pack('<I', len(s)) + s + struct.pack('<iB', raw, fr)
    return bytes(out)


class Global(unittest.TestCase):
    def test_sections(self):
        rows = [('FGlobalShaderMapContent', 104, GLOBAL_KEY[2]), ('FHashedName', 8, LAY.deps['FHashedName'][1]), ('FFilterVS', SHADER_SIZE, '01' * 20), ('FFilterPS', SHADER_SIZE, '02' * 20)]
        # the types array of the test image has TYPE_HASH[0..1]; the layout rows give two shader types
        ents = [(stream(lslg_record(b'SV', 1)), len(lslg_record(b'SV', 1)), 0, b'\x01' * 20), (stream(lslg_record(b'SP', 2)), len(lslg_record(b'SP', 2)), 3, b'\x02' * 20)]
        rows = [(rows[0][0], 104, GLOBAL_KEY[2]), (rows[1][0], 8, LAY.deps['FHashedName'][1]), rows[2], rows[3]]
        d = global_cache([(n, s if i != 0 else 104, sha) for i, (n, s, sha) in enumerate(rows)], ents, sections=2, shaders=[0, 3])
        reds, st = [], __import__('collections').Counter()
        ms = uepak.ue5_global_maps(d, 'GlobalShaderCache', reds.append, stats=st)
        self.assertEqual((len(ms), reds), (2, []))
        self.assertEqual(ms[0]['types'], {TYPE_HASH[0]: 'FFilterVS', TYPE_HASH[1]: 'FFilterPS'})
        self.assertEqual(ms[0]['submaps'][0]['shaders'], [(TYPE_HASH[0], 0, 0, 0), (TYPE_HASH[1], 0, 3, 1)])
        pairs, _, fs = ss.ue_global_pairs(ms, lambda m, i: f'g{i}')
        self.assertEqual(pairs, {('g0', 'g1')})

    def test_unknown_global_layout(self):
        rows = [('FGlobalShaderMapContent', 104, 'cd' * 20), ('FHashedName', 8, LAY.deps['FHashedName'][1]), ('FFilterVS', SHADER_SIZE, '01' * 20)]
        ents = [(stream(lslg_record(b'SV', 1)), len(lslg_record(b'SV', 1)), 0, b'\x01' * 20)]
        d = global_cache(rows, ents, sections=1, shaders=[0])
        reds, seen = [], {}
        ms = uepak.ue5_global_maps(d, 'G', reds.append, seen=seen)
        self.assertEqual((ms, reds), ([], []))
        self.assertEqual(list(seen), [('FGlobalShaderMapContent', 104, 'cd' * 20)])


class Jobs(unittest.TestCase):
    """ue5_map_jobs: no job for a game without UE5 inline shaders, one per run of chunks otherwise, encrypted containers refused"""
    def container(self, root, name, version=8, encrypted=False, n=3):
        from test_uepak_iostore import container, chunk_id
        return container(root, name, [(chunk_id(i, uepak.IO_EXPORT_BUNDLE), b'x' * 100) for i in range(n)], encrypted=encrypted, version=version)

    def test_jobs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = self.container(root, 'a.utoc'); b = self.container(root, 'old.utoc', version=2); c = self.container(root, 'enc.utoc', encrypted=True)
            files = [(str(p), p.name) for p in (a, b, c)] + [(str(a.with_suffix('.ucas')), 'a.ucas')]
            self.assertEqual(ss.ue5_map_jobs(files, False), ([], set()))
            with contextlib.redirect_stdout(io.StringIO()) as out: jobs, taken = ss.ue5_map_jobs(files, True, parts=1)
            self.assertIn('enc.utoc: the container is encrypted', out.getvalue())
            self.assertEqual([(j[1], j[2][0]) for j in jobs], [('a.utoc', ss.UE5_MAPS)] * len(jobs))
            self.assertEqual(sorted(i for j in jobs for i in j[2][1]), [0, 1, 2])
            self.assertIn(str(a.with_suffix('.ucas')), taken); self.assertNotIn(str(b), taken); self.assertNotIn(str(c), taken)


class Scale(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('DM_TEST_KIMETSU2_CHUNKS'), 'DM_TEST_KIMETSU2_CHUNKS is not set')
    def test_kimetsu2_counts(self):
        d = Path(os.environ['DM_TEST_KIMETSU2_CHUNKS']); maps = sub = shaders = pipes = 0; reds = []
        for p in sorted(d.iterdir()):
            for m in uepak.ue5_shader_maps(p.read_bytes(), p.name, reds.append):
                maps += 1; sub += len(m['submaps']); shaders += sum(len(s['shaders']) for s in m['submaps']); pipes += sum(len(s['pipes']) for s in m['submaps'])
        self.assertEqual(reds, [])
        self.assertGreaterEqual(maps, 16862); self.assertGreaterEqual(shaders, 647855); self.assertGreaterEqual(pipes, 132638)


if __name__ == '__main__':
    unittest.main()
