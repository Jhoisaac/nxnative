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

On the Mac every Core Haptics locality of the Xbox Wireless Controller (Bluetooth LE) fails to make a player (NSCocoaErrorDomain 4097, the connection to gamecontrollerd's haptics service interrupted), so the host falls back to the controller's HID rumble report; the log shows two `[RED] haptics` lines once, then `uses the controller's HID rumble report`.

## Found on this game

General changes first needed here; each applies to every game:

- **A system register read into x18** (`patch_nso.py` `emit_slot_copy`): one `mrs x18, tpidr_el0` among 3,812 `tpidr_el0` reads crashed the RHI thread ([System register reads into x18](../../../docs/reference/rewriter.md#system-register-reads-into-x18)).
- **Event descriptors** (`hle_net.c` `nn::socket::EventFd`, unit test `t_net`): gRPC's `poll` engine aborted at boot without them ([Event descriptors for gRPC's poll engine](../../../docs/reference/services.md#event-descriptors-for-grpcs-poll-engine)).
- **Pipeline archive compaction compiles the bases again from source** (`nvn_mtl.m` `g_compact_opts`): with the old files as the compiler's lookup archives, Metal's serializer crashed at the first start with 15 archive files and 421 bases taken from them. A compaction costs one full compile of those bases in the prewarm's background time (421 bases, about 8 s; the next start took all 491 from the one file in 32 ms).
- **Xbox Wireless Controller rumble over its HID report when Core Haptics fails** (`haptics_apple.m`, above).
- The Mac audio device's 5 ms callbacks: CRI ADX2's 6-channel output keeps 3 × 240 frames in flight, so with the default 512-frame callbacks every 8th one found 496 frames queued and padded 16 (exactly 250 underruns and 83 ms in each 2000 callbacks: a click every 85 ms) ([The Mac's default I/O buffer](../../../docs/reference/audio.md#the-macs-default-io-buffer)).

## Open

- The red flash was fixed on this branch by an aligned copy made on the GPU before each draw (`tbal`, which split about a dozen render passes a frame in battle); it now relies on main's `tbuf_shadow` (a CPU copy per submission). Check Waterfall Basin's water techniques and dashes again on an M4 Pro.
- The residency set adds and removes about 100 buffer texture views a frame in battle; the GPU stays near 10–13 ms of the 16.7 ms on an M4 Pro, but it is worth trimming before an iPhone build.
