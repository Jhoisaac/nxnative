# Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles 2 (0100AD80208A8000): the rewriter's patches of this game's own builds. dm/tools/patch_nso.py loads every profile's patches.py and applies
# CUTS as described there ("Registered patches").
CUTS = {
  # Version 1.81 main. A deliberate change of the game's own code, for picture quality: nothing here is wrong on the Switch. The cutscene player (AAPKDemoPlayer, method at main+0x5ef220c) starts from a
  # per-object scale ([x19,#0xd5c], 0.8 in the cutscenes measured), and in docked mode multiplies it by the cvar APK2.SceneCapture.ScreenPercentageMultiply (0.7), then sets r.ScreenPercentage to the
  # result and resizes the capture target: 0.8 x 0.7 = 56% of the output in the scenes that use it, a budget for the Switch's GPU. The cvar comes from the device profile, so a preset can set it, but
  # the per-object scale cannot be reached from any ini. The load becomes 1.0, which leaves the cvar alone in charge.
  '68e3a0ea176a79f403b859d4addad8c3': [
    (0x5ef2300, '685e4dbd', '08102e1e', 'AAPKDemoPlayer: ldr s8,[x19,#0xd5c] (per-object cutscene scale) → fmov s8,#1.0; the scale is then APK2.SceneCapture.ScreenPercentageMultiply alone (ue_quality.tsv: 0.9 at Maximum; the game\'s 0.7 elsewhere)'),
  ],
}
GENERALIZE = 'No: one function of the game\'s own cutscene player, found by disassembly of this build. The per-object scale is in the game\'s data and no ini reaches it.'
