# Demon Slayer 2: quality reached per machine

A record of the picture quality this game reaches on each Apple chip at 60 fps, so a later chip can be compared with the same method. The game's [note](README.md#graphics-quality) explains the mechanisms. This page holds the results.

| Machine | Date | Build | Repository | Status |
|---|---|---|---|---|
| M4 Pro, 24 GB, macOS 27.0.1 | 2026-11-02 | 1.81, main `68e3a0ea176a79f403b859d4addad8c3` | `k2-pc-textures` at 43e3dcb | Below |
| M5 Pro | Not run | | | Add its columns by the [procedure](#repeating-the-pass-on-another-machine) |

## How to read the numbers

- **fps** is frames divided by the summed `@frame_ms` in the stated window. It is capped at 60 and includes scene loads inside the window, so it moves little. A window with a load shows about 58-59 fps even when nothing is wrong.
- **Over budget** is the share of frames with `@gpu_ms` above 16.6 ms. It and the GPU p99 are what separate two settings.
- **The GPU median does not show headroom.** It stays about 14 ms whatever is added, so `1000 / median` is not a speed. This page gives no uncapped fps, because none was measured.
- **Runs are single passes.** The spread between passes of one setting is about ±0.5 ms of GPU p50. Over-budget counts below about 1% are close to noise.

Windows: *route* is the regression route, frames 6000-10500, a load and the tutorial fight. *Tatami* is chapter 1 node 0, frames 11250-22000. *Cutscene* is chapter 3 node 3, frames 18000-32500. *Fight* is the same node, frames 33500-36000. Runs are in `<game folder>/0100AD80208A8000-work/pc_pilot/runs`.

## Applied at Maximum

| Improvement | Switch or earlier state | Now | fps before → after | Over budget, GPU p99 before → after | How far it was taken | Next step, measured on the M4 Pro |
|---|---|---|---|---|---|---|
| Render resolution | 1600x900 | 3840x2160 | Battle: no late frames at either (45 s, no fps window) | Battle GPU p95 12.1-12.5 → 15.0 ms | 100%: the display's native 4K | Above 4K not tried |
| Character and scene shadow maps | 256 | 2048 | No separate window | Part of the resolution row | 2048 | 4096: see "Not applied" |
| Texture filtering, LOD bias | Linear, LODBias 1-2 | Anisotropic 16x, LODBias 0 | No separate window | No separate window | 100% | None higher |
| PC textures, full set | Top mip stripped from about 9,000 textures; 756 Mpixels registered on the route | 12,194 textures; 1,262 Mpixels | Route 58.8 → 58.9 (`sw1`, `full1`) | 0.18% → 0.22%, 15.16 → 15.15 ms | 100% of the textures the PC build has larger | None higher. Cost is memory: 5.65 → 7.21 GB |
| PC lightmaps | Switch lightmaps | All 134 differing `*_BuiltData` packages, 4x pixels | Included in the row above | Included | 100% | None higher |
| PC stage meshes | Top LODs stripped | 1,584 meshes | Included in the row above | Included | Every mesh that passes the tool's checks; 284 with bulk data and 27 others skipped | Skipped ones need tool work, not power |
| Maximum post-processing set: AO, bloom, light shafts, translucency volume, LOD 0.5, view distance 2, foliage | The Switch's lowered values | The rows in `ue_quality.tsv` (set G) | Route 58.8 → 58.4 (`cw_0`, `cw_G`) | 0.24% → 0.31%, 15.18 → 15.97 ms | Every row kept, except AO resolution below | With shadows and effects too: 58.7 fps, 2.00%, 17.41 ms (`cw_F`) |
| Ambient occlusion resolution | Half, flatter (MaxQuality 0) | Half, MaxQuality 100 | Tatami 59.0 → 58.9 (`svv0b`, `svvH1`) | 0.57% → 0.72%, 15.41 → 15.52 ms | Half resolution | Full resolution: 57.6 fps, 23.7%, 19.31 ms (`svvP0`) |
| Cutscene scale (rewriter cut) | 56% | 90% | Cutscene 59.3 → 59.4 (`st0`, `st_M9_scale1`) | 0.19% → 0.57%, 15.42 → 15.32 ms | 90%. 95% was not tried | 100%: 59.3 fps, 4.70%, 17.95 ms, frame p99 19.5 ms (`st_M1_full`) |
| Texture pool, application pool | 1,200 MB; 3.21 GB | 3,000 MB; 8 GB | No effect on fps | None | 8 GB is thin: see [the session](#full-story-session) | 12 GB not tried |

Story nodes: 19 nodes reached, 59.1-59.9 fps. The table is in the note's [Story scenes](README.md#story-scenes-at-maximum).

## Not applied

| Improvement | Why | Evidence |
|---|---|---|
| Cutscenes at 100% | Power | 4.70% of frames over budget against 0.57% at 90%. fps still reads 59.3: see "How to read" |
| Full-resolution ambient occlusion | Power | Tatami room 57.6 fps, 23.7% over budget, and one pass at 5.59 ms against 1.39 ms |
| Every row together (`cw_F`) | Power | Route 58.7 fps, 2.00% over budget, GPU p99 17.41 ms |
| Shadows at 4096, 4 cascades, quality 5 (`cw_S`) | Cost without a seen gain | Route 58.4 fps, 0.62% over budget against 0.31%; in the shot, the fight's shadow targets stay 2048x512 |
| `r.Shadow.TexelsPerPixel` 2.546 (`st_T2`) | Cost without a compared gain | Fight 59.1 fps, GPU p99 16.15 ms against 15.38; shadow viewport doubled; not compared by eye |
| `r.DetailMode` 2, Niagara quality 3, particle lights (`cw_V`) | No seen gain; power was not the limit | Route 58.3 fps, 0.31%; frames without effects unchanged; frames with effects could not be compared |
| PC materials, material instances, Niagara systems, maps | Incompatible shaders | They carry D3D bytecode and `PCD3D_SM5` shader maps (survey of 26,834 other differing packages) |
| TAA/TSR, SSR, depth of field, motion blur, separate translucency, distance-field AO, Lumen, Nanite, virtual shadow maps | Incompatible shaders: not cooked for the Switch | The general rule in [07-quality.md](../../../docs/agents/07-quality.md). Not tried on this game |
| Better movies, audio | No better source | The `.usm` movies (1080p, 30 fps) and the audio are byte-identical on the PC |

Not tried at all: cutscenes at 95%, shadow settings between 2048 and 4096, above 4K, a Switch 2 dump as an asset source.

## Is this the maximum at 60 fps?

For the settings and scenes measured, yes: each step above what is applied either costs frames or showed no gain. It is not proven as an absolute maximum:

- 95% cutscenes and the shadow steps between 2048 and 4096 are untried.
- The effects set had no measured cost. It stays off for lack of a seen gain, so it could be turned on.
- 60 fps is not perfectly steady: see the session below.
- Only 19 story nodes were measured by tool. The player's session covers more, without per-scene numbers.

## Full story session

The player's session of 2026-11-02 on the 4K TV, against the certification session of 2026-11-01 before the PC assets. Both are at Maximum and use the app's log. The content and length differ, so the "first 99,900 frames" column is the fairest comparison, though the scenes still differ. The later session also had the Metal HUD on.

| Metric | Before (99,900 frames, 28 min) | After, first 99,900 frames | After, whole session (498,900 frames, 2.31 h) |
|---|---|---|---|
| Effective fps (shown / (shown + dropped) × 60) | 59.76 | 59.75 | 59.73 |
| Frames dropped | 0.399% | 0.415% | 0.452% |
| Frames with GPU over 16.6 ms | 95 (0.095%) | 147 (0.147%) | 593 (0.119%) |
| Frames over 100 ms | 34 (0.034%) | 18 (0.018%) | 56 (0.011%) |
| GPU p95 per 300 frames, median | 14.83 ms | | 14.82 ms |
| Windows with GPU p95 over 16.6 ms | 2 of 333 (0.6%) | | 83 of 1,663 (5.0%) |
| Peak footprint | 6.96 GB | 8.35 GB | 11.80 GB |
| Peak Metal allocation | 3.71 GB | | 6.15 GB |
| Application pool mapped | 4.75 GB | 5.75 GB by 28 min | 7.51 of 8.00 GB |
| `[RED]` lines, crashes, audio underruns | 0, 0, 0 | | 0, 0, 0 |

Open from this session:

- **The application pool is thin.** The game's allocator reached 7.51 of 8 GB at 110 minutes, growing about 0.25 GB per 20-30 minutes late in the session. Its earlier out-of-memory abort came at 3.03 of 3.21 GB, 94% of the pool, and 94% of 8 GB is 7.55 GB. A session of about 3 hours may abort the same way (an extrapolation). Whether the growth is the game's own or a leak is not known. A larger `ue_quality_app_pool` should move the ceiling; not tried.
- **Heavy GPU moments.** 375 frames with GPU over 20 ms in 106 clusters, up to 103 ms, with no new pipelines. The largest start at about 9, 25, 38, 64, 66, 71 and 99 minutes. The log does not name the scenes. These are the scenes the node survey did not reach.
- **The crash.** The session had no crash and no hit of the crash probes. The log does not show whether Zenitsu vs Daki was played, so that crash stays open.

## Repeating the pass on another machine

Keep the same app, save and scripts, and add a column set per machine. Scripts are in `<game folder>/0100AD80208A8000-work/pc_pilot/cv`.

1. Measure what is applied: `svbot.sh` on each node, `stroute.sh M9` and `sweep2.sh G`.
2. Measure the rows of "Not applied" that are marked Power: `use.sh scale1 M1` then `stroute.sh M1`; `use.sh scale1 P0` then `SUF=p svroute.sh 1:0`; `sweep2.sh F`.
3. Try what this machine never reached: `mkvar.py` variants for cutscenes at 0.95 and 1.0, full-resolution AO, 4096 shadows.
4. A step is accepted when over-budget frames stay under about 1% in its window and GPU p99 stays under 16.6 ms, in the node's heaviest window, with a visible gain in frame-aimed shots.
5. Add the changed rows to `ue_quality.tsv`. A preset for one chip needs a decision first: the app ships one Maximum for every Mac.
