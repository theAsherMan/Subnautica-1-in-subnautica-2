# Deep-start crash in L_Main — OPEN (2026-11-18)

Moved out of the `process/core_rules.md` crash table in research pass 2 (2026-11-28). One-line rule: use the Shallows start for any L_Main diagnostic run. Not the GC watchdog (0 `LogGarbage` lines).

## Instances
- **2026-11-18 18:54:02** (tester launch without args: `LogInit: Command Line:` empty; New Survival game, **no `-OverridePlayerStart`**, `SN2EmptyWorld` + `SN2Census` installed). AV READ 0x20 at `Subnautica2-Win64-Shipping.exe+0x162AD90`, thread 25092; dump `crashes\crash_2026_11_18_18_54_02.6892856.dmp`, log `reports\test_deepstart_crash_Subnautica2.log`. Sequence: `LoadMap /Game/Maps/Main/L_Main??game=Survival` 10:53:44 -> ModActor purge -> player possessed 10:54:02.634 -> `LogSN2: Applying start conditions of Deep` 10:54:02.662 -> `FlushAsyncLoading(15254): 4 QueuedPackages, 264 AsyncPackages` -> crash (census armed, no sample line). The same world with `-OverridePlayerStart=Shallows` loaded fine (12.7 s from LoadMap to start conditions). **UNEXPLAINED (2026-11-18).**
- **Reproduced 2026-11-27 in STOCK L_Main** (run `20261127_164614_uwprobe_lmain`, plan `pioneer` chain, default start, SN2EmptyWorld still installed but only acting in the lobby/L_SN2World): character select Play at 16:52:29, `LogSN2: Applying start conditions of Deep` + `FlushAsyncLoading(15558): 1 QueuedPackages, 269 AsyncPackages` at 08:52:32.57 UTC, then AV READ 0x20 at `Subnautica2-Win64-Shipping.exe+0x162AD90` (same RVA as 2026-11-18; dump `crash_2026_11_27_16_52_32.8662535.dmp` in the run's `crash/`), process stayed alive without a log line until the 600 s timeout (reclassified CRASH). Spawn was (-346323,447332,-57929) (579 m deep). LOGGED.

## State
- Hypothesis UNTESTED: the default (Deep) start condition touches an actor/asset the purge destroyed. The 2026-11-27 reproduction in stock L_Main (purge mod not acting there) weakens it.
- To test: repeat with `LogicMods/SN2EmptyWorld` moved away and no override, to see if Deep crashes in vanilla too.
- Workaround (not a fix for the Deep start itself): `SN2_START=Shallows bash src/tools/autotest.sh <plan> ...` (hidden launch honours it since 2026-11-27, `research/code/README.md`); `launch_game.sh` adds `-OverridePlayerStart=Shallows`. The default start of `L_SN2World` is Shallows.
