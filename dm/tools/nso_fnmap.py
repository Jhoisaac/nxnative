#!/usr/bin/env python3
# Carry offsets across two builds (recover addresses hard-coded in the host / rewriter after a game update): nso_fnmap.py <old .orig.bin> <new .orig.bin> 0xoffset...
# The function table comes from eh_frame (starts + FDE lengths). Each function is hashed over its instructions with address-dependent bits masked: the immediates of b / bl / b.cond / cbz / tbz / adr / adrp / literal ldr,
# and the low 12 bits of an add / ldr / str that follows an adrp and uses its destination register as the base (the data segments moved as a whole, so in-page offsets change too). Struct member offsets and constants still take part.
#   Code offsets: if the containing function has a unique identical hash in the new build → same offset within that function ("exact"); otherwise pick by instruction similarity between the nearest exact matches before / after ("near", similarity reported).
#   Text that no FDE covers (Unreal Engine builds: most of main has no unwind entries) is cut into functions by prologue (sub sp / pre-indexed stp x29, x30) after a ret / b / br / brk / padding word, over the whole text up to the last PLT stub (br x17).
#   Such a function with a unique identical hash in the new build gives the same offset within it ("segment-exact"). Last resort for code offsets: the 16-word window around the offset (shifted up to a few windows) is searched in the whole masked new text and
#   the candidate with the longest identical masked run wins ("run N words"; equal best runs are reported as ambiguous in red). FDE-covered offsets are answered as before; the locator only replaces "not found in the new build" there.
#   Data offsets (globals): the adrp + add/ldr/str pairs in the old build that compute exactly that address are decoded at the same place in the new build when their function is an exact match (FDE or fallback segment); several references must agree.
# One line per offset: old → new, method, old / new containing function; reported in red when the instruction at the new place differs (after masking) from the old one.
# The .orig.bin files are produced by dm/tools/nso.py (the whole memory image).
import bisect, collections, difflib, hashlib, struct, sys
import numpy as np

class Img:
    def __init__(self, path):
        with open(path, 'rb') as f: self.b = f.read()
        self.w = np.frombuffer(self.b[:len(self.b) // 4 * 4], dtype='<u4')
        m0 = struct.unpack_from('<I', self.b, 4)[0]
        ehs = m0 + struct.unpack_from('<i', self.b, m0 + 16)[0]
        _, penc, cenc, tenc = self.b[ehs:ehs + 4]
        assert (penc, cenc, tenc) == (0x1b, 0x03, 0x3b), f'eh_frame_hdr encodings {penc:#x} {cenc:#x} {tenc:#x}'
        n = struct.unpack_from('<I', self.b, ehs + 8)[0]
        fn = {}
        for i in range(n):
            loc, fde = struct.unpack_from('<ii', self.b, ehs + 12 + i * 8); loc += ehs; fde += ehs
            pc0 = fde + 8 + struct.unpack_from('<i', self.b, fde + 8)[0]; size = struct.unpack_from('<I', self.b, fde + 12)[0]
            if pc0 != loc: continue   # skip FDEs whose encoding is not pcrel sdata4
            fn[loc] = max(fn.get(loc, 0), size)
        self.starts = sorted(fn); self.size = fn
        self.text_end = text_end(self.w, ehs)
        self.mask = masked(self.w, 0, self.text_end)
        self.hash = {s: hashlib.sha1(self.mask[s // 4:(s + fn[s]) // 4].tobytes()).digest() for s in self.starts}
        self.fstarts, self.fend = fallback_segments(self.w[:self.text_end // 4], self.starts, [self.size[s] for s in self.starts])
        self.fhash = {a: hashlib.sha1(self.mask[a // 4:b // 4 - trailing_zeros(self.w[a // 4:b // 4])].tobytes()).digest() for a, b in zip(self.fstarts, self.fend)}   # without the alignment padding after the last instruction
    def func(self, off):
        i = bisect.bisect_right(self.starts, off) - 1
        return self.starts[i] if i >= 0 and off < self.starts[i] + self.size[self.starts[i]] else None
    def seg(self, off):
        """start of the fallback segment (text no FDE covers) holding off"""
        i = bisect.bisect_right(self.fstarts, off) - 1
        return self.fstarts[i] if i >= 0 and off < self.fend[i] else None
    def u32(self, off): return int(self.w[off // 4])

def text_end(w, ehs):
    """end of the text in a memory image (its header is not in the file): just after the last PLT stub (br x17) below eh_frame_hdr, else after the last ret"""
    for ins in (0xd61f0220, 0xd65f03c0):
        r = np.nonzero(w[:ehs // 4] == ins)[0]
        if len(r): return (int(r[-1]) + 1) * 4
    return ehs

def trailing_zeros(x):
    nz = np.nonzero(x)[0]
    return len(x) - (int(nz[-1]) + 1 if len(nz) else 0)

def fallback_segments(w, starts, sizes):
    """(starts, ends) of the functions cut by prologue in the words w (the text) outside the FDE functions starts / sizes: a start is a sub sp / pre-indexed stp x29, x30 right after a ret, b, br, brk or padding word, or the first word of a gap"""
    p = np.concatenate(([0], w[:-1]))
    pro = ((w & 0xFF0003FF) == 0xD10003FF) | (((w & 0xFFC003E0) == 0xA98003E0) & (((w >> 10) & 31) == 30) & (((w >> 5) & 31) == 31))
    prev = (p == 0xd65f03c0) | (p == 0) | ((p >> 26) == 5) | ((p & 0xFFFFFC1F) == 0xD61F0000) | (p == 0xd4200000)
    cut = pro & prev
    cov = np.zeros(len(w) + 1, dtype=np.int8)   # FDE function words
    for a, n in zip(starts, sizes):
        if a // 4 < len(w): cov[a // 4] += 1; cov[min((a + n) // 4, len(w))] -= 1
    cov = np.cumsum(cov[:-1]) > 0
    gap0 = np.nonzero(~cov & np.concatenate(([True], cov[:-1])))[0]   # first word of each gap
    cut = (cut | np.isin(np.arange(len(w)), gap0)) & ~cov
    s = np.nonzero(cut)[0]
    # a segment ends at the next start or where the next FDE function begins
    fs = np.array(sorted(starts), dtype=np.int64) // 4; k = np.searchsorted(fs, s, side='right')
    e = np.minimum(np.append(s[1:], len(w)), np.where(k < len(fs), fs[np.minimum(k, max(len(fs) - 1, 0))], len(w)))
    return (s * 4).tolist(), (e * 4).tolist()

def masked(w, lo, hi):
    """mask address-dependent bits word by word within lo..hi (unchanged outside)"""
    m = w.copy(); s = slice(lo // 4, hi // 4); x = m[s]
    for msk, val, keep in ((0x7c000000, 0x14000000, 0xfc000000),   # b / bl
                           (0xff000010, 0x54000000, 0xff00001f),   # b.cond
                           (0x7e000000, 0x34000000, 0xff00001f),   # cbz / cbnz
                           (0x7e000000, 0x36000000, 0xfff8001f),   # tbz / tbnz
                           (0x1f000000, 0x10000000, 0x9f00001f),   # adr / adrp
                           (0x3b000000, 0x18000000, 0xff00001f)):  # literal ldr
        sel = (x & msk) == val; x[sel] &= keep
    # add (64-bit immediate) / ldr / str (unsigned offset) within 8 instructions after an adrp, based on its destination register: mask the low 12 bits
    raw = w[s]; adrp = np.nonzero((raw & 0x9f000000) == 0x90000000)[0]
    rd = (raw[adrp] & 31); live = np.ones(len(adrp), dtype=bool)
    for k in range(1, 9):
        ok = live & (adrp + k < len(raw)); idx = np.minimum(adrp + k, len(raw) - 1); v = raw[idx]
        hit = ok & ((((v & 0xff800000) == 0x91000000) | ((v & 0x3b000000) == 0x39000000)) & (((v >> 5) & 31) == rd))
        x[idx[hit]] &= ~np.uint32(0x3ffc00)
        live &= ok & ~hit & ~(((v & 31) == rd) & ((v & 0x9f000000) != 0x90000000) & ((v & 0x3b000000) != 0x39000000))   # destination register rewritten by another instruction
    return m

def adrp_refs(img, target):
    """instruction pairs in img whose adrp + add/ldr/str compute exactly target"""
    out = []; w = img.w; page = target & ~0xfff
    cand = np.nonzero((w & 0x9f000000) == 0x90000000)[0]
    for i in cand:
        v = int(w[i]); imm = ((v >> 29) & 3) | (((v >> 5) & 0x7ffff) << 2)
        if imm & (1 << 20): imm -= 1 << 21
        if ((i * 4) & ~0xfff) + (imm << 12) != page: continue
        rd = v & 31
        for j in range(i + 1, min(i + 9, len(w))):
            u = int(w[j])
            if (u >> 5) & 31 != rd: continue
            if (u & 0xff800000) == 0x91000000: lo = (u >> 10) & 0xfff
            elif (u & 0x3b000000) == 0x39000000: lo = ((u >> 10) & 0xfff) << (u >> 30 if not (u & 0x04800000) == 0x04800000 else 4)
            else: continue
            if page + lo == target: out.append((i * 4, j * 4))
            break
    return out

def pair_addr(img, a, b):
    v, u = img.u32(a), img.u32(b)
    imm = ((v >> 29) & 3) | (((v >> 5) & 0x7ffff) << 2)
    if imm & (1 << 20): imm -= 1 << 21
    lo = (u >> 10) & 0xfff
    if (u & 0x3b000000) == 0x39000000: lo <<= (u >> 30 if not (u & 0x04800000) == 0x04800000 else 4)
    return (a & ~0xfff) + (imm << 12) + lo

def run_len(a, i, b, j, backward):
    """number of equal words of a from i and b from j, going up (or down from i - 1 / j - 1)"""
    n, done, step = 0, 0, 1 << 10
    while True:
        if backward:
            k = min(step, i - done, j - done)
            if k <= 0: return done
            eq = a[i - done - k:i - done][::-1] == b[j - done - k:j - done][::-1]
        else:
            k = min(step, len(a) - i - done, len(b) - j - done)
            if k <= 0: return done
            eq = a[i + done:i + done + k] == b[j + done:j + done + k]
        if not eq.all(): return done + int(np.argmin(eq))
        done += k; step = min(step * 2, 1 << 20)

def locate(old, new, off, win=16):
    """candidates (new offset of off, run length in words, window shift) from the longest identical masked run around off, best first.
    A window of win words at off - shift is looked up in the new masked text through its rarest words; the first shift that has a candidate is used."""
    o = off // 4; O, N = old.mask, new.mask
    for shift in (win // 2, 0, win, win // 4, 3 * win // 4, 2 * win, -win // 2, -win):
        a = o - shift
        if a < 0 or a + win > len(O): continue
        ws = O[a:a + win]; c = min(range(win), key=lambda d: int(np.count_nonzero(N == ws[d])))   # the rarest word anchors the search
        cand = np.nonzero(N == ws[c])[0] - c; cand = cand[(cand >= 0) & (cand + win <= len(N))]
        for d in range(win):
            if len(cand) == 0: break
            cand = cand[N[cand + d] == ws[d]]
        if len(cand) == 0: continue
        res = []
        for n in cand[:200].tolist():
            b = run_len(O, a, N, n, True); f = run_len(O, a, N, n, False)
            res.append(((n + shift) * 4, b + f, shift))
        return sorted(res, key=lambda r: -r[1])
    return []

def main():
    old, new = Img(sys.argv[1]), Img(sys.argv[2])
    by_new = collections.defaultdict(list)
    for s, h in new.hash.items(): by_new[h].append(s)
    by_old = collections.Counter(old.hash.values())
    exact = {s: by_new[h][0] for s, h in old.hash.items() if by_old[h] == 1 and len(by_new.get(h, ())) == 1}
    print(f'functions old {len(old.starts)} new {len(new.starts)}, unique exact matches {len(exact)}')
    ex_old = sorted(exact)
    fby_new = collections.defaultdict(list)
    for a, h in new.fhash.items(): fby_new[h].append(a)
    fby_old = collections.Counter(old.fhash.values())
    fexact = {a: fby_new[h][0] for a, h in old.fhash.items() if fby_old[h] == 1 and len(fby_new.get(h, ())) == 1}
    print(f'fallback segments (no FDE) old {len(old.fstarts)} new {len(new.fstarts)}, unique exact matches {len(fexact)}')
    def run_line(off):
        r = locate(old, new, off)
        if not r: print(f'[RED] {off:#x}: not found in the new build (no identical masked window around it)'); return
        n, ln, sh = r[0]; amb = [x for x in r if x[1] == ln]
        print(f'{"[RED] " if len(amb) > 1 else ""}{off:#x} → {n:#x}  code  run {ln} words' + (f'  ambiguous {[hex(x[0]) for x in amb[:5]]}' if len(amb) > 1 else '') + ('' if old.mask[off // 4] == new.mask[n // 4] else f'  instruction differs {old.u32(off):08x} / {new.u32(n):08x}'))
    def near(f):
        if f in exact: return exact[f], 1.0, 'exact'
        i = bisect.bisect_left(ex_old, f); lo = exact[ex_old[i - 1]] if i else 0; hi = exact[ex_old[i]] if i < len(ex_old) else 1 << 62
        a = old.mask[f // 4:(f + old.size[f]) // 4].tolist(); best = (0, None)
        for g in new.starts[bisect.bisect_right(new.starts, lo):bisect.bisect_left(new.starts, hi)]:
            if abs(new.size[g] - old.size[f]) > max(64, old.size[f] // 4): continue
            r = difflib.SequenceMatcher(None, a, new.mask[g // 4:(g + new.size[g]) // 4].tolist(), autojunk=False).ratio()
            if r > best[0]: best = (r, g)
        return best[1], best[0], f'near {best[0]:.3f}'
    for arg in sys.argv[3:]:
        off = int(arg, 16); f = old.func(off)
        if f is not None:
            g, r, how = near(f)
            if g is None: print(f'[RED] {off:#x}: function {f:#x} not found in the new build; locator:'); run_line(off); continue
            n = g + off - f; same = old.mask[off // 4] == new.mask[n // 4]
            print(f'{"" if same and r == 1.0 else "[RED] " if not same else ""}{off:#x} → {n:#x}  code  {how}  old fn {f:#x}+{off - f:#x} → new {g:#x}' + ('' if same else f'  instruction differs {old.u32(off):08x} / {new.u32(n):08x}'))
            continue
        if off < old.text_end:   # code outside the FDEs
            a = old.seg(off)
            if a in fexact:
                n = fexact[a] + off - a; same = old.mask[off // 4] == new.mask[n // 4]
                print(f'{"" if same else "[RED] "}{off:#x} → {n:#x}  code  segment-exact  old seg {a:#x}+{off - a:#x} → new {fexact[a]:#x}' + ('' if same else f'  instruction differs {old.u32(off):08x} / {new.u32(n):08x}'))
            else: run_line(off)
            continue
        refs = adrp_refs(old, off); got = collections.Counter(); used = 0
        for a, b in refs:
            fa = old.func(a); tab = exact
            if fa is None: fa = old.seg(a); tab = fexact
            if fa is None or fa not in tab: continue
            g = tab[fa]; got[pair_addr(new, g + a - fa, g + b - fa)] += 1; used += 1
        how = ''
        if not got:   # no reference in an exact-match function: place each reference by its identical masked run (at least 40 words, clearly the longest)
            used = 0; how = ' by run'
            for a, b in refs[:400]:
                r = locate(old, new, a)
                if not r or r[0][1] < 40 or len(r) > 1 and r[1][1] > 0.8 * r[0][1]: continue
                try: got[pair_addr(new, r[0][0], r[0][0] + b - a)] += 1; used += 1
                except (struct.error, IndexError): continue
        if not got: print(f'[RED] {off:#x}: data, {len(refs)} references in the old build, none placed (exact-match function, FDE or fallback segment, or masked run)'); continue
        (n, k), = got.most_common(1)
        print(f'{"" if len(got) == 1 else "[RED] "}{off:#x} → {n:#x}  data  {k}/{used} references agree{how} ({len(refs)} in the old build)' + ('' if len(got) == 1 else f'  disagree {dict(got)}'))

if __name__ == '__main__': main()
