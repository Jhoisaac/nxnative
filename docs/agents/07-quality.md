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
3. **Check the pak version.** `ue_quality.py` writes the replacement pak in the version of the pak it replaces files of, because an engine refuses a newer one: `write_pak` writes version 11 and the legacy 4, 7, 8 and 9 (My Hero One's Justice 2 is version 7, UE 4.21; `uepak.py`'s format notes).
4. **Write the profile's `ue_quality.tsv`.** Its header gives the format.
   - Change only runtime variables that need no new shaders: the resolution, shadow map sizes, shadow distance and cascade count, LOD and draw distances, the texture pool, anisotropy and the texture-group filters.
   - Do not turn on features the game never cooked shaders for: TAA/TSR when it ships FXAA, SSR, depth of field, motion blur, separate translucency, distance-field AO, Lumen, Nanite or virtual shadow maps. Their shaders are missing, and draws fail or the game asserts.
   - Use the `Old>New` field form for texture groups, so that point-filtered data groups stay point.
   - A setting that is no console variable takes a key `=<name>` (`=FixedFrameRate` in `/Script/Engine.Engine`, `APK/Config/DefaultEngine.ini`): the plain line is replaced. Check the game's speed after any change of its time step ([what happened on one game](../../dm/games/0100309016E7A000/README.md#frame-rate)).
5. **Pack and check boot.** Run the NSP script, then start the game with `DM_UE_QUALITY=<preset>`. The log must show:
   - `ue quality: preset <p> (...)`;
   - `WindowInitialize swap chain ... first <W>x<H>` at the preset's resolution.

   A pass dump (`DM_CTL passdump 1`) then shows the shadow depth targets at the new size. If the swap chain keeps the Switch size, the pak was not mounted, or another file overrides the edited one.
6. **Check memory.** The host reports the Switch's application pool (`app_pool`, 3.21 GB) to the game, and Unreal's allocator budgets against that number, not against the Mac's memory. Larger render targets push it over: at 4K, Demon Slayer 2 aborted entering a story fight with `FGenericPlatformMemory::OnOutOfMemory`, after the probe on the engine's failure reporter caught `GenericPlatformMemory.cpp`. It had 3.03 GB mapped and the host had refused nothing.
   - Watch `[mem] alias region mapped N GB (application pool P GB)` in long sessions at each preset.
   - Set `ue_quality_app_pool` with room to spare. Demon Slayer 2 mapped 5.0 GB after 72 minutes at 4K, still growing in 0.25 GB steps, so its preset pool is 8 GB.
   - This raises only the ceiling the game may map. The footprint follows what the game uses (6.5–7.3 GB there).
7. **Measure.** Use a fixed route (Demon Slayer 2: battle mode against the CPU) for each preset. Read the per-frame `@gpu_ms` and `@itv` from `DM_NVN_TSV`, the timing lines, and the memory lines. Repeat the Switch preset to get the run-to-run spread (±0.5 ms there). Near the frame budget the median `@gpu_ms` stops showing the cost (Demon Slayer 2 stayed about 14.4 ms in a fight whatever a preset added): compare the frames over budget and the p99, and aim comparison shots by frame number (`DM_NVN_SHOT`) instead of by time.
8. **Play long sessions.** Look at the slow windows (`timing up to frame N` with a high p95) and tell their two causes apart:
   - **GPU-bound:** GPU time over the frame budget with no new pipelines. A full-screen effect at 4K reached 18–27 ms on an M4 Pro. A lower preset helps; nothing else does.
   - **First-time pipelines:** `new pipelines … ms` in `[longframe]` lines. The device archive keeps them, so they do not come back.

   A preset reaches shader permutations the Switch settings never drew, so its first sessions compile more pipelines than the Switch preset did.
9. **Document.** Add the game note's Graphics quality section (presets, measurements, what was not checked) and its line under Found on this game.

## Display and upscaling

The settings window's Upscaling row (`DM_PRESENT_UPSCALE`) keeps its meaning. MetalFX's spatial scaler is used only when the picture is shown larger than the game renders it. At a preset whose resolution matches the display (Maximum on a 4K display), the host presents through a plain bilinear pass (0.24 ms) and MetalFX does nothing. At the lower presets MetalFX still scales up to the display. Leaving it on costs nothing when it is not needed.

## What presets cannot reach

- **A scale in the game's own code or data.** A cutscene or scene player can set `r.ScreenPercentage` itself at run time, over the device profile: read `@rt_store_mb` and the pass dumps' scene sizes in story scenes, not only in battle. Demon Slayer 2's cutscene player takes a per-object scale no ini reaches, so it took a rewriter cut ([its note](../../dm/games/0100AD80208A8000/README.md#story-scenes-at-maximum)). A preset that passes the regression route can still fail a heavy scene: survey the story too.
- **Texture resolution, from the Switch files alone.** Most texture groups were cooked with `LODBias=1`, and the cook usually strips the mips that bias skips. Lowering `LODBias` then gains nothing by itself; sharper textures need the files of another platform's build ([PC textures](#pc-textures)).
- **Effects with no cooked shaders.** See step 4.
- **Engines other than Unreal.** Crash Team Racing Nitro-Fueled runs on Vicarious Visions' Alchemy engine, which has no `.ini` / console-variable system. Its resolution has to be found in its own code and raised there, as the `RENDER_SCALE` rewriter patches do for other games (`dm/games/*/patches.py`).

## PC textures

When the player owns the game on PC as well, the PC build can supply the texture mips the Switch cook stripped. This needs an Unreal Engine 5 game whose two builds share the IoStore/zen package layout, so that a package has the same chunk IDs (a hash of its lower-case path) and the PC chunks load in the Switch build. Demon Slayer 2 was the first; its note has the comparison and the pilot ([Graphics quality](../../dm/games/0100AD80208A8000/README.md#graphics-quality)).

The mechanism:

- `ue_pc_assets.tsv` in the profile chooses packages per preset: `textures` rows take the matching textures whose PC top mip has more pixels (same pixel format), `package` rows take every match (a map's `*_BuiltData` lightmaps).
- `dm/tools/ue_pc_assets.py` indexes both builds' containers, skips a package whose container-header store entry (imports, shader map hashes) differs or, for a `textures` row, whose name map differs (some games store no shader map hashes, and a platform name such as `PhysXPC` or `PCD3D_SM5` then marks physics or shaders the Switch build cannot read), and copies the chosen packages' chunks from the PC `.ucas` block for block (Oodle blocks are not recompressed) into `<stem>_99_P.utoc` / `.ucas` with `uepak.write_toc`. The container gets the PC store entries in its header (chunk type 6, version 3) and a perfect-hash chunk table, as the game's own TOCs (version 5) have.
- The container goes into the preset's folder beside that preset's `<stem>_99_P.pak`. Unreal mounts a `.utoc` with the pak of the same name, with the pak's patch priority, so the chosen chunks resolve to the PC ones; everything else stays the Switch's.
- `meshes` rows take static meshes (a `BodySetup` in the name map) whose PC package is longer with the same exports: the top LODs the Switch cook stripped. Their cooked collision is named for the PC's physics format, so `rename` rows rewrite that name in the package's name map (its hash, the header sizes and offsets after it), and the mesh is taken only when the renamed name map equals the Switch's; the renamed chunk is written stored (no Oodle compressor here). On the packages whose only difference is that name, the rename gives the Switch chunk byte for byte, and the tool checks that on the first 20 it meets.
- The preset's `ue_quality.tsv` rows set `LODBias` to 0 (`TextureLODGroups`, `LODBias=1>0`) and a larger `r.Streaming.PoolSize`, so the engine streams the extra mip.
- The NSP script builds it only when given the PC `Content/Paks` folder (`--ue-pc-paks`, `UE_PC_PAKS`); nothing from the PC build enters the repository.
- A package whose export chunk has the same length on both builds is skipped before its head is decoded: a stripped mip changes the mip count and the bulk data map in it. A rule of `*` then decodes only the packages that differ (Demon Slayer 2: 13 GB written in 43 s). `pack_app.py` clones the presets' folder into the app (APFS), so the container takes no second copy.

Checks for a new game:

1. Compare the builds first: the TOC version and flags, the container-header version, and a texture package on both sides (pixel format, `FirstMipToSerialize`, mip count). The PC Oodle blocks must decode with the game's own Oodle (`uepak.OodleHost`).
2. Find what a route loads with `DM_FSLOG`: a file read from the RomFS image is logged as `img:<name>`, and the offsets map to the containers' blocks and chunks, and through the TOC directory index (`Toc.paths()`) to package paths.
3. Boot with the preset and check that the game reads `<stem>_99_P.ucas` when the chosen packages load, that no `[RED]` line appears, and the memory lines (`[mem] alias region mapped`, `DM_MEMSTAT`).
4. Compare a scene with and without the container, with the same `ue_quality.tsv` rows in both, and once with the textures only. A lightmap package changes the scene's lighting, not only its detail, so judge it on its own.

## Unreal Engine 4.25

Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles keeps its packages in IoStore containers of TOC version 2 (zen packages, ExportBundleData is chunk type 2, bulk data type 3, container header type 10, Zlib blocks, no perfect hash), and the PC build keeps legacy paks (version 9). A PC package cannot replace a zen package, so `dm/tools/ue_pc_assets.py` hands such a game to `dm/tools/ue_pc_zen4.py`, which keeps the Switch package and rebuilds the texture platform data:

- When every stored Switch level is the PC level of its size (block-linear swizzle tried, as in `ue_pc_paks.py`), the PC's top levels are added. When the first stored level matches and a later one does not (the same image encoded again), the PC's whole chain replaces the Switch's, so no texture mixes the builds (`full chain` in the report). Otherwise the Switch's stays. Skip reasons are counted in the report.
- The container is written with `uepak.write_toc2` and `container_header2` as `<stem>_99_P.utoc` / `.ucas` in the preset's folder, beside the preset's pak. The game mounts it with that pak: in the Switch `main` (1.53) the pak mount gives the container the pak's order plus 100 times the number in a `_P` pak's name, and the chunk lookup walks the containers by order and takes the first that holds the ID. That was read from the code, not run: see the game's note.
- `ue_quality.tsv`'s Maximum row sets `LODBias=1>0` so the engine asks for the extra level.
- Only `textures` rows exist for this engine. Lightmaps are a different bake on the PC (most textures have no partner by export name, most partners differ), so they are taken only where the textures rule accepts them; meshes were not attempted ([the game's note](../../dm/games/0100309016E7A000/README.md#pc-assets)).

## Pak games

A game with no IoStore container cannot take another platform's packages: `ue_pc_assets.py` hands such a game to `dm/tools/ue_pc_paks.py`. What moves is the texel data. On My Hero One's Justice 2 (UE 4.21, pak version 7), each Switch mip is the PC mip of its size, swizzled, byte for byte; the Switch's are block-linear in the shape of 64 KB tiles (8 GOBs for 8- and 16-byte blocks, shrinking with the level's rows) and the PC's linear, and the cook stripped the top one (`FirstMip` 1 there, 0 on the PC). DRAGON BALL Z: KAKAROT (UE 4.24 against the PC's 4.21) holds the same, and also textures stored smaller or with one level and no chain.

- The tool keeps the Switch package and gives each texture the PC's chain (below): the entry in the `.uexp`, the swizzled data in the `.ubulk` (or inline), then the bulk offsets, `SkipOffset`, the export's `SerialSize` and `SerialOffset`, and the summary's `BulkDataStartOffset`.
- A texture whose stored levels are a contiguous slice of the PC's chain (each the PC level of that size) gets the PC's size, first mip and level count, with the top levels added and the tail levels after. It is taken only if every stored Switch level equals the PC level of that size, swizzled, byte for byte, so a wrong rule never reaches the game. When only the first stored level matches (a re-encode of the same image) the PC's whole chain replaces the Switch's (`full chain` in the report), so no texture mixes the two; otherwise the Switch's stays (`level`). Inline small levels carry their swizzled size. Every rebuilt package is read back and compared with the swizzled PC levels. A cube or array keeps the Switch's.
- The report per preset: textures taken (full chain), packages, raw texels added, the pak's size, and the skips (`missing`, `same`, `format`, `level`). Kakarot's full set: 9,670 taken (24 full chain) of 162,022, 3.73 GB added ([note](../../dm/games/010051C0134F8000/README.md#pc-textures)).
- The output joins the preset's `<stem>_99_P.pak` in Zlib blocks of 64 KB (`uepak.LegacyPakWriter`). An encrypted PC index needs its key: the tool finds it in the build's executable and keeps it in memory. It is never printed or written.
- The preset's rows set `LODBias=1>0` and `MaxLODSize=2048>4096` for those groups, with a larger `r.Streaming.PoolSize`.

Check a new game as in [PC textures](#pc-textures): which packages a route reads (`DM_FSLOG`, offsets to `Pak.files`), the pak in the log, a pilot first.
