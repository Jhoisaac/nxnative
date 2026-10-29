# Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles 2 (`0100AD80208A8000`)

Update v131072 (display version 1.02, `main` build `437c43801a1c9aee25bc83d4e8b18c64`) with its five DLC, SDK 16.2.3. CyberConnect2's game on Unreal Engine 5 (TOC version 5, no engine version string in `main`), with gRPC (`npln`) and CRI middleware (ADX2 sound, `.usm` movies). 60 fps on the Mac (30 on the Switch).

Status: brought up on the Mac: the title, the story mode's chapter map and its battles at 60 fps, with sound and controller rumble. The profile is the NSP script's provisional one with `fps_target 60` and a prewarm list (1,502 lines) recorded on the Mac. Not tried on the iPhone yet.

## What it needs

| Setting | Where | Why |
|---|---|---|
| `fps_target 60` | `game.tsv` | the host writes Unreal's fixed frame rate and `rhi.SyncInterval` for 60 fps (below) |
| three rows for build `437c4380…` | `hle_fpslock.c` | `t.MaxFPS`, `rhi.SyncInterval` and `UEngine::FixedFrameRate` of this build |

## Frame rate

- **Current:** 60 fps (30 on the Switch). `t.MaxFPS` is 0 in this game: the cap is Unreal's fixed frame rate, `bUseFixedFrameRate=True` and `FixedFrameRate=30` in `DefaultEngine.ini`, so the engine steps exactly 1/30 s a frame and waits out the rest ([Unreal's fixed frame rate](../../../docs/reference/frame-rate.md#unreals-fixed-frame-rate-uenginefixedframerate)). The host writes `UEngine::FixedFrameRate` 60 (`[main+0xcd23388]+0xaf8`: the `GEngine` pointer, and the property offset from Unreal's reflection data at `main+0x9d703d8`) and `rhi.SyncInterval` 1 (`main+0xcbfb958`), gated by this build; the game puts the fixed rate back at each load and the host writes it again.
- With a fixed frame rate the engine's delta time is 1/60 s, so the game's time-based logic keeps its speed (checked by hand in combat, no speed-up). Frame time p50 16.7 ms, p95 17.0–17.2 ms in battle on an M4 Pro; `DM_FPS_TARGET=0` keeps the game's 30.

## Memory

About 4.3 GB resident and 2.1 GB of Metal allocations in battle.

## Rendering

- The particle sprites (Cascade) read their attributes from R32Float / RG16F / RGBA8 buffer textures at 4-byte offsets in Unreal's pools. Read in place on an M4 Pro, every attribute came one to three elements early: Waterfall Basin's blue water and the HUD seen through it came out red at water techniques and dashes (the scene colour, R11G11B10F, held reds of 10^3–3·10^4 over up to 15% of the screen, which the bloom spread as a red flash). Found with `DM_CTL texraw` of the scene colour and of the bloom chain (whose blur weights, `DM_NVN_CBDUMP`, were right), then Metal validation (`Offset of a buffer-backed texture … must be aligned to 16 bytes`). Such views are now read through an aligned copy ([Buffer textures at offsets below 16 bytes](../../../docs/reference/rendering.md#buffer-textures-at-offsets-below-16-bytes)).

## Files and shaders

- No shader code archive and no IoStore shader library: eleven `pakchunk*-Switch.utoc` / `.ucas` containers (11 GB) beside version 11 paks, every shader inline in the cooked packages and the engine's in `Engine/GlobalShaderCache-SP_GLSL_SWITCH.bin` of `pakchunk0-Switch.pak`. They are decoded by the game's own Oodle in the Mac host's tool mode (`uepak.py` `ue5_inline_shaders` / `inline_archives`, the lazy `Lazy` decoder in step 5 of the NSP script): global 2,854 (1,480 pixel, 1,287 compute, 85 vertex, 2 geometry), packages 113,444 (90,610 pixel, 14,277 vertex, 8,555 compute, 2 geometry); 113,089 unique keys ([Unreal Engine 5 shaders inline in IoStore cooked packages](../../../docs/reference/shaders.md#unreal-engine-5-shaders-inline-in-iostore-cooked-packages-oodle)).

## Input

On the Mac the Xbox Wireless Controller's haptics server offers no advanced pattern players: every locality refused one with NSCocoaErrorDomain 4097 ("Couldn't communicate with a helper application"), which this branch first answered with the controller's HID rumble report. The host now plays plain players in 0.5 s pulses instead ([Controller haptic engines without advanced players](../../../docs/reference/services.md#controller-haptic-engines-without-advanced-players)); the log says the controller has no advanced players.

## Found on this game

General changes first needed here; each applies to every game:

- **A system register read into x18** (`patch_nso.py` `emit_slot_copy`): one `mrs x18, tpidr_el0` among 3,812 `tpidr_el0` reads crashed the RHI thread ([System register reads into x18](../../../docs/reference/rewriter.md#system-register-reads-into-x18)).
- **Event descriptors** (`hle_net.c` `nn::socket::EventFd`, unit test `t_net`): gRPC's `poll` engine aborted at boot without them ([Event descriptors for gRPC's poll engine](../../../docs/reference/services.md#event-descriptors-for-grpcs-poll-engine)).
- **Pipeline archive compaction without lookup archives**: with the old files as the compiler's lookup archives, Metal's serializer crashed at the first start with 15 archive files and 421 bases taken from them; first fixed here by compiling the bases again, then upstream fixed it the same way, capturing them from the original shader functions, with a guard for a compaction that does not finish ([A compaction flush that crashes, then crashes every start](../../../docs/reference/shaders.md#a-compaction-flush-that-crashes-then-crashes-every-start)).
- The Mac audio device's 5 ms callbacks: CRI ADX2's 6-channel output keeps 3 × 240 frames in flight, so with the default 512-frame callbacks every 8th one found 496 frames queued and padded 16 (exactly 250 underruns and 83 ms in each 2000 callbacks: a click every 85 ms) ([The Mac's default I/O buffer](../../../docs/reference/audio.md#the-macs-default-io-buffer)).
- **Pipelines a scene draws the first time** (`nvn_mtl.m`): a draw served by a pulling stand-in is now recorded in `pso_user.tsv` at once; a prediction of every draw's stand-in and joining its build were measured and reverted (in play a joined draw waited longer than one compiling its own pipeline) ([Pipelines a scene draws the first time, on a cold archive](../../../docs/reference/shaders.md#pipelines-a-scene-draws-the-first-time-on-a-cold-archive)).
- **The depth mode for the bases made before the game runs** (`depth_mode zero` in `game.tsv`, current): the game sets near = 0, and the NSP script's prebuild and the app's offline archive were made for near = −w, so no draw found them and the host built every base again (the app log said `the game's depth mode is not the one built for`). With the key the app's archive is stamped `depth near=0`.

## Open

- The red flash was fixed on this branch by an aligned copy made on the GPU before each draw (`tbal`, which split about a dozen render passes a frame in battle); it now relies on main's `tbuf_shadow` (a CPU copy per submission). Check Waterfall Basin's water techniques and dashes again on an M4 Pro.
- First pass of a scene on a cold archive: the draws' shader pairs are known only once drawn (the game ships no Unreal pipeline cache; `shader_pairs.tsv` holds only cover pairs), so the chapter start still waits about 0.8 s in all, spread over frames 6400–8100, once per scene and device (`pso_user.tsv` records them: the next start has no wait there). The shader maps in the cooked packages could give real pairs if their frozen content were decoded (every VS × PS per map is 2.26 million pairs, too many to prebuild). The 235–250 ms frames at the chapter load are on the game's loading screen (it sets the present interval to 0 around them): submit and present take 4 ms of them and texture uploads under 2 ms; the rest is the game's own loading or host calls on its threads that the longframe line does not time (open).
- The residency set adds and removes about 100 buffer texture views a frame in battle; the GPU stays near 10–13 ms of the 16.7 ms on an M4 Pro, but it is worth trimming before an iPhone build.
