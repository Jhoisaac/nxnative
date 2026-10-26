---
name: drive-game
description: Run a game in the Mac host (headless or in a visible window) and drive it from the shell — press buttons, move the character with the sticks, take screenshots, dump a frame's render passes and colour targets — to reproduce and debug a defect live, alone or together with the user. Use for any visual defect (wrong colours, fog, black or white screens, missing objects), for checking that a change still boots and plays, and whenever a bug only shows at a point in the game that has to be reached by playing.
---

# Driving a game in the Mac host

The host reads `DM_CTL=<file>` (`dm/host/hle_hid.c` `ctl_main`): every line appended to the file is acted on at once. The scripts in `scripts/` wrap it so that a session needs no setup analysis. Everything they write goes into a run folder in the game's work folder (`<NSP folder>/<id>-work/<name>`), never into the repository or the home folder.

## Set up (once per game)

```
S=.claude/skills/drive-game/scripts            # from the repository root
$S/mkrun.sh "<NSP folder>/<id>_build" "<NSP folder>/<id>-work/run_dbg"
```

`mkrun.sh` copies the user's run state (`<id>_build/run`: saves, pipeline archive, prewarm list) and writes `run.sh`. Always test on that copy: state-dependent paths (archive compaction, saves, prewarm lists) only show with the user's state, and the original is never touched. `fresh.sh <run folder>` restores the copy; `route.sh` does it before every run, so runs are repeatable.

## Drive it

- **Interactive** (look, decide, press, look again):
  ```
  R="<NSP folder>/<id>-work/run_dbg"
  "$R/run.sh" &            # in the background (Bash run_in_background); log in $R/run.log
  $S/ctl.sh "$R" snap t1   # → $R/shots/t1.png, then Read it
  $S/ctl.sh "$R" A~0.3
  $S/ctl.sh "$R" LUp~2
  ```
- **Route** (repeatable, for reaching a place again after a change, or comparing two hosts at the same spot):
  ```
  $S/route.sh "$R" base f1200 w20 A~0.3 w5 A~0.3 w20 s0 LUp~8 s1 "passdump 1" w2
  DMHOST=/path/to/other/dmhost $S/route.sh "$R" fix f1200 …same steps…
  $S/sheet.sh "$R/shots/sheet.png" "$R"/shots/base_*.png   # one image for the whole route
  ```
  Build a route step by step: run it with a shot after each new step, look at the contact sheet, extend. Write the final route into the work folder's HANDOFF/notes so the next session reuses it.

### Inputs (`DM_CTL` lines, the same syntax as `DM_KEYS`)

- Buttons `A B X Y L R ZL ZR LS RS Plus Minus Up Down Left Right`, combined with `+`, hold with `~<seconds>` (default 0.15): `A~0.3`, `LUp+A~0.7`, `L+R~0.5`.
- Sticks fully pushed: `LUp LDown LLeft LRight` (move), `RUp RDown RLeft RRight` (camera). `Shake` shakes the controller; `T<x>x<y>` taps the touch screen (normalized, top left origin); `drag x0 y0 x1 y1 [s]` pans.
- Other lines: `shot <path>`, `passdump <n>`, `texdump <path with %d>`, `texraw <serial> <path>`, `texlist <target>`, `peek <addr> <n>`, `memdump <addr> <bytes> <path>`, `env KEY=VALUE`, `cvarf` / `cvari` (Unreal console variables). See `docs/agents/05-debugging.md`.
- A press blocks the reader for its hold: lines after it wait. `route.sh` waits for the hold too.

### Lessons that cost time before

- **Menus may ignore early or short presses.** Super Mario Odyssey's title ignored `A` (0.15 s) and any A in its first ~20 s after frame 1200, while directions moved the cursor; `A~0.3` at +20 s and +25 s worked every time. When a press does nothing, take a shot, wait, press longer.
- **Timing moves when the machine is busy**: the same route walks a different distance if other hosts run or frames are slow (`DM_TEST_PRESENT_LAG`). Check `pgrep -fl dmhost` before a route and re-shoot each step after a change.
- **Stop only your own host, by PID.** Never `pkill -f dmhost` or any pattern: other sessions run other games' hosts (one such pkill ended another session's game). `run.sh` `exec`s the host, so the PID `route.sh` holds is the host's; in a wrapper without `exec`, `kill` stops only the shell and the host keeps running (ten were left once). After a run: `pgrep -fl dmhost` and check that only others' hosts are left.
- **Build a game's host with the NSP script, not by hand.** `scripts/build_ipa_from_nsp.py <NSP folder> --platform mac` builds `<id>_build/tools/dmhost` from the profile the game was packed with; a build packed from a derived or provisional profile (`<id>_build/profile/`) needs `DM_GAMES_DIR`, and a hand-made `make GAME=<id>` takes the repository's profile instead (a Mario Kart 8 Deluxe update the profile does not register then showed "Ver. 1.0.0": the display version comes from the profile's `build` rows). An update the profile does not register is packed from a derived profile, which the script makes by itself: Mario Kart 8 Deluxe 4.0.1 (v1507328) plays so on the Mac with sound and Xbox rumble, its title showing "Ver. 4.0.1". Keep a copy of the old host before replacing it.
- **Headless first.** Without `WINDOW=1` the host renders at the game's size without a window, needs no focus and does not disturb the user. Its shots are the game's own frames.
- **A window needs focus.** With `WINDOW=1` many games suspend themselves while the window is not key (`oe::SetFocusHandlingMode 3` in the log: "suspended out of focus"), and then nothing is presented: `snap` times out. The user is usually working on the Mac, so focus goes back to their app; do not fight it with AppleScript. Tell the user before opening a window, and for a window-only defect let the user drive (below).
- **Sound is off unless `AUDIO=1`.** Say so when a window opens, or the user wonders why it is silent.

## Visual defects: the standard procedure

1. Reproduce headless along a route to the place where it shows, on the user's state, and compare with a good host (`DMHOST=`; not `HOST`, which zsh sets to the machine name) or a good spot: `capture.sh "$R" bad` / `capture.sh "$R" good`.
2. If it does not show headless but the user sees it (window size, fullscreen, focus, timing), **the user drives and you capture**. Give them their usual run command with `DM_CTL="$R/ctl.txt"` added and its output teed into a log in `$R`, and this line to run in another terminal when the defect is on screen:
   ```
   .claude/skills/drive-game/scripts/capture.sh "<run folder>" <name>
   ```
   It saves `shots/<name>.png`, one frame's render passes (`[pass] F<frame> …` lines in the log: `P` attachments, `K` shaders, `B` bindings, `E` render conditions, `Q` counter reports, `d`/`D` draw state; see the `DM_NVN_PASSDUMP` row in `docs/agents/04-graphics.md`) and that frame's colour targets as PNGs (`tex_<name>/`). Ask for one capture with the defect and one without (another spot, or maximized vs windowed).
3. Compare the two passdumps (attachment sizes, viewports `vp=`, skipped or extra passes, render conditions) and the colour targets of the pass where the picture first goes wrong; then form the hypothesis. Do not ship a fix the capture did not support (Odyssey's fog: `render_cond on` looked likely from a red line, but all 476 conditions were same-frame occlusion queries it does not evaluate, so it changed nothing).
4. After a fix: the same route on the user's state with the new host, a shot at the same spot, and a boot check (the game reaches the same screen with no new `[RED]` line) before handing back.

## Reference: Super Mario Odyssey (0100000000010000)

From the user's save at the title: `f1200 w20 A~0.3 w5 A~0.3 w20` (Resume, Cap Kingdom start), then to the lamp gate: `LUp~8 LUp~3 LUp~3 LRight~0.7 LUp+A~0.7 w0.3 LUp+A~0.7 w0.3 LUp+A~0.7 w0.3 LUp~1 LLeft~2 LLeft~2 LUp~3`. Jump is A (B did not climb the steps).
