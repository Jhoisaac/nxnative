# DRAGON BALL Z: KAKAROT + A NEW POWER AWAKENS SET (`010051C0134F8000`)

Update 1.70 (v1048576, `main` build `e99dffa39354b6068f8e7c984c77bc84`) with its 17 DLC (16 of them licences only), SDK 9.3.1. CyberConnect2's game on Unreal Engine 4.24 (`++UE4+Release-4.24`, pak version 8) on NVN, with CRIWARE sound and movies (`.usm`, VP9, decoded by the SDK's movie module in `subsdk0`). 60 fps on the Mac (30 on the Switch).

Status: played on the Mac by the user: the title, a new game, the Raditz / Nappa / Vegeta cutscene and the forest drawn right, at 30 fps with sound and natural movie colours; 60 fps checked headless (below). Not tried on the iPhone. The profile started from the NSP script's provisional one, with two texture keys, the frame rate and a prewarm list.

## What it needs

| Setting | Where | Why |
|---|---|---|
| `tex_flush_upload on`, `tex_dirty_upload on` | `game.tsv` | Unreal's texture streamer writes streamed mips straight into the textures' storage (below) |
| `mem_reserve 0x1028000000`, `mem_alias 0x1000000000` | `game.tsv` | `nninitStartup` reserves a 62 GB address region and `FMallocBinned3` takes 37 GB of it: a 64 GB alias region for the Mac. The game's regions reach alias +62.06 GB in its first 15 s in `nnMain` (the rewrite `ceddb1ec254f`; what it takes later in play is not measured). An iPhone needs the allocator cut for the build and a capped region (`game_args`), as Octopath Traveler 0's ([Provisional Unreal layout leaves no heap](../../../docs/reference/memory.md#provisional-unreal-layout-leaves-no-heap)) |
| `fps_target 60`; two rows for build `e99dffa3…` | `game.tsv`; `hle_fpslock.c` | the host writes Unreal's `t.MaxFPS` and `rhi.SyncInterval` for 60 fps (below) |
| `sys_resource 0x1000000` | `game.tsv` | the NPDM declares 16 MB of system resource |
| `shader_groups ShaderArchive-Global-=global ShaderArchive-=game` | `game.tsv` | the decoded shader code archives: the engine's global shaders and the game's materials |

## Frame rate

- **Current:** 60 fps (30 on the Switch), with the 30 / 60 choice in the settings window (`DM_FPS_TARGET=30` keeps the game's own rate). The cap is `rhi.SyncInterval=2` in `DefaultEngine.ini` (`[SystemSettings]`) and `t.MaxFPS` 30, which the game sets at run time; `bUseFixedFrameRate=False`, so the engine steps by the real delta. The host writes `t.MaxFPS` 60 (the variable registered at `main+0x3e8ee78`, its value at `main+0x9d02df8`+0x10) and `rhi.SyncInterval` 1 (`main+0x2a2699c`, value at `main+0x9c0a080`+0x10), gated by this build (`hle_fpslock.c`; the names are UTF-16 strings at `main+0x7923c92` and `main+0x77e61e4`), and `UEngine::FixedFrameRate` 60 (`[main+0x9d02558]+0x814`: the GEngine pointer, and the property offset from the reflection record at `main+0x8cfbcd0`).
- **Cinematics** (resolved): for every movie and real-time cutscene the game turns on `bUseFixedFrameRate` (bit 0x40 of `[GEngine]+0x810`) with `FixedFrameRate` 30 (`main+0xdde930`, which also writes `t.MaxFPS` 30; `main+0xddb490` clears it), so cutscenes stayed at 33.4 ms frames while the two cvars were already rewritten ([Unreal's fixed frame rate](../../../docs/reference/frame-rate.md#unreals-fixed-frame-rate-uenginefixedframerate)). With the `FixedFrameRate` row they present at 59.8 fps. Checked headless (New Game route): the Raditz cutscene lasts 102.1 s at both 30 and 60 fps, the movies 67.6 / 33.4 / 6.0 s at both, the subtitles come at the same moments in paired screenshots, and with the GPU saturated (frames of 140-166 ms) the cutscene still lasts 104.3 s: its timing follows the clock, not the frame count. Movies (30 fps content) repeat frames at 60.
- Checked headless on an M4 Pro: the forest at frame time p50 16.70 ms, p95 17.26, p99 18.23 (game GPU p50 12.2 ms, p99 16.0); the same stick input from one save puts Goku at the same place at 60 and 30 fps (movement and voice triggers keep their speed). Played windowed by a player at 60 fps with MetalFX to 3840x2160 (combat and exploration at p50 16.71 ms, p95 about 17.1 ms).
- With the Mac's MetalFX spatial upscale to 3840x2160 the upscale's own GPU time (p50 5.2 ms) comes on top of the game's (p50 about 9.5 ms in that player's session) and fits 16.7 ms.
- **Hitches** (a player's 14-minute session at 30 fps): load stalls of 300-720 ms with the GPU idle (the engine's async loading and game thread on the CPU, not the host's write protection: under 5 ms of it), pipelines compiled on the spot (85 in 37 frames, about 2.2 s; the prewarm list `pso_manifest.tsv`, 1,913 lines recorded in that session, covers them), and short CPU hitches not yet attributed.
- A 12 fps reading at the end of one log was the window out of focus (the display link stalls), not the game.

## Rendering

- **Streamed textures** (current, resolved by the two keys): random-colour block mosaics on Raditz's armour and hair, tree trunks, ground and rocks, and a black Gohan, with no `[RED]` line. Unreal's streamer writes each streamed mip level on the CPU, straight into the texture's storage in `CPU_UNCACHED` pools (flags `0xe2`), after `nvnTextureInitialize` and with no flush; without both keys the host kept those textures GPU-only (filled once at first use, or zero) and they held stale or zero blocks. The guest's storage decoded correctly (a comparison of the guest's bytes with the host's picture). With the keys the forest and the cutscene draw right ([Mapped-range flushes taken as uploads](../../../docs/reference/nvn-objects.md#mapped-range-flushes-taken-as-uploads-tex_flush_upload), [CPU writes with no flush, caught by page protection](../../../docs/reference/nvn-objects.md#cpu-writes-with-no-flush-caught-by-page-protection-tex_dirty_upload); Yoshi's Crafted World and OCTOPATH TRAVELER set the same pair).
- The `sparse texture sampled from level 1 of 10` lines are Unreal's sparse pools and harmless.

## Movies

The `.usm` cinematics (257 loose files in `AT/Content/Movies`, 6.2 GB: VP9 1920x1080 at 30 fps with HCA sound and subtitle channels) are decoded in native-texture mode into a BGRA8 texture; the host wrote RGBA bytes and the colours came out red / blue swapped (blue-white skin, `[RED] movie: client texture format 0x9a is not RGBA8`). Fixed for every game ([Native-texture output into BGRA8 / BGRX8 textures](../../../docs/reference/movies.md#native-texture-output-into-bgra8--bgrx8-textures)).

## Files and shaders

- 2 pak files (version 8) plus 7,988 loose `.uasset` files in the RomFS; the packed Mac app is 25.5 GB (a 24.3 GB RomFS image). The shaders are inline in the cooked packages: 75,430 in the split, global and material shaders ([Unreal Engine 4.21 to 4.25 paks (versions 7, 8 and 9) and 4.25 IoStore containers](../../../docs/reference/shaders.md#unreal-engine-421-to-425-paks-versions-7-8-and-9-and-425-iostore-containers)). A fresh save boots to the language select, the EULA (the dialog defaults to Decline: Up, then A), the privacy page and the title (Version 1.70) with no `is not in the shader map` line.

## Graphics quality

`ue_quality.tsv` gives the settings window's **Graphics quality** row (`DM_UE_QUALITY`): Switch (off, the default), High (1080p), Very high (1440p), Maximum (4K output). Unreal reads its device-profile cvars from `AT/Config/Switch/SwitchDeviceProfiles.ini` in `pakchunk0-Switch.pak` at boot, so a preset is a pak `pakchunk0-Switch_99_P.pak` with that ini edited, version 8 like the game's ([how](../../../docs/agents/07-quality.md)). Current, Mac only. The per-machine results are in the [quality reference](quality-reference.md). Maximum takes the PC textures ([below](#pc-textures)).

The profile also sets `ue_quality_app_pool` (8 GB: Unreal's allocator budgets against the reported pool, and the Switch's 3.21 GB does not fit 4K targets) and `depth_mode zero` (the game sets near = 0, so the app's offline pipeline archive takes the `main0_z` vertex entries; without the key its bases were made for near = -w and could not stand in for a draw).

The Switch asks 1600x900 with dynamic resolution, `LODBias` 2 on the world and character texture groups (1 on effects and lightmaps), and lower `sg.*` groups.

| Row | High | Very high | Maximum |
|---|---|---|---|
| `r.setres` | 1920x1080 | 2560x1440 | 3840x2160 |
| `r.ScreenPercentage` | 100 | 100 | 70 (the scene 2688x1512, the interface at 4K) |
| `r.DynamicRes.OperationMode` | 0 | 0 | 0 |
| `r.MaxAnisotropy`; the groups' `linear` becomes `aniso`, mip `point` becomes `linear` | 8 | 8 | 16 |
| `r.Streaming.PoolSize` | 1600 | 1600 | 3000 |

Maximum also raises shadows (`r.Shadow.MaxResolution` and `MaxCSMResolution` 2048, 4 cascades, `r.ForceLODShadow` -1, landscape shadows), post-processing (bloom 5, lens flares, light shafts, tonemapper 5), LOD and foliage (`r.ViewDistanceScale` 2, `r.StaticMeshLODDistanceScale` 0.5, `r.LandscapeLODDistributionScale` 2), ambient occlusion and effects, and `LODBias` to 0 on the groups that had 2 or 1 (for the PC textures). The whole set is the reason for a scene below native: each group alone passes at 90% on the forest walk, all together at 90% leave 25.88% of its frames over budget, and at 100% with nothing else 36.48%. Maximum was 80% until the player's decision of 2026-11-03 to take 70%, because the east canyon flight was over budget at 80% ([result](quality-reference.md#the-east-canyon)).

**Cinematics.** The 257 movies are `.usm` VP9 outside the paks, so resolution does not raise them. The PC's movies are MPEG-2 (CRI Prime), which the Switch's player shows as a black screen, so they cannot replace them; re-encoding was not tried. Real-time cutscenes were not sampled for their scene size.

### PC textures

Current, Mac only. `ue_pc_assets.tsv` has one rule, `max textures AT/Content/*`, handled by `dm/tools/ue_pc_paks.py` (the [pak-game path](../../../docs/agents/07-quality.md#pak-games)). The PC copy's base paks (`AT/Content/Paks`, version 7, Zlib, not encrypted) hold each Switch level as the PC level of its size, swizzled, byte for byte. A Switch texture whose stored levels are a contiguous slice of the PC's mip chain gets the PC's size, first mip and level count, with the top levels added and the tail levels after; it is taken only if every stored Switch level equals the PC level of that size. When only the first stored level matches (a re-encode of the same image) the PC's whole chain replaces the Switch's, so no texture mixes the two; otherwise the Switch's stays.

Full set (2026-11-03): 9,670 textures taken (full chain 24) of 162,022 packages, 3.73 GB of raw texels added, pak 1.63 GB. Skipped: missing 5,922, same 6,960, format 139,248, level 222. The first pilot (Area03, the shared trees, the playable characters) was 493 textures and a 0.04 GB pak; the earlier rule took 7,946 on the full set.

Not taken, and why:

- **Lightmaps.** 413 `*_BuiltData` maps have no baked lighting on the Switch (an empty registry); 54 have a different bake (other texture counts and atlas sizes). 8 compatible ones are in the set. The heightmap `.umap` data textures have another layout (502 maps). 169 PC-only textures are referenced by no Switch package.
- **Meshes.** The playable characters' meshes are the same size on both builds; NPC, enemy and vehicle meshes are 1.4-1.5x larger on the PC. The PC cook is UE 4.21 and the Switch's 4.24 (the executables' version strings), so the packages would need a converter: not attempted.
- **The PC's `dlc/Remaster` paks** (UE 4.27, Oodle Kraken): the same audio, 236 of the same movies, 31-81 stage textures larger (inferred from the index sizes). Not used.

In the picture (100% crops) the canyon rocks show cracks and grain the pilot smeared; the characters (Piccolo, Goku) are nearly unchanged. The cost at the canyon is about +2 ms of GPU with the draws equal (inferred: bandwidth of the bigger mips); memory about +250 MiB footprint and +300-400 MB resident and GPU allocated, the app pool of 8 GB not approached and `r.Streaming.PoolSize` 3000 not exceeded. This is why the full set moved the scene percentage: at 80% the canyon was over budget on every frame, and the player chose 70% with the full set (2026-11-03). The measurements are in the [quality reference](quality-reference.md#pc-textures-full-set). Engine acceptance: 8 runs, 0 `[RED]`, no crash, no black or corrupt texture.

The same tool serves MY HERO ONE'S JUSTICE 2 ([its note](../01007E700DBF6000/README.md)); with this rule it takes 5,663 textures (full chain 129), 7.72 GB raw, pak 3.68 GB, 141 failing the level check (the earlier rule took 5,646); not run in game with the new rule.

## Mac routes

- A fresh save: A twice at the language screen, the opening movie about 2 minutes after boot, the EULA (Plus, Up, A), New Game, the first cinematic and the first Piccolo fight.
- The user's state (`~/Library/Application Support/nxnative/010051C0134F8000/`) holds a save past the Piccolo fight; copy it into a run folder rather than writing there.
- `smoke.tsv` (for `scripts/regress.py`) starts from the autosave at the start of Piccolo's canyon flight, kept as `saves/canyon` in the NSP folder. The harness runs the game at its own 30 fps and its first frame comes about 64 to 67 s after launch (frame f at about 65 + f/30 s): A at frames 1,500 and 1,900 take the title, A at 2,300 and 2,700 Continuar and the autosave, Up and A at 3,100 and 3,500 answer the load confirmation (Si), A at 3,900 and 4,300 dismiss the first tutorial bubble, and Piccolo stands on the canyon edge from about 215 s (shots at 250 and 300 s). Checked on two harness runs (7,567 and 7,457 frames in 330 s, both shots as described).

## Found on this game

General changes first needed here; each applies to every game:

- **Unreal Engine 4.21 to 4.25 paks in the shader split** (`uepak.py`, `shader_split.py` `ue_io_jobs`): [Unreal Engine 4.21 to 4.25 paks (versions 7, 8 and 9) and 4.25 IoStore containers](../../../docs/reference/shaders.md#unreal-engine-421-to-425-paks-versions-7-8-and-9-and-425-iostore-containers).
- **Movie output into BGRA8 / BGRX8 textures** (`nvn_host_write_texture`): [Native-texture output into BGRA8 / BGRX8 textures](../../../docs/reference/movies.md#native-texture-output-into-bgra8--bgrx8-textures).
- **PC mip chains for pak games** (`ue_pc_paks.py`, current): the PC's size, first mip and level count around the stored levels, a full chain when a re-encode differs ([Pak games](../../../docs/agents/07-quality.md#pak-games)).
- **Streamed mips written to uncached pools** (profile keys `tex_flush_upload`, `tex_dirty_upload`, current): [CPU writes with no flush, caught by page protection](../../../docs/reference/nvn-objects.md#cpu-writes-with-no-flush-caught-by-page-protection-tex_dirty_upload).
- **Graphics-quality presets** (`ue_quality.tsv`, `ue_quality_app_pool`, `depth_mode`, current): [Graphics quality](#graphics-quality), [Raising an Unreal game's graphics quality](../../../docs/agents/07-quality.md).

## Open

- Load stalls and short CPU hitches are the game's own CPU work, not attributed further.
- Not tried on the iPhone (the alias region, the allocator cut and a capped region are needed there).
- A Latin American Spanish dub of the cinematics is planned, not made: the voices are in the `.usm` files (the `ja` / `en` voice channels beside a 6-channel bed), the game's other voices are `ja` and `en` AWB banks; the idea is `DM_ROMFS_OVERLAY` with same-size audio.
- The shader tables, `c1_full.tsv` and `cb_extent.tsv` come from the provisional profile's build. My Hero One's Justice 2 needed the same two texture keys (its walls).
