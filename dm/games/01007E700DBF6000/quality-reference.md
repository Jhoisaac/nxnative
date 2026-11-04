# My Hero One's Justice 2: quality reached per machine

A record of the picture quality this game reaches on each Apple chip at 60 fps, so a later chip can be compared with the same method. The game's [note](README.md#graphics-quality) explains the mechanisms. This page holds the results.

| Machine | Date | Build | Status |
|---|---|---|---|
| M4 Pro, 24 GB | 2026-11-03 | 1.1.5, main `29e1cd0fbb24697e379da855ca5c367b` | Below, headless, one pass each |

## How to read the numbers

- **fps** is frames divided by the summed `@frame_ms` in the window. It is capped at 60, so it moves little.
- **Over budget** is the share of frames with `@gpu_ms` above 16.6 ms. It and the GPU p99 are what separate two settings. Below about 1% is close to noise.
- `@gpu_ms` can pass 16.6 ms with no dropped frame: passes overlap on the GPU, so the fps stays at 59.9 in the gym with GPU p99 above budget.

Windows: *fight* is free battle against the CPU, frames 8000-13800 (5,785 frames, screenshot frames left out). *Story* is the story's first node, frames 6000-12500: comic panels, then the tutorial fight in the gym. The save is a copy of the player's, past the first steps.

## Applied at Maximum

| Improvement | Switch | Now | fps before → after | Over budget, GPU p99 before → after | How far | Next step, measured |
|---|---|---|---|---|---|---|
| Render resolution, dynamic resolution off | 1920x1080, dynamic against 33.33 ms | 3840x2160, fixed | Fight 59.8 → 59.9 (`s1_sw`, `s1_base`) | Fight 0% → 0.03%, 13.72 → 15.42 ms | 100%: the display's native 4K | Above 4K not tried |
| Filtering | Linear, mip point | Anisotropic 16x, mip linear | Fight 59.9 → 59.9 (`s1_base`, `s1_aniso`) | 0.03% → 0.05%, 15.42 → 15.66 ms | 16x | None higher |
| PC textures, the full set | Top mip stripped | 5,663 textures with it (5,646 with the rule before 2026-11-04), `LODBias` 0 | Fight 59.9 → 59.9 (`s1_base`, `s5_full`) | 0.03% → 0.10%, 15.42 → 15.58 ms | Every texture that passes the level check: 141 fail it and keep the Switch's. New rule, headless (`rule_app1`): fight 59.3 fps, 13.69 / 15.59 ms, 0.08%, peak 5,367 MiB | None: the PC has no larger mips |
| Texture pool, application pool | 800 MB; 3.21 GB | 3,000 MB; 8 GB | No effect | None | 3.25 GB mapped in a fight | A long session not measured |

The full set, all together: fight 59.9 fps, 0.10% over budget, GPU p99 15.58 ms, frame p99 19.9 ms, 60 frames over 20 ms against 34 with the pilot (`s5_full`, `s4_rel`); story 59.9 fps, 2.37% over budget, GPU p99 18.36 ms, frame p99 17.6 ms (`st5_full`). The story's gym misses the GPU rule with no dropped frame, and it was 1.12%, 17.72 ms with the pilot. Peak footprint 5.30 GB, alias region 3.53 GB in a fight. The pilot's own numbers: fight 0.02%, 15.35 ms; story 1.12%, 17.72 ms (`s4_rel`, `st4_rel`). A player's session of 14,700 frames on the pilot, with a window, at 3840x2160: 0 red lines, 0 audio underruns, 68 empty display ticks in all, most at first-time pipelines (the longest frame after boot 297.5 ms, a second fight's first pipelines; those of that session and the routes now seed `pso_manifest.tsv`, 653 lines).

## Not applied

Measured in the fight window against `s1_base` (0.03%, 15.42 ms). Pictures at a fixed frame in training (`t1_*`): none shows a difference a player would see in a crop at 4K, and same-frame differences stay near the idle animation's.

| Improvement | Why | Evidence |
|---|---|---|
| Ambient occlusion: `r.AmbientOcclusionLevels` -1, `r.DefaultFeature.AmbientOcclusion` 1, quality 100 | No visible gain, though no measurable cost | 0.00%, 15.29 ms |
| Post-processing: bloom 5, lens flare, tonemapper 5, `r.PostProcessAAQuality` 6, light shafts | No visible gain, costs budget | 0.66%, 16.43 ms |
| LOD: `r.ViewDistanceScale` 2, `r.StaticMeshLODDistanceScale` 0.5, `r.SkeletalMeshLODBias` -1 | No visible gain, over the rule | 1.38%, 16.91 ms |
| Shadows 4096, 4 cascades, `r.Shadow.RadiusThreshold` 0.01 | No visible gain, over the rule | 1.40%, 16.80 ms |
| Shadows 2048, 3 cascades, `r.ShadowQuality` 5 (in the first presets) | No visible gain in training; the gym's frames over budget fall without it (story 4.90-6.99% with them on `st2_*`, 1.12% without) | `st4_rel` |
| Effects: `r.DetailMode` 2, particle lights, translucency volume 64 | No visible gain, over the rule | 1.78%, 17.27 ms |
| FXAA `r.PostProcessAAQuality` 6, alone | No visible gain in a crop at 4K, over the rule | 1.43%, 17.15 ms (`s5_aa6`, `t5_aa6`) |
| `r.BloomQuality` 5, alone | No visible gain, over the rule | 1.12%, 16.72 ms (`s5_bloom5`, `t5_bloom5`) |
| `r.DepthOfFieldQuality` 2, alone | No blur appears in the fight intro; no cost | 0.07%, 15.65 ms (`s5_dof2`, `s6_dof2`) |
| Temporal AA `r.DefaultFeature.AntiAliasing` 2 | Over the rule | 8.64%, 18.82 ms, 59.7 fps (`s5_taa`) |
| MSAA 2x `r.DefaultFeature.AntiAliasing` 3, `r.MSAACount` 2 | Metal rejects the command buffers: a million red lines, 45 fps | `s5_msaa2` |
| Movies at a higher resolution | Video, the same files on the PC | 15 `.usm`, byte-identical |
| Full resolution cutscene work | Nothing to do: fight intros and rounds stay 3840 wide (79 of 80 sampled frames, the other is before the first scene) | `s3p`, pass dumps every 120 frames |

## Audio against the PC

Compared on 2026-11-03: all 1,371 files of `HeroGame/Content/CriWareData` are byte-identical on the PC (SHA-256): 1,356 `.awb`, 942 MB, and the 15 `.usm` movies, 793 MB. So the sound and the movies stay the Switch's. From the headers of every sub-file: voices HCA, mono, 48 kHz, about 128 kbps (6,469 English; 6,319 Japanese, and 148 at 44.1 kHz, about 117 kbps); `Common`, 174 sub-files, HCA at 44.1 kHz, mono about 117 kbps or stereo about 235 kbps, and two stereo at 48 kHz, about 256 kbps.

## Not checked

A session over 28 minutes, the other presets (High, Very high), handheld, a played session on the archive rebuilt with `depth_mode zero`, and the stage's lighting on a real Switch or PC. One run (`t1_base`) logged a GPU recovery (`kIOGPUCommandBufferCallbackErrorInnocentVictim`, 68 lines, then frames went on) that no other of 17 runs showed; cause not found, open.
