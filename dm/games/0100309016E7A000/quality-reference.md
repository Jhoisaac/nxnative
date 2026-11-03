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
- Better audio: not compared, no PC copy. The sound is inside the IoStore containers and paks (no loose `.awb`), so a comparison needs the PC copy and a look into its packages.
- PC textures: no PC copy yet. This game is UE 4.25 with IoStore containers, so `ue_pc_assets.py` (made for UE 5) may need work; not checked.

## Not checked

Headless: a fight. The offline archive rebuilt with `depth_mode zero`, and a first start with the seeded list on an empty state. Which scenes cost 17.5-18.5 ms of GPU. the High and Very high presets at 60, the player's judgement.
