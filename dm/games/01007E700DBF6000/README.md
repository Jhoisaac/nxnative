# MY HERO ONE'S JUSTICE 2 (`01007E700DBF6000`)

Update 1.1.5 (v983040, `main` build `29e1cd0fbb24697e379da855ca5c367b`) with its add-ons, SDK 6. Byking's game on Unreal Engine 4.21 (`HeroGame-Switch.pak`, pak version 7, Zlib) on NVN, with CRIWARE sound and movies (15 `.usm` files outside the pak).

Status: brought up on the Mac, with graphics-quality presets up to 4K. Headless on a copy of the player's save (M4 Pro, 2026-11-03, 1.1.5): title, opening movie, the story's comic panels and the tutorial fight against All Might drawn right, 24,000 frames, frame time p50 16.65 ms, no `[RED]` line, no crash. Update 1.1.2 (v786432) was played by the player on the Mac before it. Not tried on the iPhone.

## What it needs

| Setting | Where | Why |
|---|---|---|
| `tex_flush_upload on`, `tex_dirty_upload on` | `game.tsv` | Unreal's texture streamer writes streamed mips straight into the textures' storage; without the keys the stage walls were random-colour block mosaics (found on 1.1.2) |
| `mem_reserve 0x1028000000`, `mem_alias 0x1000000000` | `game.tsv` | `nninitStartup` reserves a 62 GB address region; the game's regions reach alias +17.45 GB in its first 15 s in `nnMain` |
| `sys_resource 0x1000000` | `game.tsv` | the NPDM declares 16 MB of system resource |
| `shader_groups ShaderArchive-Global-=global ShaderArchive-=game` | `game.tsv` | the decoded shader code archives: the engine's global shaders and the game's materials |

The game's own `DefaultEngine.ini` fixes the frame rate at 60 (`bUseFixedFrameRate`, `FixedFrameRate=60`), so it needs no `fps_target`.

## Graphics quality

`ue_quality.tsv` gives the settings window's **Graphics quality** row (`DM_UE_QUALITY`): Switch (off, the default), High (1080p), Very high (1440p), Maximum (4K). Unreal reads its device-profile cvars from `HeroGame/Config/DefaultDeviceProfiles.ini` in `HeroGame-Switch.pak` at boot, so a preset is a pak `HeroGame-Switch_99_P.pak` with that ini edited, version 7 like the game's ([how](../../../docs/agents/07-quality.md)). Current, Mac only. The per-machine results are in the [quality reference](quality-reference.md).

The Switch's profile asks 1920x1080 (`SwitchConsole`) with resolution dynamic against a 33.33 ms budget (`r.DynamicRes.OperationMode 2`), `r.Streaming.PoolSize` 800, linear filtering and `LODBias=1` with `MaxLODSize=2048` on every texture group, so the cook stripped each large texture's top mip.

| Row | High | Very high | Maximum |
|---|---|---|---|
| `r.setres` (SwitchConsole) | 1920x1080 | 2560x1440 | 3840x2160 |
| `r.DynamicRes.OperationMode` | 0 | 0 | 0 |
| `r.MaxAnisotropy`; the groups' `linear` becomes `aniso`, mip `point` becomes `linear` | 8 | 8 | 16 |
| `r.Streaming.PoolSize` | 1600 | 1600 | 3000 |
| `LODBias=1>0`, `MaxLODSize=2048>4096` (only with the PC textures) | | | yes |

`ue_quality_app_pool` is 8 GB: at Maximum the fight mapped 3.25 GB in a 2-minute run; a long session is not measured.

**Picture.** The game renders forward (`r.ForwardShading=True`) with FXAA and a toon look. Ambient occlusion, bloom and post-processing, LOD and view distance, 4096 shadows and effects cost budget and showed no visible gain in training at a fixed frame (numbers in the reference), so they stay out. Raising shadows to 2048 changed nothing visible in the stage either and left the story's gym with 5 to 7% of its frames over budget (1.12% without), so the shadow values stay the game's.

**Cinematics.** The 15 story movies are `.usm` video outside the pak (`HeroGame/Content/CriWareData/Movie`), the same size on the PC, so resolution does not raise them. The rest of the story is comic panels and the fight engine. In the fight, pass dumps every 120 frames show the scene at 3840x2160 through its intro and the rounds; nothing lowers it at run time.

### PC textures

Current, the full set: the pilot (the stage St204, the characters Pl00 and Pl02) played with no defect on the player's display on 2026-11-03. `ue_pc_assets.tsv` takes every package through `dm/tools/ue_pc_paks.py`: 5,646 textures, 7.72 GB of raw texels added, 3.67 GB of pak; 141 fail the level check and 17 differ in size, and keep the Switch's. The add-on content's images hold no packages (191 bytes each): its characters are in the base pak, so the set covers them. The PC build (update of 2022-05, one pak version 7 with an encrypted index) has the same cooked layout: same pixel formats, same sizes, and each Switch level is the PC level of its size, swizzled, byte for byte, on the five levels compared at first and on every texture the tool takes. Of 1,816 packages matching the pilot, 1,610 are not textures or have nothing to add, and 5 fail the level comparison; those keep the Switch's. Materials are not taken (D3D shaders). Meshes and audio are not compared further: the movies are the same.


## Driving it on the Mac

- The first story panel ("El fin del principio y el principio del fin") waits for a confirm. Its prompt bar hides after 3 to 5 s without input; a press while it is hidden only shows the bar again, and a press while it is visible advances. Press `A` repeatedly, not once. Every press reaches the game (checked by logging the host's input fill on 1.1.2): this is game behaviour, not a stall.
- From a fresh title: `A~0.3` at the title, then the opening movie (about 2 minutes), then `A~0.3` every 3 s through the panels reaches the tutorial fight against All Might in about 90 s.

- The fight route for measurements (`smoke.tsv`): a save past the story's first steps, then free battle against the CPU, All Might, default stage; the CPU beats the idle player in about 100 s. Training (idle dummy) holds a static scene for pictures at a fixed frame: Down 5 times from the menu.
- The rules screen's Confirm goes straight to the character select once the Mic Channel lesson has been seen; the same character cannot be picked twice, so move the cursor between picks (`Right`).

## The player's session

Current: 28 minutes on 2026-11-03 at Maximum, fullscreen at 3840x2160, the full PC set (97,760 frames): picture approved by the player, 0 red lines, 0 audio underruns, exit 0, peak footprint 5.5 GB, 459 pipeline bases compiled in play, with an archive that could not stand in for a draw. Open:

- **Stretches at 20 fps** (open, cause unknown): frames about 23145-23586 and 96900-97800 hold a 50 ms frame at present interval 1. The game thread works about 8 ms of each frame and waits; two unnamed worker threads (0x100c, 0x100d) take about 300 ms/s each and energy per frame is about 21 times normal. GPU time does not limit them. Not reproduced in 5 headless runs: a fight, the results screen, pause, an exit to the menu, the story's tutorial and its movie `MV_Demo_m01.usm` at 60 fps. The first follows the tutorial fight's end (inferred). The player thinks the game was paused or its window had lost focus at those moments; that was not measured, so this stays open for a later look. To find it: pause the game and move the focus away in a played session, then `DM_NVN_TSV`, `DM_FSLOG` and `sample <pid>` during one.
- **Frames 88801-89400:** the system discarded the drawables (181 in one window) while the game ran at 16.67 ms: not a game cost. Its cause is inferred, a screenshot or an overlay.
- **Dark shadows on the U.A. building stage:** dark navy, darkest 5% of the pixels about (2,11,18), with a blue tint, so ambient light is not zero. The Switch preset, without the PC set, is as dark: darkest 5% (1,11,24) to (7,15,21); the fight camera differs between runs, so this is not pixel-aligned. The preset sets no lighting, shadow or tone cvar. Most likely the stage's own look; no real Switch or PC capture of the stage was found, so a missing ambient term common to both presets is not excluded (open: the view's sky irradiance rows are not decoded).
- **Speed:** the game's own `FixedFrameRate` is 60 and no preset changes it, so the slow jump and walk the player noticed are not a frame-rate effect in the 60 fps stretches.

## Pipelines

Current: the profile has `depth_mode zero` (the game sets near = 0) and a prewarm list of 653 lines. Without the key the bundled archive could not stand in for a draw; the log said `made for ... depth near=-w ... this run needs ... near=0`. That archive holds only bases without a vertex layout, so bases with a layout are still built on the device. The rebuilt app, first start headless on an empty state (Maximum, about 2.5 minutes): no stamp mismatch, 16 of 16 probed bases found, the prewarm compiled 285 bases with a layout in 6 s in the background, 0 red lines. Not measured: a stand-in actually taken from it, and a played session.

## Found on this game

- [Legacy paks and PC mips](../../../docs/agents/07-quality.md#pak-games): a pak game's PC textures, the swizzled mips and the version 7 writer.

- [Jump tables](../../../docs/reference/rewriter.md#jump-tables): the search over the control flow in the rewriter that the first builds of this game needed.
