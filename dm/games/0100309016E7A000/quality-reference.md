# Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles: quality reached per machine

| Machine | Date | Build | Status |
|---|---|---|---|
| M4 Pro, 24 GB | 2026-11-03 | 1.53, main `14c878ecca9d7cb5b57e9b492b1bdb92` | Below, headless, the story's first scene only |

## How to read the numbers

The window is the wisteria path of the story's first scene: *walk* is 3 s of stick from the wide view, *stand* is the 25 s after it beside the guides. Each run walks as far as its frame rate lets it, so a slow run stands further back with more on screen (947 draws against 546): compare walks, and stands only between runs that reached the guides. Below about 14 ms `@gpu_ms` stops falling with resolution: passes wait on the frame's submissions, so it is not the GPU's cost alone.

## Applied at Maximum

| Improvement | Switch | Now | fps before → after | GPU p50 / p99 ms | How far | Next step, measured |
|---|---|---|---|---|---|---|
| Frame rate | 30 | 60, cinematics too | 30 → walk 57.6, stand 59.8, cinematic about 58 (`hc_h80c`, `m4_hsh`) | 14.7 / 18.0 walk, 14.7 / 14.9 stand | 60 | |
| Resolution | 1600x900 | 3840x2160 | Before the host's fix, wide view 27.8 fps (`hf_h4ksw`); after it 58.0 (`m3_hfin2`) | 35.9 / 37.7 → 14.0 / 15.1 | 100% | Above 4K not tried |
| Filtering | Linear | Anisotropic 16x | In every row | | 16x | |
| Shadows | 256, CSM 800 | 1024, CSM 2048 | Walk 57.9 → 57.6 (`m3_hfin*`, `m4_hsh`) | Stand 14.0 → 14.7 | Faces and hair shadows slightly firmer at a fixed spot | Higher not tried |
| Texture pool, application pool | 800 MB; 3.21 GB | 3,000 MB; 8 GB | | | | |

The walk's frame rate is below 60 for a burst of first-time pipelines at its start: 0 red lines in 3 of 3 runs with the final host (`m3_*`).

Resolution before the host's fix, for the record (wide view, stand): 3840x2160 27.8 fps, 90% 35.6, 85% 39.4. The walk: 80% 52.7, 70% 57.7, 2560x1440 59.3, 1920x1080 59.7.

The player's 75 minute session (`<work>/q/play/session_2026-11-03_1139.log`), before `depth_mode` and the prewarm list: 0.43% frames dropped, GPU median 13.7 ms, 7.5 GB peak, 1,783 bases compiled in play ([its note](README.md#the-players-session)). Sustained GPU over budget in three stretches: 18.5, 17.5 and 17.5 ms.

## Not applied, not measured

- Ambient occlusion, bloom, LOD, effects: the next pass, with a fight to measure in.
- PC lightmaps and meshes: not integrated ([below](#against-the-pc-build)); the PC textures are in ([PC textures in the game](#pc-textures-in-the-game)).

## Against the PC build

The Steam build (2 legacy paks, version 9, not encrypted, 25.8 GB) against Switch 1.53, read from the packages without running either game. Scratch tables: `<work>/q/pc`.

- **Audio: the same.** CRI ADX2, in `.awb` inside the paks on both sides. 129 of 131 `.awb` are byte-identical by SHA-256 (2.48 GB); the other two, `V_MAIN05` in English and Japanese, hold one clip that sits in the AWB on PC and in the ACB on Switch, with the same bytes. 294 of 296 ACB tables are identical; the other two differ for that clip. ADX mono 48 kHz about 216 kbps (22,361 tracks), stereo about 432 kbps (287), and 206 tiny HCA not decoded.
- **Movies: the same picture, other encodes.** 54 of 54 match by name, 1920x1080 at 30 fps with equal frame counts. PC: MPEG-1 at about 12.1 Mbps with ADX sound (432 and 216 kbps), 9.39 GB. Switch: VP9 at about 1.18 Mbps with HCA sound (96 and 64 kbps), 1.06 GB. On the one dark scene sampled (`dm0020`), PSNR 45-47 dB and SSIM 0.99, so little to gain there. Which movie sound is closer to the master is undetermined, busy scenes were not sampled, and whether the Switch's CRI runtime plays MPEG-1 was not checked.
- **Textures: the PC has more.** Of 200 sampled matched textures, 133 have a larger top level (96 with 4 times the pixels, 19 with 16 times), 63 are equal, and 197 have the same format. Matched `Texture2D`: 3.56 GB on PC against 1.67 GB, about 1.9 GB more if all were taken (extrapolated).
- **Lightmaps and meshes: larger on PC.** Lightmap packages 6.79 GB against 1.23 GB. Static meshes 910 MB against 432 MB of raw bytes, skeletal 2,125 MB against 1,524 MB; whether that is extra LODs or precision was not parsed.
- **Tools: written 2026-11-03.** Both are UE 4.25 with unversioned properties, but Switch keeps its packages in IoStore TOC version 2. `ue_pc_zen4.py` (called by `ue_pc_assets.py`) writes a version 2 patch container with `uepak.write_toc2`; how the game orders containers is in [PC assets](README.md#pc-assets). Run in the game since 2026-11-04 ([below](#pc-textures-in-the-game)).

## PC textures in the game

Headless on the M4 Pro, Maximum, same route (the first scene, the wisteria path, the two girls), 2026-11-04. The game reads the patch container (1,562 `.ucas` reads, 409 MB in the run; fewer bytes of the base container), 0 `[RED]`, no crash.

| Measure | Without | With the PC textures |
|---|---|---|
| Textures bound, one frame of the path | 438, 244.3 Mpix | 438, 352.7 Mpix (+44%) |
| Textures bound, the girls' scene | 223.2 Mpix | 304.5 Mpix (+36%) |
| Textures of 1024 and 2048 on the path | 37 and 7 | 91 and 14, plus one of 4096 |
| Footprint, peak | 4,819-4,875 MiB | 5,155-5,160 MiB (about +340 MiB) |
| GPU on the wisteria path | | about +1 ms (runs not scene-aligned) |

Ground and scenery visibly sharper; characters look the same.

The player's session (2026-11-04, 5.8 minutes, 20,700 frames, `<work>/q/play_pc/log.txt`): 0 `[RED]`, 0 audio underruns, exit 0. The prewarm prepared 3,722 lines in 3.9 s before the first frame (1,634 bases from the archive); 11 bases compiled in play. The opening cinematic held 53-57 fps for a moment: frames of 60-158 ms, the worst with 17 pipelines and 14 shader libraries made (93.7 ms). Walking the wisteria path (frames 11,700-14,100): GPU p50 16.8-17.3 ms, p95 18-19.5, 57-58 fps, 80 doubled frames in 47 s, the hitches the player saw. The training fight with Sabito: GPU p50 13-14 ms, 59.8 fps. The session without the PC textures (`<work>/q/play/session_2026-11-03_1139.log`) had stretches at 17-18.6 ms too. The player keeps Maximum as it is.

## Not checked

A fight measured headless. A stand-in taken from the archive rebuilt with `depth_mode zero`. Which draws cost 17-18.5 ms of GPU on the wisteria path. The High and Very high presets at 60. Lightmaps and meshes.
