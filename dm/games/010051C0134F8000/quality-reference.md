# DRAGON BALL Z: KAKAROT: quality reached per machine

A record of the picture quality this game reaches on each Apple chip at 60 fps, so a later chip can be compared with the same method. The game's [note](README.md#graphics-quality) explains the mechanisms.

| Machine | Date | Build | Status |
|---|---|---|---|
| M4 Pro, 24 GB | 2026-11-03 | 1.70, main `e99dffa39354b6068f8e7c984c77bc84` | Below, headless, one pass each; Maximum at 70% by the player's decision |

## How to read the numbers

**fps** is frames divided by the summed `@frame_ms` in the window, capped at 60. **Over budget** is the share of frames with `@gpu_ms` above 16.6 ms; it and the GPU p99 are what separate two settings. Below about 1% is close to noise.

The window is the forest walk: frames 8800-12800, 3,988 frames with screenshot frames left out. The east canyon windows are described under [The east canyon](#the-east-canyon).

PC textures are a separate change; rows below that include the PC pilot say so.

## Applied at Maximum

| Improvement | Switch | Now | fps | Over budget, GPU p99 | How far | Next step, measured |
|---|---|---|---|---|---|---|
| Output and interface | 1600x900 | 3840x2160 | | | 100% | None |
| Scene resolution | 1600x900, dynamic | 2688x1512 (70%) | 59.7 | 0.00%, 15.17 ms at the canyon, standing | 70% with the raised set | 75% at the canyon: 0.00%, 16.18 ms; 80%: 73.4%, 17.44 ms |
| Shadows, post-processing, LOD and foliage, ambient occlusion, effects | The Switch's | The rows in `ue_quality.tsv` | | Part of the row above | Together at 70% | Together at 90% on the forest walk: 59.4 fps, 25.88%, 17.53 ms |
| Filtering, texture pool, application pool | Linear for most groups; 3.21 GB | Anisotropic 16x; 3,000 MB; 8 GB | | Part of the row above | 16x | None higher |

Peak footprint 4.69 GB, alias region 4.50 GB mapped, no `[RED]` line, no crash.

## Measured steps

| Set | fps | Over budget | GPU p50 / p99 | Run |
|---|---|---|---|---|
| Switch | 59.9 | 0.03% | 14.26 / 15.49 | `s1_sw` |
| 100%, none of the raised rows | 59.5 | 36.48% | 16.24 / 17.72 | `s1_base` |
| 95% | 59.7 | 4.09% | 15.00 / 17.15 | `s2_sp95` |
| 90% | 59.8 | 0.00% | 14.57 / 15.15 | `s1_sp90` |
| 80% | 59.8 | 0.03% | 14.67 / 15.14 | `s1_sp80` |
| 70% (scene percentage alone) | 59.8 | 0.03% | 14.65 / 15.20 | `s1_sp70` |
| 90% + shadows | 59.8 | 0.00% | 14.67 / 15.58 | `s2_shadow` |
| 90% + post-processing | 59.8 | 0.00% | 14.88 / 15.84 | `s2_post` |
| 90% + LOD and foliage | 59.8 | 0.00% | 14.76 / 15.79 | `s2_lod` |
| 90% + ambient occlusion | 59.8 | 0.00% | 14.63 / 15.07 | `s2_ao` |
| 90% + effects | 59.8 | 0.00% | 14.60 / 15.13 | `s2_fx` |
| 90% + LOD + post-processing | 59.8 | 2.83% | 15.47 / 16.77 | `s3_LP` |
| 90% + all | 59.4 | 25.88% | 15.97 / 17.53 | `s3_G` |
| 85% + all | 59.8 | 0.03% | 14.81 / 16.29 | `s3_G85` |
| 85% + all + PC pilot (a separate change), `LODBias` 0 | 59.7 | 8.10% | 15.26 / 16.88 | `s4_rel` |
| 80% + all + PC pilot (a separate change), `LODBias` 0 | 59.8 | 0.00% | 14.66 / 15.54 | `s5_rel80` |

A walk in Goku's house and the cooking menu at 85% with the PC pilot: 60 fps, 0.02% over budget, GPU p99 15.08 ms (`st1`).

## Not applied

| Improvement | Why | Evidence |
|---|---|---|
| Native 4K scene | Power | 36.48% over budget before anything else |
| PC movies | MPEG-2 (CRI Prime): the Switch's player shows black; re-encoding not tried | |
| PC textures | A separate change | |

## The player's session

62 minutes at Maximum on the M4 Pro (2026-11-03): 220,800 frames, 0 red lines, 0 audio underruns, exit 0, peak footprint 6,044 MiB. 714 of 736 windows of 300 frames stay at or under 15.5 ms of GPU median; 22 do not, all in the last 9 minutes.

- **Over budget, resolved by 70%:** flying as Piccolo over the canyon held 54-57 fps at 80%. See [The east canyon](#the-east-canyon).
- **Display beat (inferred):** a frame of about 17.4 ms on a 60 Hz display leaves about 14 of 314 ticks with no new frame, which fits the regular spikes in the frame-interval graph.
- **Flying dinosaur, open:** the player sees it move unevenly. The preset has no animation row (no `a.URO.*`); the log shows no host fault. Not confirmed; see the canyon section.
- **Pipelines:** that session's app had no `depth_mode`, so its bundled archive (near=-w) could not stand in for a draw in this near=0 game; 627 bases compiled in play, none in the flight. The profile now has `depth_mode zero` and 795 more seed lines. The rebuilt app, first start headless on an empty state: no stamp mismatch, 16 of 16 probed bases found, the prewarm compiled 1,194 bases with a layout in 23 s in the background, 0 red lines. The archive holds only bases without a layout, so these are still built on the device, once. A stand-in taken from it was not measured.

## The east canyon

Measured 2026-11-03 on the M4 Pro, headless, Maximum.

**Flight at 80% (the player's log and a flight run).** Flying as Piccolo over the east canyon held 54-57 fps: GPU p50 17.2-17.9 ms, frame time follows the GPU, CPU submit and present about 3.3 ms, 0 pipeline compiles, draws about 1,450, the same as places at 60 fps. The cost is GPU work per draw in this view.

**Per pass** (`DM_NVN_GPUPROF`, the canyon standing at the flight start against the forest walk, divided by passes per frame, about +-0.2 ms):

| Pass group | Canyon | Forest |
|---|---|---|
| Sum | about 16.5 ms | 13.5 ms |
| 3072x1728 G-buffer | 6.2 ms | 4.3 ms, at about the same draw count (heavier terrain and cliff materials) |
| RG11B10 and two-colour passes | 2.7 ms | 1.5 ms |
| Shadows | 0.36 ms | 1.0 ms |

About 90% of the frame scales with scene resolution.

**Variants** at the canyon, standing, frames 13500-15500, one change each from Maximum at 80%:

| Set | fps | GPU p50 / p99 | Over budget |
|---|---|---|---|
| 80% | 59.2 | 16.69 / 17.44 | 73.4% |
| 75% | 59.7 | 14.98 / 16.18 | 0.00% |
| 70% (chosen) | 59.7 | 13.39 / 15.17 | 0.00% |
| LOD distances lowered | 59.7 | 16.19 / 16.93 | 13.9% |
| Anisotropy 8x | 59.7 | 16.44 / 16.91 | 21.8% |
| `DM_NVN_TBDR=1` | 58.3 | 16.83 / 19.67 | 79.3% |
| Switch preset | 59.8 | 11.00 / 16.50 | 0.85% |

Flying costs about 0.6-1.2 ms more than standing (from the player's log), which 70% leaves room for (p99 15.17 ms standing).

**Forest:** 70, 80 and 90% all had GPU p99 about 15.1-15.2 ms earlier (`s1_sp70`, `s1_sp80`, `s1_sp90`), so 70% costs nothing there.

**Picture.** 100% crops at the canyon show 70% a hair softer on rock edges and the bridge than 80%, with no artifacts. The Switch preset is clearly blurrier.

**Flying dinosaur's uneven motion: not confirmed, open.** The player's canyon windows drop about 19 of 300 frames on screen against about 1 in 60 fps stretches, which would show as about 4 Hz judder on a small fast object (inferred). The game's own animation update rate for distant skeletons is not checked.

**Route.** A headless route to the canyon from a save at the flight start is `q/keys_canyon.txt` in the work folder; take-off with the left stick up.

## Not checked

Fights and towns as a measured route, real-time cutscenes' scene size, the High and Very high presets, handheld. The 70% set with every raised row was measured at the canyon standing, not yet on the forest walk or in a fight; the player's flight at 70% is not measured.
