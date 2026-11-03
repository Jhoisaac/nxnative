#!/usr/bin/env python3
# Unreal Engine game files for the shader tools: pak files (versions 4, 7, 8, 9 and 11: UE 4.18 to 4.25 and 4.26 and later; Octopath Traveler 0 is UE5), shader code archives (.ushaderbytecode version 2) and the job files the Mac host decodes Oodle with
# (DM_OODLE_JOB, dm/host/hle_oodle.c). Octopath Traveler 0 keeps everything in one pak, Octopath_Traveler0/Content/Paks/pakchunk0-Switch.pak (1.5 GB, 159,757 files): its index is AES-256 encrypted,
# its files are stored or Oodle-compressed in blocks. Its two shader code archives are stored, but every shader inside is Oodle-compressed (Mermaid, block header 8C 0A), which no decoder in this
# repository can undo, so the game's own OodleLZ_Decompress decodes them in the Mac host (the NSP script's decode_ue_shaders, for any game with Unreal paks).
# Unreal Engine 4.27 (DRAGON QUEST VII Reimagined) keeps its packages in IoStore containers (.utoc / .ucas) and the rest in pakchunk0-Switch.pak (3,972 files, index not encrypted), among them
#   two stored shader code archives (ShaderArchive-Global-SF_GLSL_SWITCH, 1,764 shaders, and ShaderArchive-DOLL_Chunk0-SF_GLSL_SWITCH, 63,185): every shader in them is an LZ4 block, the
#   engine's default shader compression since 4.26, decoded here (lz4_shaders) without the host.
# Unreal Engine 5.6 (FINAL FANTASY RESONANCE) has no shader code archive in its pak (FFRS-Switch.pak holds configs only): the cooker converted both libraries into its IoStore container
#   (FFRS-Switch.utoc / .ucas, Oodle in 64 KB blocks, not encrypted) as one ShaderCodeLibrary chunk each (the tables) and one ShaderCode chunk per group of shaders, every group Oodle-compressed
#   on its own (Toc, io_archive). Both layers need the game's decoder, which runs in the Mac host's tool mode (OodleHost); the libraries come out as version 2 archives with every shader decoded.
# Unreal Engine 5 without shared material shader code (Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles 2) has neither: each shader map is inline in its cooked package's exports
#   (ExportBundleData chunks of eleven IoStore containers) and the engine's in Engine/GlobalShaderCache-SP_GLSL_SWITCH.bin of pakchunk0-Switch.pak, every shader one Oodle stream; they are
#   found by scanning (ue5_inline_shaders), decoded through the same OodleHost and written as version 2 archives too (inline_archives: 2,854 + 113,444 shaders).
#   The shader maps also say which vertex and pixel shaders belong together: ue5_shader_maps / ue5_global_maps read them (the frozen FMemoryImage of each map, gated by its type layout hashes) for
#   shader_split.py's pso_pairs.tsv.
# The AES key is in main (Unreal embeds it): the 32-byte window of main's read-only or data segment that decrypts the index start to its mount point ("../../../"; Octopath Traveler 0: one window of
#   116,287 tried). It is only kept in memory, never printed or written.
# Pak footer (version 11, the last 0xdd bytes): encryption key GUID (16), encrypted index flag (u8), magic 0x5A6F12E1, version (u32), index offset (u64), index size (u64), index SHA-1 (20),
#   5 compression method names (32 bytes each).
# Index: mount point (FString), entry count (i32), path hash seed (u64), path hash index (i32 flag, then u64 offset, u64 size, SHA-1), full directory index (the same, encrypted like the index),
#   encoded entries (i32 size + bytes), the count of unencoded entries (0 here). Directory index: i32 count, then per directory its name (FString) and its files (i32 count, then name + i32 offset into
#   the encoded entries). FString: i32 length with the NUL, UTF-8; a negative length is UTF-16.
# Encoded entry: u32 bits (0-5 compression block size >> 11, 0x3f = a u32 follows; 6-21 block count; 22 encrypted; 23-28 compression method, 1-based; 29 stored size fits 32 bits; 30 raw size fits
#   32 bits; 31 offset fits 32 bits), then offset, raw size, stored size (compressed entries only) and, for several blocks or an encrypted one, each block's u32 stored size. The data starts after
#   the FPakEntry the pak repeats in front of it (53 bytes, + 4 + 16 per block when compressed); blocks follow each other, 16-aligned when encrypted.
# Older paks (version 4, UE 4.18: DRAGON QUEST XI S, pakchunk0-Switch.pak 6.6 GB / 264,844 files and pakchunk1-Switch.pak 7.2 GB / 147,824 files, the update's *_0_P.pak beside them) keep the
#   legacy layout. Footer (the last 0x2d bytes): encrypted index flag (u8), magic, version, index offset, index size, SHA-1. Index: mount point, entry count, then per file its name (relative to the
#   mount point) and its FPakEntry: offset, stored size, raw size (i64 each), compression flags (i32), SHA-1 (20), for a compressed file the block count (i32) and each block's start and end
#   (i64, from the file start before version 5, from the entry after), the encrypted flag (u8) and the compression block size (u32). The FPakEntry is repeated in front of the data.
#   The compression flags are no names: 1 zlib, 2 gzip, 4 custom; DRAGON QUEST XI S's engine uses 3, which is LZ5 2.0 (main exports LZ5_*; every block starts with its level, 0x2d = 45), and only the
#   game's own decoder reads it (hle_oodle.c, through a decode function given to Pak.read).
# Versions 7 (UE 4.21/4.22: the footer adds the key GUID in front of the flag, still read from its last 0x2d bytes), 8 (UE 4.23/4.24: the footer ends with five 32-byte method names, magic 0xcc from the
#   end, and an entry's method is 1-based into them) and 9 (UE 4.25: magic 0xcd from the end, a u8 frozen index flag between the SHA-1 and the names) keep that per-file index; a version 9 pak may write it
#   as a frozen memory image instead (Pak.frozen). Shaders are zlib streams in 4.21 to 4.24 and LZ4 blocks in 4.25. UE 4.25 also keeps packages in IoStore containers (TOC version 2, ExportBundleData is type 2).
# Unreal Engine 4.27 with bShareMaterialShaderCode off (OCTOPATH TRAVELER II: Majesty/Content/Paks/Majesty-Switch.pak, version 11, 3.3 GB / 376,601 files, index not encrypted, Zlib blocks)
#   has no shader code archive at all: each material keeps its shaders in its own cooked package (.uexp) and the engine's global shaders are in Engine/GlobalShaderCache-SF_GLSL_SWITCH.bin,
#   every shader an LSLG record stored without compression, as in a legacy pak (inline_shaders; shader_split.py ue_legacy_jobs reads them). Zlib and LZ4 blocks are decoded here (Pak.read).
# Writing (write_pak, for dm/tools/ue_quality.py's replacement paks): version 11, nothing compressed or encrypted, the mount point given, one FPakEntry in front of each file's data, and the
#   index with the encoded entries (bits 29-31 set: offset, raw size fit 32 bits; method 0) and a FULL DIRECTORY INDEX that also lists every parent directory (the engine looks a file up by walking
#   its directories, and an empty parent entry is what lets it find "A/B/C/f" under "A/" and "A/B/"). No path hash index is written (flag 0): the engine falls back to the directory index, and
#   the hash (CityHash64 of the lower-case path with a seed) is then not needed. The index is two blocks, primary then directory; the primary holds the directory index's own offset, so it is built twice.
#   Versions 4, 7, 8 and 9 write the legacy layout above: the per-file index in one block, each entry's FPakEntry with method 0 and no blocks, the footer of that version (a version 9 pak with the frozen flag clear).
# Writing an IoStore container (write_toc, for a patch container the game mounts over its own: Unreal's loader gives a container mounted later, such as <stem>_P.utoc, priority over the earlier ones):
#   TOC version 5, blocks of 64 KB, no directory index (size 0, flag 8 clear), no encryption or signing; flag 1 when any block is Oodle-compressed (method names: "Oodle" only). The chunks are stored in
#   perfect hash slot order (io_perfect_hash: seed count ceil(n / 2), no overflow list), each chunk's offset in the uncompressed stream a multiple of 64 KB, its blocks in the .ucas 16-aligned.
#   After the blocks and method names come the chunk metas (32-byte chunk hash, u8 flags) the engine reads for every chunk. container_header builds the container header chunk (type 6, version 3).
# Shader code archive (version 2): shader map hashes (20 bytes each), shader hashes (20 each), shader map entries {u32 first index, u32 shader count, u32 first preload, u32 preload count}, shader
#   entries {u64 offset, u32 size, u32 raw size, u8 frequency} (17 bytes, packed), preload entries (16 each), shader indices (u32): each array is a u32 count and its elements; the code follows,
#   offsets relative to its start. A shader whose size differs from its raw size is compressed.
# Usage: uepak.py list <pak> <main NSO> <out tsv>                       every file in the pak: path, raw size, stored size, compression, encrypted, blocks
#        uepak.py job <RomFS> <main NSO> <work dir> [<Mac host> <rewritten modules>]   the shader code archives of every pak, and an Oodle job of their Oodle-compressed shaders (LZ4 ones
#                                                                       decoded at once); IoStore shader libraries (UE 5.6) decoded at once through the game's Oodle in the host (OodleHost)
#        uepak.py finish <work dir> <out dir>                           after the host has run the job: the archives with every shader decoded
import collections, ctypes, json, os, re, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../tools'))
from romfs import os, open

PAK_MAGIC, ARCHIVE_VERSION = 0x5A6F12E1, 2
JOB_MAGIC, OUT_MAGIC = 0x4a4f4d44, 0x524f4d44   # "DMOJ", "DMOR" (hle_oodle.c)
FREQ = {0: 'vs', 1: 'hs', 2: 'ds', 3: 'ps', 4: 'gs', 5: 'cs'}   # EShaderFrequency (the archive's frequency census: 0 vertex, 3 pixel, 5 compute)

_cc = None
def aes_decrypt(key, data):
    """AES-256 ECB decryption through CommonCrypto (every Mac has it; no Python package needed)"""
    global _cc
    if _cc is None:
        _cc = ctypes.CDLL('/usr/lib/libSystem.B.dylib').CCCrypt
        _cc.restype = ctypes.c_int32
        _cc.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    out = ctypes.create_string_buffer(len(data)); moved = ctypes.c_size_t()
    if _cc(1, 0, 2, key, len(key), None, data, len(data), out, len(data), ctypes.byref(moved)): raise ValueError('CCCrypt failed')   # decrypt, AES, ECB
    return out.raw[:moved.value]

_M, _K0, _K1, _K2 = (1 << 64) - 1, 0xc3a5c85c97cb3127, 0xb492b66fbe98f273, 0x9ae16a3b2f90404f
def _rot(v, s): return ((v >> s) | (v << (64 - s))) & _M if s else v
def _f64(s, i): return struct.unpack_from('<Q', s, i)[0]
def _bswap(v): return int.from_bytes((v & _M).to_bytes(8, 'little'), 'big')
def _h16(u, v, mul=0x9ddfea08eb382d69):
    a = ((u ^ v) * mul) & _M; a ^= a >> 47
    b = ((v ^ a) * mul) & _M; b ^= b >> 47
    return (b * mul) & _M
def _weak(s, i, a, b):
    w, x, y, z = _f64(s, i), _f64(s, i + 8), _f64(s, i + 16), _f64(s, i + 24)
    a = (a + w) & _M; b = _rot((b + a + z) & _M, 21); c = a
    a = (a + x + y) & _M; b = (b + _rot(a, 44)) & _M
    return ((a + z) & _M, (b + c) & _M)
def city64(s):
    """CityHash64 (Google's CityHash 1.1, the one Unreal's Core links; checked against python-cityhash 0.4.10 on 1,500 random inputs of 0 to 299 bytes)"""
    n = len(s)
    if n <= 16:
        if n >= 8:
            mul = _K2 + n * 2; a = (_f64(s, 0) + _K2) & _M; b = _f64(s, n - 8)
            return _h16((_rot(b, 37) * mul + a) & _M, ((_rot(a, 25) + b) * mul) & _M, mul)
        if n >= 4:
            mul = _K2 + n * 2
            return _h16((n + (struct.unpack_from('<I', s, 0)[0] << 3)) & _M, struct.unpack_from('<I', s, n - 4)[0], mul)
        if n:
            y, z = s[0] + (s[n >> 1] << 8), n + (s[n - 1] << 2); v = ((y * _K2) ^ (z * _K0)) & _M
            return ((v ^ (v >> 47)) * _K2) & _M
        return _K2
    mul = _K2 + n * 2
    if n <= 32:
        a = (_f64(s, 0) * _K1) & _M; b = _f64(s, 8); c = (_f64(s, n - 8) * mul) & _M; d = (_f64(s, n - 16) * _K2) & _M
        return _h16((_rot((a + b) & _M, 43) + _rot(c, 30) + d) & _M, (a + _rot((b + _K2) & _M, 18) + c) & _M, mul)
    if n <= 64:
        a = (_f64(s, 0) * _K2) & _M; b = _f64(s, 8); c = _f64(s, n - 24); d = _f64(s, n - 32)
        e = (_f64(s, 16) * _K2) & _M; f = (_f64(s, 24) * 9) & _M; g = _f64(s, n - 8); h = (_f64(s, n - 16) * mul) & _M
        u = (_rot((a + g) & _M, 43) + (_rot(b, 30) + c) * 9) & _M; v = (((a + g) ^ d) + f + 1) & _M
        w = (_bswap((u + v) * mul) + h) & _M; x = (_rot((e + f) & _M, 42) + c) & _M
        y = ((_bswap((v + w) * mul) + g) * mul) & _M; z = (e + f + c) & _M
        a = (_bswap((x + z) * mul + y) + b) & _M; b = ((z + a) * mul + d + h) & _M; b = ((b ^ (b >> 47)) * mul) & _M
        return (b + x) & _M
    x = _f64(s, n - 40); y = (_f64(s, n - 16) + _f64(s, n - 56)) & _M; z = _h16((_f64(s, n - 48) + n) & _M, _f64(s, n - 24))
    v = _weak(s, n - 64, n, z); w = _weak(s, n - 32, (y + _K1) & _M, x); x = (x * _K1 + _f64(s, 0)) & _M
    left, i = (n - 1) & ~63, 0
    while left:
        x = (_rot((x + y + v[0] + _f64(s, i + 8)) & _M, 37) * _K1) & _M
        y = (_rot((y + v[1] + _f64(s, i + 48)) & _M, 42) * _K1) & _M
        x ^= w[1]; y = (y + v[0] + _f64(s, i + 40)) & _M; z = (_rot((z + w[0]) & _M, 33) * _K1) & _M
        v = _weak(s, i, (v[1] * _K1) & _M, (x + w[0]) & _M); w = _weak(s, i + 32, (z + w[1]) & _M, (y + _f64(s, i + 16)) & _M)
        z, x = x, z; i += 64; left -= 64
    return _h16((_h16(v[0], w[0]) + (y ^ (y >> 47)) * _K1 + z) & _M, (_h16(v[1], w[1]) + x) & _M)

def nso_image(path):
    """A decompressed NSO image (dm/tools/nso.py) and its (read-only start, data end); nso.Error (a ValueError) on a damaged file"""
    import nso
    with open(path, 'rb') as f: m = nso.load(f.read(), path)
    return bytes(m.image), m.segments[1][0], len(m.image)

class OodleHost:
    """The game's own OodleLZ_Decompress in the Mac host's tool mode (DM_OODLE_SERVE, dm/host/hle_oodle.c: served before the SDK starts, so no boot), called as decode(compressed, raw length).
    host = the Mac host built for the game, modules = its rewritten modules, env = the host's environment (default: this process's)"""
    def __init__(self, host, modules, env=None):
        import subprocess, tempfile
        self.err = tempfile.TemporaryFile()
        self.p = subprocess.Popen([str(host), str(modules)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err, env=dict(env or os.environ, DM_OODLE_SERVE='1'))
        self.n = 0
    def __call__(self, comp, n):
        try:
            self.p.stdin.write(struct.pack('<QQ', len(comp), n)); self.p.stdin.write(comp); self.p.stdin.flush()
            got = struct.unpack('<Q', self.p.stdout.read(8))[0]
        except (BrokenPipeError, struct.error): got = None
        if got != n:
            self.err.seek(0)
            raise ValueError(f'the game\'s Oodle in the Mac host failed on a {len(comp)} → {n} byte stream; ---- host output ----\n' + self.err.read().decode(errors='replace')[-3000:])
        self.n += 1
        return self.p.stdout.read(n)
    def close(self):
        if self.p.poll() is None:
            self.p.stdin.close()
            try: self.p.wait(10)
            except Exception: self.p.kill()

class R:
    """A reader over a table from the game files (what = its name in the errors): a read past its end is the ValueError of a damaged file, not a struct.error or a short slice"""
    def __init__(self, b, o=0, what='table'): self.b, self.o, self.what = b, o, what
    def need(self, n):
        if n < 0 or not 0 <= self.o <= len(self.b) - n: raise ValueError(f'{self.what}: {n:#x} bytes at {self.o:#x} do not fit in its {len(self.b):#x}')
    def take(self, fmt):
        self.need(struct.calcsize(fmt))
        v = struct.unpack_from(fmt, self.b, self.o); self.o += struct.calcsize(fmt); return v if len(v) > 1 else v[0]
    def raw(self, n): self.need(n); v = self.b[self.o:self.o + n]; self.o += n; return v
    def array(self, c, n): return struct.unpack(f'<{n}{c}', self.raw(struct.calcsize(c) * n))   # n elements of struct code c, checked before unpacking
    def fstr(self):
        n = self.take('<i')
        if n < 0: return self.raw(-2 * n).decode('utf-16-le')[:-1]
        return self.raw(n)[:-1].decode('utf-8', 'replace') if n else ''

LEGACY = (4, 7, 8, 9)   # pak versions with the per-file index (4: UE 4.18; 7: UE 4.21/4.22; 8: 4.23/4.24, compression named in the footer; 9: 4.25, named, and the index may be a frozen memory image); 11 has the encoded one
LEGACY_METHODS = {1: 'Zlib', 2: 'Gzip', 3: 'LZ5', 4: 'Custom'}   # compression flags of a legacy pak (3: DRAGON QUEST XI S's engine, see the header)

def magic_back(f):
    """(how far from the end the footer's magic is, the pak version): a legacy footer is the last 0x2d bytes (magic 0x2c from the end); version 11's magic is 0xc8 from the end in
    Octopath Traveler 0 (UE5) and 0xcc in Unreal Engine 4.27 (DRAGON QUEST VII Reimagined: five whole 32-byte compression method names after the SHA-1)"""
    size = f.seek(0, 2)
    for back, foot in ((0x2c, 0x2d), (0xc8, 0xc8 + 21), (0xcc, 0xcc + 21), (0xcd, 0xcd + 21)):   # 0xcc: version 8 as well (UE 4.23/4.24: five 32-byte names); 0xcd: version 9 (one more byte, the frozen index flag, before the names)
        if size < foot: continue   # shorter than this footer
        f.seek(-back, 2); m, ver = struct.unpack('<II', f.read(8))
        if m == PAK_MAGIC: return back, ver
    raise ValueError('no pak footer')

def pak_version(f):
    return magic_back(f)[1]

def footer(f):
    """(encrypted index, index offset, index size, compression method names by number from 1, version); ValueError when the index does not lie inside the file"""
    back, ver = magic_back(f)
    if ver not in LEGACY and ver != 11: raise ValueError(f'pak version {ver}, only {", ".join(map(str, LEGACY))} and 11 are read')
    if (ver in (4, 7)) != (back == 0x2c): raise ValueError(f'a version {ver} pak footer with its magic {back:#x} bytes from the end, where that version has none')
    if ver in (4, 7):   # no names in the footer (version 7 adds the key GUID in front of the flag)
        f.seek(-0x2d, 2); ft = f.read(0x2d); ioff, isz = struct.unpack_from('<QQ', ft, 9)
        enc, methods = ft[0], [LEGACY_METHODS.get(i, f'flags {i}') for i in range(1, 8)]
    else:   # versions 8, 9 and 11: the methods are named; version 9 has the frozen index flag (u8) between the SHA-1 and the names
        f.seek(-(back + 21), 2); ft = f.read(back + 21); k = 21
        ioff, isz = struct.unpack_from('<QQ', ft, k + 8)
        n0 = k + 44 + (ver == 9)
        enc, methods = ft[k - 1], [ft[n0 + 32 * i:n0 + 32 * i + 32].rstrip(b'\0').decode('latin1') for i in range(5)]
    if ioff + isz > f.seek(0, 2): raise ValueError(f'the index ({isz:#x} bytes at {ioff:#x}) runs past the end of the pak')
    return enc, ioff, isz, methods, ver

def frozen_index(f):
    """Whether a version 9 pak (UE 4.25) writes its index as a frozen memory image (the flag byte right after the index SHA-1: Kimetsu no Yaiba - The Hinokami Chronicles 1)"""
    back, ver = magic_back(f)
    if ver != 9: return False
    f.seek(-(back + 21), 2); return f.read(back + 21)[21 + 44] == 1

def read_range(f, off, n, what):
    """n bytes of the file at off, after checking that they lie inside it: a size from a damaged pak would otherwise be allocated by f.read first (up to 2^64)"""
    if off < 0 or n < 0 or off + n > f.seek(0, 2): raise ValueError(f'{what}: {n:#x} bytes at {off:#x} do not lie inside the file')
    f.seek(off); return f.read(n)

def find_key(img, lo, hi, pak):
    """The AES key among main's 32-byte windows (read-only and data segments, 4-aligned, at least 20 distinct bytes): the one that decrypts the index start to a short mount point"""
    with open(pak, 'rb') as f:
        _, ioff, _, _, _ = footer(f); f.seek(ioff); blk = f.read(16)
    for a in range(lo, hi - 32, 4):
        w = img[a:a + 32]
        if len(set(w)) < 20: continue
        d = aes_decrypt(w, blk)
        if 0 < struct.unpack_from('<i', d)[0] < 512 and d[4:7] == b'../': return w
    return None

class Pak:
    def __init__(self, path, key=None):
        self.path, self.key = path, key; self.f = open(path, 'rb')
        enc, ioff, isz, self.methods, self.version = footer(self.f)
        if enc and not key: raise ValueError(f'{path}: the index is encrypted and no key was given')
        if self.version == 9 and frozen_index(self.f): self.frozen(self.read_at(ioff, isz, enc)); return
        r = R(self.read_at(ioff, isz, enc), what=f'{path}: the index')
        self.mount = r.fstr(); self.count = r.take('<i')
        if self.version in LEGACY:   # one FPakEntry per file, kept as parsed
            self.files = {}
            for _ in range(self.count):
                name = r.fstr(); off, size, raw, meth = r.take('<qqqi'); r.raw(20)
                blocks = [r.take('<qq') for _ in range(r.take('<i'))] if meth else []
                e, bsz = r.take('<BI'); head = 53 + (4 + 16 * len(blocks) if meth else 0)
                if self.version < 5: blocks = [(s - off, t - s) for s, t in blocks]
                else: blocks = [(s, t - s) for s, t in blocks]
                if self.version >= 8 and meth > len(self.methods) or meth and self.version >= 8 and not self.methods[meth - 1]: raise ValueError(f'{path}: {name} names compression method {meth}, which the footer does not')
                self.files[name] = dict(off=off, raw=raw, size=size, method=(self.methods[meth - 1] if self.version >= 8 else LEGACY_METHODS.get(meth, f'flags {meth}')) if meth else '', encrypted=e, block_size=bsz, blocks=blocks or [(head, size)])
            return
        r.take('<Q')
        if r.take('<i'): r.take('<QQ'); r.raw(20)   # path hash index (not needed with the full directory index)
        if not r.take('<i'): raise ValueError(f'{path}: no full directory index')
        doff, dsz = r.take('<QQ'); r.raw(20)
        self.enc = r.raw(r.take('<i'))
        if r.take('<i'): raise ValueError(f'{path}: unencoded entries are not read')
        d = R(self.read_at(doff, dsz, enc), what=f'{path}: the directory index'); self.files = {}
        for _ in range(d.take('<i')):
            dn = d.fstr()
            for _ in range(d.take('<i')): fn = d.fstr(); self.files[(dn + fn).lstrip('/')] = d.take('<i')
    def frozen(self, b):
        """Version 9 with a frozen index (UE 4.25, a TMemoryImage written to the pak): every pointer is relative, a u64 whose bit 0 is set and whose upper bits are the byte distance from the pointer's own place.
        Root: FString mount point (ptr, i32 num, i32 max) at 0; TArray<FPakEntry> at 0x10 (80-byte entries: i64 offset, size, raw size, SHA-1 padded to 24, TArray<FPakCompressedBlock> (16-byte blocks:
        i64 start, end, relative to the entry), u32 block size, u32 method (1-based, the footer's names), u8 flags, padded); the directory TSet<TTuple<FString, FPakDirectory>> at 0x20: sparse array elements
        of 80 bytes (FString directory name; its TMap<FString, i32> elements pointer and count at +16; the rest is the bit array and the hash), each file element 32 bytes (FString name, i32 index into
        the entries, hash link). Checked on Kimetsu no Yaiba - The Hinokami Chronicles 1 (UE 4.25: pakchunk0-Switch.pak, 1,284 files, and pakchunk1-Switch.pak, 88)"""
        what = f'{self.path}: the frozen index'; self.b = b
        def at(o, n):   # o, after checking that n bytes from it lie inside the index
            if not 0 <= o <= len(b) - n: raise ValueError(f'{what}: {n:#x} bytes at {o:#x} do not fit in its {len(b):#x}')
            return o
        def ptr(slot):
            v = struct.unpack_from('<Q', b, at(slot, 8))[0]
            if not v & 1: raise ValueError(f'{what}: the pointer at {slot:#x} is not set')
            return at(slot + (v >> 1), 0)
        def fstr(slot):
            n = struct.unpack_from('<i', b, at(slot + 8, 4))[0]
            if n <= 0: return ''
            p = ptr(slot); return b[at(p, 2 * n):p + 2 * (n - 1)].decode('utf-16-le')
        self.mount = fstr(0); entries = []
        n = struct.unpack_from('<i', b, at(0x18, 4))[0]; ep = ptr(0x10)
        for k in range(n):
            o = at(ep + 80 * k, 80); off, size, raw = struct.unpack_from('<qqq', b, o); nb = struct.unpack_from('<i', b, o + 56)[0]
            bp = ptr(o + 48) if nb else 0; bsz, meth = struct.unpack_from('<II', b, o + 64); fl = b[o + 72]
            if meth > len(self.methods) or meth and not self.methods[meth - 1]: raise ValueError(f'{what}: entry {k} names compression method {meth}, which the footer does not')
            blocks = [(s, t - s) for s, t in (struct.unpack_from('<qq', b, at(bp + 16 * i, 16)) for i in range(nb))]
            entries.append(dict(off=off, raw=raw, size=size, method=self.methods[meth - 1] if meth else '', encrypted=fl & 1, block_size=bsz, blocks=blocks or [(53 + (4 + 16 * nb if meth else 0), size)]))
        self.files = {}; dp = ptr(0x20)
        for k in range(struct.unpack_from('<i', b, at(0x28, 4))[0]):
            o = at(dp + 80 * k, 80); dn = fstr(o); nf = struct.unpack_from('<i', b, o + 24)[0]; fp = ptr(o + 16) if nf else 0
            for i in range(nf):
                q = at(fp + 32 * i, 32); j = struct.unpack_from('<i', b, q + 16)[0]
                if not 0 <= j < len(entries): raise ValueError(f'{what}: {dn}{fstr(q)} names entry {j} of {len(entries)}')
                self.files[(dn + fstr(q)).lstrip('/')] = entries[j]
        self.count = len(self.files)
    def read_at(self, off, n, enc):
        if enc and not self.key: raise ValueError(f'{self.path}: {n:#x} encrypted bytes at {off:#x} and no key was given')
        b = read_range(self.f, off, (n + 15) & ~15 if enc else n, self.path)
        return aes_decrypt(self.key, b)[:n] if enc else b
    def entry(self, path):
        if self.version in LEGACY: return self.files[path]
        r = R(self.enc, self.files[path], what=f'{self.path}: the entry of {path}'); v = r.take('<I')
        bsz = (v & 0x3f) << 11
        if v & 0x3f == 0x3f: bsz = r.take('<I')
        nblk, enc, meth = v >> 6 & 0xffff, v >> 22 & 1, v >> 23 & 0x3f
        off = r.take('<I' if v >> 31 & 1 else '<Q'); raw = r.take('<I' if v >> 30 & 1 else '<Q')
        size = r.take('<I' if v >> 29 & 1 else '<Q') if meth else raw
        cur, blocks = 53 + (4 + 16 * nblk if meth else 0), []
        if nblk == 1 and not bsz: bsz = raw   # FINAL FANTASY RESONANCE's pak (UE 5.6) stores block size 0 for a file of one block
        if nblk == 1 and not enc: blocks = [(cur, size)]
        else:
            for _ in range(nblk): s = r.take('<I'); blocks.append((cur, s)); cur += (s + 15) & ~15 if enc else s
        if meth > len(self.methods) or meth and not self.methods[meth - 1]: raise ValueError(f'{self.path}: {path} names compression method {meth}, which the footer does not')
        return dict(off=off, raw=raw, size=size, method=self.methods[meth - 1] if meth else '', encrypted=enc, block_size=bsz, blocks=blocks)
    def read(self, path, decode=None):
        """A file's bytes, block by block (each block holds block_size raw bytes, the last one the rest). Zlib and LZ4 blocks are decoded here (OCTOPATH TRAVELER II: Zlib); any other
        method needs decode(block bytes, raw length) → bytes: the game's own decoder in the Mac host (shader_split.py oodle); Octopath Traveler 0's archives go through the Oodle job instead"""
        e = self.entry(path)
        if not e['method']: return self.read_at(e['off'] + 53, e['size'], e['encrypted'])
        import zlib
        bad = (zlib.error,)   # a block its decoder refuses
        if e['method'] == 'Zlib': decode = zlib_block
        elif e['method'] == 'LZ4': import lz4.block; decode = lambda b, k: lz4.block.decompress(b, uncompressed_size=lz4_raw(b, k, path)); bad = (lz4.block.LZ4BlockError,)
        elif not decode: raise ValueError(f'{path} is {e["method"]}-compressed in the pak')
        out, left = [], e['raw']
        for i, (s, n) in enumerate(e['blocks']):
            k = min(left, e['block_size'])
            try: b = decode(self.read_at(e['off'] + s, n, e['encrypted']), k)
            except bad as x: raise ValueError(f'{self.path}: {path} block {i} does not decode ({x})') from None
            if len(b) != k: raise ValueError(f'{self.path}: {path} block {i} decodes to {len(b):#x} bytes, not {k:#x}')
            out.append(b); left -= k
        return b''.join(out)

class LegacyPakWriter:
    """A pak of a legacy version (4, 7, 8, 9) written file by file, for a replacement pak too large to hold in memory: add() stores a file, add_zlib() a file already split into Zlib blocks of block_size raw bytes.
    The method is the flag 1 in versions 4 and 7, and the first name in the footer of versions 8 and 9. close() (or leaving the with block) writes the index and the footer"""
    def __init__(self, out, mount, version):
        import hashlib
        if version not in LEGACY: raise ValueError(f'LegacyPakWriter: pak version {version}, only {", ".join(map(str, LEGACY))} are written')
        self.sha1, self.version, self.mount = hashlib.sha1, version, mount
        self.f, self.pos, self.idx, self.count, self.zlib = open(out, 'wb'), 0, bytearray(), 0, False
    @staticmethod
    def fstr(t): b = t.encode('utf-8') + b'\0'; return struct.pack('<i', len(b)) + b
    def _entry(self, off, size, raw, meth, sha, blocks, bsz):
        e = struct.pack('<qqqi', off, size, raw, meth) + sha
        if meth: e += struct.pack('<i', len(blocks)) + b''.join(struct.pack('<qq', a, b) for a, b in blocks)
        return e + struct.pack('<BI', 0, bsz)
    def add(self, path, blob):
        sha = self.sha1(blob).digest()
        self.idx += self.fstr(path) + self._entry(self.pos, len(blob), len(blob), 0, sha, (), 0)
        head = self._entry(0, len(blob), len(blob), 0, sha, (), 0)
        self.f.write(head); self.f.write(blob); self.pos += len(head) + len(blob); self.count += 1
    def add_zlib(self, path, chunks, raw, block_size):
        h = self.sha1()
        for c in chunks: h.update(c)
        sha, size, nhead = h.digest(), sum(map(len, chunks)), 53 + 4 + 16 * len(chunks)
        base = self.pos if self.version < 5 else 0   # block offsets: from the file start before version 5, from the entry after
        blocks, at = [], nhead
        for c in chunks: blocks.append((base + at, base + at + len(c))); at += len(c)
        self.zlib = True
        self.idx += self.fstr(path) + self._entry(self.pos, size, raw, 1, sha, blocks, block_size)
        head = self._entry(0, size, raw, 1, sha, blocks, block_size)
        self.f.write(head)
        for c in chunks: self.f.write(c)
        self.pos += nhead + size; self.count += 1
    def close(self):
        idx = self.fstr(self.mount) + struct.pack('<i', self.count) + bytes(self.idx)
        foot = (b'' if self.version == 4 else bytes(16)) + struct.pack('<BIiqq', 0, PAK_MAGIC, self.version, self.pos, len(idx)) + self.sha1(idx).digest()
        if self.version >= 8: foot += bytes(self.version == 9) + (b'Zlib'.ljust(32, b'\0') if self.zlib else bytes(32)) + bytes(32 * 4)   # no frozen index; the method names
        self.f.write(idx); self.f.write(foot); self.f.close()
    def __enter__(self): return self
    def __exit__(self, *a): self.close()

def write_pak(out, mount, files, version=11):
    """An uncompressed, unencrypted pak (see "Writing" in the notes above) at out: files = [(path in the pak, bytes)], paths relative to mount (mount is "../../../" for the game's own). version: 11, or
    4, 7, 8, 9 (the legacy per-file index) for an engine that reads no later one: an engine refuses a pak newer than itself, so a replacement pak takes the version of the pak it replaces files of.
    A game mounts a pak named <stem of another>_99_P.pak beside it with priority over the original (Unreal's patch paks), so the files here replace those of the same path"""
    import hashlib
    def fstr(t): b = t.encode('utf-8') + b'\0'; return struct.pack('<i', len(b)) + b
    if version != 11 and version not in LEGACY: raise ValueError(f'write_pak: pak version {version}, only {", ".join(map(str, LEGACY))} and 11 are written')
    if version in LEGACY:
        with LegacyPakWriter(out, mount, version) as w:
            for path, blob in files: w.add(path, blob)
        return
    data, recs = bytearray(), []
    for path, blob in files:
        off = len(data)
        data += struct.pack('<qqqI', 0, len(blob), len(blob), 0) + hashlib.sha1(blob).digest() + struct.pack('<BI', 0, 0) + blob   # FPakEntry: offset, size, raw size, method 0, SHA-1, flags, block size
        recs.append((path, off, len(blob)))
    enc, where = bytearray(), {}
    for path, off, size in recs:
        if off >= 1 << 32 or size >= 1 << 32: raise ValueError(f'{path}: a replacement pak holds at most 4 GB')
        where[path] = len(enc); enc += struct.pack('<III', (1 << 31) | (1 << 30) | (1 << 29), off, size)
    dirs = {}
    for path, _, _ in recs:
        d, _, f = path.rpartition('/'); d = d + '/' if d else '/'
        dirs.setdefault(d, {})[f] = where[path]
        parts = d.strip('/').split('/') if d != '/' else []
        for i in range(len(parts)): dirs.setdefault('/'.join(parts[:i]) + '/' if i else '/', {})   # the parents, empty
    di = bytearray(struct.pack('<i', len(dirs)))
    for d, fs in dirs.items():
        di += fstr(d) + struct.pack('<i', len(fs))
        for f, o in fs.items(): di += fstr(f) + struct.pack('<i', o)
    def primary(di_off):
        p = bytearray(fstr(mount)) + struct.pack('<iQ', len(recs), 0) + struct.pack('<i', 0)   # entry count, path hash seed, no path hash index
        p += struct.pack('<iqq', 1, di_off, len(di)) + hashlib.sha1(di).digest()                # the full directory index
        return p + struct.pack('<i', len(enc)) + enc + struct.pack('<i', 0)                     # encoded entries, no unencoded ones
    idx = len(data); p = primary(0); di_off = idx + len(p); p = primary(di_off)
    foot = bytes(16) + struct.pack('<BIiqq', 0, 0x5A6F12E1, 11, idx, len(p)) + hashlib.sha1(p).digest() + bytes(32 * 5)
    with open(out, 'wb') as f: f.write(data); f.write(p); f.write(di); f.write(foot)

def zlib_block(b, k):
    """A Zlib block of k raw bytes: inflated no further than k (a damaged stream could inflate about 1,000 times its size), short when the stream ends early"""
    import zlib
    z = zlib.decompressobj(); out = z.decompress(b, max(k, 1))   # (a max_length of 0 means no limit)
    if not z.eof: raise zlib.error(f'the stream does not end within its {k:#x} raw bytes')
    return out

def archive(b, what='shader code archive') -> dict:
    """A shader code archive's tables: {'maps': [(first index, count)], 'shaders': [(offset, size, raw size, frequency)], 'indices': [...], 'code': start of the code}; what names it in errors"""
    r = R(b, what=what)
    if r.take('<I') != ARCHIVE_VERSION: raise ValueError('not a version 2 shader code archive')
    nmap = r.take('<I'); r.raw(20 * nmap); nsh = r.take('<I'); r.raw(20 * nsh)
    maps = [r.take('<IIII')[:2] for _ in range(r.take('<I'))]
    shaders = [r.take('<QIIB') for _ in range(r.take('<I'))]
    r.raw(16 * r.take('<I'))
    indices = list(r.array('I', r.take('<I')))
    return dict(maps=maps, shaders=shaders, indices=indices, code=r.o)

def decoded_archive(b, raws):
    """The archive with every shader replaced by its decoded bytes (raws, in entry order): the same tables, each entry's size = its raw size, the code laid out again
    (the preload entries keep their old file ranges; only the shader tools read these copies)"""
    a = archive(b); r = R(b, what='shader code archive'); r.take('<I')
    for elem in (20, 20, 16): r.raw(elem * r.take('<I'))
    head, ents_at = b[:r.o + 4], r.o + 4; n = len(a['shaders']); tail_at = ents_at + 17 * n
    ents, off = bytearray(), 0
    for (_, _, raw, fr), d in zip(a['shaders'], raws):
        if len(d) != raw: raise ValueError(f'decoded shader of {len(d)} bytes, the archive says {raw}')
        ents += struct.pack('<QIIB', off, raw, raw, fr); off += raw
    return head + bytes(ents) + b[tail_at:a['code']] + b''.join(raws)

LZ4_RATIO = 255   # the most an LZ4 block expands: a match-length byte of 255 adds 255 output bytes for one input byte, every other part of a sequence less
def lz4_raw(b, k, where):
    """The raw size of an LZ4 block, checked before lz4.block.decompress allocates it: a size from a damaged file can be up to 2^64"""
    if k > LZ4_RATIO * len(b): raise ValueError(f'{where}: an LZ4 block of {len(b):#x} bytes cannot hold {k:#x}')
    return k

def lz4_shaders(b, a):
    """Every shader of an archive decoded as an LZ4 block (Unreal Engine 4.26 and later compress shaders with LZ4 unless the project picks another format: DRAGON QUEST VII Reimagined's
    64,949), or None when one of the compressed ones is no LZ4 block that decodes to its raw size as an LSLG record (Octopath Traveler 0's Oodle: the game's own decoder is needed)"""
    import lz4.block
    out = []
    for off, size, raw, _ in a['shaders']:
        c = b[a['code'] + off:a['code'] + off + size]
        if size == raw: out.append(c); continue
        if raw > LZ4_RATIO * len(c): return None   # more than an LZ4 block of this size can hold
        try: d = lz4.block.decompress(c, uncompressed_size=raw)
        except Exception: return None
        if len(d) != raw or d[:4] != b'LSLG': return None
        out.append(d)
    return out

TOC_MAGIC, IO_SHADER_LIBRARY, IO_SHADER_CODE = b'-==--==--==--==-', 8, 9   # EIoChunkType in Unreal Engine 5 (TOC version 4 and later; 4.27 numbers its chunk types otherwise)

class Toc:
    """An IoStore container: the .utoc's chunk table and compression blocks, the data in the .ucas beside it (<name>_s<n>.ucas for partitions after the first). A chunk is a range of the
    container's uncompressed stream, which is cut into blocks of one size, each stored or compressed on its own (method index 0 = stored, else the TOC's method names from 1).
    Header (FIoStoreTocHeader, 144 bytes): magic, u8 version, u8, u16, u32 header size, entry count, block count, block entry size (12), method count, method name length, block size,
    directory index size, partition count, u64 container ID, encryption key GUID (16), u8 flags (1 compressed, 2 encrypted, 4 signed, 8 indexed), u8, u16, u32 perfect hash seed count,
    u64 partition size, u32 count of chunks without a perfect hash, then reserved words. After it: chunk IDs (12 bytes: u64 hash, u16 index, u8, u8 type), offsets and lengths
    (5 + 5 bytes, big-endian), the perfect hash seeds and overflow list (u32 each), the blocks (5-byte offset, 3-byte stored size, 3-byte raw size, u8 method; little-endian), the method names"""
    def __init__(self, path, key=None):
        b = open(path, 'rb').read()
        if b[:16] != TOC_MAGIC: raise ValueError(f'{path}: not an IoStore TOC')
        self.path, self.key, self.version = path, key, b[16]
        hsz, n, nblk, bsz, nmeth, mlen, self.block_size, self.dir_size, nparts = struct.unpack_from('<9I', b, 20)
        if bsz != 12: raise ValueError(f'{path}: compression block entries of {bsz} bytes')
        self.flags = b[80]; self.encrypted = b[80] >> 1 & 1
        nseeds = struct.unpack_from('<I', b, 84)[0] if self.version >= 4 else 0
        self.part_size = struct.unpack_from('<Q', b, 88)[0] if self.version >= 3 and nparts > 1 else 1 << 64
        nover = struct.unpack_from('<I', b, 96)[0] if self.version >= 5 else 0
        o = hsz; self.ids = [b[o + 12 * i:o + 12 * i + 12] for i in range(n)]; o += 12 * n
        self.ranges = [(int.from_bytes(b[o + 10 * i:o + 10 * i + 5], 'big'), int.from_bytes(b[o + 10 * i + 5:o + 10 * i + 10], 'big')) for i in range(n)]; o += 10 * n
        self.seeds = list(struct.unpack_from(f'<{nseeds}i', b, o)); o += 4 * nseeds + 4 * nover
        self.blocks = []
        for i in range(nblk):
            e = b[o + 12 * i:o + 12 * i + 12]
            self.blocks.append((int.from_bytes(e[:5], 'little'), int.from_bytes(e[5:8], 'little'), int.from_bytes(e[8:11], 'little'), e[11]))
        o += 12 * nblk
        self.methods = [b[o + mlen * i:o + mlen * (i + 1)].rstrip(b'\0').decode('latin1') for i in range(nmeth)]
        o += mlen * nmeth + self.dir_size; self.meta_at = o   # the directory index, then one 33-byte meta per chunk
        self.index = {c: i for i, c in enumerate(self.ids)}; self.files = {}; self._paths = None
    def meta(self, i):
        """Chunk i's 33-byte meta (32-byte chunk hash, u8 flags; 1 = compressed), read from the .utoc"""
        with open(self.path, 'rb') as f: f.seek(self.meta_at + 33 * i); m = f.read(33)
        if len(m) != 33: raise ValueError(f'{self.path}: chunk {i} has no meta')
        return m
    def raw_blocks(self, i, lazy=False):
        """Chunk i's blocks as stored: [(stored bytes, raw size, method name or '')], verbatim from the .ucas (what write_toc takes, to carry a chunk over without decoding it); lazy=True gives
        a zero-argument function that reads the bytes in place of them (write_toc calls it when it writes the block, so a container is copied without holding its data)"""
        if self.encrypted: raise ValueError(f'{self.path}: the container is encrypted')
        off, ln = self.ranges[i]; first = off // self.block_size; out = []
        def read(k):
            at, size = self.blocks[k][:2]; f = self.ucas(at // self.part_size); f.seek(at % self.part_size)
            d = f.read(size)
            if len(d) != size: raise ValueError(f'{self.path}: chunk {i} block {k} is cut short')
            return d
        for k in range(first, (off + ln - 1) // self.block_size + 1 if ln else first):
            m = self.blocks[k][3]
            out.append(((lambda k=k: read(k)) if lazy else read(k), self.blocks[k][2], self.methods[m - 1] if m else ''))
        return out
    def paths(self):
        """{chunk index: path} from the directory index (FIoDirectoryIndexResource, unencrypted), as the engine mounts it ("../../../APK2/Content/..."); {} when the container has none. The index is
        the mount point (FString), the directories (u32 count, then name, first child, next sibling, first file: u32 each), the files (u32 count, then name, next file, chunk index) and the string table
        (u32 count, FStrings); 0xFFFFFFFF = none. ValueError for an encrypted container or a damaged index"""
        if self._paths is not None: return self._paths
        out = {}
        if self.dir_size:
            if self.flags & 2: raise ValueError(f'{self.path}: the directory index is encrypted')
            with open(self.path, 'rb') as f: f.seek(self.meta_at - self.dir_size); d = f.read(self.dir_size)
            r = R(d, what='directory index'); mount = r.fstr()
            dirs = [r.take('<4I') for _ in range(r.take('<I'))]; files = [r.take('<3I') for _ in range(r.take('<I'))]
            strs = [r.fstr() for _ in range(r.take('<I'))]; none, seen = 0xFFFFFFFF, set()
            def name(k):
                if not 0 <= k < len(strs): raise ValueError(f'{self.path}: directory index string {k} is out of range')
                return strs[k]
            stack = [(0, mount)] if dirs else []   # (directory, path prefix); a directory's siblings share its prefix
            while stack:
                di, prefix = stack.pop()
                while di != none:
                    if di >= len(dirs) or ('d', di) in seen: raise ValueError(f'{self.path}: directory index entry {di} is out of place')
                    seen.add(('d', di)); nm, child, sib, first = dirs[di]
                    p = prefix + (name(nm) + '/' if nm != none else ''); fi = first
                    while fi != none:
                        if fi >= len(files) or ('f', fi) in seen: raise ValueError(f'{self.path}: directory index file {fi} is out of place')
                        seen.add(('f', fi)); fn, nxt, ud = files[fi]; out[ud] = p + name(fn); fi = nxt
                    if child != none: stack.append((child, p))
                    di = sib
        self._paths = out
        return out
    def export_bundles(self):
        """Indices of the cooked packages' chunks (ExportBundleData): type 1 in Unreal Engine 5 (TOC version 4 and later), 2 in UE 4.25 to 4.27 (Kimetsu no Yaiba - The Hinokami Chronicles 1: TOC version 2; its
        chunk types are 2 ExportBundleData, 3 BulkData, 10 ContainerHeader, and 7, 8, 9 the loader's global metadata, names and name hashes in global.utoc)"""
        t = IO_EXPORT_BUNDLE if self.version >= 4 else IO_EXPORT_BUNDLE_UE4
        return [i for i, c in enumerate(self.ids) if c[11] == t]
    def of_type(self, t):
        """Indices of the chunks of one EIoChunkType (Unreal Engine 5 numbering: TOC version 4 and later)"""
        return [i for i, c in enumerate(self.ids) if c[11] == t] if self.version >= 4 else []
    def ucas(self, part):
        if part not in self.files: self.files[part] = open(self.path[:-5] + ('.ucas' if not part else f'_s{part}.ucas'), 'rb')
        return self.files[part]
    def read(self, i, decode=None):
        """Chunk i's bytes; Oodle blocks need decode(block bytes, raw length) → bytes (the game's own decoder, OodleHost)"""
        # TOC metadata is unencrypted. Check the selected chunk here: a patch can replace an encrypted library or refer to an encrypted group-only container.
        if self.encrypted and not self.key: raise ValueError(f'{self.path}: the container is encrypted and no key was given')
        off, ln = self.ranges[i]; first = off // self.block_size; out = []
        for k in range(first, (off + ln - 1) // self.block_size + 1 if ln else first):
            at, size, raw, m = self.blocks[k]; f = self.ucas(at // self.part_size); f.seek(at % self.part_size)
            d = f.read((size + 15) & ~15 if self.encrypted else size)
            if self.encrypted: d = aes_decrypt(self.key, d)[:size]
            meth = self.methods[m - 1] if m else ''
            if not meth: out.append(d[:raw])
            elif meth == 'Oodle':
                if not decode: raise ValueError(f'{self.path}: chunk {i} is Oodle-compressed and no decoder was given')
                out.append(decode(d, raw))
            elif meth == 'Zlib': import zlib; out.append(zlib.decompress(d))
            elif meth == 'LZ4': import lz4.block; out.append(lz4.block.decompress(d, uncompressed_size=raw))
            else: raise ValueError(f'{self.path}: compression method {meth} is not read')
        s = off - first * self.block_size
        return b''.join(out)[s:s + ln]

def io_library_name(toc, i, names):
    """A shader library chunk's archive name: Unreal makes its chunk ID from CityHash64 of "<library>-<format>" lowercased, in UTF-16 (FINAL FANTASY RESONANCE: global-sf_glsl_switch-sp_glsl_switch
    → be76feab0415c156, the hash's bytes in memory order), names = the candidate "ShaderArchive-<library>-<format>" names (the RomFS manifests list them); a chunk none matches is named by its ID"""
    h = toc.ids[i][:8]
    for n in names:
        if city64(n[len('ShaderArchive-'):].lower().encode('utf-16-le')).to_bytes(8, 'little') == h: return n
    return f'ShaderArchive-IoStore-{h.hex()}'

def io_archive(toc, i, decode, chunk=None):
    """An IoStore shader library (Unreal Engine 5: FIoStoreShaderCodeArchive) as a version 2 shader code archive with every shader decoded, the form the shader tools read.
    The library chunk: u32 version (1), shader map hashes (20 bytes each), shader hashes (20 each), the shader groups' chunk IDs (12 each), shader map entries {u32 first index, u32 shader count},
    shader entries (u64: frequency in bits 0-3, group in 4-33, offset in the group's decoded bytes from bit 34), group entries {u32 first index, u32 shader count, u32 raw size, u32 stored size},
    shader indices (u32): each a u32 count and its elements. Each group is one ShaderCode chunk holding its shaders end to end, Oodle-compressed as a whole when its stored size is below its raw
    size (FINAL FANTASY RESONANCE: 5,919 groups of 74,244 shaders); a shader runs to the next shader's offset in its group, or to the group's end. chunk(chunk ID) → (container, index) looks a
    group up in every container under the RomFS: a patch container's library lists the groups it did not change from the base container's"""
    r = R(toc.read(i, decode), what=f'{toc.path}: shader library chunk {i}')
    if r.take('<I') != 1: raise ValueError(f'{toc.path}: shader library chunk {i} is not version 1')
    maph = r.raw(20 * r.take('<I')); nsh = r.take('<I'); shh = r.raw(20 * nsh)
    gids = [r.raw(12) for _ in range(r.take('<I'))]
    maps = [r.take('<II') for _ in range(r.take('<I'))]
    n = r.take('<I'); ents = r.array('Q', n)
    groups = [r.take('<IIII') for _ in range(r.take('<I'))]
    idx = r.array('I', r.take('<I'))
    if r.o != len(r.b) or n != nsh or len(gids) != len(groups): raise ValueError(f'{toc.path}: shader library chunk {i} does not parse')
    code = [None] * n
    for g, (gid, (first, cnt, raw, stored)) in enumerate(zip(gids, groups)):
        owner = chunk(gid) if chunk else (toc, toc.index.get(gid))
        if not owner or owner[1] is None: raise ValueError(f'{toc.path}: shader group {g} ({gid.hex()}) is in no container under the RomFS')
        d = owner[0].read(owner[1], decode)
        if len(d) != stored: raise ValueError(f'{toc.path}: shader group {g} is {len(d)} bytes, its entry says {stored}')
        if stored < raw: d = decode(d, raw)
        mine = sorted(((ents[s] >> 34, s) for s in idx[first:first + cnt]))
        for (at, s), (nxt, _) in zip(mine, mine[1:] + [(raw, None)]):
            if (ents[s] >> 4) & 0x3FFFFFFF != g: raise ValueError(f'{toc.path}: shader {s} is listed in group {g} but names another')
            code[s] = d[at:nxt]
    if any(c is None for c in code): raise ValueError(f'{toc.path}: {sum(c is None for c in code)} shaders in no group')
    out, off = bytearray(struct.pack('<II', ARCHIVE_VERSION, len(maph) // 20) + maph + struct.pack('<I', n) + shh + struct.pack('<I', len(maps))), 0
    for a, c in maps: out += struct.pack('<IIII', a, c, 0, 0)
    out += struct.pack('<I', n)
    for e, c in zip(ents, code): out += struct.pack('<QIIB', off, len(c), len(c), e & 0xF); off += len(c)
    out += struct.pack('<I', 0) + struct.pack(f'<I{len(idx)}I', len(idx), *idx)
    return bytes(out) + b''.join(code)

IO_EXPORT_BUNDLE = 1   # EIoChunkType ExportBundleData in Unreal Engine 5: a cooked package's exports
IO_EXPORT_BUNDLE_UE4 = 2   # the same chunk type in UE 4.25 to 4.27 (TOC versions 2 and 3)
IO_BULK_DATA, IO_OPTIONAL_BULK_DATA, IO_MEMORY_MAPPED_BULK_DATA, IO_CONTAINER_HEADER = 2, 3, 4, 6   # EIoChunkType in Unreal Engine 5 (TOC version 4 and later)
IO_BLOCK = 65536   # the compression block size write_toc writes

def io_chunk_id(oid, index, typ):
    """A chunk ID (12 bytes): u64 object ID, u16 index, u8 0, u8 EIoChunkType"""
    return struct.pack('<QHBB', oid, index, 0, typ)

def io_container_id(name):
    """A container's ID: CityHash64 of its lower-case name (the file stem, "pakchunk10-Switch") in UTF-16 (also the object ID of its container header chunk)"""
    return city64(name.lower().encode('utf-16-le'))

def io_hash(cid, seed):
    """The engine's perfect hash of a chunk ID: FNV-1 over its 12 bytes (multiply, then xor), starting from the seed, or from the FNV offset basis when the seed is 0"""
    h = seed & 0xFFFFFFFFFFFFFFFF if seed else 0xcbf29ce484222325
    for c in cid: h = ((h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF) ^ c
    return h

def io_lookup(ids, seeds, cid):
    """The engine's lookup of a chunk ID in the table stored in slot order: the seed of bucket io_hash(cid, 0) % len(seeds) (0 = absent, negative = slot -seed - 1, else the slot is
    io_hash(cid, seed) % len(ids)), and the chunk is there only if that slot holds this ID → its index, or None"""
    if not ids or not seeds: return None
    s = seeds[io_hash(cid, 0) % len(seeds)]
    if not s: return None
    slot = -s - 1 if s < 0 else io_hash(cid, s) % len(ids)
    return slot if 0 <= slot < len(ids) and ids[slot] == cid else None

def io_perfect_hash(ids):
    """A perfect hash for unique chunk IDs (the engine's scheme, as the game's own TOCs use it): (slots, seeds), slots[k] = the index in ids of the ID stored in slot k, seeds = int32 list of
    ceil(n / 2) buckets. Buckets (io_hash(id, 0) % seed count) are placed largest first, each given the smallest seed that sends its IDs to distinct free slots; a bucket of one takes
    the next free slot (seed -slot - 1); an empty one stays 0. ValueError for duplicate IDs or a seed search past 1 << 24"""
    n = len(ids)
    if len(set(ids)) != n: raise ValueError('duplicate chunk IDs')
    m = max(1, (n + 1) // 2); buckets = [[] for _ in range(m)]
    for i, c in enumerate(ids): buckets[io_hash(c, 0) % m].append(i)
    seeds, slots, free = [0] * m, [None] * n, [True] * n
    order = sorted(range(m), key=lambda b: -len(buckets[b]))
    for b in order:
        if len(buckets[b]) < 2: break
        s = 1
        while True:
            if s > 1 << 24: raise ValueError('no perfect hash seed found')
            at = [io_hash(ids[i], s) % n for i in buckets[b]]
            if len(set(at)) == len(at) and all(free[a] for a in at): break
            s += 1
        seeds[b] = s
        for i, a in zip(buckets[b], at): slots[a] = i; free[a] = False
    nxt = 0
    for b in order:
        if len(buckets[b]) != 1: continue
        while not free[nxt]: nxt += 1
        slots[nxt] = buckets[b][0]; free[nxt] = False; seeds[b] = -nxt - 1
    return slots, seeds

def stored_blocks(data):
    """The blocks write_toc takes for an uncompressed chunk: 64 KB pieces, method ''"""
    return [(data[o:o + IO_BLOCK], len(data[o:o + IO_BLOCK]), '') for o in range(0, len(data), IO_BLOCK)]

def fstring(t):
    """An FString: i32 length with the NUL (negative = UTF-16, its characters with the NUL) and the text"""
    try: b = t.encode('ascii') + b'\0'; return struct.pack('<i', len(b)) + b
    except UnicodeEncodeError: b = t.encode('utf-16-le') + b'\0\0'; return struct.pack('<i', -(len(b) // 2)) + b

def dir_index(files, mount='../../../'):
    """A directory index (the layout Toc.paths reads) for files = [(path starting with mount, chunk index)]"""
    strs, at = [], {}
    def s(t):
        if t not in at: at[t] = len(strs); strs.append(t)
        return at[t]
    tree = dict(name=None, kids={}, files=[])
    for path, ud in files:
        if not path.startswith(mount): raise ValueError(f'{path}: not under {mount}')
        parts = path[len(mount):].split('/'); node = tree
        for d in parts[:-1]: node = node['kids'].setdefault(d, dict(name=d, kids={}, files=[]))
        node['files'].append((parts[-1], ud))
    dirs, fl, none = [], [], 0xFFFFFFFF
    def emit(node):
        k = len(dirs); dirs.append([none if node['name'] is None else s(node['name']), none, none, none]); prev = None
        for nm, ud in node['files']:
            fl.append([s(nm), none, ud])
            if prev is None: dirs[k][3] = len(fl) - 1
            else: fl[prev][1] = len(fl) - 1
            prev = len(fl) - 1
        prev = None
        for kid in node['kids'].values():
            c = emit(kid)
            if prev is None: dirs[k][1] = c
            else: dirs[prev][2] = c
            prev = c
        return k
    emit(tree)
    return (fstring(mount) + struct.pack('<I', len(dirs)) + b''.join(struct.pack('<4I', *d) for d in dirs) + struct.pack('<I', len(fl)) + b''.join(struct.pack('<3I', *f) for f in fl)
            + struct.pack('<I', len(strs)) + b''.join(fstring(t) for t in strs))

def write_toc(stem, name, chunks, paths=None):
    """An IoStore container (see "Writing an IoStore container" in the notes above) at stem + '.utoc' and stem + '.ucas' (stem: a path without extension), name = the container's name for its ID
    (the file stem); chunks = [dict(id=12 bytes, size=raw length, blocks=[(stored bytes or a zero-argument function returning them, raw size, method '' or 'Oodle')], meta=33 bytes or None (32 zero
    bytes, flag from the blocks))]. The .ucas is written as the blocks come (a function is called once, when its block is written, and its length checked then), so only the tables stay in memory.
    paths = {chunk ID: path starting "../../../"} also writes a directory index (flag 8). Each chunk is ceil(size / 64 KB) blocks, all 64 KB raw but the last. → the container ID. ValueError for what
    the engine would not read: duplicate IDs, blocks that do not fit that rule, a stored block whose length is not its raw size, another method, a size of 2^40 or more, a stored block of 2^24 or
    more. The file is read back and every ID looked up as the engine does"""
    ids = [c['id'] for c in chunks]
    if any(len(i) != 12 for i in ids): raise ValueError('a chunk ID is not 12 bytes')
    for c in chunks:
        size, blks = c['size'], c['blocks']
        if not 0 <= size < 1 << 40: raise ValueError(f"{c['id'].hex()}: size {size} does not fit 40 bits")
        if len(blks) != -(-size // IO_BLOCK): raise ValueError(f"{c['id'].hex()}: {len(blks)} blocks for {size} bytes")
        if c.get('meta') is not None and len(c['meta']) != 33: raise ValueError(f"{c['id'].hex()}: a meta is 33 bytes")
        for k, (d, raw, meth) in enumerate(blks):
            if raw != min(IO_BLOCK, size - k * IO_BLOCK): raise ValueError(f"{c['id'].hex()}: block {k} has raw size {raw}")
            if meth not in ('', 'Oodle'): raise ValueError(f"{c['id'].hex()}: method {meth!r}")
            if not callable(d) and (not meth and len(d) != raw or len(d) >= 1 << 24): raise ValueError(f"{c['id'].hex()}: block {k} is {len(d)} bytes, raw size {raw}")
    if paths is not None and not set(paths) <= set(ids): raise ValueError('paths names a chunk that is not in the container')
    slots, seeds = io_perfect_hash(ids)
    cid = io_container_id(name); compressed = any(m for c in chunks for _, _, m in c['blocks'])
    rng, blk, metas, voff, pos = bytearray(), bytearray(), bytearray(), 0, 0
    with open(stem + '.ucas', 'wb') as uf:
        for sl in slots:
            c = chunks[sl]; rng += voff.to_bytes(5, 'big') + c['size'].to_bytes(5, 'big'); voff += len(c['blocks']) * IO_BLOCK
            if voff >= 1 << 40: raise ValueError('the container is larger than 2^40 bytes')
            for d, raw, meth in c['blocks']:
                if callable(d): d = d()
                if not meth and len(d) != raw: raise ValueError(f"{c['id'].hex()}: stored block is {len(d)} bytes, raw size {raw}")
                if len(d) >= 1 << 24: raise ValueError(f"{c['id'].hex()}: block stored in {len(d)} bytes")
                pad = -pos & 15; uf.write(bytes(pad)); pos += pad
                if pos >= 1 << 40: raise ValueError('the .ucas is larger than 2^40 bytes')
                blk += pos.to_bytes(5, 'little') + len(d).to_bytes(3, 'little') + raw.to_bytes(3, 'little') + bytes([1 if meth else 0]); uf.write(d); pos += len(d)
            metas += c['meta'] if c.get('meta') is not None else bytes(32) + bytes([1 if any(m for _, _, m in c['blocks']) else 0])
    di = dir_index([(paths[ids[sl]], k) for k, sl in enumerate(slots) if ids[sl] in paths]) if paths else b''
    head = bytearray(144); head[:16] = TOC_MAGIC; head[16] = 5
    struct.pack_into('<9I', head, 20, 144, len(chunks), len(blk) // 12, 12, int(compressed), 32, IO_BLOCK, len(di), 1)
    struct.pack_into('<Q', head, 56, cid); head[80] = (1 if compressed else 0) | (8 if di else 0)
    struct.pack_into('<IQI', head, 84, len(seeds), 0xFFFFFFFFFFFFFFFF, 0)
    toc = bytes(head) + b''.join(ids[sl] for sl in slots) + bytes(rng) + struct.pack(f'<{len(seeds)}i', *seeds) + bytes(blk) + (b'Oodle' + bytes(27) if compressed else b'') + di + bytes(metas)
    with open(stem + '.utoc', 'wb') as f: f.write(toc)
    t = Toc(stem + '.utoc')
    if t.version != 5 or t.seeds != seeds or len(t.ids) != len(ids): raise ValueError(f'{stem}.utoc does not read back')
    for k, c in enumerate(t.ids):
        if io_lookup(t.ids, t.seeds, c) != k: raise ValueError(f'{stem}.utoc: chunk {c.hex()} is not found by the perfect hash')
    if paths and len(t.paths()) != len(paths): raise ValueError(f'{stem}.utoc: the directory index does not read back')
    return cid

def container_header(cid, entries):
    """A container header chunk (type 6, stored uncompressed), version 3, for entries = [(package ID, (imported package IDs), (20-byte shader map hashes))]: u32 signature 0x496f436e, u32 version,
    u64 container ID, i32 package count and the package IDs, i32 byte count of the store entries and the entries, the same for the optional segment packages (none), then 12 zero bytes (no
    redirect names, localized packages or package redirects). A store entry is 16 bytes {u32 import count, u32 import offset, u32 shader map hash count, u32 hash offset}, all of them first,
    then each package's imports (u64 each) and hashes; each offset is relative to the start of its own array view, as Unreal's TFilePackageStoreEntryCArrayView stores it: the imports'
    to the entry's start, the hashes' to the entry's start + 8 (what pc_compare's zen.py reads); 0 for an empty array"""
    for pid, imps, hashes in entries:
        if any(len(h) != 20 for h in hashes): raise ValueError(f'package {pid:#x}: a shader map hash is not 20 bytes')
    head, tail = bytearray(), bytearray(); base = 16 * len(entries)
    for j, (pid, imps, hashes) in enumerate(entries):
        eo = 16 * j; oi = base + len(tail) - eo if imps else 0; tail += struct.pack(f'<{len(imps)}Q', *imps)
        os_ = base + len(tail) - (eo + 8) if hashes else 0; tail += b''.join(hashes)
        head += struct.pack('<IIII', len(imps), oi, len(hashes), os_)
    store = bytes(head + tail)
    return (struct.pack('<IIQi', 0x496f436e, 3, cid, len(entries)) + struct.pack(f'<{len(entries)}Q', *[e[0] for e in entries]) + struct.pack('<i', len(store)) + store
            + struct.pack('<ii', 0, 0) + bytes(12))

def read_container_header(d):
    """A container header chunk (container_header's layout) → dict(cid=, version=, entries=[(package ID, (imported IDs), (20-byte hashes))]); ValueError for another signature or version"""
    r = R(d, what='container header')
    if r.take('<I') != 0x496f436e: raise ValueError('container header: wrong signature')
    v = r.take('<I')
    if v != 3: raise ValueError(f'container header: version {v}, not 3')
    cid = r.take('<Q'); pids = r.array('Q', r.take('<i')); store = r.raw(r.take('<i')); out = []
    for j, pid in enumerate(pids):
        ni, oi, nh, oh = struct.unpack_from('<IIII', store, 16 * j) if 16 * j + 16 <= len(store) else (0, 0, 0, 0)
        if 16 * j + 16 > len(store): raise ValueError('container header: store entries are cut short')
        eo = 16 * j; R(store, eo + oi, 'container header').need(8 * ni); R(store, eo + 8 + oh, 'container header').need(20 * nh)
        out.append((pid, struct.unpack_from(f'<{ni}Q', store, eo + oi) if ni else (), tuple(store[eo + 8 + oh + 20 * q:eo + 8 + oh + 20 * q + 20] for q in range(nh))))
    return dict(cid=cid, version=v, entries=out)
OODLE_HEAD, LSLG_AT = re.compile(b'[\x8c\xcc][\x06\x0a\x0b\x0c]'), re.compile(b'LSLG')   # an Oodle stream's first block header (Kraken, Mermaid, Selkie or Leviathan); a stored record
TAG_FREQ = {'SV': 0, 'SH': 1, 'SD': 2, 'SP': 3, 'SG': 4, 'SC': 5}   # LSLG stage tag → EShaderFrequency

def ue5_inline_shaders(d, decode):
    """Shaders kept inline in cooked Unreal Engine 5 data, when the project does not share material shader code (Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles 2: no shader code
    archive and no IoStore shader library; each material's shader map in its package's exports, the engine's in Engine/GlobalShaderCache-SP_GLSL_SWITCH.bin, 2,854 shaders). A shader map's code
    (FShaderMapResourceCode) lists its shaders as entries {byte array (i32 length, then the bytes), i32 raw size, u8 frequency}; the bytes are one Oodle stream (Mermaid, 8C 0A), or the record
    itself when that is no larger. Found by the stream's header with the length in front of it: an entry whose bytes the game's decoder takes to exactly its raw size, an LSLG record whose stage
    tag is its frequency (a false match fails the decode: the host answers 0 and goes on). → [(frequency, record)]"""
    out = []
    def take(s, fr):
        try: ok = s[:4] == b'LSLG' and TAG_FREQ.get(s[4:6].decode('latin1')) == fr and lslg(s)
        except struct.error: ok = False   # shorter than the record's layout
        if ok: out.append((fr, s))
    for m in OODLE_HEAD.finditer(d, 4):
        i = m.start(); n = int.from_bytes(d[i - 4:i], 'little')
        if not 2 <= n <= len(d) - i - 5: continue
        raw, fr = struct.unpack_from('<iB', d, i + n)
        if not n < raw < 1 << 24 or fr > 5: continue
        try: take(decode(d[i:i + n], raw), fr)
        except ValueError: pass
    for m in LSLG_AT.finditer(d, 4):
        i = m.start(); n = int.from_bytes(d[i - 4:i], 'little')
        if 2 <= n <= len(d) - i - 5 and struct.unpack_from('<i', d, i + n)[0] == n: take(d[i:i + n], d[i + n + 4])
    return out

# ---- Unreal Engine 5 shader maps: the real vertex / pixel pairs (Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles 2) ----
# A cooked material's FMaterialShaderMapContent (and the engine's FGlobalShaderMapContent) is a memory image (FMemoryImage) serialized inline after the material's properties:
#   u32 count, then count x {u32 length with NUL, name, u32 hash}   the memory image's name table: the first N are the TYPE names (the root's first), then the FNames used in the image
#   u32 FrozenSize, the frozen image (FrozenSize bytes)
#   u32 N, N x {u64 index (0..N-1), u32 frozen size of the type, SHA-1 of its layout}   the type layout table, one row per type name in order (in the global cache each row starts with its own FString name
#                                                                                       instead of an index, and no name table comes before the image)
#   u32 nST, u32 nVF, nST x u64 shader type hashes, nVF x u64 vertex factory type hashes   FShaderMapPointerTable; then the FMemoryImageName patches, then FShaderMapResourceCode:
#   u32 n, n x 20-byte shader hash, u32 n, n x {u32 length, stream, i32 raw size, u8 EShaderFrequency}   (the streams are ue5_inline_shaders' entries)
# The frozen image is 64-bit: a pointer is a u64 whose low 24 bits are 1 (non-null; 0 is null) and whose upper 40 bits are a signed distance from the pointer itself to its target; TMemoryImageArray<T> is
# {pointer, i32 Num, i32 Max}. The offsets below are the layout of one engine build: a map is read only when its types' layout hashes (the table above) are ones in UE5_MAP_LAYOUTS, so another engine
# gives a [RED] line and no pairs, never wrong ones. A shader type is a type whose frozen size reaches the FShader members (target + 8): every other type of the table is smaller.
MapLayout = collections.namedtuple('MapLayout', 'types perms shaders pipes meshes vf target resource slots deps found')
_FSHADER = dict(types=0x18, perms=0x28, shaders=0x38, pipes=0x48, target=0xd0, resource=0xd4, slots=((8, 0), (0x10, 1), (0x18, 2), (0x20, 3), (0x28, 4)))   # FShaderMapContent base, FShader, FShaderPipeline
UE5_MAP_LAYOUTS = {   # (root type name, its frozen size, its layout SHA-1) → the offsets; deps = the other types the walk reads, {name: (size, SHA-1)}, checked when the map has them
    ('FMaterialShaderMapContent', 572, '36197f830bb149ff750d0910175517f54887b8b4'): MapLayout(meshes=0x60, vf=0x60, found='Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles 2', **_FSHADER, deps={
        'FMeshMaterialShaderMap': (104, 'cc035a0c0b55828628a25cbb4df55e48acb5487c'), 'FShaderPipeline': (68, 'd730ca31ef9aefb7d3042317e1dd60f6eaf3ece4'), 'FHashedName': (8, '30fd5af790b755e56b0409fc43602589073952bb')}),
}
UE5_MAP_NO_PAIRS = ('FNiagaraShaderMapContent',)   # compute only: no vertex / pixel pair
UE5_GLOBAL_LAYOUTS = {   # the same, for the engine's GlobalShaderCache-<format>.bin: FGlobalShaderMapContent (no mesh shader maps)
    ('FGlobalShaderMapContent', 104, 'dd7532b8724177cb24645b6b5cda7bd81a19bcd3'): MapLayout(meshes=None, vf=None, **_FSHADER, found='Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles 2', deps={'FHashedName': (8, '30fd5af790b755e56b0409fc43602589073952bb')}),
}
CODE_SCAN = 1 << 14   # how far past the pointer table the resource code's counts are looked for

class MapError(ValueError): pass

def zen_header(d):
    """The Zen package summary of an ExportBundleData chunk (UE 5.2 and later: 13 u32, no versioning info), its name map and its exports: {names, exports: [(start, size, name index)]}, or None when
    an offset does not fit the chunk (an earlier or later summary, or no package). Only used for labels and ranges; the shader maps do not depend on it"""
    try:
        if len(d) < 0x38: return None
        s = struct.unpack_from('<13I', d)
        if s[0] or not 0x38 <= s[1] <= len(d): return None
        o = 0x34; cnt, nb = struct.unpack_from('<II', d, o); o += 16
        if not 0 < cnt < 1 << 20 or o + 10 * cnt + nb > s[1]: return None
        lens = [int.from_bytes(d[o + 8 * cnt + 2 * i:o + 8 * cnt + 2 * i + 2], 'big') for i in range(cnt)]; o += 10 * cnt
        names = []
        for n in lens: names.append(d[o:o + n].decode('latin1')); o += n
        if o > s[1]: return None
        ex, bundles = s[8], s[9]
        if not (ex <= bundles <= s[1]) or (bundles - ex) % 72: return None
        exports = []
        for i in range((bundles - ex) // 72):
            off, size, name = struct.unpack_from('<QQI', d, ex + 72 * i)
            if s[1] + off + size > len(d): return None
            exports.append((s[1] + off, size, name))
        return dict(names=names, exports=exports)
    except (struct.error, UnicodeDecodeError): return None

TYPE_TABLE = re.compile(b'(?s)[\x01-\xc8]\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')   # u32 N, then the first row's u64 index 0

def _layout_rows(d, T, named=False):
    """The type layout table at T: [(name or None, frozen size, SHA-1 hex)] and its end, or None when the rows do not count 0..N-1 (a false match)"""
    n, o, rows = struct.unpack_from('<I', d, T)[0], T + 4, []
    if not 3 <= n <= 0x400: return None   # a real table has more than the root and its first type
    for i in range(n):
        name = None
        if named:
            if o + 4 > len(d): return None
            ln = struct.unpack_from('<I', d, o)[0]
            if not 1 <= ln < 200 or o + 4 + ln + 24 > len(d) or d[o + 3 + ln]: return None
            name = d[o + 4:o + 3 + ln].decode('latin1'); o += 4 + ln
        else:
            if o + 32 > len(d) or struct.unpack_from('<Q', d, o)[0] != i: return None
            o += 8
        rows.append((name, struct.unpack_from('<I', d, o)[0], d[o + 4:o + 24].hex())); o += 24
    return rows, o

def _name_table(d, lo, T):
    """The name table that ends before the frozen image the layout table at T closes: (names, end) of the one nearest below T (above lo), or None. It starts with the root type's name"""
    k = d.rfind(b'ShaderMapContent\x00', lo, T)
    if k < 0: return None
    for p in range(k, max(lo + 8, k - 64), -1):
        ln = struct.unpack_from('<I', d, p - 4)[0]
        if ln < 18 or d.find(b'\x00', p, p + ln) != p + ln - 1 or d[p] not in b'FT': continue
        cnt, o, names = struct.unpack_from('<I', d, p - 8)[0], p - 4, []
        for _ in range(cnt):
            if o + 4 > len(d): break
            ln = struct.unpack_from('<I', d, o)[0]
            if not 1 <= ln < 300 or o + 8 + ln > len(d) or d[o + 3 + ln]: break
            names.append(d[o + 4:o + 3 + ln].decode('latin1')); o += 8 + ln
        if len(names) == cnt: return names, o
    return None

def _code_run(d, at, end):
    """The FShaderMapResourceCode after the pointer table: the first position from `at` where u32 n, n x 20 bytes, u32 n agree and n entries {u32 length, stream, i32 raw size, u8 frequency} fit
    before `end`. → ([hash], [(start, length, raw size, frequency)], end of the last entry), or None"""
    for q in range(at, min(at + CODE_SCAN, end - 8)):
        n = struct.unpack_from('<I', d, q)[0]
        if not 0 < n < 1 << 20 or q + 8 + 20 * n > end or struct.unpack_from('<I', d, q + 4 + 20 * n)[0] != n: continue
        e, ents = q + 8 + 20 * n, []
        for _ in range(n):
            if e + 4 > end: break
            ln = struct.unpack_from('<I', d, e)[0]
            if ln > end - e - 9: break
            raw, fr = struct.unpack_from('<iB', d, e + 4 + ln)
            if not 0 < raw < 1 << 24 or fr > 5 or not (d[e + 4:e + 8] == b'LSLG' and ln == raw or d[e + 4:e + 5] in b'\x8c\xcc' and ln < raw): break   # one Oodle stream, or the record itself
            ents.append((e + 4, ln, raw, fr)); e += 9 + ln
        if len(ents) == n: return [d[q + 4 + 20 * i:q + 24 + 20 * i] for i in range(n)], ents, e
    return None

class _Frozen:
    """A frozen memory image d[b:b + size] and its pointers; every read is checked against the image"""
    def __init__(self, d, b, size): self.d, self.b, self.size = d, b, size
    def _at(self, o, n):
        if not 0 <= o <= self.size - n: raise MapError(f'{n} bytes at {o:#x} are outside the {self.size:#x} byte image')
        return self.b + o
    def u32(self, o): return struct.unpack_from('<I', self.d, self._at(o, 4))[0]
    def i32(self, o): return struct.unpack_from('<i', self.d, self._at(o, 4))[0]
    def u64(self, o): return struct.unpack_from('<Q', self.d, self._at(o, 8))[0]
    def ptr(self, o, plain=True):
        """The target offset of the pointer at o (None for null). An array's data pointer has 1 in its low 24 bits in every layout known; the elements of an array of TMemoryImagePtr (shaders,
        pipelines, mesh shader maps) keep their type there (plain=False)"""
        v = self.u64(o)
        if not v & 1: return None
        if plain and v & 0xffffff != 1: raise MapError(f'the pointer at {o:#x} has low bits {v & 0xffffff:#x}')
        t = v >> 24
        t = o + (t - (1 << 40) if t >= 1 << 39 else t)
        self._at(t, 0); return t
    def need(self, o, plain=True):
        """ptr(), refusing a null pointer"""
        p = self.ptr(o, plain)
        if p is None: raise MapError(f'the pointer at {o:#x} is null')
        return p
    def array(self, o):
        """(first element offset, count) of the TMemoryImageArray at o"""
        n = self.i32(o + 8)
        if n < 0 or n > self.size // 4: raise MapError(f'the array at {o:#x} counts {n}')
        return (self.need(o) if n else 0), n

def _walk(d, b, size, lay, types, svf, entries, hashes):
    """One image's shader maps → [dict(vf, shaders=[(type hash, permutation, frequency, entry)], pipes=[(pipeline type hash, {frequency: entry})])]: the root (no vertex factory: vf 0) and its mesh
    shader maps. Raises MapError when the image does not satisfy what the layout assumes"""
    f = _Frozen(d, b, size); known = set(types)
    def stage(o, fr_want=None):
        tg, ri = f.u32(o + lay.target), f.u32(o + lay.resource)
        if ri >= len(entries): raise MapError(f'shader at {o:#x} names code entry {ri} of {len(entries)}')
        if tg & 0xf != entries[ri][3]: raise MapError(f'shader at {o:#x} has frequency {tg & 0xf} but its code entry says {entries[ri][3]}')
        if fr_want is not None and tg & 0xf != fr_want: raise MapError(f'shader at {o:#x} has frequency {tg & 0xf} but sits in the pipeline slot of frequency {fr_want}')
        return tg & 0xf, ri
    def one(base, vf):
        st, n = f.array(base + lay.types); pm, n1 = f.array(base + lay.perms); sh, n2 = f.array(base + lay.shaders)
        if not n == n1 == n2: raise MapError(f'shader map at {base:#x}: {n} types, {n1} permutations, {n2} shaders')
        shaders = []
        for j in range(n):
            th = f.u64(st + 8 * j)
            if th not in known: raise MapError(f'shader map at {base:#x}: type hash {th:#x} is not in the pointer table')
            fr, ri = stage(f.need(sh + 8 * j, False)); shaders.append((th, f.i32(pm + 4 * j), fr, ri))
        pipes, (pa, pn) = [], f.array(base + lay.pipes)
        for j in range(pn):
            po = f.need(pa + 8 * j, False); stages = {}
            for slot, fr_want in lay.slots:
                if f.u64(po + slot) & 1: stages[fr_want] = stage(f.need(po + slot, False), fr_want)[1]
            pipes.append((f.u64(po), stages))
        return dict(vf=vf, shaders=shaders, pipes=pipes)
    out = [one(0, 0)]
    if lay.meshes is not None:
        arr, n = f.array(lay.meshes)
        if n != svf: raise MapError(f'{n} mesh shader maps, {svf} vertex factory types in the pointer table')
        for i in range(n):
            m = f.need(arr + 8 * i, False); out.append(one(m, f.u64(m + lay.vf)))
    return out

def _table_end(rows, T, named):
    return T + 4 + sum((5 + len(n) if named else 8) + 24 for n, _, _ in rows)

def _read_image(d, label, red, x, T, rows, names, layouts, named, seen, stats, limit):
    """The map of the image whose FrozenSize is at x and layout table at T: ({root, layout, types, submaps, entries, data}, end of its code run) or (None, end of the pointer table). The
    layout gate: the root's (name, size, SHA-1) must be one of `layouts`, and the dependent types the layout names must agree where the image has them"""
    o = _table_end(rows, T, named)
    nst, nvf = struct.unpack_from('<II', d, o); o += 8
    if nst > 1 << 16 or nvf > 1 << 16 or o + 8 * (nst + nvf) > len(d): return None, o, 'pointer table'
    sth = struct.unpack_from(f'<{nst}Q', d, o); o += 8 * (nst + nvf)
    run = _code_run(d, o, limit)
    if run is None: return None, o, 'no resource code'
    hashes, ents, end = run
    root = names[0]
    if root in UE5_MAP_NO_PAIRS: stats['skipped ' + root] += 1; return None, end, None
    key = (root, rows[0][1], rows[0][2]); lay = layouts.get(key)
    if lay is None:
        seen.setdefault(key, label)   # reported once per layout by the caller (unknown_layout)
        stats['unknown layout'] += 1; return None, end, None
    for i, nm in enumerate(names):
        if nm in lay.deps and rows[i][1:] != lay.deps[nm]:
            red(f'{label}: {nm} layout {rows[i][2]} (frozen size {rows[i][1]}) differs from the one the {root} layout was found with ({lay.deps[nm][1][:12]}, {lay.deps[nm][0]}); its shader maps give no pairs')
            stats['dependent layout'] += 1; return None, end, None
    shader_rows = [i for i in range(1, len(rows)) if rows[i][1] >= lay.target + 8]
    if len(shader_rows) != nst: red(f'{label}: {len(shader_rows)} shader types in the layout table but {nst} in the pointer table; its shader maps give no pairs'); stats['type count'] += 1; return None, end, None
    types = {h: names[i] for h, i in zip(sth, shader_rows)}
    try: subs = _walk(d, x + 4, T - x - 4, lay, types, nvf, ents, hashes)
    except MapError as e: red(f'{label}: {root}: {e}; its shader maps give no pairs'); stats['broken map'] += 1; return None, end, None
    return dict(root=root, layout=rows[0][2], types=types, submaps=subs, entries=ents, hashes=hashes, data=d), end, None

def unknown_layout(key, label, layouts):
    """The [RED] line for a root layout that is in no row of `layouts` (key = (root name, frozen size, SHA-1), label = where it was first met)"""
    return f'[RED] {label}: {key[0]} layout {key[2]} (frozen size {key[1]}) is not one this reader knows (known: {", ".join(f"{k[2][:12]} ({k[1]})" for k in layouts) or "none"}); its shader maps give no pairs'

def ue5_shader_maps(d, label, red, layouts=None, stats=None, seen=None):
    """The shader maps in one ExportBundleData chunk (UE 5 cooked material or material instance packages): [dict(root, layout, types {type hash: name}, submaps [dict(vf, shaders [(type hash,
    permutation, frequency, entry)], pipes [(pipeline type hash, {frequency: entry})])], entries [(start, length, raw size, frequency)] in d, hashes [20-byte shader hash per entry], data)]. The
    first image of a package has a name table in front; a later one (a package of several maps) has none and is walked only when its layout table equals the last named one's. red(msg) gets the text of each
    [RED] line, without the prefix, for a map that breaks a check (dropped whole); an unknown root layout is not reported here but put in `seen` {key: label} for unknown_layout, once per layout. stats counts what was not walked. A chunk with no shader map gives [] and no line"""
    layouts = UE5_MAP_LAYOUTS if layouts is None else layouts
    stats = collections.Counter() if stats is None else stats; seen = {} if seen is None else seen
    if b'ShaderMapContent\x00' not in d: return []
    tables = [(m.start(), got) for m in TYPE_TABLE.finditer(d, 4) if (got := _layout_rows(d, m.start()))]
    maps, last, lo = [], None, 0
    for k, (T, (rows, tend)) in enumerate(tables):
        if T < lo: continue
        nt = _name_table(d, lo, T)
        if nt and len(nt[0]) >= len(rows):
            names, o = nt[0][:len(rows)], nt[1]; x = next((x for x in range(o, min(o + 256, T - 3)) if struct.unpack_from('<I', d, x)[0] == T - x - 4), None)
            last = (names, rows)
        elif last is not None and rows == last[1]:   # an image without a name table of its own: the last named one's types
            names = last[0]; x = next((x for x in range(T - 4 - rows[0][1], max(lo, T - (1 << 22)), -1) if struct.unpack_from('<I', d, x)[0] == T - x - 4 and d[x + 4] & 1 and d[x + 5:x + 7] == b'\x00\x00'), None)   # the image starts with a pointer (the root's hash table)
        else:
            stats['unnamed image, other layout' if last else 'no name table'] += 1
            if last: red(f'{label}: an image without a name table whose type layout is not the first image\'s; its shader maps give no pairs')
            continue
        if x is None: stats['no image start'] += 1; continue
        try: mp, lo, why = _read_image(d, label, red, x, T, rows, names, layouts, False, seen, stats, tables[k + 1][0] if k + 1 < len(tables) else len(d))
        except (struct.error, IndexError): mp, lo, why = None, tend, 'truncated'
        if why: stats[why] += 1
        if mp: maps.append(mp)
    return maps

def ue5_global_maps(d, label, red, layouts=None, stats=None, seen=None):
    """The shader maps of a GlobalShaderCache-<format>.bin: u32 section count, then per section ff ff ff ff, u32 1, u32 FrozenSize, the image, the layout table with each row's own name, the
    pointer table and the resource code (ue5_shader_maps: the same dicts). The global shader map has no mesh shader maps"""
    layouts = UE5_GLOBAL_LAYOUTS if layouts is None else layouts
    stats = collections.Counter() if stats is None else stats; seen = {} if seen is None else seen
    maps = []
    try:
        n, o = struct.unpack_from('<I', d, 0)[0], 4
        for k in range(n):
            if d[o:o + 8] != b'\xff\xff\xff\xff\x01\x00\x00\x00': raise MapError(f'section {k} does not start where the last one ended')
            size = struct.unpack_from('<I', d, o + 8)[0]; x = o + 8; T = x + 4 + size
            got = _layout_rows(d, T, True)
            if got is None: raise MapError(f'section {k}: no type layout table')
            rows, _ = got
            mp, o, why = _read_image(d, f'{label} section {k}', red, x, T, rows, [r[0] for r in rows], layouts, True, seen, stats, len(d))
            if why: raise MapError(f'section {k}: {why}')
            if mp: maps.append(mp)
    except (MapError, struct.error) as e: red(f'{label}: {e}; the rest of its shader maps give no pairs'); stats['global cache'] += 1
    return maps

def ue5_entry(mp, i, decode):
    """The decoded LSLG record of a map's code entry i (ue5_inline_shaders' two forms: one Oodle stream, or the record itself), or None when the bytes are no record of its frequency"""
    start, ln, raw, fr = mp['entries'][i]; s = mp['data'][start:start + ln]
    if s[:4] != b'LSLG':
        try: s = decode(s, raw)
        except ValueError: return None
    try: return s if s[:4] == b'LSLG' and TAG_FREQ.get(s[4:6].decode('latin1')) == fr and lslg(s) else None
    except struct.error: return None


def made_archive(shaders):
    """A version 2 shader code archive of decoded shaders [(frequency, record)], the form the shader tools read: no shader maps, each shader's hash its SHA-1"""
    import hashlib
    out = bytearray(struct.pack('<III', ARCHIVE_VERSION, 0, len(shaders)))
    for _, s in shaders: out += hashlib.sha1(s).digest()
    out += struct.pack('<II', 0, len(shaders)); off = 0
    for fr, s in shaders: out += struct.pack('<QIIB', off, len(s), len(s), fr); off += len(s)
    return bytes(out + struct.pack('<II', 0, 0)) + b''.join(s for _, s in shaders)

def inline_archives(romfs, work, paks, key, decode):
    """The shaders kept inline (ue5_inline_shaders) as version 2 archives in <work>/archives, every shader once: the engine's global shader caches (GlobalShaderCache-<format>.bin in a pak, one
    archive each, ShaderArchive-Global-<format>) and the cooked packages of every IoStore container (ExportBundleData chunks, ShaderArchive-Packages). → their listing (job)"""
    seen, listing = set(), []   # every shader once: many materials share shaders
    def new(shaders):
        out = [x for x in shaders if x[1] not in seen]; seen.update(s for _, s in out); return out
    def put(name, src, path, shaders):
        if not shaders: return
        open(os.path.join(work, 'archives', name), 'wb').write(made_archive(shaders))
        listing.append(dict(name=name, pak=os.path.relpath(src, romfs), path=path, shaders=len(shaders), compressed=0, compression='inline, decoded'))
    for p in paks:
        for path in sorted(x for x in p.files if re.fullmatch(r'GlobalShaderCache-.+\.bin', os.path.basename(x))):
            fmt = os.path.basename(path)[len('GlobalShaderCache-'):-len('.bin')]
            put(f'ShaderArchive-Global-{fmt}.ushaderbytecode', p.path, path, new(ue5_inline_shaders(p.read(path, decode), decode)))
    found, tocs = [], io_tocs(romfs)
    for t in tocs:
        t.key = key   # io_tocs opens the containers without the pak key
        for i in t.of_type(IO_EXPORT_BUNDLE): found += new(ue5_inline_shaders(t.read(i, decode), decode))
    put('ShaderArchive-Packages.ushaderbytecode', os.path.dirname(tocs[0].path) if tocs else romfs, 'ExportBundleData chunks', found)
    return listing

class Lazy:
    """A decoder started at its first call (start() → the decoder, e.g. an OodleHost): the NSP script builds and starts the Mac host only when a game's files need the game's decoder"""
    def __init__(self, start): self.start, self.dec = start, None
    def __call__(self, comp, n):
        if not self.dec: self.dec = self.start()
        return self.dec(comp, n)
    def close(self):
        if self.dec: self.dec.close()

def mount_order(path):
    """A container's place in the mount stack: the game's container first, then the numbered patch chunks in order. A chunk ID that two containers both have resolves to the later container, as in
    the engine: the update's Glow-Switch_0_P.utoc (LEGO Horizon Adventures) carries the shader libraries' full tables with the base container's Glow-Switch.utoc, and lists the groups it did not
    change with that container's chunk IDs"""
    m = re.search(r'(?:_(\d+))?_P\.utoc$', os.path.basename(path), re.IGNORECASE)
    return (1, int(m.group(1) or 0), path) if m else (0, 0, path)

def io_tocs(romfs):
    """Every IoStore container under the RomFS, in mount order (mount_order): the base game's, then its patch chunks. A shader library's groups may live in any of them. TOC metadata needs no
    key; Toc.read refuses encrypted data when a selected library or group would have to be read"""
    out = []
    for dp, _, fs in os.walk(romfs):
        for f in fs:
            if not f.endswith('.utoc'): continue
            try: out.append(Toc(os.path.join(dp, f)))
            except (OSError, ValueError, struct.error): pass
    return sorted(out, key=lambda t: mount_order(t.path))

def io_shader_tocs(romfs):
    """The IoStore containers under the RomFS that hold Unreal Engine 5 shader libraries"""
    return [t.path for t in io_tocs(romfs) if t.of_type(IO_SHADER_LIBRARY)]

def archive_names(romfs):
    """The shader code archive names ("ShaderArchive-<library>-<format>") the RomFS's manifests list (Unreal's Manifest_UFSFiles_<platform>.txt)"""
    import re
    names = set()
    for f in os.listdir(romfs):
        if f.startswith('Manifest_') and f.endswith('.txt'):
            names |= set(re.findall(r'(ShaderArchive-[\w-]+?)\.ushaderbytecode', open(os.path.join(romfs, f), encoding='utf-8', errors='replace').read()))
    return sorted(names)

def paks(romfs):
    """Every pak under the RomFS"""
    return sorted(os.path.join(dp, f) for dp, _, fs in os.walk(romfs) for f in fs if f.endswith('.pak'))

def inline_shaders(path):
    """Whether a pak keeps its shaders inline in its cooked packages rather than in shader code archives: every legacy pak (DRAGON QUEST XI S), and a version 11 pak whose directory index
    names cooked packages (.uexp) and no .ushaderbytecode (OCTOPATH TRAVELER II: bShareMaterialShaderCode off). FINAL FANTASY RESONANCE's pak holds configs only (its shaders are in its IoStore
    container) and Octopath Traveler 0's index is encrypted (reading it takes main's key; it holds the archives): neither counts"""
    with open(path, 'rb') as f:
        enc, ioff, isz, _, ver = footer(f)
        if ver in LEGACY: return True
        if enc: return False
        r = R(read_range(f, ioff, isz, path), what=f'{path}: the index'); r.fstr(); r.take('<iQ')
        if r.take('<i'): r.take('<QQ'); r.raw(20)
        if not r.take('<i'): return False
        doff, dsz = r.take('<QQ'); d = read_range(f, doff, dsz, path)
    return b'.ushaderbytecode\0' not in d and b'.uexp\0' in d

def unreal_paks(romfs, inline=None):
    """The paks under the RomFS that Unreal wrote (its magic in the footer; inline None = any, True = those whose shaders are inline in the cooked packages, False = the others, inline_shaders):
    the NSP script decodes the shader code archives of the others (decode_ue_shaders); shader_split.py reads the inline ones file by file (ue_legacy_jobs)"""
    out = []
    for p in paks(romfs):
        try: inl = inline_shaders(p)
        except (OSError, ValueError, struct.error): continue   # shorter than a footer, or no Unreal pak
        if inline is None or inl == inline: out.append(p)
    return out

def job(romfs, main_nso, work, decode=None):
    """The shader code archives of every pak under the RomFS into <work>/archives, and one Oodle job (<work>/oodle.job) of every compressed shader in them; <work>/job.json lists them.
    The shader libraries of IoStore containers (Unreal Engine 5.6, FINAL FANTASY RESONANCE: no archive in the pak) go there already decoded: their container blocks and shader groups are
    Oodle-compressed, two layers, so they need decode (OodleHost: the game's decoder over a pipe) rather than the job. With neither (Unreal Engine 5 without shared material shader code, Demon
    Slayer -Kimetsu no Yaiba- The Hinokami Chronicles 2) the shaders are inline in the cooked data, taken out through decode as well (inline_archives)"""
    os.makedirs(os.path.join(work, 'archives'), exist_ok=True)
    img, lo, hi = nso_image(main_nso); key = None; listing, recs, opened = [], [], []
    tocs = io_tocs(romfs)
    libs = [t for t in tocs if t.of_type(IO_SHADER_LIBRARY)]
    if libs and not decode: raise ValueError(f'{libs[0].path}: IoStore shader libraries need the game\'s decoder (decode)')
    names = archive_names(romfs)
    # Chunk ID → (container, index), newest container first: a patch container's library lists the shader groups it did not change with the base container's chunk IDs
    chunk = {}
    for t in reversed(tocs):
        for k, c in enumerate(t.ids): chunk.setdefault(c, (t, k))
    seen = set()
    for t in reversed(tocs):
        for i in t.of_type(IO_SHADER_LIBRARY):
            if t.ids[i] in seen: continue   # a library the patch container replaces: its chunk ID is the same, and its tables are the current ones
            seen.add(t.ids[i])
            name = io_library_name(t, i, names) + '.ushaderbytecode'; b = io_archive(t, i, decode, chunk.get)
            open(os.path.join(work, 'archives', name), 'wb').write(b)
            listing.append(dict(name=name, pak=os.path.relpath(t.path, romfs), path=f'chunk {t.ids[i].hex()}', shaders=len(archive(b)['shaders']), compressed=0, compression='IoStore, decoded'))
    for pak in unreal_paks(romfs, inline=False):
        with open(pak, 'rb') as f: enc = footer(f)[0]
        if enc and key is None:
            key = find_key(img, lo, hi, pak)
            if key is None: raise ValueError(f'{pak}: the index is encrypted and no window of main decrypts it')
        p = Pak(pak, key); opened.append(p)
        for path in sorted(x for x in p.files if x.endswith('.ushaderbytecode')):
            b = p.read(path); a = archive(b, f'{pak}: {path}'); name = os.path.basename(path)
            comp = [i for i, (_, size, raw, _) in enumerate(a['shaders']) if size != raw]
            raws = lz4_shaders(b, a)
            if comp and raws: b = decoded_archive(b, raws); comp, how = [], 'LZ4'   # decoded here: the Oodle job gets none of them
            else: how = 'Oodle' if comp else ''
            open(os.path.join(work, 'archives', name), 'wb').write(b)
            for i in comp:
                off, size, raw, _ = a['shaders'][i]; recs.append((name, i, b[a['code'] + off:a['code'] + off + size], raw))
            listing.append(dict(name=name, pak=os.path.relpath(pak, romfs), path=path, shaders=len(a['shaders']), compressed=len(comp), compression=how))
    if not listing:
        if not decode: raise ValueError(f'{romfs}: no shader code archive or IoStore shader library, and the shaders kept inline need the game\'s decoder (decode)')
        listing = inline_archives(romfs, work, opened, key, decode)
    with open(os.path.join(work, 'oodle.job'), 'wb') as f:
        f.write(struct.pack('<II', JOB_MAGIC, len(recs)))
        for _, _, c, raw in recs: f.write(struct.pack('<II', len(c), raw)); f.write(c)
    json.dump(dict(archives=listing, records=[(n, i) for n, i, _, _ in recs]), open(os.path.join(work, 'job.json'), 'w'), indent=1)
    return listing, len(recs)

def finish(work, out):
    """The decoded archives into out, from <work>/oodle.job.out (the host's results, in job order)"""
    meta = json.load(open(os.path.join(work, 'job.json')))
    b = open(os.path.join(work, 'oodle.job.out'), 'rb').read() if meta['records'] else struct.pack('<II', OUT_MAGIC, 0)   # no Oodle shader: no host run
    magic, n = struct.unpack_from('<II', b)
    if magic != OUT_MAGIC or n != len(meta['records']): raise ValueError('the job output does not match the job')
    o, dec = 8, {}
    for name, i in meta['records']:
        l = struct.unpack_from('<I', b, o)[0]; o += 4
        if not l: raise ValueError(f'{name}: shader {i} was not decoded')
        dec[(name, i)] = b[o:o + l]; o += l
    os.makedirs(out, exist_ok=True)
    for x in meta['archives']:
        src = open(os.path.join(work, 'archives', x['name']), 'rb').read(); a = archive(src, x['name'])
        raws = [dec.get((x['name'], i)) or src[a['code'] + off:a['code'] + off + size] for i, (off, size, _, _) in enumerate(a['shaders'])]
        tmp = os.path.join(out, x['name'] + '.partial'); open(tmp, 'wb').write(decoded_archive(src, raws)); os.replace(tmp, os.path.join(out, x['name']))
    return [x['name'] for x in meta['archives']]

def lslg(s):
    """A decoded Switch shader (LSLG): 'LSLG', a stage tag (SV vertex, SP pixel, SC compute, ...), a header with the shader's source name, then u32 code length, the code area,
    u32 control length and the control section (0x880 bytes), and a short tail (24 or 29 bytes). → (tag, control section, code area), or None if the layout differs"""
    if s[:4] != b'LSLG': return None
    k = s.find(b'\x34\x12\x76\x98')
    if k < 8 or k + 0x708 > len(s): return None
    nctl, ncode = struct.unpack_from('<I', s, k - 4)[0], struct.unpack_from('<I', s, k + 0x704)[0]
    c = k - 4 - ncode
    if c < 4 or struct.unpack_from('<I', s, c - 4)[0] != ncode or k + nctl > len(s): return None
    return s[4:6].decode('latin1'), s[k:k + nctl], s[c:c + ncode]

if __name__ == '__main__':
    try:
        cmd = sys.argv[1] if len(sys.argv) > 1 else ''
        if cmd == 'list':
            img, lo, hi = nso_image(sys.argv[3])
            with open(sys.argv[2], 'rb') as f: enc = footer(f)[0]
            p = Pak(sys.argv[2], find_key(img, lo, hi, sys.argv[2]) if enc else None)
            with open(sys.argv[4], 'w') as f:
                f.write('path\traw\tstored\tmethod\tencrypted\tblocks\n')
                for path in sorted(p.files):
                    e = p.entry(path); f.write(f"{path}\t{e['raw']}\t{e['size']}\t{e['method'] or 'none'}\t{e['encrypted']}\t{len(e['blocks'])}\n")
            used = sorted({p.entry(x)['method'] for x in p.files} - {''})
            print(f'pak version {p.version}, mount {p.mount}, {len(p.files)} files, compression {used}')
        elif cmd == 'job':
            dec = OodleHost(*sys.argv[5:7]) if len(sys.argv) > 6 else None
            try: listing, n = job(*sys.argv[2:5], decode=dec)
            finally:
                if dec: dec.close()
            for x in listing: print(f"{x['name']}: {x['shaders']} shaders, {x['compressed']} compressed")
            print(f'{n} records in {os.path.join(sys.argv[4], "oodle.job")}')
        elif cmd == 'finish':
            print('decoded:', ', '.join(finish(*sys.argv[2:4])))
        else: sys.exit(__doc__ or 'usage: uepak.py list | job | finish (see the header)')
    except ValueError as e: sys.exit(f'[RED] {e}')   # a damaged main (nso.Error), pak or archive
