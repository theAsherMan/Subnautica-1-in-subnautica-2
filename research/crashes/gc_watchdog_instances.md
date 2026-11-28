# GC watchdog: list of instances and ending variants (OPEN crash)

Moved verbatim out of the `process/core_rules.md` crash table in research pass 2 (2026-11-28). Summary and explanation chain: `gc_watchdog.md`.

**Signature, lobby -> world LoadMap:** `LogGarbage: Spent more than 20.00s on routing FinishDestroy to objects (objects in queue: 227xx)` -> `Spent too much time waiting for FinishDestroy for 227xx object(s) (last object: SphereComponent)` -> `UObject::AbortInsideMemberFunction`.

## Dates (queue size)
- 2026-11-14 13:24 and 18:33 (~10 s after the menu, L_Main).
- 2026-11-17 17:27:51 (22790, ~59 s after the menu, SN2IntroSkip v4 + IntroProbe loaded) and 17:30:21 (22791, LoadMap 17:30:00, crash exactly 20 s later).
- 2026-11-18 16:08:18 (22797, new Creative save, **all our Lua mods disabled**).
- 2026-11-22 08:34:36 UTC (22795, run 163326, `L_SN2World`, lobby-teardown stall then 0xC0000005 write).
- 2026-11-23 10:04:53 UTC (22783, user-started launch, new Creative world into `savegame_1` on `L_SN2World`, ~23 s after the lobby loaded; Lua mods loaded: SN2Census (arms only from the ClientRestart hook), SN2AutoTest idle, SN2Tadpole + SN2BugShot keybinds only; no `LogExit`, no new minidump in `%LOCALAPPDATA%\Subnautica2\Saved\Crashes` or `%LOCALAPPDATA%\CrashDumps`; logs copied to `<Workspace>\crashes\20261123_180518_user_load\`).
- 2026-11-23 10:52:49 UTC (22808, harness run `holes_recheck`, new Survival world on `L_SN2World`, 28.3 s after the lobby LoadMap, boot -> lobby 28.4 s with ~80 `LogShaderLibrary: Warning: Spent N ms in a blocking wait for shader preload` lines, up to 505 ms).
- 2026-11-23 11:10:54 UTC (22798, harness run `vanish_proof` attempt 1, 27.8 s after the lobby LoadMap, boot -> lobby 28.3 s).
- 2026-11-24 ~17:37 local (22785, bugreport run `20261124_173454_bugreport`, dump `crash_2026_11_24_17_37_00.4065658.dmp`, no slot created; investigated in another session).

Always intermittent (many loads succeed). Same engine behaviour on L_Main and L_SN2World, with and without our Lua mods.

## Variants of the ending (LOGGED 2026-11-23)
- (a) dump-less exit after the SkyLight lines (10:04:53).
- (b) AV WRITE 0x0 at `Subnautica2-Win64-Shipping.exe+0x1626F24` (11-17).
- (c) **hang, no exit:** 10:52:49 logged `LogAudioMixer: Warning: AudioMixerPlatformInterface Timeout [15 Seconds] waiting for h/w` 10:53:24.965, two SkyLight lines 10:53:53.856, then nothing, frame counter stuck at 712, process alive at ~7.5 GB.
- (d) **dump written 1 s later, then hang:** 11:10:54 minidump `crash/crash_2026_11_23_19_11_15.0394906.dmp` (not analysed), frame counter stuck at 475, harness force-killed it after its 300 s menu-step timeout (FAIL_MENU, harness re-labelled CRASH from the dump); its retry `20261123_191841_vanish_proof` had boot -> lobby 43.3 s and purge 14.34 s and completed.

Harness verdicts must treat dump-less exit, AV and hang as this bug.
