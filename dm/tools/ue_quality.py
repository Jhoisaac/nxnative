#!/usr/bin/env python3
# Unreal graphics-quality presets as replacement paks: ue_quality.py <game id> <RomFS root of the extracted game> <out dir> <host> <modules dir>
# For each preset in the profile's ue_quality.tsv (dm/games/README.md) it writes <out dir>/<preset>/<directory of the pak>/<pak stem>_99_P.pak, holding every ini the preset edits, each read from the
# game's own pak (the last of the RomFS's paks, in name order, that holds it; Oodle-compressed inis go through the game's Oodle in the host, uepak.OodleHost, started only when one is needed) and edited.
# The packer copies <out dir> to the app's Resources/dm/ue_quality/; the host (hle_fs.c, DM_UE_QUALITY=<preset>) puts <preset> in front of the RomFS overlay roots, and the game mounts the _99_P pak with
# priority over the original: the console variables are read at boot from the ini, so they cannot be set later (docs/development.md, Unreal graphics quality).
# A row that matches no ini, no section, or (TextureLODGroups) no line stops with a message and a non-zero exit.
import os, re, shutil, sys
from pathlib import Path
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '../gfx/tools')); sys.path.insert(0, os.path.join(HERE, '../games'))
import uepak

class Error(Exception): pass

def rows(path):   # [(preset, ini, section, key, value)] in file order
    out = []
    for n, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip() or line.startswith('#'): continue
        c = line.split('\t')
        if len(c) != 5 or not all(c): raise Error(f'{path}:{n}: expected preset, ini, section, key, value (5 tab-separated fields)')
        out.append(tuple(c))
    return out

def apply(text, section, edits, ini='the ini'):
    """text with edits = [(key, value)] applied to [section]: its own line ends are kept (Unreal's inis are CRLF)"""
    lines = text.splitlines(keepends=True)
    nl = '\r\n' if '\r\n' in text else '\n'
    head = f'[{section}]'
    start = next((i for i, l in enumerate(lines) if l.strip() == head), None)
    if start is None: raise Error(f'{ini}: no section {head}')
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('[')), len(lines))
    for key, value in edits:
        if key == 'TextureLODGroups':
            fields = [f.split('=', 1) for f in value.split(',')]
            if any(len(f) != 2 for f in fields): raise Error(f'{ini}: TextureLODGroups value must be Field=Value[,Field=Value...]: {value}')
            hit = 0
            for i in range(start + 1, end):
                m = re.match(r'(\+TextureLODGroups=\()(.*)(\)\s*)$', lines[i], re.S)
                if not m: continue
                body, touched = m.group(2), False
                for f, v in fields:
                    old, _, v = v.rpartition('>')   # Field=Old>New edits only the groups whose Field is Old (the data textures keep their point filter)
                    cur = re.search(r'(?<![\w.])' + re.escape(f) + r'=([^,)]*)', body)
                    if old and (not cur or cur.group(1) != old): continue
                    if cur: body = body[:cur.start(1)] + v + body[cur.end(1):]
                    else: body += f',{f}={v}'
                    touched = True
                if touched: lines[i] = m.group(1) + body + m.group(3); hit += 1
            if not hit: raise Error(f'{ini}: [{section}] has no +TextureLODGroups line')
            continue
        pat = re.compile(r'\+CVars=' + re.escape(key) + r'=')
        i = next((i for i in range(start + 1, end) if pat.match(lines[i])), None)
        if i is not None:
            lines[i] = f'+CVars={key}={value}' + (lines[i][len(lines[i].rstrip('\r\n')):] or nl)
        else:
            last = max((i for i in range(start, end) if lines[i].strip()), default=start)   # after the section's last non-blank line
            if not lines[last].endswith('\n'): lines[last] += nl
            lines.insert(last + 1, f'+CVars={key}={value}{nl}'); end += 1
    return ''.join(lines)

def build(game_id, romfs, out, host, modules):
    import game
    g = game.load(game_id); tsv = g.table('ue_quality.tsv')
    if not tsv.is_file(): raise Error(f'game profile {game_id} has no ue_quality.tsv')
    table = rows(tsv)
    if not table: raise Error(f'{tsv} has no rows')
    paks = uepak.paks(romfs)
    if not paks: raise Error(f'no .pak under {romfs}')
    dec = uepak.Lazy(lambda: uepak.OodleHost(host, modules, os.environ))
    opened, cache, report = {}, {}, []
    def holder(ini):   # the last pak (name order) that holds the ini, and its text
        if ini not in cache:
            for p in reversed(paks):
                if p not in opened: opened[p] = uepak.Pak(p)
                if ini in opened[p].files:
                    try: cache[ini] = (p, opened[p], opened[p].read(ini, dec).decode('utf-8')); break
                    except ValueError as e: raise Error(str(e)) from e
            else: raise Error(f'no pak under {romfs} holds {ini}')
        return cache[ini]
    try:
        presets = list(dict.fromkeys(r[0] for r in table))
        for preset in presets:
            d = os.path.join(out, preset); shutil.rmtree(d, ignore_errors=True)
            by_pak = {}
            for ini in dict.fromkeys(r[1] for r in table if r[0] == preset):
                p, pak, text = holder(ini)
                for sec in dict.fromkeys(r[2] for r in table if r[0] == preset and r[1] == ini):
                    text = apply(text, sec, [(r[3], r[4]) for r in table if r[0] == preset and r[1] == ini and r[2] == sec], ini)
                by_pak.setdefault(p, (pak, []))[1].append((ini, text.encode('utf-8')))
            size = 0
            for p, (pak, files) in by_pak.items():
                rel = os.path.relpath(p, romfs); stem = os.path.basename(rel)[:-4]
                dest = os.path.join(d, os.path.dirname(rel)); os.makedirs(dest, exist_ok=True)
                f = os.path.join(dest, f'{stem}_99_P.pak'); uepak.write_pak(f, pak.mount, files, pak.version); size += os.path.getsize(f)
            report.append(f'{preset}: {sum(len(v[1]) for v in by_pak.values())} ini file(s) in {len(by_pak)} pak(s), {size:,} bytes')
    finally:
        dec.close()
    return report

def main(argv):
    if len(argv) != 5: sys.exit(__doc__ or 'usage: ue_quality.py <game id> <RomFS root> <out dir> <host> <modules dir>')
    try:
        for line in build(*argv): print(line)
    except (Error, ValueError, OSError) as e:
        sys.exit(f'ue_quality.py: {e}')

if __name__ == '__main__': main(sys.argv[1:])
