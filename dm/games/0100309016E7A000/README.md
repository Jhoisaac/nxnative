# Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles (`0100309016E7A000`)

Update 1.53 (v589824, `main` build `14c878ecca9d7cb5b57e9b492b1bdb92`) with its add-ons, SDK 9. CyberConnect2's game on Unreal Engine 4.25 (`pakchunk0-Switch.pak`, pak version 9 with a frozen index, and IoStore containers) on NVN.

## What it needs

| Setting | Where | Why |
|---|---|---|
| `mem_reserve 0x1028000000`, `mem_alias 0x1000000000` | `game.tsv` | Unreal's address reservation |
| `sys_resource 0x1000000` | `game.tsv` | the NPDM declares 16 MB of system resource |
| `shader_groups ShaderArchive-Global-=global ShaderArchive-=game` | `game.tsv` | the decoded shader code archives |

## Graphics quality

`ue_quality.tsv` gives the settings window's **Graphics quality** row: Switch (off), High (1080p), Very high (1440p), Maximum (4K). The cvars come from `APK/Platforms/Switch/Config/SwitchDeviceProfiles.ini` in `pakchunk0-Switch.pak`; a preset is `pakchunk0-Switch_99_P.pak`, version 9 with the frozen flag clear ([how](../../../docs/agents/07-quality.md)). Current, Mac only. The Switch asks 1600x900, `LODBias=1`, linear filtering, `r.Shadow.MaxResolution` 256, `r.Shadow.MaxCSMResolution` 800, `r.MaxAnisotropy` 1. All three presets set `r.Shadow.MaxResolution` 1024, `r.Shadow.MaxCSMResolution` 2048, anisotropic filtering (8x; 16x at Maximum) and a larger texture pool. `ue_quality_app_pool` is 8 GB. Results: [quality reference](quality-reference.md).

There are no movies in the RomFS: the cutscenes are in the engine. The first scene runs at 3840x2160 in the pass dump; the other scenes are not sampled.

## Frame rate

Current: every preset plays at 60 fps, with no change to the game's code. The Switch preset stays at 30. `ue_quality.tsv` sets `=FixedFrameRate` 60 in `/Script/Engine.Engine` (`DefaultEngine.ini`), `rhi.SyncInterval` 1 in `SwitchConsole`, and `=MaxFrameRateUsedInCinema` and `=MaxFrameRateUsedInStandDemo` 60 (`DefaultGame.ini`, `APKDemoManager` and `APKDemo`), the two limits that held cinematics at 30. The game's code knows both rates: it compares `FixedFrameRate` with 60 and picks its constants for 1/60 or 1/30 (main+0x2b892b0, main+0x2c92fb0, main+0x23c9c14).

The game steps by a fixed 1/`FixedFrameRate` per frame, so a frame rate under 60 slows the game instead of dropping frames: a walk at 30 fps covered half the ground, which first looked like a wrong game speed. It was the GPU: 35.9 ms a frame at 3840x2160 in the wisteria path's wide view, 122 render passes, 8.1 GB of attachment traffic a frame. The cause was the host's: [Geometry-shader draws split a pass](../../../docs/reference/rendering.md#geometry-draws-keep-the-render-pass-across-ordinary-draws). With that fixed, the same view takes about 14 ms.

Speed checked by the clock: a 3 s walk ends at the two guides as at 30 fps, and a cinematic at 58 fps shows the same shot as at 30 fps at the same second. Sound was off in those runs: lip and voice sync are not checked.

`hle_fpslock.c` has no row for this build: nothing at run time was found to change these values in the scenes tested. The addresses, should a scene need them: `t.MaxFPS` object main+0xb314820, `rhi.SyncInterval` object main+0xb1c6988, GEngine main+0xb314540 with `FixedFrameRate` at +0x7fc, and the setters of `APKGameInstance` that write it at main+0x1a3e5fc, +0x1a40048, +0x1a5b778, +0x1a5ccb8, +0x1fe0e78, +0x200cb20, +0x2485d60 (found by disassembly only).

### The player's session

Current: 75 minutes on 2026-11-03 at Maximum, fullscreen at 3840x2160, story and fights on the first app with these settings (267,847 frames): 0.43% of the frames dropped, GPU median 13.7 ms, peak footprint 7.5 GB, 0 audio underruns, exit 0. The one red line is the audio device changing at frame 14,700; the AudioUnit restarted by itself.

What the player saw as drops: first-time pipelines hold 19 of the 28 moments under about 50 fps after boot, and about 70% of all the time lost (worst frame 729.8 ms, frame 258859). Most of the rest are short game-side stalls with no pipeline (0.6 s, frames up to 88 ms, at frames 139500 and 158114). Separately, a few scenes cost real GPU: 18.5 ms at frames 195601-196500 (about 56 fps), 17.5 ms at frames 61801-62400 and 216601-216900. Which screens those are is not known yet: the log does not name them.

Pipelines: the log said `pipeline archive bundled with the app: made for ... depth near=-w ... this run needs ... near=0`. The profile had no `depth_mode`, so the 657 MB archive could not stand in for a draw, and the session compiled 1,783 bases, 73.5 s of compiler time. That archive holds only bases without a vertex layout (the pulling stand-ins), so the key alone does not remove those compiles: bases with a layout are built on the device. The profile now has `depth_mode zero` and a prewarm list of 3,877 lines from this session.

The rebuilt app, first start headless on an empty state (Maximum, 3 minutes): no stamp mismatch, 16 of 16 probed bases found, so the device builds none of the pairs' bases itself. The prewarm compiled 1,656 bases with a layout in 28 s in the background, at 59.8 fps by the end, 0 red lines. They are in the device archive from the second start. Not measured: a stand-in actually taken from the rebuilt archive (no draw needed one in that run), and a played session.

## PC assets

Current, 2026-11-04, generated, read back and run in the game: headless on the M4 Pro and in the player's session, both measured in [quality-reference.md](quality-reference.md#pc-textures-in-the-game). `ue_pc_assets.tsv` has one row, `max textures *`; `dm/tools/ue_pc_zen4.py` (called by `ue_pc_assets.py`) adds the PC build's texture levels to the Switch packages and writes `pakchunk0-Switch_99_P.utoc` / `.ucas` (TOC version 2) beside the Maximum preset's pak. `ue_quality.tsv`'s Maximum row also sets `LODBias=1>0`.

Generated from the Switch 1.53 RomFS and the player's PC paks (legacy version 9, not encrypted), `q/full/ue_quality/max`: 11,715 packages taken (11,660 with the PC's levels added, 55 `full chain`), 2,202,566,640 bytes of `.ucas` (7.29 GB uncompressed; 20,814 chunks: 11,715 packages, 9,098 bulk chunks, the container header). Skipped: 67,561 without texture data, 6,057 where the PC holds nothing more, 2,885 of another pixel format or shape, 602 missing on the PC, 143 whose first stored level is not the PC's, 64 in the container header's culture map.

What the check is: every stored Switch level must be the PC level of its size, byte for byte (the Switch's are stored linear, so the copy is the whole rule; the block-linear swizzle of `ue_pc_paks.py` is tried and was not needed on the first texture checked by hand, where the levels were equal as stored); when the first matches and a later one does not, the PC's whole chain replaces the Switch's. In an 800-texture random sample: 609 added, 5 full chain, 6 first level differs.

How the game takes the container (read from `main`, build `14c878ec...`, not run): the pak mount stores a pak order of the pak's order plus 100 times the number in a `_P` name (main+0x4758068, `madd`) in the path record it hands to the container reader (main+0x2e985b0, from main+0x4758530); the reader keeps it as the container's order (main+0x2e9c4c4) and inserts itself into a list ordered by order, later mounts first among equals (main+0x2e98a1c); the chunk lookup walks that list and takes the first container that holds the ID (main+0x2eb33bc). The reader builds `.ucas` and `.utoc` from the pak's name (main+0x2e9ada4), checks the TOC magic and the version ("Outdated TOC header version"), and reads the container header chunk by an ID made from the TOC header's container ID, which the writer keeps equal. The 4.25 container header has no sort order of IDs (the game's own ones are unsorted) and the writer reproduces it byte for byte on `pakchunk1-Switch` (775 packages) and up to the culture map on `pakchunk0-Switch`. Open: the engine's package store, which merges the headers of all containers, was not read; if it takes the first or the last container's entry for an ID, the patch's entries (the Switch's own imports, export counts and load order, the new chunk length) are the same as the base's apart from the length. The first run in the game decides.

Lightmaps (`*_BuiltData`) and meshes: not taken beyond what the textures rule accepts. Lightmaps are a different bake on the PC: of 6,075 lightmap textures in 213 packages, 4,229 have no partner of the same export name there, 1,080 partners differ at every level, 484 match; 34 change pixel format (B8G8R8A8 to DXT5, G8 to B8G8R8A8, DXT5 to DXT1), and 248 differ in size by other than a power of two. Taking them would mix two bakes with other lighting, so the rule does not. Static meshes: in a sample of 347, the PC's export data is 83 MB against 37.8 MB for the Switch's, and the Switch's data appears inside the PC's in 289, but the PC's legacy serialisation, extra LODs and `PhysXPC` names would need a converter to the zen layout; not attempted.

## Found on this game

- [Geometry draws keep the render pass across ordinary draws](../../../docs/reference/rendering.md#geometry-draws-keep-the-render-pass-across-ordinary-draws): 20 ms of GPU work a frame at 4K, its outline passes.
- [Frozen pak index](../../../docs/reference/shaders.md#unreal-engine-421-to-425-paks-versions-7-8-and-9-and-425-iostore-containers): the shader reader for its version 9 pak and 4.25 containers.
