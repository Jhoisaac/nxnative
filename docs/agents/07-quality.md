# Raising an Unreal game's graphics quality

This guide shows how a Switch game built on Unreal Engine gets graphics-quality presets. The presets render natively at up to 4K, with sharper shadows and texture filtering, and the player picks one in the settings window.

Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles 2 was the first game done this way. On an M4 Pro, its Maximum preset renders 3840x2160 at a steady 60 fps, where the Switch build renders 1600x900. Its note has the measurements: [Graphics quality](../../dm/games/0100AD80208A8000/README.md#graphics-quality).

The mechanism is general:

- `ue_quality.tsv` in the game profile lists the presets.
- `dm/tools/ue_quality.py` and `uepak.write_pak` build the packs.
- The NSP script packs them into `Resources/dm/ue_quality/`.
- The host's `DM_UE_QUALITY` mounts the chosen one (`hle_fs.c rom_overlay_roots`).
- `ue_quality_app_pool` reports a larger memory pool while a preset is chosen (`hle_svc.c app_pool`).

What a game needs is its profile rows, plus the checks below. [development.md](../development.md) describes the feature; this page is the procedure and what was learned getting there.

## Why the presets apply at boot

An Unreal game's quality comes from console variables. The cooked device profile and scalability `.ini` files set them, and the files are read from the game's pak at boot. On the Switch they are set low: a 1600x900 render target, 256-texel character shadows, two shadow cascades at 40 % of the distance, linear texture filtering and short LOD distances.

The engine and the cooked assets support far more. The Switch's configuration lowers the values; it does not take the code or the content out.

Changing the variables while the game runs does not work:

- **Writing a variable in memory.** The `TAutoConsoleVariable` object holds its value at `+0x10`, a game-thread copy and a render-thread copy. Writing both (`DM_CTL cvari` / `cvarf`) changed nothing measurable: GPU time stayed the same and a paused frame was identical pixel for pixel. The renderer reads a scalability cache, `FCachedSystemScalabilityCVars`. The engine's sink fills that cache only after a variable changes through the console manager, and a memory write does not count as one.
- **Writing the cache.** In Demon Slayer 2 the cache is `main+0xcd22ce0`. Its fields are DetailMode `+4`, MaterialQuality `+8`, MaxShadowResolution `+0x10`, MaxCSMShadowResolution `+0x14`, ViewDistanceScale `+0x18` and its square `+0x1c`, and MaxAnisotropy `+0x2c`. Writing it (`DM_CTL poke`) did change the shadow depth target, from 256x256 to 1024x1024. It did nothing for anisotropy, because samplers take their filter when they are created.
- **`r.setres`.** It is a command, not a variable, so no write reaches it.

A pak read at boot avoids all of this. It holds the game's own `.ini`, edited, and is named `<stem>_99_P.pak` next to the pak that holds the original. Unreal mounts `_P` paks with priority, and the host's RomFS overlay serves the file as if it were part of the game. The game then boots with the values through the engine's own path: callbacks, caches, render-target sizes and sampler states are all consistent.

## Procedure for a new game

1. **Find the config.** List the paks with `uepak.Pak(path).files`. You want:
   - `Default*.ini` and `<Platform>/Config/<Platform>*.ini`, the game's own;
   - `Engine/Config/Base*.ini` and `Engine/Platforms/Switch/Config/Base*.ini`, the engine's.

   Read them with `Pak.read(name, decode)`. Oodle-compressed files need the game's own decoder in the host's tool mode (`uepak.OodleHost`); Zlib and LZ4 files are decoded in Python. An encrypted index needs the AES key, which `uepak` finds in `main`. Some engine files are not in the pak at all (Demon Slayer 2's `BaseEngine.ini` was): only edit files the pak holds.
2. **Read the device profiles.** In `[Switch DeviceProfile]`, `[SwitchConsole DeviceProfile]` and `[SwitchHandheld DeviceProfile]`, collect:
   - `r.setres`, `r.ScreenPercentage` and the `r.DynamicRes.*` variables;
   - `sg.*` and `r.Shadow.*`;
   - the LOD scales;
   - the `+TextureLODGroups` lines (`MinMagFilter`, `MipFilter`, `LODBias`).

   The console profile inherits from `Switch` (`BaseProfileName`), so a resolution set in `SwitchConsole` wins over one set in `Switch`.
3. **Check the pak version.** `write_pak` writes version 11 (UE 4.27 / 5.x): uncompressed, unencrypted, with a full directory index and no path hash index. An older engine needs the legacy layout, described in `uepak.py`'s format notes (My Hero One's Justice 2 is version 7, UE 4.21). Add that writer before profiling such a game.
4. **Write the profile's `ue_quality.tsv`.** Its header gives the format.
   - Change only runtime variables that need no new shaders: the resolution, shadow map sizes, shadow distance and cascade count, LOD and draw distances, the texture pool, anisotropy and the texture-group filters.
   - Do not turn on features the game never cooked shaders for: TAA/TSR when it ships FXAA, SSR, depth of field, motion blur, separate translucency, distance-field AO, Lumen, Nanite or virtual shadow maps. Their shaders are missing, and draws fail or the game asserts.
   - Use the `Old>New` field form for texture groups, so that point-filtered data groups stay point.
5. **Pack and check boot.** Run the NSP script, then start the game with `DM_UE_QUALITY=<preset>`. The log must show:
   - `ue quality: preset <p> (...)`;
   - `WindowInitialize swap chain ... first <W>x<H>` at the preset's resolution.

   A pass dump (`DM_CTL passdump 1`) then shows the shadow depth targets at the new size. If the swap chain keeps the Switch size, the pak was not mounted, or another file overrides the edited one.
6. **Check memory.** The host reports the Switch's application pool (`app_pool`, 3.21 GB) to the game, and Unreal's allocator budgets against that number, not against the Mac's memory. Larger render targets push it over: at 4K, Demon Slayer 2 aborted entering a story fight with `FGenericPlatformMemory::OnOutOfMemory`, after the probe on the engine's failure reporter caught `GenericPlatformMemory.cpp`. It had 3.03 GB mapped and the host had refused nothing.
   - Watch `[mem] alias region mapped N GB (application pool P GB)` in long sessions at each preset.
   - Set `ue_quality_app_pool` with room to spare. Demon Slayer 2 mapped 5.0 GB after 72 minutes at 4K, still growing in 0.25 GB steps, so its preset pool is 8 GB.
   - This raises only the ceiling the game may map. The footprint follows what the game uses (6.5–7.3 GB there).
7. **Measure.** Use a fixed route (Demon Slayer 2: battle mode against the CPU) for each preset. Read the per-frame `@gpu_ms` and `@itv` from `DM_NVN_TSV`, the timing lines, and the memory lines. Repeat the Switch preset to get the run-to-run spread (±0.5 ms there).
8. **Play long sessions.** Look at the slow windows (`timing up to frame N` with a high p95) and tell their two causes apart:
   - **GPU-bound:** GPU time over the frame budget with no new pipelines. A full-screen effect at 4K reached 18–27 ms on an M4 Pro. A lower preset helps; nothing else does.
   - **First-time pipelines:** `new pipelines … ms` in `[longframe]` lines. The device archive keeps them, so they do not come back.

   A preset reaches shader permutations the Switch settings never drew, so its first sessions compile more pipelines than the Switch preset did.
9. **Document.** Add the game note's Graphics quality section (presets, measurements, what was not checked) and its line under Found on this game.

## Display and upscaling

The settings window's Upscaling row (`DM_PRESENT_UPSCALE`) keeps its meaning. MetalFX's spatial scaler is used only when the picture is shown larger than the game renders it. At a preset whose resolution matches the display (Maximum on a 4K display), the host presents through a plain bilinear pass (0.24 ms) and MetalFX does nothing. At the lower presets MetalFX still scales up to the display. Leaving it on costs nothing when it is not needed.

## What presets cannot reach

- **Texture resolution.** Most texture groups were cooked with `LODBias=1`, and the cook usually strips the mips that bias skips. Lowering `LODBias` then gains nothing; sharper textures need the files of another platform's build.
- **Effects with no cooked shaders.** See step 4.
- **Engines other than Unreal.** Crash Team Racing Nitro-Fueled runs on Vicarious Visions' Alchemy engine, which has no `.ini` / console-variable system. Its resolution has to be found in its own code and raised there, as the `RENDER_SCALE` rewriter patches do for other games (`dm/games/*/patches.py`).
