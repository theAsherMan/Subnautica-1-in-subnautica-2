# Burst comparison

Sources: 01_runbook.md "Burst comparison: time-varying effects, mod vs stock (built" (split 2026-11-28; old text: git show 7221ba9:research/<old file>)

## Burst comparison: time-varying effects, mod vs stock (built 2026-11-28, UNTESTED in game)
- `bash src/tools/burst.sh [--only mod|stock] [--offset X,Y,Z] [--views NAME:YAW:PITCH,...] [--frames 8] [--span 1.0]` (run_in_background; ~2 game runs). For effects that change over time (caustics); a single shot cannot show them.
- Pose is pod-relative (pawn = first `BP_StaticLifepod_Surface_C` + offset), because the terrain differs between L_SN2World and L_Main; default = 8 m straight below the pod origin (`0,0,-800`), views `down` (pitch -85) and `angled` (pitch -40), yaw 0.
- Steps: takes the heavy lock for the whole job; `burst.py plan` writes the gitignored plans `plans/burst_mod.json` (L_SN2World) and `burst_stock.json` (L_Main, `pioneer`); `SN2_START=Shallows autotest_retry.sh burst_mod`; then moves `Content/Paks/LogicMods/{SN2EmptyWorld,SN2BugShot}` to `Content/Paks_burst_disabled/` (true stock world; the UE4SS harness mods stay), runs `burst_stock`, moves the paks back (also in the EXIT trap, and at the next start if a stash is left over); deletes the temp plans.
- Output `<Workspace>/burst/<ts>/`: `compare_<view>.png` (mod 4x2 frame grid above the stock grid, frames half size, captioned `#k t=<ms> diff=<..>`), `montage_mod*.png`, `montage_stock*.png`, `burst_info.txt` (run dirs + BURST/VIEWERR lines), copies of the plans. `python src/tools/burst.py compare <mod_run> <stock_run> <out_dir>` rebuilds the images from existing runs.
