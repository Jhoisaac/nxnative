# Crash™ Team Racing Nitro-Fueled (`0100F9F00C696000`)

Update 1.0.15 (v983040, `main` build `1c689518406930512c13ddf4217e7676`) with its seven DLC, SDK 8.2.0. Beenox's port of Vicarious Visions' Alchemy engine on NVN, with Havok physics, FMOD sound and Bink movies (decoded by the game's own code, shaders compiled at run time). 60 fps on the Mac (30 on the Switch).

Status: played on the Mac by the user at 60 fps with sound: the language select, the licence pages, the main menu, the Adventure hub, local Arcade and races, with the movies drawn. Controls: B accelerates, Y brakes and reverses, A uses the item. The profile is the NSP script's provisional one with `present_interval display` and `fps_target 60`. Not tried on the iPhone.

## What it needs

| Setting | Where | Why |
|---|---|---|
| `present_interval display`, `fps_target 60` | `game.tsv` | one frame per display tick, so 60 fps; the game's speed does not depend on the frame count (below) |
| `mem_reserve 0x100000000`, `app_pool 0xCD500000`, `sys_resource 0x0` | `game.tsv` | main sets a heap of at most the pool minus 64 MB (3,328 MB), and the NPDM declares no system resource, so `IsVirtualAddressMemoryEnabled` is false as on Horizon |
| `shader_groups /archives/=archives /ghosts/=ghosts /dlog/=dlog` | `game.tsv` | the shader split's source groups: the effect files of the Alchemy archives |
| `depth_mode zero` | `game.tsv` | the game sets near = 0: the app's log said `pipeline archive bundled with the app: made for ... depth near=-w ... this run needs ... depth near=0`, so the bundled archive could not stand in for a draw and the device built its bases itself. Added 2026-11-04; the rebuilt app, headless: no mismatch line, 16 of 16 probed bases found, 0 red lines, a race drawn right |

## Frame rate

- **Current:** 60 fps. The Switch's 30 fps is the present interval 2 the game sets (`igVideoFormat+0x18` into `nvnWindowBuilderSetPresentInterval` in `igNxGraphicsDevice::activate`, `main+0x15a8a5c`). Game time is the wall-clock delta (`CClock::update`, `main+0xa00b90`; Havok steps with that delta), so one frame per display tick keeps the speed: a race timer of 58.12 s against 58.115 s of wall clock, and the karts at the same place after 58 s as at 30 fps (headless, 1.0.15).
- **30 fps** is offered in the Mac settings window: `fps_target 60` makes the launcher show the Frame rate row, and with display pacing the host presents one frame per two display ticks at `DM_FPS_TARGET=30` ([Engine-native frame caps also govern presentation](../../../docs/reference/frame-rate.md#engine-native-frame-caps-also-govern-presentation)). No stub or memory write is involved, because the game's time is the clock. Not run at 30 yet (open below).

## Files and shaders

- The game's shaders are GLSLC outputs inside its Alchemy IGA archives (`/archives/*.pak`, 401 archives, 9.6 GB): 1,933 in `archives/shaders_nx.pak` and 12 in `main`, read by `shader_split.py` (`iga_members`, `iga_shaders`); the game also compiles two at run time ([GLSLC outputs in Alchemy IGA archives](../../../docs/reference/shaders.md#glslc-outputs-in-alchemy-iga-archives)). The map has 1,947 shaders; `shader_pairs.tsv` holds the vertex / pixel pairs and `pso_pairs.tsv` is empty.
- The Bink movies' vertex and three-plane YUV pixel shaders (`4e4208ca043b8c27`, `a48c0d8a47c19850`) are compiled with `glslcCompile` when the first movie starts, after the language select on a fresh save. Without them in the map the movie's quad is skipped: black screens with the intro movies' sound. The NSP script's capture boot presses A once the frame loop runs and waits for quiet, which captures them.
- The one-off `is not in the shader map` keys of a session were the Bink pixel program, finalized when a movie ends and bound again about 20 s later; the host had dropped its keys ([Program keys computed inside nvnProgramSetShaders](../../../docs/reference/shaders.md#program-keys-computed-inside-nvnprogramsetshaders), the finalized-program bullet). The run that logged the line in 3 of 4 headless runs logs it in none of 4.

## Audio

The game opens one audio renderer at boot and a second (48 kHz, 6 mix buffers) after its language select, and waits on the second's event: the host drives up to four renderers ([A game that opens more than one renderer](../../../docs/reference/audio.md#a-game-that-opens-more-than-one-renderer)).

## Mac routes

- A fresh save: language select (A), the licence and privacy pages (R at about 1 s spacing turns pages, A on the last), the no-internet popup, the main menu. Adventure loads for about 90 s after "Third time is the charm" (a brown screen); Local Arcade, Single Race loads in about 20 s.
- Driving: B accelerates, Y brakes and reverses, A uses the item; A and ZR do not drive (the input mask in `CKartControllerComponent::updateLinearVelocityInput`, `main+0xeb3460`). A kart that goes back to the start is an idle one.
- `smoke.tsv` (for `scripts/regress.py`, checked on 2026-11-04: the race is up by the 100 s shot) starts from a copy of the user's save (`saves/arcade` in the NSP folder), presses through Local Arcade, Single Race at frames converted from the seconds of an earlier headless route, and holds B for 20 s once the race is up.

## Found on this game

General changes first needed here; each applies to every game:

- **A jump table the rewriter did not recognise** (`patch_nso.py` `check_before_copy`, `main+0x5ae924`: the table base is built between the bounds check and the load, and an `and x18,x8,#0xffffffff` follows): [Bounds check apart from the load, and guards reached over the control flow](../../../docs/reference/rewriter.md#bounds-check-apart-from-the-load-and-guards-reached-over-the-control-flow).
- **Alchemy IGA archives in the shader split**, and the capture boot that presses A: [GLSLC outputs in Alchemy IGA archives](../../../docs/reference/shaders.md#glslc-outputs-in-alchemy-iga-archives).
- **More than one audio renderer** (`hle_audren.c`, unit test `t_audren_multi`): [A game that opens more than one renderer](../../../docs/reference/audio.md#a-game-that-opens-more-than-one-renderer).
- **A finalized program keeps its shader keys** (`hle_nvn.c` `pk_finalize`): [Program keys computed inside nvnProgramSetShaders](../../../docs/reference/shaders.md#program-keys-computed-inside-nvnprogramsetshaders).

## Open

- The four-texture Bink pixel shader (with `texalpha`, a GLSL source in `main`) was never seen compiled, so it is not in the map; no movie using it has been played.
- `6f93905d03105942` and the other one-off keys were explained by the finalized program above; none was seen after that fix, but no long session was logged.
- 30 fps (the settings window's choice) has not been run on the Mac; only the 60 fps default has been played.
- The profile's shader tables come from the provisional profile; `c1_full.tsv` and `cb_extent.tsv` are generated by a full `dmsh_build.py` run (git ignores them). The prewarm list `pso_manifest.tsv` holds 929 lines from a player's session at 60 fps (the boot, the intro movies, the menus, Adventure and Local Arcade races). Not tried on the iPhone.
