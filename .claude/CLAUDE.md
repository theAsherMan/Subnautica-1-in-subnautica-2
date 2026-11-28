# Additional project rules

## Research notes: images
Images are allowed in `research/` (rule changed by the user 2026-11-28). Put them in an `img/` folder next to the note
(`research/<folder>/img/<name>.png`) and link them with a relative markdown link. Still say in text what an image shows (objects visible,
map/location, HUD values, anything unexpected) with the usual status word and date, e.g. **VERIFIED (2026-11-18, tester screenshot)**,
because agents search the notes as text.

## Work autonomously
The main agent works largely on its own: carry the given task through to the end (diagnose, fix, test runs, follow-up steps) without asking
"should I go ahead?". Do not stop to ask for permission to continue.
Ask the user only when there is a meaningful decision to make:
- several mutually exclusive approaches where the choice is theirs;
- an action that risks permanent damage (e.g. deleting saves or data that are not backed up, destructive git operations);
- large financial cost.

Everything else (test runs, cooks, installs, follow-up fixes, calibration loops) just gets done, then reported.
