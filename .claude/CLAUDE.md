# Additional project rules

## Research notes: no images
Never add images to the `research/` notes: no markdown image links, no copied screenshot files, no `<img>`.
When the tester sends a screenshot, describe in text what it shows (objects visible, map/location, HUD values, anything unexpected),
with the usual status word and date (e.g. **VERIFIED (2026-11-18, tester screenshot)**). Include this rule in briefs for any agent that edits `research/`.

## Work autonomously
The main agent works largely on its own: carry the given task through to the end (diagnose, fix, test runs, follow-up steps) without asking
"should I go ahead?". Do not stop to ask for permission to continue.
Ask the user only when there is a meaningful decision to make:
- several mutually exclusive approaches where the choice is theirs;
- an action that risks permanent damage (e.g. deleting saves or data that are not backed up, destructive git operations);
- large financial cost.

Everything else (test runs, cooks, installs, follow-up fixes, calibration loops) just gets done, then reported.
